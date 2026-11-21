"""Release 1.10.0rc7: a listing's verdict from the products actually accounted for (``route_audit``).

SYNTHETIC evidence shaped like the full run R7 (2026-11-17): Cat Food 27021 (234 of 234, the positive
control), Dog Food 27017 (224 reported, page 7's 24 products without a record) and Cat Treats 27022 (52
reported, page 2's 20 products without a record). Until 1.10.0rc6 the coverage file reported both short
listings DONE with no gap (the larger of the pages' identities and the cursor's count); here they are
INCOMPLETE with the products named.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from marianos_headless.collection import route_audit as ra
from marianos_headless.collection.route_audit import PageEvidence, RecordFact, RouteEvidence


def upcs(prefix: str, n: int) -> list[str]:
    # 13 digits with leading zeros, as the source writes them (never cast to a number).
    return [f"00{prefix[:5]}{i:06d}" for i in range(n)]


def pages_of(ids: Sequence[str], size: int = 24, prefix: str = "f") -> tuple[PageEvidence, ...]:
    out = []
    for k in range(0, len(ids), size):
        n = k // size + 1
        out.append(
            PageEvidence(
                page=n, identities=tuple(ids[k : k + size]), fetch_id=f"{prefix}{n}", store_bound=True
            )
        )
    return tuple(out)


def placed(ids: Iterable[str], fetch: str | None = None) -> frozenset[tuple[str, str | None]]:
    return frozenset((u, fetch) for u in ids)


def route(
    key: str,
    ids: Sequence[str],
    *,
    total: int | None,
    status: str = "DONE",
    recorded: Iterable[str] | None = None,
    **kw: object,
) -> RouteEvidence:
    pages = pages_of(ids, prefix=key + "-")
    rec = list(ids if recorded is None else recorded)
    by_upc = {u: p.fetch_id for p in pages for u in p.identities}
    placements = frozenset((u, by_upc.get(u)) for u in rec)
    args: dict[str, object] = {"pages": pages, "placements": placements, "total": total}
    args.update(kw)
    return RouteEvidence(key=key, cursor_status=status, **args)  # type: ignore[arg-type]


def valid(ids: Iterable[str], node: str = "") -> dict[str, RecordFact]:
    return {u: RecordFact("valid", (), node) for u in ids}


def test_the_positive_control_cat_food_reconciles() -> None:
    ids = upcs("27021", 234)
    v = ra.audit([route("27021", ids, total=234)], valid(ids, "27021"))["27021"]
    assert (v.status, len(v.accounted), v.missing, v.unexpected, v.pages_counted) == ("DONE", 234, {}, (), 10)
    assert v.fresh_valid == 234 and v.cross_listed == 0
    assert all(u.startswith("00") and len(u) == 13 for u in v.accounted)


def test_dog_food_page_7_without_records_is_incomplete_with_its_products_named() -> None:
    ids = upcs("27017", 224)
    lost = ids[6 * 24 : 7 * 24]
    kept = [u for u in ids if u not in lost]
    v = ra.audit([route("27017", ids, total=224, recorded=kept)], valid(kept))["27017"]
    assert v.status == "INCOMPLETE" and v.cursor_status == "DONE"
    assert (len(v.accounted), len(v.missing), list(v.missing_by_page)) == (200, 24, [7])
    assert set(v.missing_by_page[7]) == set(lost) and set(v.missing.values()) == {ra.MISSING_NO_RECORD}
    assert "24 of the 224 products" in v.reason and "page 7: 24" in v.reason


def test_cat_treats_page_2_short_by_20_is_incomplete() -> None:
    ids = upcs("27022", 52)
    lost = ids[24 + 4 : 48]  # 20 of page 2's 24 (4 recorded: placed under the listing from that page)
    kept = [u for u in ids if u not in lost]
    v = ra.audit([route("27022", ids, total=52, recorded=kept)], valid(kept))["27022"]
    assert (v.status, len(v.accounted), len(v.missing), list(v.missing_by_page)) == (
        "INCOMPLETE",
        32,
        20,
        [2],
    )


def test_one_product_short_223_of_224_is_never_done() -> None:
    # rc6: a ratio of 0.9955 is above both thresholds (0.98 warn, 0.90 fail): G3 passed and the run published.
    ids = upcs("27017", 224)
    kept = ids[:-1]
    v = ra.audit([route("27017", ids, total=224, recorded=kept)], valid(kept))["27017"]
    assert (v.status, len(v.accounted), list(v.missing)) == ("INCOMPLETE", 223, [ids[-1]])


def test_equal_counts_with_a_substituted_upc_are_not_a_match() -> None:
    ids = upcs("27017", 224)
    other = "0099999999999"
    kept = [*ids[:-1], other]  # 224 records placed under the listing, one of them a product no page lists
    r = route("27017", ids, total=224, recorded=ids[:-1])
    r = RouteEvidence(**{**r.__dict__, "placements": r.placements | {(other, "27017-10")}})
    v = ra.audit([r], valid(kept))["27017"]
    assert v.status == "INCOMPLETE"
    assert (list(v.missing), v.unexpected) == ([ids[-1]], (other,))
    assert "placement(s) under the listing for products none of its counted pages lists" in v.reason


def test_overlapping_subdivisions_complete_only_by_their_union() -> None:
    a, b = upcs("10001", 200), upcs("10002", 150)
    shared = a[:50]
    b = [*shared, *b[50:]]  # 50 products in both subdivisions
    parent_total = 300
    records = valid({*a, *b})
    kids = [
        route("1000101", a, total=200, parent="10001"),
        route("1000102", b, total=150, parent="10001"),
    ]
    parent = RouteEvidence(key="10001", cursor_status="PARTITIONED", total=parent_total)
    v = ra.audit([parent, *kids], records)["10001"]
    assert (v.status, len(v.union_accounted)) == ("DONE", 300)
    # The same subdivisions sum to 350 >= 310, but their union is 300: never complete by a sum.
    parent = RouteEvidence(key="10001", cursor_status="PARTITIONED", total=310)
    v = ra.audit([parent, *kids], records)["10001"]
    assert v.status == "INCOMPLETE" and "300 distinct products (their union) of the 310" in v.reason


def test_a_subdivision_short_of_its_products_keeps_the_parent_incomplete() -> None:
    a, b = upcs("10001", 200), upcs("10002", 100)
    kept_b = b[:-1]
    kids = [
        route("1000101", a, total=200, parent="10001"),
        route("1000102", b, total=100, parent="10001", recorded=kept_b),
    ]
    out = ra.audit(
        [RouteEvidence(key="10001", cursor_status="PARTITIONED", total=300), *kids], valid([*a, *kept_b])
    )
    assert out["1000102"].status == "INCOMPLETE"
    assert out["10001"].status == "INCOMPLETE" and "1000102 INCOMPLETE" in out["10001"].reason


def test_a_brand_reading_whose_filter_the_page_did_not_bind_counts_nothing() -> None:
    # Its pages were refused (verdict unbound, never counted): the reading has no counted page.
    brand = RouteEvidence(
        key="08120~0123456789abcdef01234567", cursor_status="DONE", parent="08120", total=40
    )
    whole = upcs("08120", 260)
    parent = route("08120", whole[:250], total=260, status="PARTITIONED")
    out = ra.audit([parent, brand], valid(whole[:250]))
    assert out[brand.key].status == "INCOMPLETE" and "0 distinct products are accounted for of the 40" in (
        out[brand.key].reason
    )
    assert out["08120"].status == "INCOMPLETE"


def test_a_page_not_shown_for_the_store_is_not_counted_evidence() -> None:
    ids = upcs("27017", 48)
    r = route("27017", ids, total=48)
    wrong = (r.pages[0], PageEvidence(**{**r.pages[1].__dict__, "store_bound": False}))
    v = ra.audit([RouteEvidence(**{**r.__dict__, "pages": wrong})], valid(ids))["27017"]
    assert v.status == "INCOMPLETE" and "page(s) 2 were not shown for the run's store" in v.reason


def test_an_empty_listing_needs_a_page_of_the_store_stating_zero() -> None:
    without = RouteEvidence(key="27029", cursor_status="EMPTY", total=0)
    with_page = RouteEvidence(key="27027", cursor_status="EMPTY", total=0, zero_result=True)
    out = ra.audit([without, with_page], {})
    assert (
        out["27029"].status == "INCOMPLETE" and "without a page of the store stating 0" in out["27029"].reason
    )
    assert out["27027"].status == "EMPTY"


def test_a_repeated_page_counted_twice_does_not_make_up_the_total() -> None:
    ids = upcs("27017", 48)
    first = PageEvidence(page=1, identities=tuple(ids[:24]), fetch_id="a", store_bound=True)
    again = PageEvidence(page=2, identities=tuple(ids[:24]), fetch_id="b", store_bound=True)
    r = RouteEvidence(
        key="27017", cursor_status="DONE", total=48, pages=(first, again), placements=placed(ids[:24], "a")
    )
    v = ra.audit([r], valid(ids[:24]))["27017"]
    assert (v.status, v.duplicates, len(v.accounted)) == ("INCOMPLETE", 24, 24)
    assert "24 distinct products are accounted for of the 48" in v.reason


def test_a_total_that_changed_while_reading_is_named() -> None:
    ids = upcs("27017", 224)
    r = route("27017", ids, total=226, totals_seen=(224, 226))
    v = ra.audit([r], valid(ids))["27017"]
    assert v.status == "INCOMPLETE" and "the source's total changed while reading: 224, 226" in v.reason


def test_carried_cross_listed_excluded_and_sponsored_stay_distinct() -> None:
    ids = upcs("27017", 24)
    sponsored = ("0001111111111",)
    pages = (
        PageEvidence(page=1, identities=tuple(ids), sponsored=sponsored, fetch_id="p1", store_bound=True),
    )
    records: dict[str, RecordFact] = {
        **valid(ids[:20], "27017"),
        ids[20]: RecordFact("valid", (), "27018"),  # recorded under another listing, placed here too
        ids[21]: RecordFact("excluded", ("APPROXIMATE_WEIGHT",), "27017"),
        ids[22]: RecordFact("historical", ("CARRIED_FORWARD",), "27017"),  # carried: not this run's
        ids[23]: RecordFact("excluded", (), "27017"),  # excluded with no reason: never an exclusion
    }
    r = RouteEvidence(key="27017", cursor_status="DONE", total=24, pages=pages, placements=placed(ids, "p1"))
    v = ra.audit([r], records)["27017"]
    assert v.status == "INCOMPLETE"
    assert (v.fresh_valid, v.cross_listed, list(v.excluded), v.sponsored) == (21, 1, [ids[21]], sponsored)
    assert v.missing == {ids[22]: ra.MISSING_CARRIED, ids[23]: ra.MISSING_UNEXPLAINED}


def test_a_record_with_no_placement_under_the_listing_does_not_count_here() -> None:
    # Seen elsewhere in the run: counts here only with this run's placement under this listing.
    ids = upcs("27017", 24)
    r = RouteEvidence(
        key="27017",
        cursor_status="DONE",
        total=24,
        pages=pages_of(ids, prefix="p"),
        placements=placed(ids[:23], "p1"),
    )
    v = ra.audit([r], valid(ids, "27018"))["27017"]
    assert v.status == "INCOMPLETE" and v.missing == {ids[23]: ra.MISSING_NO_PLACEMENT}


def test_a_placement_made_from_another_listings_page_is_not_unexpected() -> None:
    ids = upcs("27017", 24)
    foreign = "0005555555555"
    r = RouteEvidence(
        key="27017",
        cursor_status="DONE",
        total=24,
        pages=pages_of(ids, prefix="p"),
        placements=placed(ids, "p1") | {(foreign, "other-listing-fetch")},
        fetches=frozenset({"p1"}),
    )
    v = ra.audit([r], valid([*ids, foreign]))["27017"]
    assert (v.status, v.unexpected, v.from_other_listings) == ("DONE", (), 1)


def test_an_incomplete_listing_stays_incomplete_and_the_summary_names_the_downgrades() -> None:
    ids = upcs("27017", 224)
    kept = ids[:200]
    out = ra.audit(
        [
            route("27017", ids, total=224, recorded=kept),
            route("27021", upcs("27021", 24), total=234, status="INCOMPLETE", reason="search route"),
        ],
        valid([*kept, *upcs("27021", 24)]),
    )
    assert out["27021"].status == "INCOMPLETE" and out["27021"].reason == "search route"
    s = ra.summary(out)
    assert s["read_to_end_but_not_accounted"] == ["27017"] and s["missing_identities"] == 24
