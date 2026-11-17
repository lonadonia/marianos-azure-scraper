"""Release 1.10.0rc6: the order a run reads its listings in, and the product pages it reads (the estimate made
from run F2's traces before the next paid run).

- Depth first: run F2 (1.10.0rc5) planned the subdivisions of 25 listings above the site's 250-result window
  and read none of them before it stopped, because a subdivision was leased after every listing of the plan
  (by creation). A listing's subdivisions are now leased before the plan's next listing.
- ``rows_first``: CSV rows read first, in a chosen order; the plan is the same.
- ``product_term_upcs``: only the named products' own pages are read (with ``coverage.read_product_terms``
  on, every tile's page would be one more request: about as many requests as products).

Tests named ``test_rc6_...`` fail on 1.10.0rc5."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import Engine, select

from marianos_headless.collection import control
from marianos_headless.collection.config import CollectionConfig, Limits
from marianos_headless.core.settings import Settings
from marianos_headless.core.timeutil import utcnow
from marianos_headless.db import queue
from marianos_headless.db.models import ProductObservation
from tests.integration import test_product_terms_collector as terms
from tests.integration.helpers import new_run, seed

pytestmark = pytest.mark.postgres

vh_env = terms.vh_env


def _drain(s: Any, run_id: str) -> list[str]:
    order: list[str] = []
    while (lease := queue.lease_next(s, run_id, "w1")) is not None:
        order.append(str(lease.taxonomy_id))
        queue.succeed(s, lease)
        s.commit()
    return order


def test_rc6_a_listings_subdivisions_are_read_before_the_plans_next_listing(migrated_engine: Engine) -> None:
    factory, store = seed(migrated_engine)
    run = new_run(factory, store)
    with factory() as s:
        for i, tax in enumerate(("06111", "06112", "06113", "06114")):
            queue.enqueue(
                s, run.id, "listing_node", f"{run.id}/node/{i:04d}-{tax}", priority=50, taxonomy_id=tax
            )
        s.commit()
        first = queue.lease_next(s, run.id, "w1")
        second = queue.lease_next(s, run.id, "w2")
        assert first is not None and second is not None
        assert (first.taxonomy_id, second.taxonomy_id) == ("06111", "06112")
        s.commit()
        # 06112 is above the window: its page 1 names its subdivisions, planned now (after the whole plan).
        for child in ("0611200694", "0611200691"):
            queue.enqueue(
                s, run.id, "listing_node", f"{second.idem_key}/{child}", priority=50, taxonomy_id=child
            )
        s.commit()
        queue.succeed(s, first)
        queue.succeed(s, second)
        s.commit()
        order = _drain(s, run.id)
        # Both subdivisions (in the order they were planned) before the plan's next listing.
        assert set(order[:2]) == {"0611200691", "0611200694"} and order[2:] == ["06113", "06114"]


def test_rc6_subdivisions_keep_the_order_they_were_planned_in(migrated_engine: Engine) -> None:
    factory, store = seed(migrated_engine)
    run = new_run(factory, store)
    with factory() as s:
        queue.enqueue(
            s, run.id, "listing_node", f"{run.id}/node/0000-03001", priority=50, taxonomy_id="03001"
        )
        queue.enqueue(
            s, run.id, "listing_node", f"{run.id}/node/0001-03002", priority=50, taxonomy_id="03002"
        )
        s.commit()
        parent = queue.lease_next(s, run.id, "w1")
        assert parent is not None and parent.taxonomy_id == "03001"
        # Brand readings: their IDs are digests, so key order is not the facet's order; one per transaction
        # here so that each has its own creation time (planned in the facet's order: zeta, then alpha).
        for pid in ("ffff000001", "0000000002"):
            queue.enqueue(s, run.id, "listing_node", f"{parent.idem_key}/{pid}", priority=50, taxonomy_id=pid)
            s.commit()
        queue.succeed(s, parent)
        s.commit()
        assert _drain(s, run.id) == ["ffff000001", "0000000002", "03002"]


def test_keys_without_a_place_in_the_plan_keep_their_creation_order(migrated_engine: Engine) -> None:
    factory, store = seed(migrated_engine)
    run = new_run(factory, store)
    with factory() as s:
        for tax in ("26003", "26002"):
            queue.enqueue(s, run.id, "listing_node", f"{run.id}/listing/{tax}", priority=50, taxonomy_id=tax)
            s.commit()
        assert _drain(s, run.id) == ["26003", "26002"]


def test_rc6_a_subdivision_waiting_for_its_re_ask_holds_no_lane(migrated_engine: Engine) -> None:
    factory, store = seed(migrated_engine)
    run = new_run(factory, store)
    t0 = utcnow()
    with factory() as s:
        queue.enqueue(
            s, run.id, "listing_node", f"{run.id}/node/0000-06112", priority=50, taxonomy_id="06112"
        )
        queue.enqueue(
            s, run.id, "listing_node", f"{run.id}/node/0001-06113", priority=50, taxonomy_id="06113"
        )
        s.commit()
        # The subdivision is planned after its listing (as when the listing's page 1 names it).
        queue.enqueue(
            s,
            run.id,
            "listing_node",
            f"{run.id}/node/0000-06112/0611200694",
            priority=50,
            taxonomy_id="0611200694",
        )
        s.commit()
        parent = queue.lease_next(s, run.id, "w1", now=t0)
        assert parent is not None and parent.taxonomy_id == "06112"
        queue.succeed(s, parent)
        s.commit()
        child = queue.lease_next(s, run.id, "w1", now=t0)
        assert child is not None and child.taxonomy_id == "0611200694"
        # Its page 2 repeated page 1: the request is set aside for 300 s (C1).
        queue.defer(s, child, not_before=t0 + timedelta(seconds=300))
        s.commit()
        nxt = queue.lease_next(s, run.id, "w1", now=t0 + timedelta(seconds=1))
        assert nxt is not None and nxt.taxonomy_id == "06113"
        queue.succeed(s, nxt)
        s.commit()
        assert queue.lease_next(s, run.id, "w1", now=t0 + timedelta(seconds=2)) is None
        again = queue.lease_next(s, run.id, "w1", now=t0 + timedelta(seconds=301))
        assert again is not None and again.taxonomy_id == "0611200694"


def test_rc6_rows_first_reads_the_named_rows_first_and_keeps_the_plan() -> None:
    cfg = CollectionConfig(rows_first=[22, 27, 22, 15])
    assert cfg.rows_first == [22, 27, 15]
    seed_rows = control.load_seed()
    sources = {
        int(r["row_index"]): (r["category"], f"id{r['row_index']}", str(r.get("url") or ""))
        for r in seed_rows["rows"]
    }
    nodes, _ = control.plan_nodes(seed_rows, sources, [], {})
    ordered = control.rows_first(nodes, cfg.rows_first)
    assert sorted(n.taxonomy_id for n in ordered) == sorted(n.taxonomy_id for n in nodes)
    rows = [n.row_index for n in ordered]
    first = [r for r in rows if r in (22, 27, 15)]
    assert rows[: len(first)] == first and first == sorted(first, key=[22, 27, 15].index)
    rest = [n for n in ordered if n.row_index not in (22, 27, 15)]
    assert rest == [n for n in nodes if n.row_index not in (22, 27, 15)]


def test_rc6_a_product_is_named_by_its_upc() -> None:
    assert Limits(product_term_upcs=["0001780014939", " 0001780014939 "]).product_term_upcs == [
        "0001780014939"
    ]
    with pytest.raises(ValueError, match="13-digit UPC"):
        Limits(product_term_upcs=["1780014939"])
    assert not Limits(product_term_upcs=["0001780014939"]).bounded()  # not a scope limit


def _terms_of(env: dict[str, Any], run_id: str) -> dict[str, Any]:
    with env["factory"]() as s:
        return {
            o.upc: (o.provenance or {}).get("coupon_terms", {}).get("status")
            for o in s.scalars(select(ProductObservation).where(ProductObservation.run_id == run_id))
        }


def test_rc6_only_the_named_products_pages_are_read(vh_env: dict[str, Any], settings: Settings) -> None:
    terms._ceiling(vh_env["factory"], 20)
    fake = terms.FakeTermsApi()
    named = [terms.TEMPTATIONS.upc, terms.PURINA.upc, terms.PLAIN.upc]
    run_id = terms._run(vh_env, settings, fake, read=False, limits=Limits(product_term_upcs=named))
    # In page order, once each, whatever the card shows (PLAIN's card shows no coupon).
    assert terms._product_pages(fake) == [terms.PURINA.upc, terms.TEMPTATIONS.upc, terms.PLAIN.upc]
    status = _terms_of(vh_env, run_id)
    assert status[terms.PURINA.upc] == "read"
    assert status[terms.TEMPTATIONS.upc] == "request_failed" and status[terms.PLAIN.upc] == "request_failed"
    assert status[terms.LAMB.upc] is None and status[terms.ENERGIZER.upc] is None


def test_rc6_named_products_narrow_the_setting_that_reads_every_coupon_card(
    vh_env: dict[str, Any], settings: Settings
) -> None:
    terms._ceiling(vh_env["factory"], 20)
    fake = terms.FakeTermsApi()
    run_id = terms._run(
        vh_env, settings, fake, read=True, limits=Limits(product_term_upcs=[terms.ENERGIZER.upc])
    )
    assert terms._product_pages(fake) == [terms.ENERGIZER.upc]
    status = _terms_of(vh_env, run_id)
    assert status[terms.ENERGIZER.upc] == "request_failed" and status[terms.PURINA.upc] is None
