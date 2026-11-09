"""The session supervisor and crash recovery (1.7.0, findings C2 and C4). OFFLINE: the sessions are separate
processes; the only connection any of them makes is the isolated worker's, to a stub on 127.0.0.1."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from decimal import Decimal
from pathlib import Path

import pytest

from classic_probe import ledger, supervisor
from tests import loopback_stub as stub

ROOT = Path(__file__).resolve().parents[1]


def campaign_files(tmp_path: Path) -> tuple[Path, Path]:
    led = ledger.Ledger.create(tmp_path / "ledger.sqlite3", "drill", ledger.Limits(), offline=True)
    ledger.write_manifest(tmp_path / "manifest.json", led)
    led.close()
    return tmp_path / "manifest.json", tmp_path / "out"


def drill(manifest: Path, out: Path, mode: str, *extra: str) -> list[str]:
    return [sys.executable, "-m", "tests.session_drill", str(manifest), str(out), mode, *extra]


def test_a_session_past_its_hard_end_is_killed_with_its_worker_and_recovered(tmp_path: Path) -> None:
    manifest, out = campaign_files(tmp_path)
    with stub.Stub(stub.hang) as s:
        session = supervisor.run_session(
            drill(manifest, out, "loopback", str(s.port)),
            hard_end_s=6.0,
            manifest=manifest,
            out_dir=out,
            retailer="walmart",
            cwd=ROOT,
        )
        ended = time.monotonic()
        while s.connections and s.connections[0].closed_at is None and time.monotonic() - ended < 5:
            time.sleep(0.05)
        assert len(s.connections) == 1, session.stdout_tail
        closed_at = s.connections[0].closed_at
    assert session.killed and session.elapsed_s < 6.0 + 10
    # The worker (the session's child) went with it: its connection closed at the kill, not when the worker's
    # own 20 s allowance would have ended.
    assert closed_at is not None and closed_at - ended < 2.0
    assert session.recovery["rows_recovered_as_unknown"] == 1
    led = ledger.open_from_manifest(manifest)
    try:
        [row] = led.rows()
        assert row["state"] == ledger.IN_FLIGHT_UNKNOWN and row["reserved_usd"] == "0.0040"
    finally:
        led.close()
    recovered = json.loads((out / "campaign_evidence.recovered.json").read_text("utf-8"))
    assert recovered["complete"] is False and "hard end" in recovered["ended_by"]


def test_a_session_that_ends_by_itself_needs_no_recovery(tmp_path: Path) -> None:
    manifest, out = campaign_files(tmp_path)
    good = json.dumps({"results": [{"status_code": 200, "content": {}}]}).encode()
    with stub.Stub(stub.respond(200, good)) as s:
        session = supervisor.run_session(
            drill(manifest, out, "loopback", str(s.port)),
            hard_end_s=60.0,
            manifest=manifest,
            out_dir=out,
            retailer="walmart",
            cwd=ROOT,
        )
    assert not session.killed and session.returncode == 0 and session.recovery == {}, session.stdout_tail
    assert not (out / "campaign_evidence.recovered.json").exists()
    assert (out / "campaign_evidence.json").is_file()


@pytest.mark.parametrize(
    ("mode", "captured", "indexed_on_recovery"),
    [
        ("crash-after-reserve", 0, []),
        ("crash-after-send", 0, []),
        ("crash-after-capture-file", 1, [1]),
        ("crash-after-index", 1, []),
    ],
)
def test_a_crash_at_each_point_leaves_the_money_held_and_the_evidence_recoverable(
    tmp_path: Path, mode: str, captured: int, indexed_on_recovery: list[int]
) -> None:
    manifest, out = campaign_files(tmp_path)
    done = subprocess.run(drill(manifest, out, mode), cwd=ROOT, capture_output=True, timeout=120, check=False)
    assert done.returncode == 23, done.stderr[-2000:]
    out.mkdir(parents=True, exist_ok=True)
    (out / "response_009.json.gz.part").write_bytes(b"half a file")  # a write the crash cut short
    recovery = supervisor.recover_session(manifest, out, "walmart", reason=f"test: {mode}")
    assert recovery["rows_recovered_as_unknown"] == 1
    assert recovery["capture_recovery"]["indexed_on_recovery"] == indexed_on_recovery
    assert "response_009.json.gz.part" in recovery["capture_recovery"]["part_files_removed"]
    led = ledger.open_from_manifest(manifest)
    try:
        [row] = led.rows()
        assert row["state"] == ledger.IN_FLIGHT_UNKNOWN  # never assumed free: the reservation stays held
        assert led.totals().committed_usd == Decimal("0.0040")
        assert len(led.captures()) == captured
    finally:
        led.close()
    recovered = json.loads((out / "campaign_evidence.recovered.json").read_text("utf-8"))
    assert [r["verified"] for r in recovered["responses"]] == [True] * captured
    assert not list(out.glob("*.part"))
