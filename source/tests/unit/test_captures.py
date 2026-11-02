"""The automated canary's source check and the 22-field contract on authentic data: the records and the
site's product responses of an earlier live run (tests/captures/run_01M5CSS9_20261020), offline."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from marianos_headless.checks import contract, source_check
from tests.conftest import CAPTURES

pytestmark = pytest.mark.captures
RUN = CAPTURES / "run_01M5CSS9_20261020"


def test_every_record_with_a_product_response_matches_it_for_the_store() -> None:
    records = json.loads((RUN / "products.json").read_text("utf-8"))
    out = source_check.check(records, RUN / "raw", "53100503")
    assert out["responses_read"] == 13
    # 157 records agree with the site's data for store 53100503 (prices, or no price shown nor returned);
    # 9 cards had no product response on their page step (reported, never assumed); none differs.
    assert out["summary"] == {"records": 166, "verified": 157, "mismatch": 0, "unverified": 9}


def test_a_record_priced_for_another_store_or_at_another_price_is_a_mismatch(tmp_path: Path) -> None:
    records = json.loads((RUN / "products.json").read_text("utf-8"))
    priced = next(r for r in records if r["regular_price"])
    out = source_check.check([priced], RUN / "raw", "53100511")  # another store
    assert out["summary"]["mismatch"] == 1 and out["mismatched_fields"] == {"store": 1}
    wrong = {**priced, "regular_price": f"{float(priced['regular_price']) + 1:.2f}"}
    out = source_check.check([wrong], RUN / "raw", "53100503")
    assert out["mismatched_fields"] == {"regular_price": 1}


def test_the_export_follows_the_22_field_contract() -> None:
    report = contract.check(RUN / "products.json")
    assert report["passed"] and report["rows"] == 166 and report["duplicate_upc"] == 0
    assert report["populated"]["gupc"] == 0 and report["populated"]["unit_price"] == 0
