"""Real Oxylabs Web API pages replayed through the Oxylabs collector (release 1.3.0).

FIXTURE (tests/fixtures/oxylabs_2026-10-28, captured live by the P3 probes of 2026-10-28, replayed
offline): the search page for "cereal" (store 53100503, In Store), the Coupons page (rendered with run_js)
and robots.txt, all fetched through the Oxylabs Web API. Nothing here is a live run: a mock transport
serves the saved pages."""

from __future__ import annotations

import asyncio
import gzip
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from marianos_headless.acquisition import oxylabs
from marianos_headless.collection.config import CollectionConfig
from marianos_headless.collection.nodes import Node
from marianos_headless.collection.oxylabs_live import OxylabsCollector
from marianos_headless.core.settings import (
    AcquisitionSettings,
    BrowserProvider,
    OxylabsSettings,
    PrivateLabelConfig,
    Settings,
    StoreConfig,
)
from marianos_headless.db.models import (
    CategorySource,
    CollectionSegment,
    MembershipRow,
    NodeCoverage,
    ProductObservation,
    RecordRow,
    Run,
    StoreAttestation,
)
from marianos_headless.storage.local import LocalStorageAdapter
from marianos_headless.worker.pipeline import Pipeline
from tests.integration.helpers import seed

pytestmark = [pytest.mark.postgres]

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "oxylabs_2026-10-28"
KEY = "oxy-replay-key-never-sent-0123456789"
BASE = "https://www.marianos.com"


def _pages() -> dict[str, str]:
    return {
        "search": gzip.decompress((FIX / "search_cereal.html.gz").read_bytes()).decode("utf-8"),
        "coupons": gzip.decompress((FIX / "coupons_run_js.html.gz").read_bytes()).decode("utf-8"),
        "robots": (FIX / "robots.txt").read_text(encoding="utf-8"),
    }


class Replay:
    def __init__(self) -> None:
        self.pages = _pages()
        self.requests: list[dict[str, Any]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append(body)
        if request.url.path.endswith("/search"):
            html = self.pages["search"]
        elif body["url"].endswith("/robots.txt"):
            html = self.pages["robots"]
        else:
            html = self.pages["coupons"]
        return httpx.Response(
            200,
            json={
                "status": "done",
                "results": [{"html": html, "metadata": {"status_code": 200}}],
                "metadata": {"request_id": f"replay-{len(self.requests)}"},
            },
        )


@pytest.fixture
def run(
    migrated_engine: Engine,
    tmp_path: Path,
    dev_store: StoreConfig,
    private_label: PrivateLabelConfig,
    settings: Settings,
) -> tuple[sessionmaker[Session], str, str, Replay]:
    factory, _ = seed(migrated_engine)
    with factory() as s:
        ids = {c.csv_row_index: c.id for c in s.scalars(select(CategorySource))}
        oxylabs.set_ceiling(s, submissions=10, usd=1, actor="test", reason="replay")
        s.commit()
    nodes = [
        Node(12, "Breakfast", ids[12], "Cereal & Granola", "03001", f"{BASE}/pl/cereal-granola/03001"),
        Node(12, "Breakfast", ids[12], "Bars & Toaster Pastries", "03002", f"{BASE}/pl/bars/03002"),
    ]
    pipe = Pipeline(
        migrated_engine,
        LocalStorageAdapter(tmp_path / "data"),
        Settings(
            # This capture is store 53100503, In Store, where the provider refused /pl/ pages: the search
            # route.
            acquisition=AcquisitionSettings(
                browser_provider=BrowserProvider.OXYLABS, oxylabs=OxylabsSettings(listing_route="search")
            ),
            records=settings.records,
            attestation=settings.attestation,
        ),
        dev_store,
        private_label,
    )
    with factory() as s:
        run_id = pipe.create_live_run(
            s,
            nodes[:1],
            trigger="console",
            snapshot={
                "plan": {"nodes": [n.as_dict() for n in nodes[:1]], "skipped": []},
                "provider": "oxylabs",
            },
        )
        s.commit()
    replay = Replay()
    collector = OxylabsCollector(
        pipe,
        run_id,
        api_key=SecretStr(KEY),
        transport=httpx.MockTransport(replay),
        sleep=lambda _: asyncio.sleep(0),
        config=CollectionConfig(),
        trigger="manual",
    )
    status = asyncio.run(pipe.execute(run_id, "replay", collector=collector))
    return factory, run_id, status, replay


def test_the_real_search_page_is_verified_for_the_store_and_its_cards_recorded(
    run: tuple[sessionmaker[Session], str, str, Replay],
) -> None:
    factory, run_id, status, replay = run
    # robots.txt, the search page, the Coupons page (rendered): three submissions.
    assert [b.get("query") or b.get("url") for b in replay.requests] == [
        f"{BASE}/robots.txt",
        "Cereal & Granola",
        f"{BASE}/savings/cl/coupons/",
    ]
    assert replay.requests[2]["run_js"] is True
    assert status == "rejected"  # a first page of a search is never a complete listing
    with factory() as s:
        r = s.get(Run, run_id)
        assert r is not None and r.counts["gates"]["G1"] == "PASS" and r.counts["gates"]["G3"] == "FAIL"
        assert r.counts["canary"]["status"] == "passed"
        assert r.counts["canary"]["source_check"] == {
            "records": 24,
            "mismatch": 0,
            "verified": 24,
            "unverified": 0,
        }
        route = r.counts["coupons_route"]
        assert route["status"] == "READ" and route["coupon_cards"] > 0 and route["products_listed"] is False
        recs = {x.upc: x for x in s.scalars(select(RecordRow).where(RecordRow.run_id == run_id))}
        assert len(recs) == 24 and {x.status for x in recs.values()} == {"valid"}
        puffs = recs["0001600012125"].record
        assert (puffs["regular_price"], puffs["sale_price"], puffs["ppm"], puffs["weight"]) == (
            "8.99",
            "6.99",
            "$0.24/each",  # exactly as the card shows it
            "29 oz",
        )
        assert recs["0002190845556"].record["sale_price"] == ""  # "Everyday Low Price": no discount
        obs = {
            o.upc: o.provenance
            for o in s.scalars(select(ProductObservation).where(ProductObservation.run_id == run_id))
        }
        placements = {u: p["membership"]["placement"] for u, p in obs.items()}
        assert {u for u, v in placements.items() if v == "sponsored"} == {"0088491212971", "0003000006322"}
        assert {p["membership"]["price_location"] for p in obs.values()} == {"53100503"}
        (cov,) = s.scalars(select(NodeCoverage).where(NodeCoverage.run_id == run_id))
        read = cov.partition["read"]
        assert cov.status == "INCOMPLETE" and cov.total_count is None
        assert (read["query_total"], read["query_available"], read["cards"], read["members"]) == (
            428,
            250,
            24,
            24,
        )
        atts = list(s.scalars(select(StoreAttestation).where(StoreAttestation.run_id == run_id)))
        assert {a.phase for a in atts} == {"preflight", "task_start", "final"}
        assert all(a.result == "PASS" for a in atts)


def test_every_placement_is_recorded(
    run: tuple[sessionmaker[Session], str, str, Replay],
) -> None:
    """Each placement is kept in ``memberships`` with its page, segment and time; the two sponsored products
    keep a sponsored placement."""
    factory, run_id, _, _ = run
    with factory() as s:
        rows = list(s.scalars(select(MembershipRow).where(MembershipRow.run_id == run_id)))
        assert len(rows) == 24 and {m.upc for m in rows} == {
            x.upc for x in s.scalars(select(RecordRow).where(RecordRow.run_id == run_id))
        }
        assert {m.upc for m in rows if m.placement == "sponsored"} == {"0088491212971", "0003000006322"}
        assert all(m.via == ("paid" if m.placement == "sponsored" else "organic") for m in rows)
        seg = s.scalar(select(CollectionSegment).where(CollectionSegment.run_id == run_id))
        assert seg is not None and seg.end_state == "ended"
        assert {m.segment_id for m in rows} == {seg.id}
        assert all(m.page_fetch_id and m.observed_at is not None for m in rows)
        assert {m.page_offset for m in rows} == {0}
