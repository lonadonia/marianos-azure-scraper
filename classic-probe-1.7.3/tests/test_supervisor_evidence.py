"""How the 1.7.2 supervisor reads a session's evidence, and how a recovery checks a raw answer's identity (the
client's review of 1.7.1, findings C2 and C4). OFFLINE: no connection is made, except the isolated worker's to
a stub on 127.0.0.1 in the last test."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from classic_probe import captures, supervisor
from classic_probe.supervisor import EvidenceRefused, read_bounded
from tests import fixture_builder as fb
from tests import loopback_stub as stub
from tests.test_c2_c4_reproduction import ROOT, campaign_files, drill
from tests.test_durable_evidence import STEP, raw_answer, sent_row


def ten() -> float:
    return 10.0


def test_a_regular_file_is_read_and_anything_else_is_refused_with_why(tmp_path: Path) -> None:
    f = tmp_path / "e.json"
    f.write_bytes(b'{"a": 1}')
    assert read_bounded(f, max_bytes=100, left=ten) == b'{"a": 1}'
    with pytest.raises(EvidenceRefused, match="does not exist"):
        read_bounded(tmp_path / "missing.json", max_bytes=100, left=ten)
    folder = tmp_path / "folder.json"
    folder.mkdir()
    with pytest.raises(EvidenceRefused, match="a directory"):
        read_bounded(folder, max_bytes=100, left=ten)
    with pytest.raises(EvidenceRefused, match="more than the 4 allowed"):
        read_bounded(f, max_bytes=4, left=ten)
    with pytest.raises(EvidenceRefused, match="time ran out"):
        read_bounded(f, max_bytes=100, left=lambda: 0.0)


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="Windows has no FIFO in its file system (see test_review_of_171.py); the refusal of a directory "
    "and of an oversized file above runs on Windows",
)
def test_a_fifo_is_refused_at_once_without_waiting_for_a_writer(tmp_path: Path) -> None:
    fifo = tmp_path / "campaign_evidence.json"
    os.mkfifo(fifo)
    t0 = time.monotonic()
    with pytest.raises(EvidenceRefused, match="a FIFO"):
        read_bounded(fifo, max_bytes=100, left=ten)
    assert time.monotonic() - t0 < 0.2


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="making a symbolic link on Windows needs a privilege a normal account lacks; Windows links are "
    "refused by the same lstat test",
)
def test_a_link_at_the_evidence_path_is_refused_even_to_a_complete_manifest(tmp_path: Path) -> None:
    real = tmp_path / "elsewhere.json"
    real.write_text('{"complete": true}', encoding="utf-8")
    link = tmp_path / "campaign_evidence.json"
    link.symlink_to(real)
    with pytest.raises(EvidenceRefused, match="a link"):
        read_bounded(link, max_bytes=100, left=ten)


def test_evidence_is_taken_only_when_it_names_this_execution_and_this_campaign_and_is_complete(
    tmp_path: Path,
) -> None:
    manifest, out, _ = campaign_files(tmp_path)
    ids = json.loads(manifest.read_text("utf-8"))
    out.mkdir()
    path = out / "campaign_evidence.json"

    def check(**changes: Any) -> tuple[bool, str]:
        data = {
            "campaign_id": ids["campaign_id"],
            "ledger_genesis_id": ids["ledger_genesis_id"],
            "execution_id": "run-2",
            "complete": True,
            **changes,
        }
        path.write_text(json.dumps(data), encoding="utf-8")
        return supervisor.evidence_of_this_execution(out, manifest, "run-2", ten)

    assert check() == (True, "campaign_evidence.json is this execution's own and complete")
    accepted, why = check(execution_id="run-1")
    assert not accepted and "not written by this execution" in why and "'run-1'" in why
    accepted, why = check(execution_id=None)
    assert not accepted and "not written by this execution" in why
    assert check(campaign_id="another")[0] is False
    assert check(ledger_genesis_id="another")[0] is False
    accepted, why = check(complete=False)
    assert not accepted and "not marked complete" in why
    path.write_text("[1, 2]", encoding="utf-8")
    assert supervisor.evidence_of_this_execution(out, manifest, "run-2", ten) == (
        False,
        "campaign_evidence.json: it is not a JSON object",
    )
    path.write_text("{not json", encoding="utf-8")
    assert supervisor.evidence_of_this_execution(out, manifest, "run-2", ten)[1].endswith("it is not JSON")


def test_a_session_is_given_its_execution_id_and_its_evidence_names_it(tmp_path: Path) -> None:
    manifest, out, _ = campaign_files(tmp_path)
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
    assert len(session.execution_id) == 32 and session.recovery == {}, session
    assert session.evidence == {
        "accepted": True,
        "why": "campaign_evidence.json is this execution's own and complete",
    }
    evidence = json.loads((out / "campaign_evidence.json").read_text("utf-8"))
    assert evidence["execution_id"] == session.execution_id
    assert session.tree["gone"] is True and session.tree["left_running"] is False, session.tree
    status = json.loads((out / "private" / "raw" / "dispatch_001.status.json").read_text("utf-8"))
    assert status["identity"]["seq"] == 1 and status["identity"]["campaign_id"] == evidence["campaign_id"]
    assert status["complete"] is True and status["declared_bytes"] == len(good)


def test_a_raw_answer_of_another_dispatch_or_without_an_identity_is_refused_and_left_as_found(
    make_ledger: Any, tmp_path: Path
) -> None:
    led = make_ledger()
    seq = sent_row(led)
    store = captures.CaptureStore(tmp_path / "out", "walmart")
    body = fb.complete()[STEP][0][1]
    stem = raw_answer(store, seq, body, renamed=True, led=led)
    status_path = stem.with_name(stem.name + ".status.json")
    status = json.loads(status_path.read_text("utf-8"))
    status["identity"]["campaign_id"] = "another-campaign"
    status["identity"]["attempt"] = 2
    status_path.write_text(json.dumps(status), encoding="utf-8")
    found = store.recover(led)
    assert found["kept_from_raw"] == [] and led.captures() == [], found
    assert found["refused"] == [
        {
            "file": status_path.name,
            "why": "its identity is not this dispatch's (campaign_id, attempt differ)",
        }
    ]
    del status["identity"]  # as a 1.7.1 worker wrote it
    status_path.write_text(json.dumps(status), encoding="utf-8")
    found = store.recover(led)
    assert found["kept_from_raw"] == [] and led.captures() == []
    assert "carries no dispatch identity" in found["refused"][0]["why"]
    assert stem.with_name(stem.name + ".body").read_bytes() == body  # never deleted


def test_a_partial_body_of_another_dispatch_is_not_recorded_as_this_ones(
    make_ledger: Any, tmp_path: Path
) -> None:
    led = make_ledger()
    seq = sent_row(led)
    store = captures.CaptureStore(tmp_path / "out", "walmart")
    stem = store.raw_stem(seq)
    stem.parent.mkdir(parents=True)
    stem.with_name(stem.name + ".partial").write_bytes(b'{"results": [')
    stem.with_name(stem.name + ".status.json").write_text(
        json.dumps(
            {
                "ok": False,
                "error": "IncompleteBody",
                "sent": True,
                "http_status": 200,
                "partial_bytes": 13,
                "partial_file": True,
                "identity": {"campaign_id": "another-campaign", "seq": seq},
            }
        ),
        encoding="utf-8",
    )
    found = store.recover(led)
    assert found["partial_recorded"] == [] and "not this dispatch's" in found["refused"][0]["why"], found
    assert [e for e in led.events() if e["kind"] == "PARTIAL_RESPONSE"] == []
