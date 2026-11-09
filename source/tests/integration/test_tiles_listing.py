"""Release 1.9.0rc2: a listing read through the tile Mariano's serves since 2026-11-06.

A fake Web API (an httpx mock transport, nothing leaves the process) answers for Cat Food (27021) at
Vernon Hills (53100502, PICKUP) with the REAL answers stage S1 saved on 2026-11-06
(tests/fixtures/oxylabs_2026-11-06, SOURCES_TILES.json): one the provider rendered (its answer states
``run_js: true``; it carries no product tile, while its page state lists 24 products) and one it did not
(24 tiles). In S1, release 1.9.0rc1 met the same pages and stopped the run as abnormal, permanently;
release 1.9.0rc2 asks for a rendered answer's page again and stops resumably only if the provider keeps
rendering it."""

from __future__ import annotations

import asyncio
import gzip
import json
from collections import Counter
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import Engine, select

from marianos_headless.collection.config import CollectionConfig, Limits
from marianos_headless.collection.nodes import Node
from marianos_headless.collection.oxylabs_live import OxylabsCollector
from marianos_headless.core.settings import (
    AcquisitionSettings,
    BrowserProvider,
    CoverageSettings,
    PrivateLabelConfig,
    Settings,
    load_stores,
)
from marianos_headless.db.models import (
    CategorySource,
    Event,
    ListingPage,
    ProductObservation,
    RecordRow,
    Run,
)
from marianos_headless.storage.local import LocalStorageAdapter
from marianos_headless.worker.pipeline import Pipeline
from tests import synthetic_marianos as syn
from tests.integration.helpers import seed
from tests.integration.test_oxylabs_collector import BASE, KEY, ROBOTS, _ceiling, _no_sleep

pytestmark = [pytest.mark.postgres]

ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / "tests" / "fixtures" / "oxylabs_2026-11-06"
SOURCES = json.loads((FIX / "SOURCES_TILES.json").read_text("utf-8"))
RENDERED, TILES = "s1_catfood_p1_rendered_nogrid.html.gz", "s1_catfood_p1_tiles.html.gz"
PET_SUPPLIES_ROW = 22  # "Pet Supplies", line 24 of config/Marianos_Category_URLs.csv


class FakeTilesApi:
    """Robots, a synthetic Coupons page, and the saved S1 answers for Cat Food page 1, in the given order (the
    last one again for any later request)."""

    def __init__(self, answers: list[str]) -> None:
        self.answers = list(answers)
        self.requests: list[dict[str, Any]] = []
        self.listing_answers: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == f"Bearer {KEY}"
        body = json.loads(request.content)
        self.requests.append({"path": request.url.path, **body})
        n = len(self.requests)
        url = body.get("url", "")
        meta: dict[str, Any] = {"status_code": 200}
        if url.endswith("/robots.txt"):
            assert "store_id" not in body
            html = ROBOTS
        else:
            assert body["store_id"] == "53100502" and body["fulfillment_type"] == "pickup"
            if "/savings/cl/coupons" in url:
                html = syn.coupons_page(1)
            elif "/pl/cat-food/27021" in url:
                name = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
                self.listing_answers.append(name)
                html = gzip.decompress((FIX / name).read_bytes()).decode("utf-8")
                meta = {"status_code": 200, "run_js": SOURCES[name]["provider_run_js"], "url": url, "page": 1}
            else:
                return httpx.Response(500, json={"detail": "REQUEST_FAILED_AFTER_TOO_MANY_RETRIES"})
        return httpx.Response(
            200,
            json={
                "status": "done",
                "results": [{"html": html, "metadata": meta}],
                "metadata": {"request_id": f"req-{n}", "timestamp": "2026-11-06T19:40:00Z"},
            },
        )


@pytest.fixture
def vh_env(migrated_engine: Engine, tmp_path: Path, private_label: PrivateLabelConfig) -> dict[str, Any]:
    factory, _ = seed(migrated_engine)
    store = next(
        s for s in load_stores(ROOT / "config" / "stores.yaml").stores if s.key == "marianos-53100502-pickup"
    )
    return {
        "engine": migrated_engine,
        "factory": factory,
        "storage": LocalStorageAdapter(tmp_path / "data"),
        "store": store,
        "private_label": private_label,
    }


def _run(
    env: dict[str, Any], settings: Settings, fake: FakeTilesApi, *, term_reads: int | None = None
) -> tuple[str, str]:
    # ``term_reads``: the product-page read for coupon terms on (``coverage.read_product_terms``), bounded.
    # The listing route with the shipped default: listing pages asked for without rendering.
    acq = AcquisitionSettings(browser_provider=BrowserProvider.OXYLABS)
    assert acq.oxylabs.listing_route == "listing" and acq.oxylabs.listing_run_js is False
    pipe = Pipeline(
        env["engine"],
        env["storage"],
        Settings(
            acquisition=acq,
            records=settings.records,
            attestation=settings.attestation,
            coverage=CoverageSettings(read_product_terms=term_reads is not None),
        ),
        env["store"],
        env["private_label"],
    )
    with env["factory"]() as s:
        ids = {c.csv_row_index: c.id for c in s.scalars(select(CategorySource))}
    nodes = [
        Node(
            PET_SUPPLIES_ROW,
            "Pet Supplies",
            ids[PET_SUPPLIES_ROW],
            "Cat Food",
            "27021",
            f"{BASE}/pl/cat-food/27021",
        )
    ]
    with env["factory"]() as s:
        run_id = pipe.create_live_run(
            s,
            nodes,
            trigger="console",
            snapshot={
                "plan": {"nodes": [n.as_dict() for n in nodes], "skipped": []},
                "started_by": "test",
                "provider": "oxylabs",
            },
        )
        s.commit()
    collector = OxylabsCollector(
        pipe,
        run_id,
        api_key=SecretStr(KEY),
        transport=httpx.MockTransport(fake),
        sleep=_no_sleep,
        config=CollectionConfig(limits=Limits(max_pages_per_listing=1, max_product_term_reads=term_reads)),
        trigger="manual",
    )
    status = asyncio.run(pipe.execute(run_id, "test-collector", resume=False, collector=collector))
    return run_id, status


def _listing_requests(fake: FakeTilesApi) -> list[dict[str, Any]]:
    return [r for r in fake.requests if "/pl/cat-food/27021" in r.get("url", "")]


def test_a_rendered_answer_without_tiles_is_asked_again_and_the_tiles_are_read(
    vh_env: dict[str, Any], settings: Settings
) -> None:
    _ceiling(vh_env["factory"], 20)
    fake = FakeTilesApi([RENDERED, TILES])
    run_id, status = _run(vh_env, settings, fake)
    # Every listing request asks for the page without rendering; the provider rendered the first one anyway.
    asked = _listing_requests(fake)
    assert len(asked) == 2 and all("run_js" not in r for r in asked)
    assert fake.listing_answers == [RENDERED, TILES]
    with vh_env["factory"]() as s:
        run = s.get(Run, run_id)
        assert run is not None and run.stop_code not in {"ABNORMAL_RESULT", "PROVIDER_ERROR"}
        pages = [
            (r.requested_page, r.state, r.verdict)
            for r in s.scalars(
                select(ListingPage)
                .where(ListingPage.run_id == run_id)
                .order_by(ListingPage.requested_page, ListingPage.attempt)
            )
        ]
        assert pages == [(1, "refused", "malformed"), (1, "completed", "new")]
        events = [
            e
            for e in s.scalars(select(Event).where(Event.run_id == run_id, Event.code == "PAGE_NOT_COUNTED"))
        ]
        assert len(events) == 1 and events[0].data["rendered"] is True
        assert "the page state lists 24 products and the grid shows 0 cards" in events[0].message
        assert "run_js true" in events[0].message
        recs = {r.upc: r for r in s.scalars(select(RecordRow).where(RecordRow.run_id == run_id))}
    assert len(recs) == 24
    friskies = recs["0005000057201"]
    assert friskies.status == "valid"
    assert (friskies.record["weight"], friskies.record["regular_price"], friskies.record["ppm"]) == (
        "5.5 oz.",
        "1.00",
        "$0.18/oz",
    )
    assert "SIZE_FROM_PRODUCT_DATA" in friskies.flags
    assert recs["0005000044569"].status == "eligible_unpriced"  # "Prices May Vary"
    assert status == "rejected"  # one page of ten read (the declared limit): never complete, never published


def test_a_provider_that_keeps_rendering_stops_the_run_resumably(
    vh_env: dict[str, Any], settings: Settings
) -> None:
    _ceiling(vh_env["factory"], 20)
    fake = FakeTilesApi([RENDERED])
    run_id, status = _run(vh_env, settings, fake)
    assert status == "interrupted"
    with vh_env["factory"]() as s:
        run = s.get(Run, run_id)
        assert run is not None and run.stop_code == "PROVIDER_ERROR"  # resumable, not ABNORMAL_RESULT
        rows = list(s.scalars(select(ListingPage).where(ListingPage.run_id == run_id)))
        assert [(r.requested_page, r.state, r.verdict) for r in rows] == [(1, "refused", "malformed")] * 3
        assert not list(s.scalars(select(RecordRow).where(RecordRow.run_id == run_id)))
    assert fake.listing_answers == [RENDERED] * 3


def test_with_the_terms_read_on_every_tile_is_a_candidate_and_an_unread_coupon_is_unknown(
    vh_env: dict[str, Any], settings: Settings
) -> None:
    """Release 1.9.0rc3. The S1 tiles show no coupon (tiles omit coupons a product's own page shows: stages
    O1 and O2). With ``coverage.read_product_terms`` on and a limit of two reads, the first two products'
    pages are asked for, rendered, and this fake brings neither (it answers 500 for a product page): every
    record says its coupon is unknown, none says the product has none, and none is invalid for it."""
    _ceiling(vh_env["factory"], 20)
    fake = FakeTilesApi([TILES])
    run_id, _ = _run(vh_env, settings, fake, term_reads=2)
    asked = [r for r in fake.requests if "/p/" in r.get("url", "")]
    assert len(asked) == 2 and all(r.get("run_js") is True for r in asked)
    with vh_env["factory"]() as s:
        recs = {r.upc: r for r in s.scalars(select(RecordRow).where(RecordRow.run_id == run_id))}
        terms = Counter(
            (o.provenance.get("coupon_terms") or {}).get("status")
            for o in s.scalars(select(ProductObservation).where(ProductObservation.run_id == run_id))
        )
    assert len(recs) == 24
    assert terms == Counter({"request_failed": 2, "unread_limit": 22})
    assert all("DIGITAL_COUPONS_UNOBSERVED" in r.flags for r in recs.values())
    friskies = recs["0005000057201"]
    assert friskies.status == "valid" and friskies.record["digital_deals_description"] == ""
