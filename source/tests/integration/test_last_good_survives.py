"""A published last-good dataset against everything that must not replace it (release 1.8.0).

SYNTHETIC: every page comes from ``tests/listing_site.py`` through a mock transport and every failure is
injected, so nothing reaches a provider or a retailer. The publication target is each test's own throwaway
database and folder, never an operational dataset. The browser route's own version of these checks is
``test_publication_safety.py``.

Each test publishes a complete run first, hashes what is published (pointer, publication rows,
``latest.json``, the manifest, ``products.json``, the first run's observations and records), runs the failure,
tries to publish the result, and hashes again. ``test_control_...`` shows the same steps do replace the
dataset when nothing is wrong, so a survival here is a refusal and not a test that could not publish anyway.
With ``PUBLICATION_EVIDENCE_DIR`` set, each test writes its hashes there as JSON (labelled synthetic).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import func, select, update

from marianos_headless.collection import control, reconciliation
from marianos_headless.collection.config import CollectionConfig
from marianos_headless.collection.oxylabs_live import OxylabsCollector
from marianos_headless.core.ids import new_id
from marianos_headless.core.settings import Settings, load_stores
from marianos_headless.db.models import (
    Artifact,
    ExportRow,
    PageFetch,
    ProductObservation,
    Publication,
    PublicationPointer,
    RecordRow,
    Run,
    Store,
)
from marianos_headless.publishing.exports import record_sha256
from marianos_headless.publishing.publish import (
    PublicationRefused,
    latest_key,
    publish_run,
    sync_latest_json,
)
from marianos_headless.validation import gates
from tests.conftest import CONFIG, STORE_KEY
from tests.integration.helpers import new_run
from tests.integration.test_listing_pages import _no_sleep, _pipe, _plan, _run, env  # noqa: F401  (env is a fixture)
from tests.listing_site import KEY, Site, products

pytestmark = [pytest.mark.postgres]

LISTINGS = ("03001", "03002")
REASON = "synthetic test"


def _catalogue() -> dict[str, list[Any]]:
    return {"03001": products(60), "03002": products(30, "0003805")}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def snapshot(e: dict[str, Any], first_run: str) -> dict[str, Any]:
    with e["factory"]() as s:
        store = s.scalar(select(Store).where(Store.key == STORE_KEY))
        assert store is not None
        ptr = s.get(PublicationPointer, store.id)
        assert ptr is not None
        obs = sorted(
            (o.upc, o.observed_at.isoformat(), json.dumps(o.provenance, sort_keys=True, default=str))
            for o in s.scalars(select(ProductObservation).where(ProductObservation.run_id == first_run))
        )
        recs = sorted(
            (r.upc, r.status, r.record_sha256)
            for r in s.scalars(select(RecordRow).where(RecordRow.run_id == first_run))
        )
        state = {
            "publication_id": ptr.publication_id,
            "version": ptr.version,
            "publications": int(
                s.scalar(
                    select(func.count()).select_from(Publication).where(Publication.store_id == store.id)
                )
                or 0
            ),
        }
    storage = e["storage"]
    latest = storage.get_bytes(latest_key(STORE_KEY))
    body = json.loads(latest)
    manifest = storage.get_bytes(body["manifest_key"])
    products_file = storage.get_bytes(json.loads(manifest)["files"]["products.json"]["key"])
    assert _sha(manifest) == body["manifest_sha256"]
    return {
        **state,
        "published_run": body["run_id"],
        "latest_json_sha256": _sha(latest),
        "manifest_sha256": _sha(manifest),
        "products_sha256": _sha(products_file),
        "published_products": len(json.loads(products_file)),
        "first_run_observations": len(obs),
        "first_run_observations_sha256": _sha(json.dumps(obs).encode()),
        "first_run_records_sha256": _sha(json.dumps(recs).encode()),
    }


def _evidence(name: str, data: dict[str, Any]) -> None:
    out = os.environ.get("PUBLICATION_EVIDENCE_DIR")
    if out:
        Path(out).mkdir(parents=True, exist_ok=True)
        body = {"synthetic": True, "injected_failure": True, **data}
        (Path(out) / f"{name}.json").write_text(json.dumps(body, indent=1, default=str), encoding="utf-8")


@pytest.fixture
def first(env: dict[str, Any], settings: Settings) -> str:  # noqa: F811
    run_id, status = _run(env, settings, Site(_catalogue()), listings=LISTINGS)
    assert status == "validated"
    assert (
        publish_run(env["factory"], env["storage"], run_id, "test", warn_override_reason=REASON).version == 1
    )
    return run_id


def _finalize(env: dict[str, Any], settings: Settings, site: Site, run_id: str) -> str:  # noqa: F811
    """An operator closes the unfinished run: what it holds is checked and exported, no page is asked for."""
    asked = len(site.requests)
    with env["factory"]() as s:
        run = s.get(Run, run_id)
        assert run is not None
        control.prepare_finish(s, run)
        s.commit()
    pipe = _pipe(env, settings)
    collector = OxylabsCollector(
        pipe,
        run_id,
        api_key=SecretStr(KEY),
        transport=httpx.MockTransport(site),
        sleep=_no_sleep,
        config=CollectionConfig(),
        trigger="finish",
    )
    status = asyncio.run(pipe.execute(run_id, "finisher", resume=True, collector=collector))
    assert len(site.requests) == asked
    return status


def _attempt(env: dict[str, Any], run_id: str) -> str:  # noqa: F811
    """A publication asked for by hand, with a reason given: the same refusal as the automatic path."""
    with pytest.raises(PublicationRefused) as refused:
        publish_run(env["factory"], env["storage"], run_id, "operator", warn_override_reason=REASON)
    return str(refused.value)


def _prove(env: dict[str, Any], name: str, first_run: str, before: dict[str, Any], run_id: str) -> None:  # noqa: F811
    refusal = _attempt(env, run_id)
    after = snapshot(env, first_run)
    with env["factory"]() as s:
        run = s.get(Run, run_id)
        assert run is not None
        status, stop = run.status, run.stop_code
    _evidence(
        f"last_good_survives_{name}",
        {
            "scenario": name,
            "first_run": first_run,
            "second_run": run_id,
            "second_run_status": status,
            "second_run_stop_code": stop,
            "refusal": refusal,
            "before": before,
            "after": after,
            "unchanged": before == after,
        },
    )
    assert after == before


# Each fault is given to every request of that page: a fault that clears on the task's retry is not one (a
# retried
# page that then comes back properly is read, and the run rightly publishes). The status the run must reach
# first:
# interrupted (resumable, the page still unread, then closed by an operator) or rejected.
EVERY_TIME = 12
PAGE_FAULTS = {
    # incomplete coverage: a page never comes, or the listing ends short of what it reports
    "provider_failure_on_page_2": ("03002", 2, "fail", "interrupted"),
    "listing_ends_short": ("03002", 2, "empty", "rejected"),  # abnormal pages in a row stop the run
    # wrong context
    "wrong_store_on_page_2": ("03001", 2, "wrong_store", "rejected"),
    "wrong_fulfillment_on_page_2": ("03001", 2, "wrong_fulfillment", "rejected"),
    "wrong_listing_on_page_2": ("03001", 2, "wrong_listing", "rejected"),
    "wrong_page_number_on_page_2": ("03001", 2, "wrong_page", "rejected"),
    # repeated pages and silent blocking
    "page_2_repeats_page_1": ("03002", 2, "repeat", "rejected"),
    "page_2_reordered_repeat": ("03002", 2, "reorder", "rejected"),
    "silent_block_with_status_200": ("03002", 2, "blocked", "rejected"),
    "page_without_cards": ("03002", 2, "no_cards", "rejected"),
}


@pytest.mark.parametrize("name", PAGE_FAULTS)
def test_a_page_failure_never_replaces_the_last_good_dataset(
    env: dict[str, Any],  # noqa: F811
    settings: Settings,
    first: str,
    name: str,
) -> None:
    before = snapshot(env, first)
    listing, page, behaviour, expected = PAGE_FAULTS[name]
    site = Site(_catalogue())
    site.on(listing, page, *(behaviour,) * EVERY_TIME)
    run_id, status = _run(env, settings, site, listings=LISTINGS)
    assert status == expected
    if status == "interrupted":
        status = _finalize(env, settings, site, run_id)
    assert status != "published"
    assert snapshot(env, first) == before
    _prove(env, name, first, before, run_id)


@pytest.mark.parametrize("name", ["empty", "thin"])
def test_empty_or_thin_output_never_replaces_the_last_good_dataset(
    env: dict[str, Any],  # noqa: F811
    settings: Settings,
    first: str,
    name: str,
) -> None:
    before = snapshot(env, first)
    n = 0 if name == "empty" else 3
    site = Site({"03001": products(n), "03002": products(n, "0003805")})
    run_id, status = _run(env, settings, site, listings=LISTINGS)
    assert status != "published"
    with env["factory"]() as s:
        carried = s.scalar(
            select(func.count())
            .select_from(RecordRow)
            .where(RecordRow.run_id == run_id, RecordRow.status == "historical")
        )
    assert carried == 90 - 2 * n  # carried products fill the export; the run is refused all the same
    with env["factory"]() as s:
        sets = reconciliation.identity_sets(s, run_id)
    assert (sets["fresh_valid"], sets["carried_forward"], sets["retained_unique"]) == (2 * n, 90 - 2 * n, 90)
    assert sets["duplicates"] == 0 and sets["holds"] is True
    _prove(env, f"{name}_output", first, before, run_id)


def test_a_validation_error_never_replaces_the_last_good_dataset(
    env: dict[str, Any],  # noqa: F811
    settings: Settings,
    first: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = snapshot(env, first)
    monkeypatch.setattr(gates, "format_violations", lambda _record: ["injected format error"])  # G6, injected
    run_id, status = _run(env, settings, Site(_catalogue()), listings=LISTINGS)
    assert status == "rejected"
    _prove(env, "validation_error", first, before, run_id)


def test_an_export_changed_after_validation_never_replaces_the_last_good_dataset(
    env: dict[str, Any],  # noqa: F811
    settings: Settings,
    first: str,
) -> None:
    before = snapshot(env, first)
    run_id, status = _run(env, settings, Site(_catalogue()), listings=LISTINGS)
    assert status == "validated"
    key = _manifest_key(env, run_id)
    products_key = json.loads(env["storage"].get_bytes(key))["files"]["products.json"]["key"]
    (env["tmp"] / "data" / products_key).write_bytes(b"[]")  # injected: the file on disk, under the storage
    _prove(env, "export_changed_after_validation", first, before, run_id)


def _manifest_key(env: dict[str, Any], run_id: str) -> str:  # noqa: F811
    with env["factory"]() as s:
        key = s.scalar(
            select(Artifact.key)
            .join(ExportRow, ExportRow.artifact_id == Artifact.id)
            .where(ExportRow.run_id == run_id, ExportRow.kind == "manifest")
        )
    assert key is not None
    return str(key)


def _validated_second(env: dict[str, Any], settings: Settings) -> str:  # noqa: F811
    run_id, status = _run(env, settings, Site(_catalogue()), listings=LISTINGS)
    assert status == "validated"
    return run_id


def _carried_row(run_id: str, source_run: str, page: str | None) -> RecordRow:
    record = {"upc": "0009999999999", "product_title": "Injected", "category": "Breakfast"}
    return RecordRow(
        id=new_id(),
        run_id=run_id,
        mode="LIVE",
        upc="0009999999999",
        record=record,
        record_sha256=record_sha256(record),
        status="historical",
        reasons=["CARRIED_FORWARD"],
        flags=["CARRIED_FORWARD"],
        provenance={"historical": {"run_id": source_run, "page_fetch_id": page}},
    )


def _mark_run_fixture(env: dict[str, Any], settings: Settings, run_id: str, first_run: str) -> None:  # noqa: F811
    with env["factory"]() as s, s.begin():
        s.execute(update(Run).where(Run.id == run_id).values(mode="FIXTURE"))


def _mark_record_fixture(env: dict[str, Any], settings: Settings, run_id: str, first_run: str) -> None:  # noqa: F811
    with env["factory"]() as s, s.begin():
        row = s.scalars(select(RecordRow).where(RecordRow.run_id == run_id)).first()
        assert row is not None
        row.mode = "FIXTURE"


def _foreign_page(env: dict[str, Any], settings: Settings, run_id: str, first_run: str) -> None:  # noqa: F811
    with env["factory"]() as s, s.begin():
        page = s.scalars(select(PageFetch.id).where(PageFetch.run_id == first_run)).first()
        row = s.scalars(select(ProductObservation).where(ProductObservation.run_id == run_id)).first()
        assert row is not None and page is not None
        row.page_fetch_id = page


def _no_observation(env: dict[str, Any], settings: Settings, run_id: str, first_run: str) -> None:  # noqa: F811
    with env["factory"]() as s, s.begin():
        row = s.scalars(select(ProductObservation).where(ProductObservation.run_id == run_id)).first()
        assert row is not None
        s.delete(row)


def _other_store_carried(env: dict[str, Any], settings: Settings, run_id: str, first_run: str) -> None:  # noqa: F811
    with env["factory"]() as s:
        other = s.scalar(select(Store).where(Store.key == "marianos-53100502-pickup"))
    assert other is not None
    source = new_run(env["factory"], other)
    with env["factory"]() as s, s.begin():
        s.add(_carried_row(run_id, source.id, None))


def _fixture_carried(env: dict[str, Any], settings: Settings, run_id: str, first_run: str) -> None:  # noqa: F811
    with env["factory"]() as s:
        store = s.scalar(select(Store).where(Store.key == STORE_KEY))
    assert store is not None
    source = new_run(env["factory"], store)  # the collector creates LIVE runs only: the label is injected
    with env["factory"]() as s, s.begin():
        s.execute(update(Run).where(Run.id == source.id).values(mode="FIXTURE"))
        s.add(_carried_row(run_id, source.id, None))


LINEAGE = {
    "synthetic_run_marked_fixture": (_mark_run_fixture, "only LIVE runs"),
    "a_fixture_record_in_a_live_run": (_mark_record_fixture, "record marked FIXTURE"),
    "a_record_observed_on_another_runs_page": (_foreign_page, "observed on a page of another run"),
    "a_fresh_record_with_no_observation": (_no_observation, "no observation of this run"),
    "a_carried_record_of_another_store": (_other_store_carried, "from another store"),
    "a_carried_record_of_a_fixture_run": (_fixture_carried, "from a FIXTURE run"),
}


@pytest.mark.parametrize("name", LINEAGE)
def test_synthetic_or_mixed_lineage_never_replaces_the_last_good_dataset(
    env: dict[str, Any],  # noqa: F811
    settings: Settings,
    first: str,
    name: str,
) -> None:
    before = snapshot(env, first)
    run_id = _validated_second(env, settings)
    inject, message = LINEAGE[name]
    inject(env, settings, run_id, first)
    assert message in _attempt(env, run_id)
    _prove(env, name, first, before, run_id)


def _die_publishing(env: dict[str, Any], run_id: str, stage: str) -> None:  # noqa: F811
    root = Path(__file__).resolve().parents[2]
    args = {
        "publish": True,
        "stage": stage,
        "db": env["engine"].url.render_as_string(hide_password=False),
        "data": str(env["tmp"] / "data"),
        "run": run_id,
    }
    p = subprocess.run(
        [sys.executable, "-m", "tests.listing_site", json.dumps(args)],
        cwd=root,
        env=dict(os.environ),
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )
    assert p.returncode == 137, (p.returncode, p.stdout[-2000:], p.stderr[-2000:])


@pytest.mark.parametrize("stage", ["before_commit", "inside_commit"])
def test_a_publication_killed_before_it_commits_keeps_the_last_good_dataset_and_one_retry_publishes(
    env: dict[str, Any],  # noqa: F811
    settings: Settings,
    first: str,
    stage: str,
) -> None:
    before = snapshot(env, first)
    run_id = _validated_second(env, settings)
    _die_publishing(env, run_id, stage)
    middle = snapshot(env, first)
    assert middle == before
    with env["factory"]() as s:
        assert s.get(Run, run_id).status == "validated"  # type: ignore[union-attr]
    publish_run(env["factory"], env["storage"], run_id, "test", warn_override_reason=REASON)
    after = snapshot(env, first)
    _evidence(
        f"last_good_survives_killed_publication_{stage}",
        {
            "stage": stage,
            "before": before,
            "after_kill": middle,
            "after_retry": after,
            "real_process_kill": True,
        },
    )
    assert after["published_run"] == run_id and after["version"] == before["version"] + 1
    assert after["publications"] == before["publications"] + 1  # exactly one, no half and no duplicate
    assert after["first_run_observations_sha256"] == before["first_run_observations_sha256"]


def test_a_publication_killed_after_its_commit_is_finished_from_the_pointer_and_the_earlier_files_stay(
    env: dict[str, Any],  # noqa: F811
    settings: Settings,
    first: str,
) -> None:
    before = snapshot(env, first)
    run_id = _validated_second(env, settings)
    _die_publishing(env, run_id, "after_commit")
    stale = json.loads(env["storage"].get_bytes(latest_key(STORE_KEY)))
    assert stale["run_id"] == first  # the convenience file is behind: the database pointer is authoritative
    with env["factory"]() as s:
        store = s.scalar(select(Store).where(Store.key == STORE_KEY))
        assert store is not None and s.get(Run, run_id).status == "published"  # type: ignore[union-attr]
        store_id = store.id
    assert sync_latest_json(env["factory"], env["storage"], store_id)
    after = snapshot(env, first)
    assert after["published_run"] == run_id and after["publications"] == before["publications"] + 1
    assert after["first_run_observations_sha256"] == before["first_run_observations_sha256"]
    key = _manifest_key(env, first)
    assert _sha(env["storage"].get_bytes(key)) == before["manifest_sha256"]
    _evidence(
        "last_good_survives_killed_publication_after_commit",
        {
            "before": before,
            "stale_latest_run": stale["run_id"],
            "after_repair": after,
            "real_process_kill": True,
        },
    )


def test_control_the_same_steps_replace_the_dataset_when_nothing_is_wrong(
    env: dict[str, Any],  # noqa: F811
    settings: Settings,
    first: str,
) -> None:
    before = snapshot(env, first)
    run_id = _validated_second(env, settings)
    publish_run(env["factory"], env["storage"], run_id, "test", warn_override_reason=REASON)
    after = snapshot(env, first)
    assert after["published_run"] == run_id and after["latest_json_sha256"] != before["latest_json_sha256"]


# -- one store's assortment is not another's -----------------------------------------------------------------


def test_a_lakeshore_identity_never_enters_vernon_hills_and_each_store_keeps_its_own_dataset(
    env: dict[str, Any],  # noqa: F811
    settings: Settings,
    first: str,
) -> None:
    before = snapshot(env, first)
    vernon = next(
        s for s in load_stores(CONFIG / "stores.yaml").stores if s.key == "marianos-53100502-pickup"
    )
    other = {**env, "store": vernon}
    site = Site(
        {"03001": products(30, "0004400")},
        location_id="53100502",
        fulfillment="pickup",
        modality="PICKUP",
        address={
            "name": "Marianos Vernon Hills",
            "addressLine1": "1720 N Milwaukee Ave",
            "zip": "60061",
        },
    )
    run_id, status = _run(other, settings, site, listings=("03001",))
    assert status == "validated"
    with env["factory"]() as s:
        rows = list(s.scalars(select(RecordRow).where(RecordRow.run_id == run_id)))
    assert len(rows) == 30 and {r.status for r in rows} == {"valid"}
    assert all(r.upc.startswith("0004400") for r in rows)  # nothing of the other store was carried
    publish_run(env["factory"], env["storage"], run_id, "test", warn_override_reason=REASON)
    assert snapshot(env, first) == before  # the Lakeshore East dataset is untouched by Vernon Hills
