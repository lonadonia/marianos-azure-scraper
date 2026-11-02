"""Audited reprocessing of stored observations (release 1.5.0, brief §6B), on a throwaway PostgreSQL.

The source run is a SYNTHETIC Oxylabs run (the fake provider of test_oxylabs_collector; nothing leaves the
process). One of its records is then given the status an earlier release's withdrawn rule gave it (here:
excluded as RELATIVE_PRICE with an estimated price kept as the regular price), as the 1.3.5 run did to 74
products sold by weight. Reprocessing rebuilds it from the stored card, page and product data with the current
rules into a separate run, with the original observation time and crawl date; the source run is unchanged."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select

from marianos_headless import __version__
from marianos_headless.assembly.private_label import PrivateLabelDetector
from marianos_headless.collection import reprocess, retention
from marianos_headless.core.paths import PARSER_VERSION
from marianos_headless.core.settings import Settings
from marianos_headless.db.models import (
    Artifact,
    ProductObservation,
    RecordRow,
    Run,
    Store,
)
from marianos_headless.db.models import PageFetch as PageFetchRow
from tests.integration.helpers import new_run
from tests.integration.test_oxylabs_collector import CEREAL, FakeOxylabs, _ceiling, _run, env

pytestmark = [pytest.mark.postgres]
__all__ = ["env"]  # the fixture, imported for this module

CHEERIOS = CEREAL[0].upc


def _source(env: dict[str, Any], settings: Settings) -> tuple[str, str]:
    """A finished synthetic run, with Cheerios recorded as an earlier release's withdrawn rule recorded it."""
    _ceiling(env["factory"], 20)
    run_id, _ = _run(env, settings, FakeOxylabs())
    with env["factory"]() as s:
        rec = s.scalars(select(RecordRow).where(RecordRow.run_id == run_id, RecordRow.upc == CHEERIOS)).one()
        assert rec.status == "valid" and rec.record["regular_price"] == "4.99"
        rec.status, rec.reasons = "excluded", ["RELATIVE_PRICE"]
        rec.record = {**rec.record, "regular_price": "4.98"}
        s.commit()
        return run_id, rec.record_sha256


def _do(env: dict[str, Any], settings: Settings, source: str, upcs: list[str], **kw: Any) -> dict[str, Any]:
    with env["factory"]() as s:
        out = reprocess.reprocess(
            s,
            storage=env["storage"],
            settings=settings,
            store=env["store"],
            detector=PrivateLabelDetector(env["private_label"], settings.records.store_brand_positive_value),
            source_run=source,
            upcs=upcs,
            reason=kw.pop("reason", "test: a withdrawn rule"),
            actor="test",
            **kw,
        )
        s.commit()
        return out


def test_a_record_is_rebuilt_from_its_stored_inputs_with_its_original_date_and_an_audit_trail(
    env: dict[str, Any], settings: Settings
) -> None:
    source, source_sha = _source(env, settings)
    with env["factory"]() as s:
        runs_before = s.scalar(select(func.count()).select_from(Run))
        original = s.scalars(
            select(ProductObservation).where(
                ProductObservation.run_id == source, ProductObservation.upc == CHEERIOS
            )
        ).first()
        assert original is not None
    dry = _do(env, settings, source, [CHEERIOS], dry_run=True)
    assert dry["by_status"] == {"valid": 1} and "run_id" not in dry
    with env["factory"]() as s:
        assert s.scalar(select(func.count()).select_from(Run)) == runs_before  # a dry run writes nothing

    out = _do(env, settings, source, [CHEERIOS])
    item = out["items"][0]
    assert item["before"] == {"status": "excluded", "reasons": ["RELATIVE_PRICE"]}
    assert item["after"] == {"status": "valid", "reasons": []}
    assert item["changes"] == {"regular_price": {"before": "4.98", "after": "4.99"}}
    with env["factory"]() as s:
        run = s.get(Run, out["run_id"])
        assert run is not None and run.trigger == "reprocess" and run.status == "rejected"
        assert run.config_snapshot["reprocess"]["source_run"] == source
        # The release that ran it and the parser rules it applied, recorded apart (release 1.6.0rc2).
        code = run.config_snapshot["code"]
        assert code["version"] == __version__ and code["parser_version"] == PARSER_VERSION
        rec = s.scalars(select(RecordRow).where(RecordRow.run_id == run.id)).one()
        assert rec.status == "valid" and "REPROCESSED" in rec.flags
        audit = rec.provenance["_reprocessed"]
        assert audit["source_record_sha256"] == source_sha and audit["source_status"] == "excluded"
        assert audit["observed_at"] == original.observed_at.isoformat().replace("+00:00", "Z")
        assert rec.record["crawl_date"] == audit["crawl_date"]  # the original date, not today's
        assert audit["page"]["page_fetch_id"] == original.page_fetch_id
        assert all(r["body_sha256"] for r in audit["responses"])
        obs = s.scalars(select(ProductObservation).where(ProductObservation.run_id == run.id)).one()
        assert obs.observed_at == original.observed_at and obs.displayed == original.displayed
        # The source run is never modified.
        src = s.scalars(select(RecordRow).where(RecordRow.run_id == source, RecordRow.upc == CHEERIOS)).one()
        assert src.status == "excluded" and src.record["regular_price"] == "4.98"

        # The rebuilt record is the product's latest verified observation; a later run that does not observe
        # it carries it forward as historical, with the audit trail, never as fresh.
        store_id = run.store_id
        verified = retention.verified_local(s, store_id)[CHEERIOS]
        assert verified.run_id == run.id and verified.reprocessed is not None
        assert verified.reprocessed["source_run"] == source
        store = s.get(Store, store_id)
        assert store is not None
    later = new_run(env["factory"], store, status="running")
    with env["factory"]() as s:
        retention.carry_forward(
            s, later.id, store_id, datetime.now(UTC), max_age_days=None, run_complete=False
        )
        s.commit()
        carried = s.scalars(
            select(RecordRow).where(RecordRow.run_id == later.id, RecordRow.upc == CHEERIOS)
        ).one()
        assert carried.status == "historical" and "CARRIED_FORWARD" in carried.flags
        assert carried.provenance["historical"]["reprocessed"]["source_status"] == "excluded"


def test_a_stored_input_that_fails_its_check_refuses_the_whole_request(
    env: dict[str, Any], settings: Settings
) -> None:
    source, _ = _source(env, settings)
    with env["factory"]() as s:
        obs = s.scalars(
            select(ProductObservation).where(
                ProductObservation.run_id == source, ProductObservation.upc == CHEERIOS
            )
        ).first()
        assert obs is not None
        page = s.get(PageFetchRow, obs.page_fetch_id)
        assert page is not None
        art = s.get(Artifact, page.dom_artifact_id)
        assert art is not None
        runs_before = s.scalar(select(func.count()).select_from(Run))
    path = Path(env["storage"].root) / art.key
    stored = path.read_bytes()
    path.write_bytes(stored[:-1] + bytes([stored[-1] ^ 1]))  # one bit changed
    with pytest.raises(reprocess.ReprocessRefused, match="does not match its recorded SHA-256"):
        _do(env, settings, source, [CHEERIOS])
    path.write_bytes(stored)
    with env["factory"]() as s:
        assert s.scalar(select(func.count()).select_from(Run)) == runs_before


def test_requests_that_cannot_be_audited_are_refused(env: dict[str, Any], settings: Settings) -> None:
    source, _ = _source(env, settings)
    with pytest.raises(reprocess.ReprocessRefused, match="not recorded with an observation"):
        _do(env, settings, source, [CHEERIOS, "0000000000000"])
    with pytest.raises(reprocess.ReprocessRefused, match="a reason is required"):
        _do(env, settings, source, [CHEERIOS], reason=" ")
    with pytest.raises(reprocess.ReprocessRefused, match="is not a live run"):
        _do(env, settings, "01NOTARUN0000000000000000", [CHEERIOS])
    out = _do(env, settings, source, [CHEERIOS])
    with pytest.raises(reprocess.ReprocessRefused, match="is itself a reprocess run"):
        _do(env, settings, out["run_id"], [CHEERIOS])
