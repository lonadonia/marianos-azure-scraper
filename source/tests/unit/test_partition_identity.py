"""Release 1.9.0, M1 and M2 (the client's review of 1.8.0rc5): a filtered reading's identity, and what a
response must state before it counts for the reading it was asked for.

M1. Up to 1.8.0rc5 a brand reading's ID was ``f"{listing}~{brand}"[:64]``: two brands that share their first
characters up to the cut got one ID, so the second was never planned (the queue's idempotent insert dropped
it) and its pages would have shared the first one's rows. The ID is now a digest of the reading's full
identity; the identity itself travels with the reading.

M2. A brand reading's page counts only when the page states that very filter (``requestVars.brandName`` =
``[value]``, no other facet), is the page's latest search, and finished loading. Observed shapes: the saved
pages of 2026-11-02 (``BINDING_SCAN.csv`` of the 1.9.0 evidence)."""

from __future__ import annotations

import gzip
from pathlib import Path

from marianos_headless.collection import pagination
from marianos_headless.collection.live import grid_cards
from marianos_headless.collection.pagination import PageVerdict
from marianos_headless.sites.marianos.initial_state import parse_initial_state
from marianos_headless.sites.marianos.search_state import brand_facets, search_summary

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "oxylabs_2026-11-02"
LISTING_URL = "https://www.marianos.com/pl/cold-cereal/0300100001"
STORE = {"store_id": "53100502", "modality": "PICKUP"}


def rc5_id(taxonomy_id: str, name: str) -> str:
    """The identity of 1.8.0rc5 (pagination.brand_partitions), kept here to show its collision."""
    return f"{taxonomy_id}~{name}"[:64]


def _html(name: str) -> str:
    return gzip.decompress((FIX / f"{name}.html.gz").read_bytes()).decode("utf-8")


def _facts(page: int, html: str) -> pagination.PageFacts:
    return pagination.page_facts(page, search_summary(parse_initial_state(html)), len(grid_cards(html)[1]))


# -- M1 ------------------------------------------------------------------------------------------------------


def test_the_rc5_identity_gives_two_brands_one_id_and_1_9_gives_each_its_own() -> None:
    a = "Blue Buffalo Life Protection Formula Natural Adult Dry Cat Food Chicken"
    b = "Blue Buffalo Life Protection Formula Natural Adult Dry Cat Food Salmon"
    assert a != b and a[:58] == b[:58]
    assert rc5_id("0300100001", a) == rc5_id("0300100001", b)  # the reproduced collision
    parts = pagination.brand_partitions(
        LISTING_URL, "0300100001", [{"name": a, "count": 3}, {"name": b, "count": 4}], **STORE
    )
    ids = [p["id"] for p in parts]
    assert len(set(ids)) == 2 and all(len(i) <= 64 for i in ids)
    assert [p["descriptor"]["value"] for p in parts] == [a, b]  # the full, exact value is kept
    assert len({p["partition_key"] for p in parts}) == 2 and all(len(p["partition_key"]) == 64 for p in parts)
    assert all(pagination.listing_id(i) == "0300100001" for i in ids)


def test_the_identity_is_a_digest_of_the_whole_descriptor_never_pythons_hash() -> None:
    d = pagination.partition_descriptor(
        store_id="53100502",
        modality="PICKUP",
        listing="0300100001",
        filter_name="brandName",
        value="Kellogg's",
    )
    assert pagination.partition_id(d) == pagination.partition_id(dict(reversed(list(d.items()))))
    for k, v in (
        ("store_id", "53100503"),
        ("modality", "IN_STORE"),
        ("listing", "03001"),
        ("value", "Kellogg's "),
    ):
        assert pagination.partition_id({**d, k: v}) != pagination.partition_id(d), k
    assert pagination.partition_id(d) == "0300100001~" + pagination.partition_digest(d)[:24]


def test_a_value_named_twice_is_read_once_and_values_that_read_alike_are_each_read() -> None:
    brands = [
        {"name": "Kellogg's", "count": 30},
        {"name": "Kellogg's", "count": 30},
        {"name": "KELLOGG'S", "count": 2},
        {"name": "Café Bustelo", "count": 1},
        {"name": "Café Bustelo", "count": 1},
    ]
    parts = pagination.brand_partitions(LISTING_URL, "0300100001", brands, **STORE)
    assert [p["name"] for p in parts] == ["Kellogg's", "KELLOGG'S", "Café Bustelo", "Café Bustelo"]
    assert len({p["id"] for p in parts}) == 4
    notes = {p["name"]: " ".join(p.get("notes", [])) for p in parts}
    assert "again" in notes["Kellogg's"] and "read alike" in notes["Kellogg's"]
    assert "read alike" in notes["Café Bustelo"]
    assert parts[0]["url"] == LISTING_URL + "?brandName=Kellogg%27s"


def test_a_reading_planned_before_1_9_is_recognised_as_legacy() -> None:
    assert pagination.legacy_partition("0300100001~General Mills", "")
    assert not pagination.legacy_partition("0300100001", "")
    d = pagination.partition_descriptor(
        store_id="53100502", modality="PICKUP", listing="0300100001", filter_name="brandName", value="x"
    )
    assert not pagination.legacy_partition(pagination.partition_id(d), pagination.canonical(d))
    assert pagination.node_filter(pagination.canonical(d)) == d


# -- M2, on the real pages of 2026-11-02 (FIXTURE, replayed offline) ----------------------------------------


def _general_mills() -> dict[str, object]:
    return pagination.partition_descriptor(
        store_id="53100502",
        modality="PICKUP",
        listing="0300100001",
        filter_name="brandName",
        value="General Mills",
    )


def test_the_real_brand_page_proves_its_brand_and_counts() -> None:
    facts = _facts(1, _html("listing_0300100001_brand"))  # probe L20: ?brandName=General%20Mills
    j = pagination.judge(
        facts, taxonomy="0300100001", earlier=[], store_verified=True, requested_filter=_general_mills()
    )
    assert j.verdict is PageVerdict.NEW, j.detail
    assert j.binding["stated"]["brandName"] == ["General Mills"]
    assert j.binding["search_id"] == j.binding["latest_search_id"]


def test_the_real_unfiltered_page_never_counts_for_a_brand_reading() -> None:
    facts = _facts(1, _html("listing_0300100001_p1"))  # probe L11: the same listing, no filter
    j = pagination.judge(
        facts, taxonomy="0300100001", earlier=[], store_verified=True, requested_filter=_general_mills()
    )
    assert j.verdict is PageVerdict.WRONG_FILTER and "brandName [] (asked ['General Mills'])" in j.detail
    assert not j.accepted and not j.retry


def test_the_real_brand_page_never_counts_for_another_brand_or_for_the_listing_itself() -> None:
    facts = _facts(1, _html("listing_0300100001_brand"))
    other = {**_general_mills(), "value": "Kellogg's"}
    j = pagination.judge(
        facts, taxonomy="0300100001", earlier=[], store_verified=True, requested_filter=other
    )
    assert j.verdict is PageVerdict.WRONG_FILTER
    j = pagination.judge(facts, taxonomy="0300100001", earlier=[], store_verified=True)
    assert j.verdict is PageVerdict.WRONG_FILTER and "asked []" in j.detail


def test_the_real_listing_page_counts_for_the_listing_itself() -> None:
    for name, page, tax in (("listing_03001_p1", 1, "03001"), ("listing_0300100001_p1", 1, "0300100001")):
        j = pagination.judge(_facts(page, _html(name)), taxonomy=tax, earlier=[], store_verified=True)
        assert j.verdict is PageVerdict.NEW, (name, j.detail)


def test_a_stale_or_unfinished_search_is_never_bound_and_may_be_asked_again() -> None:
    base = _facts(1, _html("listing_0300100001_brand"))
    for change, why in (
        ({"latest_search_id": "another"}, "latest search"),
        ({"loading": True, "loaded": False}, "not a finished answer"),
        ({"has_error": True}, "not a finished answer"),
    ):
        facts = pagination.PageFacts(**{**base.__dict__, **change})
        j = pagination.judge(
            facts, taxonomy="0300100001", earlier=[], store_verified=True, requested_filter=_general_mills()
        )
        assert j.verdict is PageVerdict.UNBOUND and why in j.detail and j.retry, change


def test_a_brand_reading_whose_page_states_no_filter_is_unproved() -> None:
    base = _facts(1, _html("listing_0300100001_brand"))
    j = pagination.judge(
        pagination.PageFacts(**{**base.__dict__, "filters": None}),
        taxonomy="0300100001",
        earlier=[],
        store_verified=True,
        requested_filter=_general_mills(),
    )
    assert j.verdict is PageVerdict.UNBOUND and not j.retry
    filters = dict(base.filters or {})
    filters.pop("brandName")
    j = pagination.judge(
        pagination.PageFacts(**{**base.__dict__, "filters": filters}),
        taxonomy="0300100001",
        earlier=[],
        store_verified=True,
        requested_filter=_general_mills(),
    )
    assert j.verdict is PageVerdict.UNBOUND and "does not state brandName" in j.detail


def test_the_real_pages_name_the_brand_facet_the_partitions_come_from() -> None:
    state = parse_initial_state(_html("listing_0300100001_p1"))
    brands = brand_facets(state)
    assert len(brands) == 67 and sum(b["count"] or 0 for b in brands) == 277
    parts = pagination.brand_partitions(LISTING_URL, "0300100001", brands, **STORE)
    assert len({p["id"] for p in parts}) == len(parts) == 67
