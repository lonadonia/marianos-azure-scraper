"""How a request leaves the probe, if it ever does.

:class:`ReplayTransport` answers from saved responses and has no way to reach a network.
:class:`HttpTransport` is the only code that can reach Oxylabs, and it refuses to exist unless the build
enables live mode (gates.py). Importing this module opens nothing.
"""

from __future__ import annotations

import base64
import json
import queue
import threading
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from classic_probe import contract, gates


@dataclass(frozen=True)
class ProviderRequest:
    step: str
    payload: Mapping[str, Any]
    query_string: str = ""  # e.g. type=raw,parsed

    @property
    def url(self) -> str:
        return contract.ENDPOINT + (f"?{self.query_string}" if self.query_string else "")


@dataclass(frozen=True)
class ProviderResponse:
    http_status: int
    body: bytes
    headers: Mapping[str, str] = field(default_factory=dict)


class Transport(Protocol):
    def send(self, request: ProviderRequest, timeout_s: float) -> ProviderResponse: ...


class TransportFailed(RuntimeError):
    """No HTTP answer. The request may have reached the provider: the remote outcome is unknown."""


class ReplayTransport:
    """Saved responses, by step, in order. A step with nothing left is an error, never a request."""

    def __init__(self, responses: Mapping[str, Sequence[ProviderResponse]]) -> None:
        self.responses = {k: list(v) for k, v in responses.items()}
        self.dispatched: list[ProviderRequest] = []

    def send(self, request: ProviderRequest, timeout_s: float) -> ProviderResponse:
        self.dispatched.append(request)
        left = self.responses.get(request.step)
        if not left:
            raise TransportFailed(f"the replay holds no response for {request.step}")
        return left.pop(0)


class HttpTransport:  # pragma: no cover - never constructed in this build (a test proves it refuses)
    """HTTP Basic authentication over the documented endpoint. No redirect to another host is followed with
    the credentials, and the credentials are never logged or stored."""

    def __init__(self, credentials: gates.Credentials) -> None:
        if not gates.LIVE_ENABLED:
            raise gates.LiveDisabled("live mode is disabled in this build")
        token = f"{credentials.username}:{credentials.password}".encode()
        self._authorization = "Basic " + base64.b64encode(token).decode("ascii")

    def send(self, request: ProviderRequest, timeout_s: float) -> ProviderResponse:
        http = urllib.request.Request(
            request.url,
            data=json.dumps(request.payload).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json", "Authorization": self._authorization},
        )
        try:
            with urllib.request.urlopen(http, timeout=timeout_s) as res:
                return ProviderResponse(res.status, res.read(), dict(res.headers.items()))
        except urllib.error.HTTPError as exc:
            return ProviderResponse(exc.code, exc.read(), dict(exc.headers.items()))
        except OSError as exc:
            # The message names no credential; the type and text are enough to report it.
            raise TransportFailed(f"{type(exc).__name__}: {exc}") from None


def bounded_send(transport: Transport, request: ProviderRequest, timeout_s: float) -> ProviderResponse:
    """Send with a hard limit on the whole exchange. On expiry the caller gets :class:`TransportFailed` and
    stops waiting. That proves nothing about the provider: the request may still finish and be charged."""
    box: queue.Queue[tuple[bool, Any]] = queue.Queue(maxsize=1)

    def work() -> None:
        try:
            box.put((True, transport.send(request, timeout_s)))
        except Exception as exc:  # noqa: BLE001 - carried to the caller, which stops the campaign
            box.put((False, exc))

    threading.Thread(target=work, daemon=True, name="classic-probe-request").start()
    try:
        ok, value = box.get(timeout=timeout_s)
    except queue.Empty:
        raise TransportFailed(f"no answer within {timeout_s} s") from None
    if ok:
        response: ProviderResponse = value
        return response
    if isinstance(value, TransportFailed):
        raise value
    raise TransportFailed(f"{type(value).__name__}: {value}") from None
