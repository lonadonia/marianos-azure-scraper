"""OR-24 (1.10.0rc6, run R7, 2026-11-17): two listing lanes share one collector, and what a listing page is
parsed into (its products' own taxonomies, their ranks, the sponsored placements, where each price comes from)
was kept on the collector itself. A lane that reads a named product's own page before building its page's
records waits for the provider, and the other lane parsed a page of its own meanwhile: the waiting page's
records were then built against the other page, and none of its products was kept while the page counted as
read. In R7, Dog Food 27017 page 7 (24 products, among them the named 0001780014939 and 0001780014941; the
other lane read Cat Food's page 2 between the two product pages) and Cat Treats 27022 page 2 (20 products,
with the named 0002310014848) were recorded with 0 products, and G3 found the two listings short (coverage
0.893 and 0.615). On the search route the page being recorded was exposed as well (it is set before the
product pages are read).

A fake Web API (an httpx mock transport, nothing leaves the process) answers a product page only once the
other lane's listing has been answered, which is the order R7 saw. SYNTHETIC listing pages
(``tests/listing_site.py``, the C1 site at Vernon Hills, Pickup) and search pages
(``test_product_terms_collector.py``, with the REAL product page saved by stage O1 on 2026-11-06).

Tests named ``test_or24_...`` fail on 1.10.0rc6."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import Engine, select

from marianos_headless.collection.config import Limits
from marianos_headless.core.settings import PrivateLabelConfig, Settings
from marianos_headless.db.models import ListingPage, NodeCoverage, ProductObservation, RecordRow
from tests import c1_site as c1
from tests.integration import test_product_terms_collector as terms
from tests.listing_site import products

pytestmark = pytest.mark.postgres

vh_env = terms.vh_env


class OtherLaneFirst:
    """The fake Web API ``site``, with each product page answered only once a request naming ``other`` (the
    other lane's listing or search) has been answered: by ``site`` itself when ``serve_product_pages``, else
    as a provider failure. ``waited`` says, for each product page, whether that happened within 10 seconds."""

    def __init__(self, site: Any, other: str, *, serve_product_pages: bool) -> None:
        self.site = site
        self.other = other
        self.serve_product_pages = serve_product_pages
        self.other_answered = asyncio.Event()
        self.waited: list[bool] = []

    @property
    def requests(self) -> list[dict[str, Any]]:
        return list(self.site.requests)

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        url = body.get("url", "")
        if "/p/" in url:
            try:
                await asyncio.wait_for(self.other_answered.wait(), 10)
                self.waited.append(True)
            except TimeoutError:
                self.waited.append(False)
            if not self.serve_product_pages:
                return httpx.Response(500, json={"detail": "REQUEST_FAILED_AFTER_TOO_MANY_RETRIES"})
        response = self.site(request)
        if self.other in url or self.other == body.get("query"):
            self.other_answered.set()
        return response


def test_or24_a_page_waiting_for_a_product_page_keeps_its_products_while_the_other_lane_reads(
    migrated_engine: Engine, tmp_path: Path, private_label: PrivateLabelConfig, settings: Settings
) -> None:
    env = c1.make_env(migrated_engine, tmp_path, private_label)
    first, other = products(30, "0003800"), products(10, "0004400")
    named = first[26].upc  # on the first listing's page 2
    clock = c1.Clock()
    site = c1.C1Site({"03001": first, "03002": other}, clock)
    api = OtherLaneFirst(site, "/03002", serve_product_pages=False)
    run_id, _ = c1.run(
        env, settings, api, clock, listings=("03001", "03002"), lanes=2, product_term_upcs=[named]
    )
    # The product page was answered after the other lane's page: the lanes interleaved as in R7.
    assert api.waited == [True]
    with env["factory"]() as s:
        recorded = {r.upc for r in s.scalars(select(RecordRow).where(RecordRow.run_id == run_id))}
        assert {p.upc for p in first} <= recorded, sorted({p.upc for p in first} - recorded)
        assert {p.upc for p in other} <= recorded
        pages = {
            (r.taxonomy_id, r.requested_page): r.new_count
            for r in s.scalars(
                select(ListingPage).where(ListingPage.run_id == run_id, ListingPage.state == "completed")
            )
        }
        assert pages == {("03001", 1): 24, ("03001", 2): 6, ("03002", 1): 10}
        cov = {c.taxonomy_id: c for c in s.scalars(select(NodeCoverage).where(NodeCoverage.run_id == run_id))}
        assert (cov["03001"].organic_upcs, cov["03001"].coverage_ratio) == (30, 1.0)
        assert (cov["03002"].organic_upcs, cov["03002"].coverage_ratio) == (10, 1.0)
        obs = {
            o.upc: (o.provenance or {}).get("coupon_terms", {}).get("status")
            for o in s.scalars(select(ProductObservation).where(ProductObservation.run_id == run_id))
        }
        assert obs[named] == "request_failed"  # its page was asked for once; the provider brought none


def test_or24_on_the_search_route_the_waiting_page_and_its_record_are_kept_while_the_other_lane_reads(
    vh_env: dict[str, Any], settings: Settings
) -> None:
    terms._ceiling(vh_env["factory"], 20)
    api = OtherLaneFirst(terms.FakeTermsApi(), "Bars & Toaster Pastries", serve_product_pages=True)
    run_id = terms._run(
        vh_env,
        settings,
        api,  # type: ignore[arg-type]
        read=False,
        limits=Limits(max_concurrent_listings=2, product_term_upcs=[terms.PURINA.upc]),
    )
    assert api.waited == [True]
    assert terms._product_pages(api) == [terms.PURINA.upc]  # type: ignore[arg-type]
    with vh_env["factory"]() as s:
        recorded = {r.upc for r in s.scalars(select(RecordRow).where(RecordRow.run_id == run_id))}
        cereal = {terms.PURINA.upc, terms.LAMB.upc, terms.ENERGIZER.upc, terms.TEMPTATIONS.upc}
        assert cereal | {terms.PLAIN.upc} <= recorded, sorted(cereal - recorded)
        pages = sorted(
            (r.taxonomy_id, r.state, r.new_count)
            for r in s.scalars(select(ListingPage).where(ListingPage.run_id == run_id))
        )
        assert pages == [("03001", "completed", 4), ("03002", "completed", 1)]
        obs = {
            o.upc: (o.provenance or {}).get("coupon_terms", {}).get("status")
            for o in s.scalars(select(ProductObservation).where(ProductObservation.run_id == run_id))
        }
        assert obs[terms.PURINA.upc] == "read"
