"""The Oxylabs Web API adapter's pure parts (release 1.3.0): the key, answers and the page state it reads."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import SecretStr

from marianos_headless.acquisition import oxylabs
from marianos_headless.collection.nodes import Node
from marianos_headless.collection.oxylabs_live import query_of
from marianos_headless.core.settings import OxylabsSettings
from marianos_headless.sites.marianos.initial_state import parse_initial_state
from marianos_headless.sites.marianos.search_state import search_summary, state_products, taxonomy_ids
from tests import synthetic_marianos as syn

KEY = "oxy-unit-key-0123456789abcdef"


@pytest.mark.parametrize(
    "content",
    [
        f"{KEY}\n",
        f"OXYLABS_API: {KEY}\n",
        f"# comment\nOXYLABS_WEB_API_KEY={KEY}\n",
        f'OXYLABS_API_KEY="{KEY}"\n',
    ],
)
def test_the_key_file_is_read_as_data(tmp_path: Path, content: str) -> None:
    f = tmp_path / "oxylabs.env"
    f.write_text(content, encoding="utf-8")
    key = oxylabs.load_key({oxylabs.ENV_KEY_FILE: str(f)})
    assert key is not None and key.get_secret_value() == KEY


def test_an_unrelated_variable_is_not_taken_for_the_key(tmp_path: Path) -> None:
    f = tmp_path / "oxylabs.env"
    f.write_text("OTHER=1\nSOMETHING=2\n", encoding="utf-8")
    assert oxylabs.load_key({oxylabs.ENV_KEY_FILE: str(f)}) is None
    assert oxylabs.load_key({}) is None


def test_the_key_never_appears_in_a_redacted_text() -> None:
    text = f"Authorization: Bearer {KEY} failed for {KEY}"
    out = oxylabs.redact(text, SecretStr(KEY))
    assert KEY not in out and out.count(oxylabs.REDACTED) == 2


@pytest.mark.parametrize(
    ("status", "body", "html", "kind", "charged"),
    [
        (200, b"{}", "<html>", None, True),
        (200, b"{}", None, "empty_result", None),
        (401, b"{}", None, "auth", False),
        (403, b"{}", None, "entitlement", None),
        (400, b"{}", None, "bad_request", None),
        (429, b"{}", None, "rate_limit", None),
        (500, b'{"detail": "REQUEST_FAILED_AFTER_TOO_MANY_RETRIES"}', None, "provider_failed_free", False),
        (502, b"{}", None, "provider_failure", None),
    ],
)
def test_answers_are_classified_and_charged_only_when_documented(
    status: int, body: bytes, html: str | None, kind: str | None, charged: bool | None
) -> None:
    assert oxylabs.classify(status, body, html) == kind
    assert oxylabs.CHARGED.get(kind) is charged


def test_the_envelope_gives_the_markup_and_the_answers_metadata_only() -> None:
    env = {
        "status": "done",
        "results": [{"html": "<html>x</html>", "metadata": {"status_code": 200}, "markdown": None}],
        "metadata": {"request_id": "abc", "timestamp": "2026-10-28T20:00:00Z"},
    }
    html, meta = oxylabs.envelope(json.dumps(env).encode())
    assert html == "<html>x</html>" and meta["request_id"] == "abc"
    assert meta["result_formats"] == ["html"] and "results" not in meta
    assert oxylabs.envelope(b"not json") == (None, {"envelope": "not JSON"})


def test_the_request_bodies_name_the_store_and_fulfillment() -> None:
    s = OxylabsSettings()
    assert oxylabs.search_body(s, query="Cereal", store_id="53100503", fulfillment="in_store") == {
        "query": "Cereal",
        "store_id": "53100503",
        "fulfillment_type": "in_store",
        "location": "US",
        "output": ["html"],
    }
    body = oxylabs.page_body(s, url="https://x/c", store_id="53100503", fulfillment="in_store", run_js=True)
    assert body["run_js"] is True and body["output"] == ["html"]
    # robots.txt is not a store page: the scraper fails it when it carries store parameters (2026-10-29).
    assert oxylabs.robots_body(s, url="https://x/robots.txt") == {
        "url": "https://x/robots.txt",
        "location": "US",
        "output": ["html"],
    }


def test_taxonomy_ids_are_most_specific_first() -> None:
    p = syn.state_product(syn.PRODUCTS[0], taxonomy="0300100001")
    assert taxonomy_ids(p) == ["0300100001", "03001", "03"]
    # The search response's sub-commodity code adds what the product's own taxonomy does not.
    assert taxonomy_ids(p, ("1800300004",)) == ["0300100001", "1800300004", "03001", "18003", "03", "18"]


def test_the_search_page_state_is_read() -> None:
    html = syn.search_page(
        "https://www.marianos.com",
        ((syn.PRODUCTS[0], "0300100001"), (syn.PRODUCTS[1], "0300200001")),
        query="cereal",
        total=428,
        sponsored=(syn.PRODUCTS[1].upc,),
    )
    state = parse_initial_state(html)
    summary = search_summary(state)
    assert summary is not None
    assert (summary.query, summary.location_id, summary.modality, summary.total, summary.available) == (
        "cereal",
        "53100503",
        "IN_STORE",
        428,
        250,
    )
    assert summary.sponsored == (syn.PRODUCTS[1].upc,)
    assert [p["id"] for p in state_products(state)] == [syn.PRODUCTS[0].upc, syn.PRODUCTS[1].upc]


def test_a_listing_is_searched_by_its_own_name() -> None:
    assert query_of(Node(12, "Breakfast", "x", "Cereal & Granola", "03001", "u")) == "Cereal & Granola"
    assert query_of(Node(24, "Batteries", "x", "", "26003", "u", kind="row_listing")) == "Batteries"
