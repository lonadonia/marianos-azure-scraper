"""The paths of the 1.7.1 corrections (C2 and C4) that the reproductions do not reach on their own. OFFLINE:
the only connection made is a request worker's, to a stub on 127.0.0.1, and none is made in most tests."""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from classic_probe import campaign, captures, ledger, money, supervisor
from classic_probe.stops import Stop
from classic_probe.transport import IsolatedHttpTransport, ProviderRequest, TransportFailed, _keep_after_kill
from tests import fixture_builder as fb
from tests import loopback_stub as stub
from tests.conftest import FakeClock, reserve
from tests.test_c2_c4_reproduction import CREDS, ROOT, LockHolder, LockingReplay, campaign_files
from tests.test_campaign import WALMART

STEP = "walmart-search-p1"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sent_row(led: ledger.Ledger) -> int:
    seq = reserve(led, step=STEP)
    led.mark_sent(seq)
    return seq


def identity(led: ledger.Ledger, seq: int) -> dict[str, Any]:
    """The dispatch identity a 1.7.2 request worker writes into its status (the campaign gives it)."""
    row = next(r for r in led.rows() if r["seq"] == seq)
    return {
        "campaign_id": led.campaign_id,
        "ledger_genesis_id": led.genesis_id,
        "seq": seq,
        "step": row["step"],
        "attempt": row["attempt"],
        "payload_sha256": row["payload_sha256"],
    }


def raw_answer(
    store: captures.CaptureStore,
    seq: int,
    body: bytes,
    *,
    renamed: bool,
    led: ledger.Ledger,
    digest: str = "",
) -> Path:
    """What the request worker leaves on disk: the status, then the body under its final name (``renamed``)
    or still under its ``.part`` name (a crash between the two). 1.7.2: the status names its dispatch."""
    stem = store.raw_stem(seq)
    stem.parent.mkdir(parents=True, exist_ok=True)
    status = {
        "ok": True,
        "status": 200,
        "reason": "OK",
        "headers": [["Content-Type", "application/json"]],
        "body_bytes": len(body),
        "truncated": False,
        "sha256": digest or sha(body),
        "elapsed_s": 0.2,
        "redirect_location": None,
        "complete": True,
        "declared_bytes": len(body),
        "framing": "content-length",
        "identity": identity(led, seq),
    }
    stem.with_name(stem.name + ".status.json").write_text(json.dumps(status), encoding="utf-8")
    stem.with_name(stem.name + (".body" if renamed else ".body.part")).write_bytes(body)
    return stem


def test_an_answer_whose_worker_died_before_its_final_rename_is_kept_without_a_refetch(
    make_ledger: Any, tmp_path: Path
) -> None:
    led = make_ledger()
    seq = sent_row(led)
    store = captures.CaptureStore(tmp_path / "out", "walmart")
    body = fb.complete()[STEP][0][1]
    stem = raw_answer(store, seq, body, renamed=False, led=led)
    found = store.recover(led)
    assert found["kept_from_raw"] == [seq] and found["indexed_on_recovery"] == [seq], found
    assert stem.with_name(stem.name + ".body").read_bytes() == body  # renamed into place, never deleted
    assert not stem.with_name(stem.name + ".body.part").exists()
    [capture] = led.captures()
    assert capture["original_sha256"] == sha(body)
    again = store.recover(led)
    assert again["indexed_on_recovery"] == [] and again["kept_from_raw"] == []  # once


def test_a_raw_body_that_does_not_match_its_status_is_refused_and_never_indexed(
    make_ledger: Any, tmp_path: Path
) -> None:
    led = make_ledger()
    seq = sent_row(led)
    store = captures.CaptureStore(tmp_path / "out", "walmart")
    stem = raw_answer(store, seq, b'{"results": []}', renamed=True, led=led, digest="0" * 64)
    found = store.recover(led)
    assert found["indexed_on_recovery"] == [] and led.captures() == []
    assert found["refused"] == [{"file": stem.name + ".body", "why": "its body does not match its status"}]
    assert stem.with_name(stem.name + ".body").is_file()  # kept as it was found: evidence is never deleted


def test_a_partial_body_found_at_a_recovery_is_recorded_once_and_never_indexed(
    make_ledger: Any, tmp_path: Path
) -> None:
    led = make_ledger()
    seq = sent_row(led)
    store = captures.CaptureStore(tmp_path / "out", "walmart")
    stem = store.raw_stem(seq)
    stem.parent.mkdir(parents=True)
    stem.with_name(stem.name + ".partial").write_bytes(b'{"results": [{"conte')
    assert store.recover(led)["partial_recorded"] == [seq]
    assert store.recover(led)["partial_recorded"] == []  # a second recovery does not record it again
    [event] = [e for e in led.events() if e["kind"] == "PARTIAL_RESPONSE"]
    detail = json.loads(event["detail"])
    assert detail["seq"] == seq and detail["bytes"] == 20 and detail["complete"] is False
    assert detail["sha256"] == sha(b'{"results": [{"conte')
    assert led.captures() == []


def test_a_dispatch_name_is_used_once_and_its_files_are_never_overwritten(tmp_path: Path) -> None:
    stem = tmp_path / "private" / "raw" / "dispatch_001"
    stem.parent.mkdir(parents=True)
    stem.with_name(stem.name + ".body").write_bytes(b"an earlier answer")
    with stub.Stub(stub.respond(200, b"{}")) as s:
        tr = IsolatedHttpTransport(CREDS, work_dir=tmp_path / "work", loopback_port=s.port)
        with pytest.raises(TransportFailed) as err:
            tr.send(ProviderRequest(STEP, {"source": "walmart_search"}, raw_stem=str(stem)), 5.0)
        assert s.connections == []  # refused before anything was sent
    assert err.value.sent is False and "already exists" in str(err.value)
    assert stem.with_name(stem.name + ".body").read_bytes() == b"an earlier answer"


def test_a_body_cut_by_the_workers_kill_is_kept_as_partial_with_its_length_and_hash(tmp_path: Path) -> None:
    files = {
        "out_path": tmp_path / "dispatch_001.body.part",
        "final_path": tmp_path / "dispatch_001.body",
        "partial_path": tmp_path / "dispatch_001.partial",
        "status_path": tmp_path / "dispatch_001.status.json",
    }
    files["out_path"].write_bytes(b"0123456789")
    described = _keep_after_kill(files)
    assert described == {
        "bytes": 10,
        "sha256": sha(b"0123456789"),
        "http_status": None,
        "error": "Killed",
        "file": "dispatch_001.partial",
        "complete": False,
    }
    assert files["partial_path"].read_bytes() == b"0123456789" and not files["out_path"].exists()
    status = json.loads(files["status_path"].read_text("utf-8"))
    assert status["ok"] is False and status["partial_bytes"] == 10 and status["partial_file"] is True
    # nothing arrived: an empty file is not evidence, and nothing is described
    empty = {k: v.with_name("e_" + v.name) for k, v in files.items()}
    empty["out_path"].write_bytes(b"")
    assert _keep_after_kill(empty) is None and not empty["out_path"].exists()


def test_after_one_refusal_of_the_lock_the_session_does_not_wait_for_it_again(
    tmp_path: Path, clock: FakeClock, card: money.RateCard
) -> None:
    path = tmp_path / "ledger.sqlite3"
    led = ledger.Ledger.create(
        path,
        "c2-once",
        ledger.Limits(campaign_minutes=1, export_reserve_seconds=50),
        offline=True,
        clock=clock,
    )
    try:
        with LockHolder(path) as holder:
            run = campaign.Campaign(
                led,
                LockingReplay(clock, holder, advance_s=40.0),
                WALMART,
                card,
                out_dir=tmp_path / "out",
                request_timeout_s=5.0,
            )
            result = run.run()
    finally:
        led.close()
    assert result.stop == Stop.DEADLINE.value
    refused = [e for e in result.ledger_errors if e.startswith("capture 1:")]
    skipped = [e for e in result.ledger_errors if "not attempted" in e]
    assert len(refused) == 1 and skipped, result.ledger_errors
    evidence = json.loads((tmp_path / "out" / "campaign_evidence.json").read_text("utf-8"))
    assert evidence["complete"] is False
    assert [n["why"] for n in evidence["capture_recovery"]["not_reached"]] == [
        f"the ledger's write lock: {result.ledger_errors[0].split(': ', 1)[1]} (not waited for again)"
    ]


def test_a_session_that_exits_cleanly_without_its_evidence_is_recovered(tmp_path: Path) -> None:
    manifest, out, _ = campaign_files(tmp_path)
    session = supervisor.run_session(
        [sys.executable, "-c", "pass"],
        hard_end_s=30.0,
        manifest=manifest,
        out_dir=out,
        retailer="walmart",
        cwd=ROOT,
    )
    assert not session.killed and session.returncode == 0
    assert session.recovery["completed"] is True, session.recovery
    assert "without a complete evidence manifest" in session.recovery["ended_by"]
    assert (out / "campaign_evidence.recovered.json").is_file()


def test_a_recovery_that_overruns_is_killed_by_the_sessions_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The recovery is told it may run 30 s past the end, and the ledger's lock is held elsewhere: the
    supervisor still ends by the session's end, and says the recovery was killed."""
    manifest, out, path = campaign_files(tmp_path)
    monkeypatch.setattr(supervisor, "RECOVERY_MARGIN_S", -30.0)
    with LockHolder(path) as holder:
        holder.take.set()
        assert holder.taken.wait(10)
        t0 = time.monotonic()
        session = supervisor.run_session(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            hard_end_s=6.0,
            manifest=manifest,
            out_dir=out,
            retailer="walmart",
            cwd=ROOT,
        )
        elapsed = time.monotonic() - t0
    assert session.killed
    assert elapsed < 6.0 + 1.0, elapsed
    assert session.recovery["completed"] is False
    assert "killed" in " ".join(session.recovery["problems"]), session.recovery
