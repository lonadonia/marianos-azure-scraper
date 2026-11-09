"""The isolated request worker (1.7.0, findings C1 and C2), against a scripted stub on 127.0.0.1.

OFFLINE: only the worker, a child process, connects, and only to the loopback stub this test runs. The test
process keeps its network closed (tests/conftest.py).
"""

from __future__ import annotations

import dataclasses
import gzip
import hashlib
import json
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from classic_probe import campaign, contract, gates, ledger, money, networker, transport
from classic_probe.stops import Stop
from classic_probe.transport import (
    BodyTooLarge,
    IsolatedHttpTransport,
    ProviderRequest,
    ProviderResponse,
    ResponseLimits,
    TransportFailed,
    decode_body,
)
from tests import loopback_stub as stub
from tests import processes
from tests.test_campaign import WALMART

CREDS = gates.Credentials("loopback-user", "loopback-password")
REQUEST = ProviderRequest(
    "walmart-search-p1", {"source": "walmart_search", "query": "milk"}, "type=raw,parsed"
)
GOOD = json.dumps({"results": [{"status_code": 200, "content": {}}]}).encode()


def isolated(tmp_path: Path, port: int, **kw: Any) -> IsolatedHttpTransport:
    return IsolatedHttpTransport(CREDS, work_dir=tmp_path / "work", loopback_port=port, **kw)


def test_an_answer_comes_back_whole_without_its_cookies(tmp_path: Path) -> None:
    with stub.Stub(stub.respond(200, GOOD, {"Set-Cookie": "sid=abc", "X-Thing": "1"})) as s:
        tr = isolated(tmp_path, s.port)
        r = tr.send(REQUEST, 20.0)
    assert (r.http_status, r.body, r.truncated) == (200, GOOD, False)
    assert {k.lower() for k in r.headers} >= {"x-thing"} and "set-cookie" not in {
        k.lower() for k in r.headers
    }
    assert tr.workers_started == 1 and tr.workers_killed == 0 and tr.last_returncode == 0
    assert s.authorizations() == ["present"]
    assert list((tmp_path / "work").glob("*.part")) == []  # the worker's file is removed once read


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
@pytest.mark.parametrize(
    "location",
    [
        "https://realtime.oxylabs.io/v1/queries?again=1",  # the same host
        "https://elsewhere.example/collect",  # another host
        "http://realtime.oxylabs.io/v1/queries",  # a downgrade to plain HTTP
        "/v1/queries",  # a relative location (a loop back to itself)
    ],
)
def test_a_redirect_is_reported_and_never_followed(tmp_path: Path, status: int, location: str) -> None:
    with stub.Stub(stub.redirect(status, location)) as s:
        r = isolated(tmp_path, s.port).send(REQUEST, 20.0)
        time.sleep(0.2)
        connections = len(s.connections)
    assert r.http_status == status and r.redirect_location == location
    assert connections == 1 and s.authorizations() == ["present"]  # one request: the credentials went once


def test_a_redirect_chain_stops_the_campaign_after_one_request(
    tmp_path: Path, make_ledger: Any, card: money.RateCard
) -> None:
    hops = [stub.redirect(302, f"https://hop{i}.example/next") for i in range(5)]
    with stub.Stub(*hops) as s:
        led = make_ledger()
        result = campaign.Campaign(
            led, isolated(tmp_path, s.port), WALMART, card, out_dir=tmp_path / "out", request_timeout_s=20
        ).run()
        connections = len(s.connections)
    assert result.stop == Stop.UNSUPPORTED_RESPONSE.value and "never followed" in result.detail
    assert connections == 1
    [row] = led.rows()
    assert (
        row["provider_status"] == 302 and row["billing"] == ledger.UNKNOWN and row["reserved_usd"] == "0.0040"
    )


def test_a_server_that_never_answers_is_killed_and_reaped_at_the_deadline(tmp_path: Path) -> None:
    with stub.Stub(stub.hang) as s:
        tr = isolated(tmp_path, s.port)
        t0 = time.monotonic()
        with pytest.raises(TransportFailed) as exc:
            tr.send(REQUEST, 1.5)
        took = time.monotonic() - t0
    assert took < 4.0 and exc.value.sent is None  # bounded by the allowance; the outcome is unknown
    assert tr.last_returncode is not None  # the worker has exited and was reaped


def test_a_body_dripped_past_the_deadline_is_cut_off(tmp_path: Path) -> None:
    """Each byte comes within the socket's timeout, so only the deadline bounds this exchange. The worker
    stops itself at its own deadline, a little before the request's; when its start was slow, the transport's
    kill at the request's deadline comes first. Either way the call ends by the request's allowance, the
    worker has exited and was reaped, and what arrived is kept as partial, never as an answer.

    1.7.2 (the client's review of 1.7.1): the 1.7.1 test required the kill (``workers_killed == 1``). On Linux
    the worker starts fast and ends itself first, so that test failed there although the exchange was bounded;
    the kill of a worker that does not end itself is tested on its own below."""
    allowance = 1.5
    with stub.Stub(stub.drip(10_000, 0.05)) as s:
        tr = isolated(tmp_path, s.port)
        t0 = time.monotonic()
        with pytest.raises(TransportFailed) as exc:
            tr.send(REQUEST, allowance)
        took = time.monotonic() - t0
    assert 1.0 <= took < allowance + 0.5, took  # it waited for the deadline, and no longer
    assert exc.value.sent is None  # the request went: its outcome is unknown
    assert tr.workers_started == 1 and tr.last_returncode is not None  # the worker has exited and was reaped
    assert processes.gone(tr.last_pid or 0)
    if tr.workers_killed == 0:
        assert tr.last_returncode == 0 and "DeadlinePassed" in str(exc.value)  # it ended itself
    else:
        assert tr.workers_killed == 1 and tr.last_returncode != 0  # the transport's kill came first
    partial = exc.value.partial
    assert partial is not None and partial["bytes"] > 0 and partial["complete"] is False, partial


HUNG_WORKER = """
import json, sys, time
spec = json.loads(sys.stdin.buffer.read())
with open(spec["out_path"], "wb") as f:
    f.write(b'{"results": [')
time.sleep(120)
"""


def test_a_worker_that_hangs_past_its_deadline_is_killed_and_reaped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A worker that never ends by itself (here: one that wrote part of a body, then hangs): the transport
    kills it at the request's deadline and reaps it, and what it wrote is kept as partial (1.7.2)."""
    real = subprocess.Popen

    def hung(args: Any, **kw: Any) -> Any:
        assert list(args) == [sys.executable, "-I", "-m", "classic_probe.networker"]
        return real([sys.executable, "-I", "-c", HUNG_WORKER], **kw)

    monkeypatch.setattr(transport.subprocess, "Popen", hung)
    stem = tmp_path / "raw" / "dispatch_001"
    tr = isolated(tmp_path, 9)  # nothing listens there; this worker never connects
    allowance = 1.5
    t0 = time.monotonic()
    with pytest.raises(TransportFailed) as exc:
        tr.send(dataclasses.replace(REQUEST, raw_stem=str(stem)), allowance)
    took = time.monotonic() - t0
    assert allowance <= took < allowance + 1.0, took  # killed at the deadline
    assert tr.workers_killed == 1 and tr.last_returncode is not None  # killed, then reaped
    if sys.platform != "win32":
        assert tr.last_returncode == -signal.SIGKILL
    assert processes.gone(tr.last_pid or 0)
    assert exc.value.sent is None
    kept = b'{"results": ['
    assert exc.value.partial == {
        "bytes": len(kept),
        "sha256": hashlib.sha256(kept).hexdigest(),
        "http_status": None,
        "error": "Killed",
        "file": "dispatch_001.partial",
        "complete": False,
    }
    assert stem.with_name("dispatch_001.partial").read_bytes() == kept
    assert not stem.with_name("dispatch_001.body").exists()


@pytest.mark.parametrize("status", [200, 500])
def test_a_body_above_its_limit_is_truncated_on_success_and_error_alike(tmp_path: Path, status: int) -> None:
    limits = ResponseLimits(max_body_bytes=100_000)
    with stub.Stub(stub.endless(status)) as s:
        r = isolated(tmp_path, s.port, limits=limits).send(REQUEST, 20.0)
    assert r.http_status == status and r.truncated is True and len(r.body) == 100_000
    with pytest.raises(BodyTooLarge):
        decode_body(r, limits)


def test_a_truncated_answer_stops_the_campaign_and_is_never_read(
    tmp_path: Path, make_ledger: Any, card: money.RateCard
) -> None:
    with stub.Stub(stub.endless(200)) as s:
        tr = isolated(tmp_path, s.port, limits=ResponseLimits(max_body_bytes=50_000))
        led = make_ledger()
        result = campaign.Campaign(
            led, tr, WALMART, card, out_dir=tmp_path / "out", request_timeout_s=20
        ).run()
    assert result.stop == Stop.UNSUPPORTED_RESPONSE.value and "not read whole" in result.detail
    [cap] = led.captures()
    assert cap["truncated"] == 1 and cap["body_bytes"] == 50_000


def test_a_compression_bomb_is_refused_within_its_decoded_limit(tmp_path: Path) -> None:
    limits = ResponseLimits(max_body_bytes=8_000_000, max_decoded_bytes=1_000_000)
    with stub.Stub(stub.gzip_bomb(50_000_000)) as s:
        r = isolated(tmp_path, s.port, limits=limits).send(REQUEST, 20.0)
    assert len(r.body) < 200_000  # what came over the wire is small
    with pytest.raises(BodyTooLarge):
        decode_body(r, limits)
    small = ProviderResponse(200, gzip.compress(GOOD), {"Content-Encoding": "gzip"})
    assert decode_body(small, limits) == GOOD


def request_to(url: str) -> ProviderRequest:
    class Elsewhere(ProviderRequest):
        @property
        def url(self) -> str:
            return url

    return Elsewhere("x", {"url": "u"})


@pytest.mark.parametrize(
    "url",
    [
        "https://realtime.oxylabs.io.evil.example/v1/queries",
        "http://realtime.oxylabs.io/v1/queries",
        "https://realtime.oxylabs.io:8443/v1/queries",
        "https://realtime.oxylabs.io/v1/other",
        "https://user@elsewhere.example/v1/queries",
    ],
)
def test_a_request_for_any_other_url_is_refused_before_a_worker_starts(tmp_path: Path, url: str) -> None:
    tr = isolated(tmp_path, 9)  # nothing listens there, and nothing is started
    with pytest.raises(TransportFailed) as exc:
        tr.preflight(request_to(url))
    assert exc.value.sent is False
    with pytest.raises(TransportFailed):
        tr.send(request_to(url), 5.0)
    assert tr.workers_started == 0


def test_without_a_loopback_stub_this_build_refuses_to_build_the_transport(tmp_path: Path) -> None:
    assert gates.LIVE_ENABLED is False
    with pytest.raises(gates.LiveDisabled):
        IsolatedHttpTransport(CREDS, work_dir=tmp_path)


def test_the_worker_itself_refuses_the_real_endpoint_and_any_other_target(tmp_path: Path) -> None:
    base = {
        "method": "POST",
        "path": contract.ENDPOINT_PATH,
        "headers": {},
        "body_b64": "",
        "allowance_s": 5,
        "max_body_bytes": 10,
        "max_header_bytes": 10,
        "out_path": str(tmp_path / "x.part"),
    }
    refused = [
        {"scheme": "https", "host": "realtime.oxylabs.io", "port": 443},  # live mode is disabled
        {"scheme": "https", "host": "elsewhere.example", "port": 443},
        {"scheme": "http", "host": "10.0.0.1", "port": 80, "loopback_stub": True},  # not the loopback
        {"scheme": "https", "host": "127.0.0.1", "port": 443, "loopback_stub": True},
    ]
    for target in refused:
        out = networker.exchange({**base, **target})
        assert out["ok"] is False and out["error"] == "Refused" and out["sent"] is False, target


def test_the_credentials_never_appear_in_the_workers_arguments_or_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, Any] = {}
    real = subprocess.Popen

    def spy(args: Any, **kw: Any) -> Any:
        seen["args"], seen["env"] = list(args), kw.get("env")
        return real(args, **kw)

    monkeypatch.setattr(transport.subprocess, "Popen", spy)
    with stub.Stub(stub.respond(200, GOOD)) as s:
        isolated(tmp_path, s.port).send(REQUEST, 20.0)
    assert seen["args"] == [sys.executable, "-I", "-m", "classic_probe.networker"]
    assert seen["env"] is None  # the environment is inherited untouched: nothing is added to it
    assert "loopback-password" not in " ".join(seen["args"])
