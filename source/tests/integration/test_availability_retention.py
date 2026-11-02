"""Availability and retention (brief §6C, release 1.5.0 regression) on a throwaway PostgreSQL; SYNTHETIC rows.

A product of the store's assortment shown unavailable ("Prices May Vary", empty prices) is kept: an empty
price is not a deletion. A later run that does not observe it carries its last verified observation forward
unchanged, with its own crawl date and its empty prices (no earlier or other price is put in), however old it
is: a configured age limit marks it, never drops it. An excluded record is never carried."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, select

from marianos_headless.collection import retention
from marianos_headless.core.ids import new_id
from marianos_headless.core.schema import OUTPUT_FIELDS
from marianos_headless.db.models import PageFetch, ProductObservation, RecordRow
from tests.integration.helpers import new_run, seed

pytestmark = pytest.mark.postgres

NOW = datetime(2026, 11, 2, 15, tzinfo=UTC)
LONG_AGO = NOW - timedelta(days=400)


def _record(upc: str, title: str, regular: str, crawl_date: str) -> dict[str, str]:
    rec = {k: "" for k in OUTPUT_FIELDS}
    rec.update(
        zipcode="60601",
        store_name="Marianos Lakeshore East",
        category="Produce",
        sub_category="Fresh Fruit",
        product_title=title,
        regular_price=regular,
        upc=upc,
        url=f"https://www.marianos.com/p/x/{upc}",
        crawl_date=crawl_date,
    )
    return rec


def test_an_unavailable_product_is_retained_indefinitely_with_its_empty_prices(
    migrated_engine: Engine,
) -> None:
    factory, store = seed(migrated_engine)
    earlier = new_run(factory, store, status="rejected")
    rows = {
        # "Prices May Vary": no fixed price shown; the product data states it out of stock at the store.
        "0000000004205": ("Limes", "", "eligible_unpriced", [], {"availability": "out_of_stock"}),
        "0001600012254": ("Cheerios Cereal", "4.99", "valid", [], {"availability": "in_stock"}),
        "0002000000000": (
            "Ship-only Gift Box",
            "19.99",
            "excluded",
            ["SHIP_ONLY"],
            {"availability": "unknown"},
        ),
    }
    with factory() as s:
        page = PageFetch(
            id=new_id(),
            run_id=earlier.id,
            url="https://www.marianos.com/pl/x",
            purpose="listing",
            http_status=200,
            started_at=LONG_AGO,
        )
        s.add(page)
        s.flush()
        for upc, (title, price, status, reasons, avail) in rows.items():
            rec = _record(upc, title, price, LONG_AGO.date().isoformat())
            s.add(
                ProductObservation(
                    id=new_id(),
                    run_id=earlier.id,
                    mode="LIVE",
                    upc=upc,
                    page_fetch_id=page.id,
                    source="card",
                    displayed={},
                    structured={},
                    provenance={"node": "01006", "fields": {"_availability": avail}},
                    flags=[],
                    parser_version="test",
                    observed_at=LONG_AGO,
                )
            )
            s.add(
                RecordRow(
                    id=new_id(),
                    run_id=earlier.id,
                    mode="LIVE",
                    upc=upc,
                    record=rec,
                    record_sha256="0" * 64,
                    status=status,
                    reasons=reasons,
                    flags=[],
                )
            )
        s.commit()
    later = new_run(factory, store, status="running")
    with factory() as s:
        counts = retention.carry_forward(s, later.id, store.id, NOW, max_age_days=30, run_complete=False)
        s.commit()
        carried = {r.upc: r for r in s.scalars(select(RecordRow).where(RecordRow.run_id == later.id))}
    assert counts == {"carried_forward": 2, "too_old": 2}
    assert set(carried) == {"0000000004205", "0001600012254"}  # the excluded record is never carried
    limes = carried["0000000004205"]
    assert limes.status == "historical" and "CARRIED_FORWARD" in limes.flags
    assert limes.record["regular_price"] == limes.record["sale_price"] == ""  # no price is put in
    assert limes.record["crawl_date"] == LONG_AGO.date().isoformat()  # its own date, not this run's
    hist = limes.provenance["historical"]
    assert hist["past_age_limit"] == 30 and hist["age_days"] == 400 and hist["kept"] is True
    assert "not verified by this run" in hist["note"]
