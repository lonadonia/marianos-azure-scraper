"""How a request leaves the probe, if it ever does.

:class:`ReplayTransport` answers from saved responses and has no way to reach a network.
:class:`IsolatedHttpTransport` is the only code that can reach Oxylabs. In this build it reaches only a
loopback test stub: the documented endpoint is refused while live mode is disabled (gates.py), here and again
in the worker. Importing this module opens nothing.

1.7.0 corrections (the client's second review):

- C1, redirects: nothing follows a redirect. The worker uses ``http.client``, which has no redirect handling,
  and a 3xx answer comes back as the answer (the campaign then stops, checks.py). The credentials go only to
  the documented scheme, host and port; a request naming any other URL is refused before a worker starts.
- C2, cancellation and bounds: each exchange runs in a child process that the transport kills and reaps at the
  request's deadline (a queue timeout and a daemon thread are not cancellation; a killed process is). The
  body is bounded on success and error alike, decompression is bounded, and every socket wait is clamped to
  the time left. A killed exchange may still have reached the provider: its reservation stays held as unknown.

1.7.1 correction (finding C4): nothing received is deleted. The worker writes each answer under the dispatch's
own number (``ProviderRequest.raw_stem``, given by the campaign: ``dispatch_NNN`` in the campaign's private
folder), with its status beside it, both synced and renamed durably (networker.py). The campaign keeps its
sanitized copy from there; a crash before that copy is kept loses nothing, because the recovery keeps it from
these files (captures.py). A body cut by a deadline, an error or a kill is kept as ``dispatch_NNN.partial``
and reported with its length and SHA-256 (:attr:`TransportFailed.partial`), never as an answer.

1.7.2 corrections (the client's review of 1.7.1, finding C4):

- a body shorter than the length its answer declared is partial (networker.py), and this transport checks it
  again (:func:`declared_shortfall`): an answer is returned only when its body is whole;
- a kill no longer replaces what the worker had already written. When the worker's kill comes after it wrote
  its status (it was stopping, or renaming its body), the transport reads that status: a whole answer killed
  between its status and its final rename is finished (renamed into place after its hash is checked) and
  returned, never turned into a partial; a partial the worker had kept is described from the status, which is
  never overwritten. 1.7.1 renamed such a whole body to ``.partial`` and wrote ``Killed`` over its status, and
  reported a kept partial as nothing (the race the drip test met on Windows);
- each request carries its dispatch's identity (:attr:`ProviderRequest.identity`), written into every status,
  so that a recovery keeps only the files of its own dispatch.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.parse
import uuid
import zlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from classic_probe import contract, durable, gates

REAP_TIMEOUT_S = 10.0


@dataclass(frozen=True)
class ProviderRequest:
    step: str
    payload: Mapping[str, Any]
    query_string: str = ""  # e.g. type=raw,parsed
    # 1.7.1 (C4): where the answer is written, by the dispatch's own number (the campaign's private folder)
    raw_stem: str | None = None
    # 1.7.2 (C4): the dispatch's identity (campaign, ledger genesis, number, step, attempt, payload hash),
    # written into every status the worker leaves, so that a recovery keeps only its own dispatch's files
    identity: Mapping[str, Any] | None = None

    @property
    def url(self) -> str:
        return contract.ENDPOINT + (f"?{self.query_string}" if self.query_string else "")


@dataclass(frozen=True)
class ProviderResponse:
    http_status: int
    body: bytes
    headers: Mapping[str, str] = field(default_factory=dict)
    truncated: bool = False  # the body was cut at the byte limit: never a complete capture
    redirect_location: str | None = None  # recorded, never followed (C1)
    elapsed_s: float = 0.0


@dataclass(frozen=True)
class ResponseLimits:
    max_body_bytes: int = 8_000_000
    max_header_bytes: int = 64_000
    max_decoded_bytes: int = 32_000_000


class Transport(Protocol):
    def send(self, request: ProviderRequest, allowance_s: float) -> ProviderResponse: ...


class TransportFailed(RuntimeError):
    """No HTTP answer. The request may have reached the provider: the remote outcome is unknown."""

    def __init__(
        self, message: str, *, sent: bool | None = None, partial: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.sent = sent  # False only when the worker proves it never sent the request
        # 1.7.1 (C4): the part of a body that arrived before the failure, kept on disk: length, SHA-256, file
        self.partial = partial


class BodyTooLarge(ValueError):
    """A body (or its decoding) is above its limit: it is evidence of a truncation, never parsed whole."""


class ReplayTransport:
    """Saved responses, by step, in order. A step with nothing left is an error, never a request."""

    def __init__(self, responses: Mapping[str, Sequence[ProviderResponse]]) -> None:
        self.responses = {k: list(v) for k, v in responses.items()}
        self.dispatched: list[ProviderRequest] = []

    def send(self, request: ProviderRequest, allowance_s: float) -> ProviderResponse:
        self.dispatched.append(request)
        left = self.responses.get(request.step)
        if not left:
            raise TransportFailed(f"the replay holds no response for {request.step}", sent=False)
        return left.pop(0)


def decode_body(response: ProviderResponse, limits: ResponseLimits) -> bytes:
    """The body as bytes to parse, decompressed within ``max_decoded_bytes`` (a compression bomb is refused).
    A truncated body is refused: half a response is never read as a whole one."""
    if response.truncated:
        raise BodyTooLarge("the body was truncated at the byte limit")
    enc = {k.lower(): v for k, v in response.headers.items()}.get("content-encoding", "").strip().lower()
    if enc in ("", "identity"):
        return response.body
    if enc not in ("gzip", "deflate"):
        raise BodyTooLarge(f"unsupported content encoding {enc!r}")
    d = zlib.decompressobj(zlib.MAX_WBITS | 32 if enc == "gzip" else zlib.MAX_WBITS)
    out = d.decompress(response.body, limits.max_decoded_bytes + 1)
    if len(out) > limits.max_decoded_bytes or d.unconsumed_tail:
        raise BodyTooLarge(f"the decoded body is above {limits.max_decoded_bytes} bytes")
    return out


class IsolatedHttpTransport:
    """HTTP Basic authentication over the documented endpoint, one supervised child process per exchange.

    ``loopback_port`` points every request at ``http://127.0.0.1:<port>`` instead (offline tests of the live
    path's mechanics); it is the only target this build allows."""

    def __init__(
        self,
        credentials: gates.Credentials,
        *,
        work_dir: Path,
        limits: ResponseLimits | None = None,
        loopback_port: int | None = None,
        python: str = sys.executable,
    ) -> None:
        if loopback_port is None and not gates.LIVE_ENABLED:
            raise gates.LiveDisabled("live mode is disabled in this build")
        token = f"{credentials.username}:{credentials.password}".encode()
        self._authorization = "Basic " + base64.b64encode(token).decode("ascii")
        self.work_dir = work_dir
        self.limits = limits or ResponseLimits()
        self.loopback_port = loopback_port
        self.python = python
        self.workers_started = 0
        self.workers_killed = 0
        self.last_pid: int | None = None
        self.last_returncode: int | None = None

    def preflight(self, request: ProviderRequest) -> None:
        """Refuse, before anything is sent or marked sent, a request this transport would never send."""
        self._target(request)

    def _target(self, request: ProviderRequest) -> tuple[str, str, int, str]:
        u = urllib.parse.urlsplit(request.url)
        if (
            u.scheme,
            u.hostname,
            u.port or 443,
        ) != contract.ENDPOINT_PARTS or u.path != contract.ENDPOINT_PATH:
            raise TransportFailed(f"refused: {request.url} is not the documented endpoint", sent=False)
        path = u.path + (f"?{u.query}" if u.query else "")
        if self.loopback_port is not None:
            return "http", "127.0.0.1", self.loopback_port, path
        return u.scheme, str(u.hostname), 443, path

    def _stem(self, request: ProviderRequest) -> Path:
        """Where this exchange's files go: the dispatch's own name, or a fresh name in the work folder."""
        if request.raw_stem:
            return Path(request.raw_stem)
        return self.work_dir / f"{request.step}-{uuid.uuid4().hex[:16]}"

    def send(self, request: ProviderRequest, allowance_s: float) -> ProviderResponse:
        if allowance_s <= 0:
            raise TransportFailed("no time is left for this request", sent=False)
        scheme, host, port, path = self._target(request)
        stem = self._stem(request)
        durable.private_dir(stem.parent)
        files = {
            "out_path": stem.with_name(stem.name + ".body.part"),
            "final_path": stem.with_name(stem.name + ".body"),
            "partial_path": stem.with_name(stem.name + ".partial"),
            "status_path": stem.with_name(stem.name + ".status.json"),
        }
        for existing in files.values():
            if existing.exists():  # a dispatch number is used once: its files are never overwritten
                raise TransportFailed(f"refused: {existing.name} already exists", sent=False)
        spec = {
            "method": "POST",
            "scheme": scheme,
            "host": host,
            "port": port,
            "path": path,
            "headers": {
                "Content-Type": "application/json",
                "Accept-Encoding": "identity",
                "Authorization": self._authorization,
            },
            "body_b64": base64.b64encode(json.dumps(request.payload).encode("utf-8")).decode("ascii"),
            "allowance_s": max(0.05, allowance_s - 0.25),  # the worker stops itself a little before its kill
            "max_body_bytes": self.limits.max_body_bytes,
            "max_header_bytes": self.limits.max_header_bytes,
            "loopback_stub": self.loopback_port is not None,
            "identity": dict(request.identity) if request.identity else None,
            **{k: os.fspath(v) for k, v in files.items()},
        }
        t0 = time.monotonic()
        proc = subprocess.Popen(
            [self.python, "-I", "-m", "classic_probe.networker"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.workers_started += 1
        self.last_pid = proc.pid
        killed = False
        out = b""
        try:
            out, _err = proc.communicate(json.dumps(spec).encode("utf-8"), timeout=allowance_s)
        except subprocess.TimeoutExpired:
            proc.kill()
            killed = True
            self.workers_killed += 1
            try:
                out, _err = proc.communicate(timeout=REAP_TIMEOUT_S)
            except subprocess.TimeoutExpired:  # pragma: no cover - a killed process that cannot be reaped
                pass
        finally:
            if proc.poll() is None:  # pragma: no cover - communicate returned, so the worker has exited
                proc.kill()
                proc.wait(REAP_TIMEOUT_S)
            self.last_returncode = proc.returncode
        return self._outcome(out or b"", files, request, killed=killed, allowance_s=allowance_s, t0=t0)

    def _outcome(
        self,
        out: bytes,
        files: Mapping[str, Path],
        request: ProviderRequest,
        *,
        killed: bool,
        allowance_s: float,
        t0: float,
    ) -> ProviderResponse:
        """What the exchange left, after the worker exited or was killed (1.7.2: one path for both). The
        worker's own status, when it wrote one, says what happened; it is never overwritten."""
        killed_note = (
            f"no answer within {allowance_s:.1f} s: the worker was killed and reaped (the provider may still "
            "run and charge the request)"
        )
        status = _read_status(out, files["status_path"])
        if status is None:
            partial = _keep_after_kill(files, identity=request.identity)
            raise TransportFailed(
                killed_note if killed else "the worker gave no readable status", sent=None, partial=partial
            )
        if not status.get("ok"):
            sent = status.get("sent")
            message = f"{status.get('error')}: {status.get('detail', '')}".strip(": ")
            if killed:
                message += f" ({killed_note})"
            raise TransportFailed(
                message,
                sent=False if sent is False else None,  # the worker's own account, written before any kill
                partial=_described_partial(status, files["partial_path"]),
            )
        # A whole answer (or one cut at the byte limit), under its final name, or still under its .part name
        # when the worker was killed between its status and its rename (1.7.2: finished here, never lost).
        final, part = files["final_path"], files["out_path"]
        source = final if final.is_file() else part
        try:
            data = source.read_bytes()
        except OSError:
            raise TransportFailed(
                f"the answer the worker described is not on disk ({final.name})", sent=None
            ) from None
        if len(data) > self.limits.max_body_bytes or hashlib.sha256(data).hexdigest() != status.get("sha256"):
            raise TransportFailed(
                f"the answer on disk ({source.name}) does not match the worker's account of it", sent=None
            )
        shortfall = declared_shortfall(status)
        if shortfall:  # never whole when shorter than declared (the worker checks it first)
            raise TransportFailed(
                f"IncompleteBody: {shortfall} of the bytes the answer declared never came",
                sent=None,
                partial={
                    "bytes": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "http_status": status.get("status"),
                    "error": "IncompleteBody",
                    "file": source.name,
                    "complete": False,
                    "declared_bytes": len(data) + shortfall,
                },
            )
        if source == part:
            durable.replace(part, final)
        return ProviderResponse(
            int(status["status"]),
            data,
            {str(k): str(v) for k, v in status.get("headers") or []},
            truncated=bool(status.get("truncated")),
            redirect_location=status.get("redirect_location"),
            elapsed_s=round(time.monotonic() - t0, 3),
        )


def declared_shortfall(status: Mapping[str, Any]) -> int:
    """How many bytes an answer's own head declared that its body lacks (1.7.2, C4). 0 when nothing is
    missing, when no length was declared (a chunked body, or one ended by the connection's close), when the
    status has no body by definition (1xx, 204, 304), or when the body was cut at the byte limit (reported
    as truncated). A status written before 1.7.2 has no ``declared_bytes``: its Content-Length header is
    read."""
    if status.get("truncated"):
        return 0
    code = int(status.get("status") or status.get("http_status") or 0)
    if "declared_bytes" in status:
        declared = status["declared_bytes"]
    else:
        if code in (204, 304) or 100 <= code < 200:
            return 0
        headers = {str(k).lower(): str(v) for k, v in status.get("headers") or []}
        if "chunked" in headers.get("transfer-encoding", "").lower():
            return 0
        try:
            declared = int(headers["content-length"])
        except (KeyError, ValueError):
            return 0
    if declared is None:
        return 0
    got = status.get("body_bytes")
    if got is None:
        got = status.get("partial_bytes") or 0
    return max(0, int(declared) - int(got))


def _read_status(out: bytes, status_path: Path) -> dict[str, Any] | None:
    """The worker's status line, or the copy it wrote to disk when its output was lost."""
    try:
        status = json.loads(out.decode("utf-8").strip().splitlines()[-1])
        if isinstance(status, dict):
            return status
    except (ValueError, IndexError):
        pass
    try:
        status = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return status if isinstance(status, dict) else None


def _described_partial(status: Mapping[str, Any], partial_path: Path) -> dict[str, Any] | None:
    """The partial body a worker's status describes, or None when nothing of a body arrived. 1.7.2: an empty
    body after the answer's head is described too (the status says ``partial_file``), with the length the head
    declared; the file is checked against the status, and a difference is reported, never hidden."""
    if not status.get("partial_bytes") and not status.get("partial_file"):
        return None
    described: dict[str, Any] = {
        "bytes": int(status.get("partial_bytes") or 0),
        "sha256": str(status.get("partial_sha256") or hashlib.sha256(b"").hexdigest()),
        "http_status": status.get("http_status"),
        "error": status.get("error"),
        "file": partial_path.name,
        "complete": False,
    }
    if status.get("declared_bytes") is not None:
        described["declared_bytes"] = int(status["declared_bytes"])
    try:
        data = partial_path.read_bytes()
    except OSError:
        described["file_problem"] = "the partial file is missing"
    else:
        if len(data) != described["bytes"] or hashlib.sha256(data).hexdigest() != described["sha256"]:
            described["file_problem"] = "the partial file does not match its status"
    return described


def _keep_after_kill(
    files: Mapping[str, Path], *, identity: Mapping[str, Any] | None = None
) -> dict[str, Any] | None:
    """A worker killed mid-body, before it wrote any status, leaves its ``.part`` file: what arrived is kept
    as the dispatch's partial body, described by its length and SHA-256 (1.7.1, C4). An empty file holds
    nothing and is removed. 1.7.2: a worker killed after it kept its partial and before its status leaves the
    ``.partial`` file alone: it is described as found. A status the worker wrote is never replaced."""
    part, kept = files["out_path"], files["partial_path"]
    try:
        data = part.read_bytes()
    except OSError:
        try:
            data = kept.read_bytes()
        except OSError:
            return None
    else:
        if not data:
            _unlink(os.fspath(part))
            return None
        durable.replace(part, kept)
    described = {
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "http_status": None,
        "error": "Killed",
        "file": kept.name,
        "complete": False,
    }
    if files["status_path"].exists():  # pragma: no cover - the caller reads such a status first
        return described
    status: dict[str, Any] = {
        "ok": False,
        "error": "Killed",
        "sent": None,
        "partial_bytes": len(data),
        "partial_sha256": described["sha256"],
        "partial_file": True,
        "complete": False,
    }
    if identity:
        status["identity"] = dict(identity)
    durable.write(files["status_path"], (json.dumps(status, sort_keys=True) + "\n").encode(), private=True)
    return described


def _unlink(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass
