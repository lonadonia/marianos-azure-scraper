"""Reproductions of the two findings the client's review left open after 1.7.0 (C2 and C4), kept as tests.

Each test here was written against release 1.7.0 first and failed there (the log of that run is delivered with
1.7.1); release 1.7.1 makes it pass.

- C2: the one session deadline must also bound what happens after the requests: the ledger writes that record
  an answer or a stop, the evidence export, and the recovery a supervisor runs after it kills a session. In
  1.7.0 the recovery ran after the session's end with no bound of its own (a held ledger lock kept it waiting
  30 s, then it raised), the writes after an answer waited 30 s for the lock whatever time was left, and a
  process that could not be reaped after its kill raised out of the supervisor with nothing recovered.
- C4: an answer that reached the disk must survive a crash. In 1.7.0 the request worker's file, written and
  synced, was deleted by the transport before the kept copy was written, so a crash between the two lost a
  paid answer; the evidence files were renamed into place without being synced; and a body cut at its deadline
  left no record of what had arrived.

OFFLINE: every connection is a request worker's (a child process) to a stub on 127.0.0.1.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from classic_probe import campaign, captures, gates, ledger, money, supervisor
from classic_probe.transport import IsolatedHttpTransport, ProviderRequest, ProviderResponse
from tests import fixture_builder as fb
from tests import loopback_stub as stub
from tests.conftest import FakeClock
from tests.test_campaign import WALMART

ROOT = Path(__file__).resolve().parents[1]
CREDS = gates.Credentials("loopback-user", "loopback-password")


def campaign_files(tmp_path: Path) -> tuple[Path, Path, Path]:
    path = tmp_path / "ledger.sqlite3"
    led = ledger.Ledger.create(path, "drill", ledger.Limits(), offline=True)
    ledger.write_manifest(tmp_path / "manifest.json", led)
    led.close()
    return tmp_path / "manifest.json", tmp_path / "out", path


def drill(manifest: Path, out: Path, mode: str, *extra: str) -> list[str]:
    return [sys.executable, "-m", "tests.session_drill", str(manifest), str(out), mode, *extra]


class LockHolder:
    """Another connection that takes the ledger's write lock when told to and keeps it until released."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.take = threading.Event()
        self.taken = threading.Event()
        self.release = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        conn = sqlite3.connect(self.path, timeout=60, isolation_level=None, check_same_thread=False)
        try:
            if not self.take.wait(120):
                return
            conn.execute("BEGIN IMMEDIATE")
            self.taken.set()
            self.release.wait(180)
            conn.execute("ROLLBACK")
        finally:
            conn.close()

    def __enter__(self) -> LockHolder:
        self.thread.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.take.set()
        self.release.set()
        self.thread.join(30)


# -- C2: the deadline bounds what follows the requests ---------------------------------------------------


def test_c2_the_recovery_after_a_kill_ends_by_the_sessions_end_even_with_the_ledger_locked(
    tmp_path: Path,
) -> None:
    """A session whose request hangs is killed; another process then holds the ledger's lock. The supervisor's
    whole run, recovery included, must end by the session's end, and say what it could not do."""
    manifest, out, path = campaign_files(tmp_path)
    with LockHolder(path) as holder:

        def hang_and_lock(conn: stub.Connection) -> None:
            holder.take.set()  # the request was sent: its row is marked sent; now the lock is held elsewhere
            stub.hang(conn)

        with stub.Stub(hang_and_lock) as s:
            t0 = time.monotonic()
            session = supervisor.run_session(
                drill(manifest, out, "loopback", str(s.port)),
                hard_end_s=12.0,
                manifest=manifest,
                out_dir=out,
                retailer="walmart",
                cwd=ROOT,
            )
            elapsed = time.monotonic() - t0
        assert holder.taken.is_set()
    assert session.killed
    assert elapsed < 12.0 + 3.0, elapsed  # the session's end, not the end plus a 30 s wait for the lock
    rec = session.recovery
    assert rec.get("completed") is False and "lock" in json.dumps(rec), rec
    # Nothing was decided about the row: it stays as the session left it, held, for the next recovery.
    led = ledger.open_from_manifest(manifest)
    try:
        [row] = led.rows()
        assert row["state"] == ledger.SENT and row["reserved_usd"] == "0.0040"
        assert led.recover() == 1 and led.rows()[0]["state"] == ledger.IN_FLIGHT_UNKNOWN
    finally:
        led.close()


class LockingReplay:
    """Answers each step from saved answers. When the first answer is returned, time has passed (the wall
    clock advances) and another connection holds the ledger's lock: the writes that follow must not wait past
    the session's end."""

    def __init__(self, clock: FakeClock, holder: LockHolder, advance_s: float) -> None:
        self.answers = {k: [ProviderResponse(s, b) for s, b in v] for k, v in fb.complete().items()}
        self.clock, self.holder, self.advance_s = clock, holder, advance_s
        self.sent = 0

    def send(self, request: ProviderRequest, allowance_s: float) -> ProviderResponse:
        self.sent += 1
        self.clock.advance(self.advance_s)
        self.holder.take.set()
        assert self.holder.taken.wait(10)
        return self.answers[request.step].pop(0)


def test_c2_the_writes_after_an_answer_wait_for_the_lock_no_longer_than_the_session_allows(
    tmp_path: Path, clock: FakeClock, card: money.RateCard
) -> None:
    path = tmp_path / "ledger.sqlite3"
    limits = ledger.Limits(campaign_minutes=1, export_reserve_seconds=50)
    led = ledger.Ledger.create(path, "c2-lock", limits, offline=True, clock=clock)
    genesis = led.genesis_id
    try:
        with LockHolder(path) as holder:
            tr = LockingReplay(clock, holder, advance_s=40.0)  # 20 s of the session are left after the answer
            run = campaign.Campaign(led, tr, WALMART, card, out_dir=tmp_path / "out", request_timeout_s=5.0)
            t0 = time.monotonic()
            result = run.run()
            elapsed = time.monotonic() - t0
        assert tr.sent == 1
        assert elapsed < 12.0, (
            elapsed
        )  # 1.7.0: 30 s for the capture's index, 30 s for the settlement, then raised
        assert result.stop is not None
        # The answer is on disk (kept and described) even though the ledger could not index it in time.
        kept = sorted(p.name for p in (tmp_path / "out").glob("response_*"))
        assert kept == ["response_001.json.gz", "response_001.meta.json"], kept
        assert (tmp_path / "out" / "campaign_evidence.json").is_file()
    finally:
        led.close()
    # A later recovery (the lock is free again) indexes it, and the row's money stays held.
    led = ledger.Ledger.open(path, campaign_id="c2-lock", genesis_id=genesis, clock=clock)
    try:
        store = captures.CaptureStore(tmp_path / "out", "walmart")
        found = store.recover(led)
        assert found["indexed_on_recovery"] == [1]
        led.recover()
        assert led.rows()[0]["state"] == ledger.IN_FLIGHT_UNKNOWN
    finally:
        led.close()


def test_c2_a_session_that_cannot_be_reaped_after_its_kill_is_still_recovered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """1.7.2: the supervisor waits for the session with ``Popen.wait`` (its output goes to a file, no longer a
    pipe read by ``communicate``), so the reap that does not end in time is made here at ``wait``: the first
    wait is the session's run, the second the reap after its kill."""
    manifest, out, _ = campaign_files(tmp_path)
    real = subprocess.Popen.wait
    sleeper = [sys.executable, "-c", "import time; time.sleep(60)"]
    calls: list[float | None] = []

    def wait(self: subprocess.Popen[bytes], timeout: float | None = None) -> Any:
        if list(self.args) == sleeper:
            calls.append(timeout)
            if len(calls) == 2:  # the reap after the kill: the process does not go away in time
                raise subprocess.TimeoutExpired(self.args, timeout or 0.0)
        return real(self, timeout)

    monkeypatch.setattr(subprocess.Popen, "wait", wait)
    session = supervisor.run_session(
        sleeper, hard_end_s=6.0, manifest=manifest, out_dir=out, retailer="walmart", cwd=ROOT
    )
    assert session.killed and len(calls) == 2
    assert session.recovery.get("manifest") == "campaign_evidence.recovered.json", session.recovery
    assert (out / "campaign_evidence.recovered.json").is_file()


# -- C4: what reached the disk survives a crash ----------------------------------------------------------


def test_c4_an_answer_received_before_a_crash_is_kept_without_a_paid_refetch(tmp_path: Path) -> None:
    """The isolated worker received the answer and wrote it; the session died before keeping its copy. The
    recovery must keep it from what is on disk: the answer was paid for and is not lost."""
    manifest, out, _ = campaign_files(tmp_path)
    body = fb.complete()["walmart-search-p1"][0][1]
    with stub.Stub(stub.respond(200, body)) as s:
        done = subprocess.run(
            drill(manifest, out, "loopback-crash-after-send", str(s.port)),
            cwd=ROOT,
            capture_output=True,
            timeout=120,
            check=False,
        )
        assert len(s.connections) == 1
    assert done.returncode == 23, done.stderr[-2000:]
    recovery = supervisor.recover_session(manifest, out, "walmart", reason="test: crash after send")
    assert recovery["capture_recovery"]["indexed_on_recovery"] == [1], recovery
    led = ledger.open_from_manifest(manifest)
    try:
        [capture] = led.captures()
        assert capture["original_sha256"] == hashlib.sha256(body).hexdigest()
        assert capture["truncated"] == 0
        assert led.rows()[0]["state"] == ledger.IN_FLIGHT_UNKNOWN  # its charge stays held: never assumed
    finally:
        led.close()
    recovered = json.loads((out / "campaign_evidence.recovered.json").read_text("utf-8"))
    assert [r["verified"] for r in recovered["responses"]] == [True]


def test_c4_the_evidence_manifest_is_synced_before_it_is_renamed_into_place(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    order: list[str] = []
    real_fsync = os.fsync

    def fsync(fd: int) -> None:
        order.append("fsync")
        real_fsync(fd)

    monkeypatch.setattr(os, "fsync", fsync)
    campaign.write_json(tmp_path / "campaign_evidence.json", {"x": 1})
    assert order, "the evidence manifest was renamed into place without ever being synced"
    assert json.loads((tmp_path / "campaign_evidence.json").read_text("utf-8")) == {"x": 1}
    assert not list(tmp_path.glob("*.part"))


@pytest.mark.skipif(
    sys.platform != "win32", reason="the write-through rename is the Windows form of a synced rename"
)
def test_c4_on_windows_a_kept_file_is_renamed_through_to_the_disk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ctypes

    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    real = kernel32.MoveFileExW
    flags_seen: list[int] = []

    def move(src: str, dst: str, flags: int) -> int:
        flags_seen.append(int(flags))
        return int(real(src, dst, flags))

    monkeypatch.setattr(kernel32, "MoveFileExW", move)
    captures.atomic_write(tmp_path / "x.json", b"{}")
    MOVEFILE_REPLACE_EXISTING, MOVEFILE_WRITE_THROUGH = 0x1, 0x8
    assert (
        flags_seen and flags_seen[-1] & MOVEFILE_WRITE_THROUGH and flags_seen[-1] & MOVEFILE_REPLACE_EXISTING
    )
    assert (tmp_path / "x.json").read_bytes() == b"{}"


def test_c4_a_body_cut_at_its_deadline_is_recorded_as_partial_never_as_an_answer(
    tmp_path: Path, make_ledger: Any, card: money.RateCard
) -> None:
    led = make_ledger()
    with stub.Stub(stub.drip(200_000, 0.01)) as s:
        tr = IsolatedHttpTransport(CREDS, work_dir=tmp_path / "work", loopback_port=s.port)
        run = campaign.Campaign(led, tr, WALMART, card, out_dir=tmp_path / "out", request_timeout_s=3.0)
        result = run.run()
    assert result.stop == "STOP_IN_FLIGHT_UNKNOWN"
    [row] = led.rows()
    assert row["state"] == ledger.IN_FLIGHT_UNKNOWN  # held: the provider may have charged it
    partial = [e for e in led.events() if e["kind"] == "PARTIAL_RESPONSE"]
    assert len(partial) == 1, led.events()
    detail = json.loads(partial[0]["detail"])
    assert detail["seq"] == 1 and detail["complete"] is False and detail["bytes"] > 0
    assert len(detail["sha256"]) == 64
    assert led.captures() == []  # a partial body is never indexed as an answer
