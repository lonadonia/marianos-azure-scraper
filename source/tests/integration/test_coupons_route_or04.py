"""OR-04 (release 1.10.0rc6): the Coupons row (CSV row 0) is read only when its list loaded, and its verdict
holds through the run: its retries, a restart, the coverage files, the checks and publication.

Seven of twelve runs before 1.10.0rc6 recorded the Coupons page as read with 0 coupons when its list had not
loaded. These tests serve, behind a fake Web API (an httpx mock transport, nothing leaves the process), the
REAL Coupons pages the collector stored on 2026-11-16 for Vernon Hills 53100502 Pickup
(``tests/fixtures/oxylabs_2026-11-16``: one loaded with 24 coupon cards, one rendered before its list
loaded), beside SYNTHETIC listing pages for the same store. A product page still loading (DERIVED from the
real rendered page of 0001780014939, stage O1, 2026-11-06) cannot prove that the product has no coupon.

Tests named ``test_or04_...`` fail on 1.10.0rc5; ``test_control_...`` hold before and after."""

from __future__ import annotations

import asyncio
import gzip
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import SecretStr
from selectolax.lexbor import LexborHTMLParser
from sqlalchemy import Engine, select

from marianos_headless.acquisition import oxylabs
from marianos_headless.collection import reconciliation
from marianos_headless.collection.config import CollectionConfig, Limits
from marianos_headless.collection.oxylabs_live import OxylabsCollector
from marianos_headless.core.settings import (
    AcquisitionSettings,
    BrowserProvider,
    OxylabsSettings,
    PrivateLabelConfig,
    Settings,
)
from marianos_headless.db.models import CategorySource, ProductObservation, RecordRow, Run, ValidationFinding
from marianos_headless.sites.marianos import pdp_savings
from marianos_headless.storage.local import LocalStorageAdapter
from marianos_headless.worker.pipeline import Pipeline
from tests.c1_site import target_store
from tests.integration import test_product_terms_collector as terms
from tests.integration.helpers import seed
from tests.listing_site import BASE, KEY, Site, plan_nodes, products

pytestmark = [pytest.mark.postgres]

FIX16 = Path(__file__).resolve().parents[1] / "fixtures" / "oxylabs_2026-11-16"
LOADED = gzip.decompress((FIX16 / "coupons_loaded_24_cards.html.gz").read_bytes()).decode("utf-8")
SPINNER = gzip.decompress((FIX16 / "coupons_not_loaded_spinner.html.gz").read_bytes()).decode("utf-8")
COUPONS_URL = f"{BASE}/savings/cl/coupons/"
# The Coupons row as the plan of a run of the client's whole list names it (1.10.0rc6: a route of the run).
ROUTE = {
    "row": 0,
    "category": "Coupons",
    "route": "coupons",
    "url": COUPONS_URL,
    "reason": "the coupons catalogue lists offers, not products: read as the run's Coupons route",
}
VH = {"name": "Marianos Vernon Hills", "addressLine1": "1720 N Milwaukee Ave", "zip": "60061"}


async def _no_sleep(_: float) -> None:
    return None


@pytest.fixture
def env(migrated_engine: Engine, tmp_path: Path, private_label: PrivateLabelConfig) -> dict[str, Any]:
    factory, _ = seed(migrated_engine)
    with factory() as s:
        oxylabs.set_ceiling(s, submissions=400, usd=10, actor="test", reason="test")
        s.commit()
    return {
        "engine": migrated_engine,
        "factory": factory,
        "storage": LocalStorageAdapter(tmp_path / "data"),
        "store": target_store(),
        "private_label": private_label,
        "tmp": tmp_path,
    }


def _site(coupons: list[str]) -> Site:
    return Site(
        {"03001": products(48)},
        location_id="53100502",
        fulfillment="pickup",
        modality="PICKUP",
        address=VH,
        coupons=coupons,
    )


def _pipe(env: dict[str, Any], settings: Settings) -> Pipeline:
    acq = AcquisitionSettings(browser_provider=BrowserProvider.OXYLABS, oxylabs=OxylabsSettings())
    return Pipeline(
        env["engine"],
        env["storage"],
        Settings(acquisition=acq, records=settings.records, attestation=settings.attestation),
        env["store"],
        env["private_label"],
    )


def _run(
    env: dict[str, Any], settings: Settings, site: Site, *, run_id: str | None = None
) -> tuple[str, str]:
    pipe = _pipe(env, settings)
    resume = run_id is not None
    if run_id is None:
        with env["factory"]() as s:
            ids = {c.csv_row_index: c.id for c in s.scalars(select(CategorySource))}
        nodes = plan_nodes(ids, ("03001",))
        with env["factory"]() as s:
            run_id = pipe.create_live_run(
                s,
                nodes,
                trigger="console",
                snapshot={
                    "plan": {"nodes": [n.as_dict() for n in nodes], "skipped": [ROUTE]},
                    "started_by": "test",
                    "provider": "oxylabs",
                },
            )
            s.commit()
    collector = OxylabsCollector(
        pipe,
        run_id,
        api_key=SecretStr(KEY),
        transport=httpx.MockTransport(site),
        sleep=_no_sleep,
        config=CollectionConfig(limits=Limits()),
        trigger="manual",
    )
    status = asyncio.run(pipe.execute(run_id, "test-collector", resume=resume, collector=collector))
    return run_id, str(status)


def _row0(env: dict[str, Any], run_id: str) -> dict[str, Any]:
    with env["factory"]() as s:
        report = reconciliation.reconciliation(s, run_id)
    return next(r for r in report["rows"] if r["csv_row"] == 0)


def test_control_a_coupons_page_whose_list_loaded_is_read_with_its_cards(
    env: dict[str, Any], settings: Settings
) -> None:
    """Before and after 1.10.0rc6: the loaded page is read once, with its 24 coupon cards, and the run of a
    complete listing is validated."""
    site = _site([LOADED])
    run_id, status = _run(env, settings, site)
    assert status == "validated" and site.coupons_asked == 1
    with env["factory"]() as s:
        run = s.get(Run, run_id)
        assert run is not None
        route = run.counts["coupons_route"]
        assert route["status"] == "READ" and route["coupon_cards"] == 24 and route["store_check"] == "PASS"
        assert run.counts["collection_complete"] is True


def test_or04_a_coupons_page_whose_list_never_loads_is_not_read_and_keeps_the_run_from_complete(
    env: dict[str, Any], settings: Settings
) -> None:
    """Expected to FAIL on 1.10.0rc5 (it records the page as read with 0 coupons and validates the run). The
    page is asked within its bounds (four answers), each kept with its reading; the route stays unread; the
    listing is complete, but the run is not: G3 fails on the Coupons row, the dataset is partial, the coverage
    file says why, and nothing is published."""
    site = _site([SPINNER])
    run_id, status = _run(env, settings, site)
    assert site.coupons_asked == 4
    with env["factory"]() as s:
        run = s.get(Run, run_id)
        assert run is not None
        route = run.counts["coupons_route"]
        assert route["status"].startswith("NOT READ") and "had not loaded" in route["status"], route["status"]
        assert (
            route["list_state"] == "not_loaded" and route["coupon_cards"] == 0 and route["mandatory"] is True
        )
        assert [a["list_state"] for a in route["attempts"]] == ["not_loaded"] * 4
        assert all(a["store_check"] == "PASS" and a["fetch_id"] for a in route["attempts"])
        assert run.counts["nodes"] == {"DONE": 1}  # the listing itself was read to its end
        assert run.counts["collection_complete"] is False
        assert status == "rejected" and run.counts["gates"]["G3"] == "FAIL"
        g3 = [
            f
            for f in s.scalars(select(ValidationFinding).where(ValidationFinding.run_id == run_id))
            if f.gate == "G3"
        ]
        assert [(f.ref, f.severity) for f in g3] == [("Coupons", "FAIL")], [(f.ref, f.message) for f in g3]
        assert _pipe(env, settings).dataset_label(run) == "partial"
    row0 = _row0(env, run_id)
    assert row0["status"] == "NOT_READ" and "had not loaded" in row0["completion_reason"], row0
    assert not (env["tmp"] / "data" / "published").exists()


def test_or04_a_coupons_page_loaded_on_a_later_answer_is_read_and_the_run_is_complete(
    env: dict[str, Any], settings: Settings
) -> None:
    """Expected to FAIL on 1.10.0rc5 (it takes the first answer, not loaded, as read with 0 coupons and never
    asks again). The first answer is kept as not loaded; the page is asked again after the listings; the
    loaded answer is read with its 24 cards and the count the page states."""
    site = _site([SPINNER, LOADED])
    run_id, status = _run(env, settings, site)
    assert site.coupons_asked == 2
    with env["factory"]() as s:
        run = s.get(Run, run_id)
        assert run is not None
        route = run.counts["coupons_route"]
        assert route["status"] == "READ" and route["list_state"] == "loaded_with_cards"
        assert (route["coupon_cards"], route["count_stated"]) == (24, 450)
        assert [a["list_state"] for a in route["attempts"]] == ["not_loaded", "loaded_with_cards"]
        assert route["fetch_id"] == route["attempts"][-1]["fetch_id"]
        assert status == "validated" and run.counts["collection_complete"] is True
        assert run.counts["gates"]["G3"] == "PASS"
    row0 = _row0(env, run_id)
    assert row0["status"] == "COMPLETE" and "24 coupon card" in row0["completion_reason"], row0
    manifest = json.loads(
        (env["tmp"] / "data" / "runs" / env["store"].key / run_id / "exports" / "manifest.json").read_bytes()
    )
    assert manifest["routes"]["coupons"]["status"] == "READ" and manifest["routes"]["coupons"]["answers"] == 2


def test_or04_the_coupons_verdict_and_its_answers_are_kept_across_a_restart(
    env: dict[str, Any], settings: Settings
) -> None:
    """Expected to FAIL on 1.10.0rc5 (the first answer, not loaded, is recorded as read). A run stopped
    (resumably) after the Coupons page came back unloaded keeps that answer; its resume asks the page again
    once, reads the loaded answer and completes; the listing pages already held are not asked again."""
    first = _site([SPINNER])
    first.on("03001", 2, *["fail"] * 40)
    run_id, status = _run(env, settings, first)
    assert status == "interrupted" and first.coupons_asked == 1
    with env["factory"]() as s:
        run = s.get(Run, run_id)
        assert run is not None and run.stop_code == "PROVIDER_ERROR"
        route = run.counts["coupons_route"]
        assert route["status"].startswith("NOT READ") and len(route["attempts"]) == 1
    again = _site([LOADED])
    _, status = _run(env, settings, again, run_id=run_id)
    assert status == "validated" and again.coupons_asked == 1
    assert ("03001", 1) not in again.asked
    with env["factory"]() as s:
        run = s.get(Run, run_id)
        assert run is not None
        route = run.counts["coupons_route"]
        assert route["status"] == "READ"
        assert [a["list_state"] for a in route["attempts"]] == ["not_loaded", "loaded_with_cards"]
        assert run.counts["collection_complete"] is True


def _loading_pdp() -> str:
    """DERIVED from the real rendered product page of 0001780014939: its Savings section replaced by the
    site's loading indicator."""
    html = gzip.decompress((terms.FIX / "pdp_0001780014939_rendered.html.gz").read_bytes()).decode("utf-8")
    tree = LexborHTMLParser(html)
    section = tree.css_first(pdp_savings.SECTION)
    assert section is not None
    indicator = (
        '<div data-citrus-component="LoadingIndicator" role="status" class="citrus-LoadingIndicator"></div>'
    )
    return (tree.html or "").replace(section.html or "", indicator, 1)


class _LoadingProductPage(terms.FakeTermsApi):
    """The product page of 0001780014939 answered rendered (the provider states run_js) but still loading."""

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        url = body.get("url", "")
        if "/p/" in url and url.endswith(terms.PURINA.upc):
            self.requests.append({"path": request.url.path, **body})
            meta = {"page": 1, "run_js": True, "url": url, "statuses": {"http_request": {"code": 200}}}
            return httpx.Response(
                200,
                json={
                    "status": "done",
                    "results": [{"html": _loading_pdp(), "metadata": meta}],
                    "metadata": {"request_id": "req-loading", "timestamp": "2026-11-06T18:30:00Z"},
                },
            )
        return super().__call__(request)


def test_or04_a_product_page_still_loading_leaves_the_coupon_unread_not_in_conflict(
    env: dict[str, Any], settings: Settings
) -> None:
    """Expected to FAIL on 1.10.0rc5 (a rendered page that shows no coupon is a conflict with the card). The
    product page was still loading: its coupons are unread, the record keeps the card's headline flagged
    DIGITAL_TERMS_UNREAD, and no conflict is recorded."""
    vh_env = env  # Vernon Hills 53100502 Pickup, as the product pages were read
    terms._ceiling(vh_env["factory"], 20)
    fake = _LoadingProductPage()
    run_id = terms._run(vh_env, settings, fake, read=True, limits=Limits(max_product_term_reads=1))
    assert terms._product_pages(fake) == [terms.PURINA.upc]
    with vh_env["factory"]() as s:
        obs = {
            o.upc: o.provenance
            for o in s.scalars(select(ProductObservation).where(ProductObservation.run_id == run_id))
        }
        read = obs[terms.PURINA.upc]["coupon_terms"]
        assert read["status"] == "unread_loading" and "loading indicator" in read["reason"], read
        rec = next(
            r
            for r in s.scalars(select(RecordRow).where(RecordRow.run_id == run_id))
            if r.upc == terms.PURINA.upc
        )
        assert "DIGITAL_TERMS_UNREAD" in rec.flags and "DIGITAL_TERMS_CONFLICT" not in rec.flags
