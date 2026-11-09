"""Reproductions of the client's review of probe 1.7.1 (findings C4 and C2), kept as tests.

Each test named ``test_c4_...`` or ``test_c2_...`` was run first against the frozen code of release 1.7.1
(``src`` tree 917932c45a7a06c3da5b8b7e8dc5d57e482f5b89, probe tree 7adfea8fbd8e562fd72444891e62e3029d544a5f,
commit 68ff3d8), with these tests and their helpers copied in, and failed there by its output; release
1.7.2 makes it pass. A test named ``..._control_...`` passes on both: it pins what the correction must keep.

- C4, a body cut short: a server declares ``Content-Length: 100``, writes the two bytes ``{}`` and closes.
  1.7.1 returned it as a whole answer (ok, not truncated, renamed to its final ``.body``), on success and
  error alike, and the campaign parsed it. ``http.client``'s ``read1`` reports such an end as an empty read,
  not as an error, and 1.7.1 took the empty read for the end of the body.
- C4, found while correcting the drip test the client saw fail on Linux: when a worker was killed after it had
  renamed its file (a whole answer to ``.body``, or the part that came to ``.partial``), 1.7.1 looked only for
  the worker's unrenamed ``.part`` file, so it reported a whole answer as lost and a kept partial as absent.
- C2, the whole session's deadline: on Linux the supervisor waited 1.10 s for a FIFO put at the evidence path,
  despite a hard end of 0.30 s; and it accepted the complete evidence a previous run left in the same folder
  when a new command exited 0 without writing any. A process the session left behind kept running after it,
  and the recovery's own bound was read from the wall clock.

OFFLINE: every connection is made by a child process (a request worker, or a process a test session leaves
behind) to a stub on 127.0.0.1.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import subprocess
import sys
import time
import types
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from classic_probe import campaign, captures, ledger, money, supervisor
from classic_probe import transport as transport_mod
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
from tests.conftest import reserve
from tests.processes import wait_gone
from tests.test_c2_c4_reproduction import CREDS, ROOT, LockHolder, campaign_files, drill
from tests.test_campaign import WALMART

# The stated tolerance (1.7.2): the supervisor returns within its hard end plus this, whatever the session
# did (supervisor.TOLERANCE_S; kept here as a number, so the 1.7.1 code could run these tests).
TOLERANCE_S = 0.5
STEP = "walmart-search-p1"
REQUEST = ProviderRequest(STEP, {"source": "walmart_search", "query": "milk"}, "type=raw,parsed")
GOOD = json.dumps({"results": [{"status_code": 200, "content": {}}]}).encode()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def isolated(tmp_path: Path, port: int, **kw: Any) -> IsolatedHttpTransport:
    return IsolatedHttpTransport(CREDS, work_dir=tmp_path / "work", loopback_port=port, **kw)


def files(stem: Path) -> dict[str, Path]:
    return {s: stem.with_name(stem.name + s) for s in (".body", ".body.part", ".partial", ".status.json")}


def exchange(tmp_path: Path, behaviour: stub.Behaviour, **kw: Any) -> tuple[ProviderResponse, Path]:
    """One exchange through the isolated worker, its files named as a dispatch's are."""
    stem = tmp_path / "raw" / "dispatch_001"
    with stub.Stub(behaviour) as s:
        response = isolated(tmp_path, s.port, **kw).send(
            dataclasses.replace(REQUEST, raw_stem=str(stem)), 20.0
        )
    return response, stem


def failed_exchange(tmp_path: Path, behaviour: stub.Behaviour, **kw: Any) -> tuple[TransportFailed, Path]:
    stem = tmp_path / "raw" / "dispatch_001"
    with stub.Stub(behaviour) as s:
        tr = isolated(tmp_path, s.port, **kw)
        with pytest.raises(TransportFailed) as exc:
            tr.send(dataclasses.replace(REQUEST, raw_stem=str(stem)), 20.0)
    return exc.value, stem


# -- C4: a body shorter than its declared length is never an answer ---------------------------------------


@pytest.mark.parametrize("status", [200, 500])
def test_c4_a_body_shorter_than_its_declared_length_is_never_an_answer(tmp_path: Path, status: int) -> None:
    exc, stem = failed_exchange(tmp_path, stub.short(status, 100, b"{}"))
    f = files(stem)
    assert not f[".body"].exists()  # never under the name of a whole answer
    assert f[".partial"].read_bytes() == b"{}"  # what arrived is kept
    recorded = json.loads(f[".status.json"].read_text("utf-8"))
    assert recorded["ok"] is False and recorded["complete"] is False, recorded
    assert recorded["declared_bytes"] == 100 and recorded["partial_bytes"] == 2, recorded
    assert recorded["partial_sha256"] == sha(b"{}") and recorded["http_status"] == status, recorded
    part = exc.partial
    assert part is not None, "the part that arrived was not described"
    assert (part["bytes"], part["sha256"], part["declared_bytes"]) == (2, sha(b"{}"), 100), part
    assert part["http_status"] == status and part["complete"] is False, part
    assert exc.sent is None  # the request went: its charge is unknown, never assumed free


def test_c4_a_declared_body_of_which_nothing_came_is_never_an_answer(tmp_path: Path) -> None:
    exc, stem = failed_exchange(tmp_path, stub.short(200, 100, b""))
    f = files(stem)
    assert not f[".body"].exists()
    assert f[".partial"].read_bytes() == b""  # the answer's head came: an empty body is kept as what it is
    recorded = json.loads(f[".status.json"].read_text("utf-8"))
    assert recorded["ok"] is False and recorded["complete"] is False, recorded
    assert (recorded["declared_bytes"], recorded["partial_bytes"]) == (100, 0), recorded
    assert recorded["partial_sha256"] == sha(b""), recorded
    assert exc.partial is not None and (exc.partial["bytes"], exc.partial["declared_bytes"]) == (0, 100)


def test_c4_a_body_cut_short_below_its_byte_limit_is_partial_not_an_answer(tmp_path: Path) -> None:
    """Declared above the byte limit, but only 50 bytes came before the close: the body ended early. It is
    neither a whole answer nor a body cut at the limit."""
    exc, stem = failed_exchange(
        tmp_path, stub.short(200, 1000, b"x" * 50), limits=ResponseLimits(max_body_bytes=100)
    )
    assert exc.partial is not None and (exc.partial["bytes"], exc.partial["declared_bytes"]) == (50, 1000)
    assert not files(stem)[".body"].exists()


@pytest.mark.parametrize(("status", "body"), [(200, b"x" * 100), (500, b"{}")])
def test_c4_control_a_body_of_exactly_its_declared_length_is_whole(
    tmp_path: Path, status: int, body: bytes
) -> None:
    r, stem = exchange(tmp_path, stub.short(status, len(body), body))
    assert (r.http_status, r.body, r.truncated) == (status, body, False)
    f = files(stem)
    assert f[".body"].read_bytes() == body and not f[".partial"].exists() and not f[".body.part"].exists()


@pytest.mark.parametrize(
    "behaviour",
    [stub.no_body(204), stub.no_body(304), stub.respond(200, b"")],
    ids=["204-no-content", "304-not-modified", "200-content-length-0"],
)
def test_c4_control_a_response_without_a_body_is_whole_and_empty(
    tmp_path: Path, behaviour: stub.Behaviour
) -> None:
    r, stem = exchange(tmp_path, behaviour)
    assert r.body == b"" and r.truncated is False
    assert files(stem)[".body"].read_bytes() == b""


def test_c4_control_a_body_of_exactly_the_byte_limit_is_whole(tmp_path: Path) -> None:
    r, _ = exchange(tmp_path, stub.respond(200, b"y" * 100), limits=ResponseLimits(max_body_bytes=100))
    assert (len(r.body), r.truncated) == (100, False)


def test_c4_control_a_body_above_the_byte_limit_is_truncated_and_never_read(tmp_path: Path) -> None:
    limits = ResponseLimits(max_body_bytes=100)
    r, _ = exchange(tmp_path, stub.respond(200, b"z" * 1000), limits=limits)
    assert (len(r.body), r.truncated) == (100, True)
    with pytest.raises(BodyTooLarge):
        decode_body(r, limits)


def test_c4_control_a_chunked_body_cut_short_is_partial(tmp_path: Path) -> None:
    exc, stem = failed_exchange(tmp_path, stub.chunked_short(200, 100, b"{}"))
    assert exc.partial is not None and exc.partial["bytes"] == 2 and exc.partial["complete"] is False
    assert not files(stem)[".body"].exists()


def test_c4_a_campaign_keeps_a_short_body_as_partial_and_holds_its_money(
    tmp_path: Path, make_ledger: Any, card: money.RateCard
) -> None:
    led = make_ledger()
    with stub.Stub(stub.short(200, 100, b"{}")) as s:
        tr = isolated(tmp_path, s.port)
        result = campaign.Campaign(
            led, tr, WALMART, card, out_dir=tmp_path / "out", request_timeout_s=20.0
        ).run()
        connections = len(s.connections)
    assert led.captures() == [], "a body shorter than its declared length was indexed as an answer"
    assert connections == 1  # nothing is fetched again
    assert result.stop == "STOP_IN_FLIGHT_UNKNOWN", result.detail
    [row] = led.rows()
    assert row["state"] == ledger.IN_FLIGHT_UNKNOWN and row["reserved_usd"] == "0.0040"  # held
    [event] = [e for e in led.events() if e["kind"] == "PARTIAL_RESPONSE"]
    detail = json.loads(event["detail"])
    assert (detail["bytes"], detail["sha256"], detail["declared_bytes"]) == (2, sha(b"{}"), 100), detail
    assert detail["complete"] is False and detail["seq"] == 1


def test_c4_a_short_body_survives_a_crash_and_an_immediate_restart_without_a_refetch(tmp_path: Path) -> None:
    manifest, out, _ = campaign_files(tmp_path)
    with stub.Stub(stub.short(200, 100, b"{}")) as s:
        done = subprocess.run(
            drill(manifest, out, "loopback-crash-on-failure", str(s.port)),
            cwd=ROOT,
            capture_output=True,
            timeout=120,
            check=False,
        )
        first_connections = len(s.connections)
    assert done.returncode == 23, (
        "the session did not take the short body for a failure; it ended with exit code "
        f"{done.returncode}: {done.stdout.decode('utf-8', 'replace')[-1500:]}"
    )
    assert first_connections == 1
    recovered = supervisor.recover_session(
        manifest, out, "walmart", reason="test: a crash after a short body"
    )
    assert recovered["capture_recovery"]["partial_recorded"] == [1], recovered
    assert recovered["capture_recovery"]["kept_from_raw"] == [], recovered
    raw = out / "private" / "raw"
    before = {p.name: sha(p.read_bytes()) for p in sorted(raw.iterdir())}
    assert "dispatch_001.body" not in before and before["dispatch_001.partial"] == sha(b"{}"), before

    def check_first(led: ledger.Ledger) -> None:
        assert led.captures() == [] or [c["seq"] for c in led.captures()] == [2]
        row = led.rows()[0]
        assert (
            row["seq"] == 1 and row["state"] == ledger.IN_FLIGHT_UNKNOWN and row["reserved_usd"] == "0.0040"
        )
        [event] = [e for e in led.events() if e["kind"] == "PARTIAL_RESPONSE"]  # recorded once
        detail = json.loads(event["detail"])
        assert (detail["seq"], detail["bytes"], detail["sha256"]) == (1, 2, sha(b"{}")), detail
        assert detail["declared_bytes"] == 100 and detail["complete"] is False, detail

    led = ledger.open_from_manifest(manifest)
    try:
        check_first(led)
    finally:
        led.close()
    # An immediate restart in the same folder: a new dispatch number, the old files untouched, the money held.
    with stub.Stub(stub.respond(200, GOOD)) as s2:
        again = subprocess.run(
            drill(manifest, out, "loopback", str(s2.port)),
            cwd=ROOT,
            capture_output=True,
            timeout=120,
            check=False,
        )
        assert again.returncode == 0, again.stderr.decode("utf-8", "replace")[-2000:]
        assert len(s2.connections) == 1
    after = {p.name: sha(p.read_bytes()) for p in sorted(raw.iterdir()) if p.name.startswith("dispatch_001")}
    assert after == {k: v for k, v in before.items() if k.startswith("dispatch_001")}
    assert (raw / "dispatch_002.body").read_bytes() == GOOD
    led = ledger.open_from_manifest(manifest)
    try:
        assert [r["seq"] for r in led.rows()] == [1, 2]
        check_first(led)
        assert led.totals().committed_usd >= Decimal("0.0040")
    finally:
        led.close()


def test_c4_a_raw_answer_shorter_than_its_declared_length_is_never_kept_as_whole(
    make_ledger: Any, tmp_path: Path
) -> None:
    """A status that calls a body whole although its own headers declare more bytes than it has (as 1.7.1's
    worker wrote for the short body above): the recovery records the body as partial and never indexes it."""
    led = make_ledger()
    seq = reserve(led, step=STEP)
    led.mark_sent(seq)
    [row] = led.rows()
    store = captures.CaptureStore(tmp_path / "out", "walmart")
    stem = store.raw_stem(seq)
    stem.parent.mkdir(parents=True)
    status = {
        "ok": True,
        "status": 200,
        "reason": "OK",
        "headers": [["Content-Length", "100"], ["Content-Type", "application/json"]],
        "body_bytes": 2,
        "truncated": False,
        "sha256": sha(b"{}"),
        "elapsed_s": 0.1,
        "redirect_location": None,
        "identity": {
            "campaign_id": led.campaign_id,
            "ledger_genesis_id": led.genesis_id,
            "seq": seq,
            "step": row["step"],
            "attempt": row["attempt"],
            "payload_sha256": row["payload_sha256"],
        },
    }
    files(stem)[".status.json"].write_text(json.dumps(status), encoding="utf-8")
    files(stem)[".body"].write_bytes(b"{}")
    found = store.recover(led)
    assert found["kept_from_raw"] == [] and led.captures() == [], found
    assert found["partial_recorded"] == [seq], found
    assert files(stem)[".body"].read_bytes() == b"{}"  # evidence is kept as it was found
    [event] = [e for e in led.events() if e["kind"] == "PARTIAL_RESPONSE"]
    assert json.loads(event["detail"])["declared_bytes"] == 100


WHOLE_THEN_HANG = """
import hashlib, json, sys, time
spec = json.loads(sys.stdin.buffer.read())
body = b'{"results": []}'
with open(spec["out_path"], "wb") as f:
    f.write(body)
status = {
    "ok": True, "status": 200, "reason": "OK", "headers": [["Content-Length", str(len(body))]],
    "headers_truncated": False, "body_bytes": len(body), "truncated": False,
    "sha256": hashlib.sha256(body).hexdigest(), "elapsed_s": 0.1, "redirect_location": None,
    "complete": True, "declared_bytes": len(body), "framing": "content-length",
}
if spec.get("identity"):
    status["identity"] = spec["identity"]
with open(spec["status_path"], "w") as f:
    f.write(json.dumps(status))
time.sleep(120)
"""

PARTIAL_THEN_HANG = """
import hashlib, json, sys, time
spec = json.loads(sys.stdin.buffer.read())
data = b'{"results": [{"conte'
with open(spec["partial_path"], "wb") as f:
    f.write(data)
status = {
    "ok": False, "error": "DeadlinePassed", "sent": True, "http_status": 200,
    "partial_bytes": len(data), "partial_sha256": hashlib.sha256(data).hexdigest(), "partial_file": True,
    "complete": False, "declared_bytes": 5000, "framing": "content-length",
}
if spec.get("identity"):
    status["identity"] = spec["identity"]
with open(spec["status_path"], "w") as f:
    f.write(json.dumps(status))
time.sleep(120)
"""


def fake_worker(monkeypatch: pytest.MonkeyPatch, code: str) -> None:
    """The transport starts ``code`` in place of the request worker (it never connects anywhere)."""
    real = subprocess.Popen

    def start(args: Any, **kw: Any) -> Any:
        assert list(args) == [sys.executable, "-I", "-m", "classic_probe.networker"]
        return real([sys.executable, "-I", "-c", code], **kw)

    monkeypatch.setattr(transport_mod.subprocess, "Popen", start)


def test_c4_a_whole_answer_whose_worker_is_killed_before_its_final_rename_is_kept_whole(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The worker wrote the whole body and the status that describes it, then was killed before it gave the
    body its final name. The answer is whole and paid for: it stays the answer, never a partial, and the
    worker's status is never overwritten."""
    fake_worker(monkeypatch, WHOLE_THEN_HANG)
    stem = tmp_path / "raw" / "dispatch_001"
    f = files(stem)
    tr = isolated(tmp_path, 9)
    try:
        r = tr.send(dataclasses.replace(REQUEST, raw_stem=str(stem)), 1.5)
    except TransportFailed as exc:
        found = {p.name: p.stat().st_size for p in sorted(stem.parent.iterdir())}
        status = json.loads(f[".status.json"].read_text("utf-8")) if f[".status.json"].exists() else None
        pytest.fail(
            f"a whole answer was reported as no answer ({exc}; partial {exc.partial}); files {found}; "
            f"status now {status}"
        )
    assert tr.workers_killed == 1
    assert (r.http_status, r.body, r.truncated) == (200, b'{"results": []}', False)
    assert f[".body"].read_bytes() == b'{"results": []}'
    assert not f[".partial"].exists() and not f[".body.part"].exists()
    assert json.loads(f[".status.json"].read_text("utf-8"))["ok"] is True  # the worker's own status


def test_c4_a_partial_the_worker_kept_before_its_kill_is_still_described(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The race the drip test met on Windows: the worker stopped at its own deadline, kept what had arrived as
    partial and wrote its status; the transport's kill came before it exited."""
    fake_worker(monkeypatch, PARTIAL_THEN_HANG)
    stem = tmp_path / "raw" / "dispatch_001"
    tr = isolated(tmp_path, 9)
    with pytest.raises(TransportFailed) as exc:
        tr.send(dataclasses.replace(REQUEST, raw_stem=str(stem)), 1.5)
    data = b'{"results": [{"conte'
    part = exc.value.partial
    assert part is not None, "the partial body the worker had kept was not described"
    assert (part["bytes"], part["sha256"], part["declared_bytes"]) == (len(data), sha(data), 5000), part
    assert (part["http_status"], part["error"], part["complete"]) == (200, "DeadlinePassed", False), part
    status = json.loads(files(stem)[".status.json"].read_text("utf-8"))
    assert status["error"] == "DeadlinePassed"  # the worker's own status, never overwritten


# -- C2: one deadline for the whole session, and only this session's evidence -----------------------------

FIFO_SESSION = """
import os, sys, time
evidence, pid_file = sys.argv[1], sys.argv[2]
os.makedirs(os.path.dirname(evidence), exist_ok=True)
os.mkfifo(evidence)
pid = os.fork()
if pid == 0:
    null = os.open(os.devnull, os.O_RDWR)
    for fd in (0, 1, 2):
        os.dup2(null, fd)
    time.sleep(1.1)
    with open(evidence, "w") as f:
        f.write('{"complete": true}')
    os._exit(0)
with open(pid_file, "w") as f:
    f.write(str(pid))
"""


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="Windows has no FIFO in its file system (a named pipe lives under the pipe namespace, never at a "
    "file's path), so nothing at the evidence path can hold an open; the same bound is tested on Windows "
    "by the stale, left-behind and wall-clock tests below",
)
def test_c2_a_fifo_at_the_evidence_path_cannot_hold_the_supervisor_past_its_hard_end(tmp_path: Path) -> None:
    manifest, out, _ = campaign_files(tmp_path)
    pid_file = tmp_path / "writer.pid"
    t0 = time.monotonic()
    session = supervisor.run_session(
        [sys.executable, "-I", "-c", FIFO_SESSION, str(out / "campaign_evidence.json"), str(pid_file)],
        hard_end_s=0.30,
        manifest=manifest,
        out_dir=out,
        retailer="walmart",
        cwd=ROOT,
    )
    elapsed = time.monotonic() - t0
    assert pid_file.is_file(), "the session ended before it made its FIFO: nothing was reproduced"
    writer = int(pid_file.read_text())
    assert elapsed < 0.30 + TOLERANCE_S, (
        f"the supervisor returned {elapsed:.2f} s after its start; the session's hard end was 0.30 s"
    )
    assert wait_gone(writer, 0.5), "the writer the session left behind was still running"
    assert session.recovery, "a FIFO was accepted as the session's evidence"


def test_c2_a_previous_runs_complete_evidence_is_not_taken_for_this_sessions(tmp_path: Path) -> None:
    manifest, out, _ = campaign_files(tmp_path)
    ids = json.loads(manifest.read_text("utf-8"))
    out.mkdir(parents=True)
    previous = {
        "complete": True,
        "campaign_id": ids["campaign_id"],
        "ledger_genesis_id": ids["ledger_genesis_id"],
        "offline": True,
        "execution_id": "an-earlier-execution",
    }
    (out / "campaign_evidence.json").write_text(json.dumps(previous), encoding="utf-8")
    session = supervisor.run_session(
        [sys.executable, "-I", "-c", "pass"],
        hard_end_s=30.0,
        manifest=manifest,
        out_dir=out,
        retailer="walmart",
        cwd=ROOT,
    )
    assert not session.killed and session.returncode == 0
    assert session.recovery, "the evidence an earlier run left in the folder was taken for this session's"
    assert (out / "campaign_evidence.recovered.json").is_file()
    assert json.loads((out / "campaign_evidence.json").read_text("utf-8")) == previous  # kept as it was


LEFT_BEHIND = """
import subprocess, sys
port, pid_file = sys.argv[1], sys.argv[2]
late = (
    "import socket, sys, time\\n"
    "time.sleep(1.0)\\n"
    "s = socket.create_connection(('127.0.0.1', int(sys.argv[1])), 5)\\n"
    "req = b'POST /v1/queries HTTP/1.1\\\\r\\\\nHost: late\\\\r\\\\n'\\n"
    "s.sendall(req + b'Content-Length: 0\\\\r\\\\n\\\\r\\\\n')\\n"
    "time.sleep(2.0)\\n"
)
p = subprocess.Popen(
    [sys.executable, "-I", "-c", late, port],
    stdin=subprocess.DEVNULL,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
with open(pid_file, "w") as f:
    f.write(str(p.pid))
"""


def test_c2_a_process_a_session_leaves_behind_is_killed_before_it_can_dispatch(tmp_path: Path) -> None:
    """The session exits 0 at once, leaving a process that connects a second later (as a request worker
    still running would): it must not outlive the session, whatever the session's exit."""
    manifest, out, _ = campaign_files(tmp_path)
    pid_file = tmp_path / "late.pid"
    with stub.Stub(stub.hang) as s:
        t0 = time.monotonic()
        supervisor.run_session(
            [sys.executable, "-I", "-c", LEFT_BEHIND, str(s.port), str(pid_file)],
            hard_end_s=20.0,
            manifest=manifest,
            out_dir=out,
            retailer="walmart",
            cwd=ROOT,
        )
        while time.monotonic() - t0 < 4.0:  # past the moment the process left behind would connect
            time.sleep(0.05)
        connections = len(s.connections)
    assert pid_file.is_file()
    late = int(pid_file.read_text())
    assert connections == 0, "a process the session left behind connected after the session had ended"
    assert wait_gone(late, 1.0), "the process the session left behind was still running"


def test_c2_the_recovery_keeps_its_bound_when_the_wall_clock_jumps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The supervisor's wall clock reads an hour ahead and the ledger's lock is held elsewhere: the recovery
    must still end its own wait for the lock by the session's end (it says so), not be cut off by a kill."""
    manifest, out, path = campaign_files(tmp_path)
    real_time = time.time
    shifted = types.SimpleNamespace(
        time=lambda: real_time() + 3600.0,
        monotonic=time.monotonic,
        sleep=time.sleep,
        perf_counter=time.perf_counter,
    )
    monkeypatch.setattr(supervisor, "time", shifted)
    with LockHolder(path) as holder:
        holder.take.set()
        assert holder.taken.wait(10)
        t0 = time.monotonic()
        session = supervisor.run_session(
            [sys.executable, "-I", "-c", "import time; time.sleep(60)"],
            hard_end_s=6.0,
            manifest=manifest,
            out_dir=out,
            retailer="walmart",
            cwd=ROOT,
        )
        elapsed = time.monotonic() - t0
    assert session.killed and elapsed < 6.0 + TOLERANCE_S, elapsed
    problems = " ".join(session.recovery.get("problems", []))
    assert "lock" in problems, session.recovery
    assert "was killed" not in problems, session.recovery


def test_c2_control_a_stalled_request_ends_within_the_tolerance_and_nothing_dispatches_later(
    tmp_path: Path,
) -> None:
    manifest, out, _ = campaign_files(tmp_path)
    with stub.Stub(stub.hang) as s:
        t0 = time.monotonic()
        session = supervisor.run_session(
            drill(manifest, out, "loopback", str(s.port)),
            hard_end_s=5.0,
            manifest=manifest,
            out_dir=out,
            retailer="walmart",
            cwd=ROOT,
        )
        returned = time.monotonic()
        time.sleep(1.5)  # nothing may connect after the supervisor returned
        connections = list(s.connections)
    assert session.killed and returned - t0 < 5.0 + TOLERANCE_S, returned - t0
    assert len(connections) == 1
    assert connections[0].closed_at is not None and connections[0].closed_at <= returned + 0.25
    led = ledger.open_from_manifest(manifest)
    try:
        [row] = led.rows()
        assert row["state"] == ledger.IN_FLIGHT_UNKNOWN and row["reserved_usd"] == "0.0040"  # held
    finally:
        led.close()


def test_c2_an_immediate_restart_in_the_same_folder_keeps_each_sessions_evidence_its_own(
    tmp_path: Path,
) -> None:
    manifest, out, _ = campaign_files(tmp_path)
    with stub.Stub(stub.hang) as s:
        first = supervisor.run_session(
            drill(manifest, out, "loopback", str(s.port)),
            hard_end_s=5.0,
            manifest=manifest,
            out_dir=out,
            retailer="walmart",
            cwd=ROOT,
        )
    assert first.killed and first.recovery.get("rows_recovered_as_unknown") == 1, first.recovery
    with stub.Stub(stub.respond(200, GOOD)) as s2:  # at once, in the same folder
        second = supervisor.run_session(
            drill(manifest, out, "loopback", str(s2.port)),
            hard_end_s=60.0,
            manifest=manifest,
            out_dir=out,
            retailer="walmart",
            cwd=ROOT,
        )
        assert len(s2.connections) == 1
    assert not second.killed and second.returncode == 0 and second.recovery == {}, second
    third = supervisor.run_session(  # at once again: a command that writes no evidence
        [sys.executable, "-I", "-c", "pass"],
        hard_end_s=30.0,
        manifest=manifest,
        out_dir=out,
        retailer="walmart",
        cwd=ROOT,
    )
    assert third.recovery, "the second session's evidence was taken for the third's"
    led = ledger.open_from_manifest(manifest)
    try:
        rows = led.rows()
        assert [r["seq"] for r in rows] == [1, 2]  # the restart did not reuse a dispatch number
        assert rows[0]["state"] == ledger.IN_FLIGHT_UNKNOWN and rows[0]["reserved_usd"] == "0.0040"
    finally:
        led.close()
    assert (out / "private" / "raw" / "dispatch_002.body").read_bytes() == GOOD
