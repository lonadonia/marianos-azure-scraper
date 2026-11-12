"""C1 (release 1.10.0): a listing request set aside and asked again later in the same run, driven through
the collector's public path at the client's store (53100502, Pickup) on a throwaway PostgreSQL.

Every page comes through a local mock transport and time is a fake clock: nothing reaches a provider or a
retailer, and no test waits. ``SYNTHETIC`` tests use the invented pages of ``tests/listing_site.py``;
``REPLAY`` tests serve answers the live stages of 2026-11-09 saved (``tests/fixtures/oxylabs_2026-11-09``,
origins in its ``SOURCES.json``): a replay shows what the collector does with those answers, never that the
site would answer so again.

The file loads on 1.9.0rc4 too (``tests/c1_site.py`` leaves out what that build lacks). Tests named
``test_control_...`` state what must hold with or without C1 and pass on both; tests named ``test_c1_...``
state what C1 adds and fail on 1.9.0rc4. With ``C1_EVIDENCE_DIR`` set, each test writes what it observed
there before judging it."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import Engine, select, update

from marianos_headless.acquisition import oxylabs
from marianos_headless.collection import pagination, reconciliation
from marianos_headless.collection.nodes import Node
from marianos_headless.core.schema import ordered_record
from marianos_headless.core.settings import PrivateLabelConfig, Settings
from marianos_headless.db.models import (
    CategorySource,
    ProductObservation,
    ProviderUsage,
    PublicationPointer,
    RecordRow,
    Run,
    Store,
    Task,
)
from marianos_headless.publishing.exports import record_sha256
from marianos_headless.publishing.publish import PublicationRefused, latest_key, publish_run
from tests import c1_site as c1
from tests.c1_site import REPLAY, START, SYNTHETIC, TARGET, WAIT_S, C1Site, Clock, Replay
from tests.listing_site import products

pytestmark = [pytest.mark.postgres]

REPEAT_REASON = (
    "accessible pages exhausted; coverage incomplete: page 2: page 2 repeats an earlier page exactly"
)
REORDER_REASON = (
    "accessible pages exhausted; coverage incomplete: page 2: page 2 shows only products of earlier pages, "
    "in another order"
)
REPEATS = [
    pytest.param("repeat", "repeated", REPEAT_REASON, id="repeat"),
    pytest.param("reorder", "reordered_repeat", REORDER_REASON, id="reorder"),
]
FIX = c1.FIXTURES / "oxylabs_2026-11-09"
BATTERIES = "https://www.marianos.com/pl/batteries/26003"
FROZEN = "https://www.marianos.com/pl/frozen/18010"


@pytest.fixture
def env(migrated_engine: Engine, tmp_path: Path, private_label: PrivateLabelConfig) -> dict[str, Any]:
    return c1.make_env(migrated_engine, tmp_path, private_label)


def _pages(
    obs: dict[str, Any], listing: str = "03001", page: int | None = None
) -> list[tuple[int, str, str]]:
    return [
        (p["page"], p["state"], p["verdict"])
        for p in obs["pages"]
        if p["listing"] == listing and (page is None or p["page"] == page)
    ]


def _request(obs: dict[str, Any], listing: str = "03001", page: int = 2) -> dict[str, Any]:
    found = [
        d for d in obs["deferred_requests"] if (d["taxonomy_id"], d["requested_page"]) == (listing, page)
    ]
    assert len(found) == 1, f"one request set aside for {listing} page {page}: {obs['deferred_requests']}"
    return found[0]


def _published(env: dict[str, Any]) -> dict[str, Any]:
    """What is published for the store: the pointer, ``latest.json``, the manifest and the products file."""
    with env["factory"]() as s:
        store = s.scalar(select(Store).where(Store.key == TARGET))
        assert store is not None
        ptr = s.get(PublicationPointer, store.id)
        assert ptr is not None
        state = {"publication_id": ptr.publication_id, "version": ptr.version}
    latest = env["storage"].get_bytes(latest_key(TARGET))
    body = json.loads(latest)
    manifest = env["storage"].get_bytes(body["manifest_key"])
    files = json.loads(manifest)["files"]
    return {
        **state,
        "published_run": body["run_id"],
        "latest_json_sha256": hashlib.sha256(latest).hexdigest(),
        "manifest_sha256": hashlib.sha256(manifest).hexdigest(),
        "products_sha256": hashlib.sha256(
            env["storage"].get_bytes(files["products.json"]["key"])
        ).hexdigest(),
    }


def _publish_first(env: dict[str, Any], settings: Settings) -> str:
    """The store's last good dataset: a complete run of the two listings, validated and published."""
    site = C1Site({"03001": products(60), "03002": products(30, "0003805")})
    run_id, status = c1.run(env, settings, site, site.clock, listings=("03001", "03002"))
    assert status == "validated", status
    assert (
        publish_run(env["factory"], env["storage"], run_id, "test", warn_override_reason="test").version == 1
    )
    return run_id


def _try_publish(env: dict[str, Any], run_id: str) -> str:
    try:
        publish_run(env["factory"], env["storage"], run_id, "test", warn_override_reason="test")
    except PublicationRefused as exc:
        return f"refused: {exc}"
    return "published"


# -- case 1: a repeat that stays through both re-asks --------------------------------------------------------


@pytest.mark.parametrize(("what", "verdict", "reason"), REPEATS)
def test_control_a_page_that_keeps_repeating_counts_nothing_and_the_last_good_dataset_stays(
    env: dict[str, Any], settings: Settings, what: str, verdict: str, reason: str
) -> None:
    """With or without C1: zero products from a repeated answer, the listing incomplete with its reason,
    G3 rejecting the run, publication refused, the published dataset untouched."""
    first = _publish_first(env, settings)
    before = _published(env)
    clock = Clock(START + timedelta(days=1))
    site = C1Site({"03001": products(60), "03002": products(30, "0003805")}, clock)
    site.on("03001", 2, what, what, what, what)
    run_id, status = c1.run(env, settings, site, clock, listings=("03001", "03002"))
    obs = c1.observe(env, run_id)
    tried = _try_publish(env, run_id)
    after = _published(env)
    c1.evidence(
        f"case1 control {what}",
        SYNTHETIC,
        {"asked": site.asked, "observed": obs, "publish": tried, "published_before": before,
         "published_after": after},
    )  # fmt: skip
    fresh = [p for p in obs["pages"] if p["listing"] == "03001" and p["page"] == 2]
    assert fresh and all((p["state"], p["verdict"], p["new"]) == ("stopped", verdict, 0) for p in fresh)
    assert obs["coverage"]["status"] == "INCOMPLETE" and obs["coverage"]["seen"] == 24
    assert obs["coverage"]["reason"].startswith(reason)
    assert obs["gates"]["G3"] == "FAIL" and status == "rejected"
    with env["factory"]() as s:
        mine = [
            r for r in s.scalars(select(RecordRow).where(RecordRow.run_id == run_id)) if r.status == "valid"
        ]
    assert sum(1 for r in mine if r.upc.startswith("0003800")) == 24  # page 1 only; nothing of a repeat
    assert tried.startswith("refused") and after == before and after["published_run"] == first


@pytest.mark.parametrize(("what", "verdict", "reason"), REPEATS)
def test_c1_a_repeated_page_is_asked_again_twice_five_minutes_apart_and_never_more(
    env: dict[str, Any], settings: Settings, what: str, verdict: str, reason: str
) -> None:
    clock = Clock()
    site = C1Site({"03001": products(60)}, clock)
    site.on("03001", 2, what, what, what, what)  # a fourth answer is there to be asked: it never is
    run_id, status = c1.run(env, settings, site, clock)
    obs = c1.observe(env, run_id)
    with env["factory"]() as s:
        files = reconciliation.coverage_files(s, run_id)
    c1.evidence(
        f"case1 c1 {what} through both re-asks",
        SYNTHETIC,
        {"asked_at": site.asked_at, "gaps_s": site.gaps("03001", 2), "observed": obs,
         "export_files": sorted(files)},
    )  # fmt: skip
    assert site.times("03001", 2) == 3 and site.times("03001", 1) == 1 and site.times("03001", 3) == 0
    assert all(g >= WAIT_S for g in site.gaps("03001", 2)) and len(site.gaps("03001", 2)) == 2
    assert _pages(obs, page=2) == [(2, "stopped", verdict)] * 3
    req = _request(obs)
    assert (req["kind"], req["state"], req["reasks_dispatched"], req["max_reasks"]) == (
        "repeated_page", "exhausted", 2, 2,
    )  # fmt: skip
    assert req["original_verdict"] == verdict and req["original_reason"] == reason
    attempts = req["attempts"]
    assert [a["role"] for a in attempts] == ["first answer", "re-ask", "re-ask"]
    # every answer kept: what was asked, what came back, counted for nothing
    for a in attempts:
        assert a["requested"] == {
            "url": "https://www.marianos.com/pl/listing-03001/03001?page=2",
            "page": 2,
            "offset": 24,
            "listing": "03001",
            "reading": "03001",
            "filter": {},
            "store_id": "53100502",
            "fulfillment": "PICKUP",
        }
        assert (a["verdict"], a["new"], a["overlap"], a["unique_before"], a["unique_after"]) == (
            verdict, 0, 24, 24, 24,
        )  # fmt: skip
        assert a["counted"] is False and len(a["returned"]["identities"]) == 24
        # the answer says it is page 2: that is recorded, and it is not what it is judged on
        assert a["returned"]["page"] == 2 and a["returned"]["store_id"] == "53100502"
        assert len(a["capture"]["sha256"]) == 64 and a["provider_request_id"].startswith("req-")
    assert len({a["provider_request_id"] for a in attempts}) == 3  # three requests, three IDs, no progress
    assert attempts[0]["capture"]["listing_page_id"] == req["original_listing_page_id"]
    # the reason the listing had is kept word for word; spent re-asks are never the listing's end
    cov = obs["coverage"]
    assert cov["status"] == "INCOMPLETE" and cov["seen"] == 24 and cov["total"] == 60
    assert cov["reason"].startswith(reason) and "asked again 2 time(s)" in cov["reason"]
    assert "says nothing about where the listing ends" in cov["reason"]
    assert obs["records"] == 24 and obs["distinct_records"] == 24
    assert obs["gates"]["G3"] == "FAIL" and status == "rejected"
    assert "deferred_requests.json" in files
    assert json.loads(files["deferred_requests.json"])["requests"][0]["state"] == "exhausted"


# -- case 2: a re-ask that brings the next page --------------------------------------------------------------


def test_c1_a_reask_that_brings_the_next_page_counts_only_new_products_and_the_listing_goes_on(
    env: dict[str, Any], settings: Settings
) -> None:
    clock = Clock()
    site = C1Site({"03001": products(60)}, clock)
    site.on("03001", 2, "repeat")
    run_id, status = c1.run(env, settings, site, clock)
    obs = c1.observe(env, run_id)
    c1.evidence("case2 c1 next page on re-ask", SYNTHETIC, {"asked_at": site.asked_at, "observed": obs})
    assert site.asked == [("03001", 1), ("03001", 2), ("03001", 2), ("03001", 3)]
    assert site.gaps("03001", 2) == [float(WAIT_S)]
    assert _pages(obs) == [
        (1, "completed", "new"),
        (2, "stopped", "repeated"),  # the first answer stays as it was judged
        (2, "completed", "new"),
        (3, "completed", "new"),
    ]
    req = _request(obs)
    assert (req["state"], req["reasks_dispatched"]) == ("recovered", 1)
    first, again = req["attempts"]
    assert (first["role"], first["verdict"], first["counted"], first["new"]) == (
        "first answer",
        "repeated",
        False,
        0,
    )
    assert (again["verdict"], again["counted"], again["new"], again["overlap"]) == ("new", True, 24, 0)
    assert (again["unique_before"], again["unique_after"]) == (24, 48)
    assert obs["coverage"] == {"status": "DONE", "seen": 60, "total": 60, "reason": ""}
    assert obs["records"] == 60 and obs["distinct_records"] == 60
    assert obs["gates"]["G3"] == "PASS" and obs["gates"]["G13"] == "PASS" and status == "validated"


def test_c1_a_reask_with_partial_overlap_counts_each_new_product_once_and_the_usual_end_applies(
    env: dict[str, Any], settings: Settings
) -> None:
    clock = Clock()
    site = C1Site({"03001": products(60)}, clock)
    site.on("03001", 2, "repeat", "overlap")  # the re-ask: 12 products of page 1 again, 12 new ones
    run_id, status = c1.run(env, settings, site, clock)
    obs = c1.observe(env, run_id)
    c1.evidence("case2 c1 partial overlap on re-ask", SYNTHETIC, {"asked_at": site.asked_at, "observed": obs})
    assert site.asked == [("03001", 1), ("03001", 2), ("03001", 2), ("03001", 3)]  # later pages are read
    assert _pages(obs)[1:3] == [(2, "stopped", "repeated"), (2, "completed", "partial_overlap")]
    again = _request(obs)["attempts"][1]
    assert (again["verdict"], again["counted"], again["new"], again["overlap"]) == (
        "partial_overlap",
        True,
        12,
        12,
    )
    assert (again["unique_before"], again["unique_after"]) == (24, 36)
    assert obs["records"] == 48 and obs["distinct_records"] == 48  # 24 + 12 + 12, none twice
    # the listing's own count still decides: 48 distinct of 60 reported is not complete
    cov = obs["coverage"]
    assert cov["status"] == "INCOMPLETE" and "48 distinct products of 60 reported" in cov["reason"]
    assert obs["gates"]["G3"] == "FAIL" and status == "rejected"


def _batteries(env: dict[str, Any]) -> list[Node]:
    with env["factory"]() as s:
        ids = {c.csv_row_index: c.id for c in s.scalars(select(CategorySource))}
    return [Node(24, "Batteries", ids[24], "", "26003", BATTERIES + "?pzn=relevance", kind="row_listing")]


def test_control_replay_the_saved_batteries_answers_page_2_repeated_page_1_and_later_did_not() -> None:
    """REPLAY, read directly: the answers saved on 2026-11-09 for Batteries. S4's page 2 (14:36:19Z) states
    page 2 and lists page 1's products; S5a's page 2 (14:42:52Z) lists 24 others; with S5a's pages 3 and 4
    the listing's 96 products are all there."""
    import gzip

    from marianos_headless.collection.live import grid_cards
    from marianos_headless.sites.marianos.initial_state import parse_initial_state
    from marianos_headless.sites.marianos.search_state import search_summary

    def facts(name: str, page: int) -> pagination.PageFacts:
        html = gzip.decompress((FIX / name).read_bytes()).decode("utf-8")
        return pagination.page_facts(
            page, search_summary(parse_initial_state(html)), len(grid_cards(html)[1])
        )

    one, rep = facts("s4_batteries_p1.html.gz", 1), facts("s4_batteries_p2_repeats_p1.html.gz", 2)
    assert (rep.returned_page, rep.loaded_pages, rep.total) == (
        2,
        (2,),
        96,
    ) and rep.search_id != one.search_id
    j = pagination.judge(rep, taxonomy="26003", earlier=[one.organic], store_verified=True)
    assert j.verdict is pagination.PageVerdict.REPEATED and not j.accepted
    seen = [one.organic]
    for name, page in (("s5a_batteries_p2.html.gz", 2), ("s5a_batteries_p3.html.gz", 3),
                       ("s5a_batteries_p4.html.gz", 4)):  # fmt: skip
        f = facts(name, page)
        j = pagination.judge(f, taxonomy="26003", earlier=seen, store_verified=True)
        assert j.verdict is pagination.PageVerdict.NEW and len(j.new) == 24
        seen.append(f.organic)
    assert len({u for p in seen for u in p}) == 96


def test_c1_replay_batteries_page_2_repeated_then_answered_six_minutes_later_is_read_to_its_end(
    env: dict[str, Any], settings: Settings
) -> None:
    """REPLAY of saved answers: Batteries (26003) as stage S4 met it at 14:36Z on 2026-11-09 (page 1, then a
    page 2 that repeated it), and the page 2, 3 and 4 that stage S5a was given from 14:42:52Z. The order the
    answers are served in is the order they were saved in; the wait between the two page-2 answers is the
    collector's own five minutes on a fake clock (6 min 33 s passed between the real ones)."""
    clock = Clock()
    replay = Replay(
        {
            BATTERIES: [FIX / "s4_batteries_p1.html.gz"],
            BATTERIES + "?page=2": [
                FIX / "s4_batteries_p2_repeats_p1.html.gz",
                FIX / "s5a_batteries_p2.html.gz",
            ],
            BATTERIES + "?page=3": [FIX / "s5a_batteries_p3.html.gz"],
            BATTERIES + "?page=4": [FIX / "s5a_batteries_p4.html.gz"],
        },
        clock,
    )
    run_id, status = c1.run(env, settings, replay, clock, nodes=_batteries(env))
    obs = c1.observe(env, run_id, "26003")
    c1.evidence(
        "case2 c1 replay batteries",
        REPLAY,
        {"served": replay.asked_at, "sources": json.loads((FIX / "SOURCES.json").read_text("utf-8")),
         "run_status": status, "observed": obs},
    )  # fmt: skip
    assert [name for _, _, name in replay.asked_at] == [
        "s4_batteries_p1.html.gz",
        "s4_batteries_p2_repeats_p1.html.gz",
        "s5a_batteries_p2.html.gz",
        "s5a_batteries_p3.html.gz",
        "s5a_batteries_p4.html.gz",
    ]
    assert replay.gaps(BATTERIES + "?page=2") == [float(WAIT_S)]
    assert _pages(obs, "26003") == [
        (1, "completed", "new"),
        (2, "stopped", "repeated"),
        (2, "completed", "new"),
        (3, "completed", "new"),
        (4, "completed", "new"),
    ]
    req = _request(obs, "26003")
    assert (req["state"], req["reasks_dispatched"]) == ("recovered", 1)
    assert (
        req["attempts"][0]["capture"]["sha256"]
        == hashlib.sha256((FIX / "s4_batteries_p2_repeats_p1.html.gz").read_bytes()).hexdigest()
    )  # the stored page of the first answer is the saved answer, byte for byte
    assert obs["coverage"]["status"] == "DONE" and (obs["coverage"]["seen"], obs["coverage"]["total"]) == (
        96,
        96,
    )
    assert obs["gates"]["G3"] == "PASS" and obs["gates"]["G13"] == "PASS"


# -- case 3: a listing above the window whose first page names nothing to subdivide it by --------------------


def _above_window(clock: Clock) -> C1Site:
    """60 products, 48 reachable; two brands of 30. Page 1 shows 24 of brand A."""
    a, b = products(30, "0003803"), products(30, "0003804")
    site = C1Site({"03001": a[:24] + b[:24], "03001~Acme Foods": a, "03001~Bravo": b}, clock)
    site.totals["03001"] = 60
    site.available["03001"] = 48
    site.brands["03001"] = [{"name": "Acme Foods", "count": 30}, {"name": "Bravo", "count": 30}]
    return site


def _brand(name: str) -> str:
    return pagination.partition_id(
        pagination.partition_descriptor(
            store_id="53100502", modality="PICKUP", listing="03001", filter_name="brandName", value=name
        )
    )


def test_control_a_listing_above_the_window_whose_page_names_its_brands_is_read_through_them(
    env: dict[str, Any], settings: Settings
) -> None:
    """With or without C1: the filters are there from the first answer; each brand reading is checked
    against its own filter and the listing is complete only by the distinct products of all of them."""
    clock = Clock()
    site = _above_window(clock)
    run_id, status = c1.run(env, settings, site, clock)
    obs = c1.observe(env, run_id)
    c1.evidence("case3 control facets present", SYNTHETIC, {"asked": site.asked, "observed": obs})
    assert site.times("03001", 1) == 1 and site.times("03001", 2) == 0
    assert _pages(obs, _brand("Acme Foods")) == [(1, "completed", "new"), (2, "completed", "new")]
    assert _pages(obs, _brand("Bravo")) == [(1, "completed", "new"), (2, "completed", "new")]
    assert obs["distinct_records"] == 60 and obs["gates"]["G3"] == "PASS" and status == "validated"
    assert obs["deferred_requests"] == []


def test_c1_a_first_page_without_filters_is_asked_again_and_the_listing_is_read_through_its_brands(
    env: dict[str, Any], settings: Settings
) -> None:
    clock = Clock()
    site = _above_window(clock)
    site.on("03001", 1, "no_facets")
    run_id, status = c1.run(env, settings, site, clock)
    obs = c1.observe(env, run_id)
    with env["factory"]() as s:
        report = reconciliation.reconciliation(s, run_id)
    lines = {x["listing_id"]: x for x in report["listings"]}
    c1.evidence(
        "case3 c1 facets on re-ask",
        SYNTHETIC,
        {"asked_at": site.asked_at, "observed": obs, "reconciliation": lines},
    )
    assert site.times("03001", 1) == 2 and site.gaps("03001", 1) == [float(WAIT_S)]
    assert site.times("03001", 2) == 0  # the rest of the listing is its brand readings
    # the answer asked again names the brands and counts no product of its own
    assert _pages(obs) == [(1, "completed", "new"), (1, "reasked", "new")]
    assert [p["new"] for p in obs["pages"] if p["listing"] == "03001"] == [24, 0]
    req = _request(obs, page=1)
    assert (req["kind"], req["state"], req["reasks_dispatched"]) == ("missing_facets", "recovered", 1)
    assert "names no child listing and no brand" in req["original_reason"]
    first, again = req["attempts"]
    assert first["counted"] is True and first["returned"]["subdivisions"] == []
    assert again["counted"] is False and again["unique_after"] == 24
    assert [x["name"] for x in again["returned"]["subdivisions"]] == ["Acme Foods", "Bravo"]
    # each brand reading answered for its own filter, and the union reconciled with the listing's total
    assert _pages(obs, _brand("Acme Foods")) == [(1, "completed", "new"), (2, "completed", "new")]
    assert _pages(obs, _brand("Bravo")) == [(1, "completed", "new"), (2, "completed", "new")]
    whole = lines["03001"]
    assert (whole["status"], whole["reported_total"]) == ("DONE", 60)
    assert (whole["unique_identities"], whole["unresolved_gap"]) == (60, 0)
    assert obs["records"] == 60 and obs["distinct_records"] == 60
    assert obs["gates"]["G3"] == "PASS" and status == "validated"


UNPROVED = [("unfiltered", "wrong_filter"), ("other_brand", "wrong_filter"), ("no_filter_state", "unbound")]


@pytest.mark.parametrize(("what", "verdict"), UNPROVED)
def test_c1_filters_recovered_on_a_reask_still_bind_every_brand_reading_to_its_own_filter(
    env: dict[str, Any], settings: Settings, what: str, verdict: str
) -> None:
    """The filters come on the re-ask; one brand's reading is then answered unfiltered, for another brand, or
    without stating a filter. That reading counts nothing and the listing cannot be complete."""
    clock = Clock()
    site = _above_window(clock)
    site.on("03001", 1, "no_facets")
    site.on("03001~Bravo", 1, what)
    run_id, status = c1.run(env, settings, site, clock)
    obs = c1.observe(env, run_id)
    with env["factory"]() as s:
        report = reconciliation.reconciliation(s, run_id)
        upcs = set(s.scalars(select(RecordRow.upc).where(RecordRow.run_id == run_id)))
    lines = {x["listing_id"]: x for x in report["listings"]}
    c1.evidence(f"case3 c1 brand reading {what}", SYNTHETIC, {"asked": site.asked, "observed": obs,
                                                              "reconciliation": lines})  # fmt: skip
    assert _request(obs, page=1)["state"] == "recovered"
    assert _pages(obs, _brand("Bravo")) == [(1, "refused", verdict)]
    assert _pages(obs, _brand("Acme Foods")) == [(1, "completed", "new"), (2, "completed", "new")]
    assert not any(u.startswith("0003804") for u in upcs) and len(upcs) == 30  # nothing of the unproved brand
    assert lines[_brand("Bravo")]["status"] == "INCOMPLETE" and lines["03001"]["status"] == "INCOMPLETE"
    assert lines["03001"]["unresolved_gap"] == 30
    assert obs["gates"]["G3"] == "FAIL" and status == "rejected"


def test_c1_filters_missing_through_both_reasks_leave_the_listing_incomplete_beyond_the_window(
    env: dict[str, Any], settings: Settings
) -> None:
    clock = Clock()
    site = _above_window(clock)
    site.on("03001", 1, "no_facets", "no_facets", "no_facets", "no_facets")
    run_id, status = c1.run(env, settings, site, clock)
    obs = c1.observe(env, run_id)
    c1.evidence("case3 c1 facets never come", SYNTHETIC, {"asked_at": site.asked_at, "observed": obs})
    assert site.times("03001", 1) == 3 and all(g >= WAIT_S for g in site.gaps("03001", 1))
    assert site.times("03001", 2) == 1  # then page by page, to the window
    req = _request(obs, page=1)
    assert (req["state"], req["reasks_dispatched"]) == ("exhausted", 2)
    assert all(a["returned"]["subdivisions"] == [] for a in req["attempts"])
    assert not any(k.startswith("03001~") for k, _ in site.asked)  # no brand reading was invented
    cov = obs["coverage"]
    assert cov["status"] == "INCOMPLETE" and cov["seen"] == 48 and cov["total"] == 60
    assert "48 of 60 results (availableCount)" in cov["reason"]
    assert "names no child listing and no brand" in cov["reason"]
    assert "says nothing about where the listing ends" in cov["reason"]
    assert obs["gates"]["G3"] == "FAIL" and status == "rejected"


def test_c1_a_reask_for_filters_answered_for_another_store_stops_the_run_and_closes_nothing(
    env: dict[str, Any], settings: Settings
) -> None:
    clock = Clock()
    site = _above_window(clock)
    site.on("03001", 1, "no_facets", "wrong_store")
    run_id, status = c1.run(env, settings, site, clock)
    obs = c1.observe(env, run_id)
    c1.evidence("case3 c1 wrong store on re-ask", SYNTHETIC, {"asked": site.asked, "observed": obs})
    assert status == "rejected" and obs["stop_code"] == "STORE_NOT_VERIFIED"
    assert _pages(obs) == [(1, "completed", "new"), (1, "refused", "wrong_context")]
    req = _request(obs, page=1)
    assert req["state"] == "waiting" and req["attempts"][1]["verdict"] == "wrong_context"
    assert req["attempts"][1]["store_check"] == "FAIL" and req["attempts"][1]["counted"] is False
    assert not any(k.startswith("03001~") for k, _ in site.asked)  # no brand reading from that answer
    assert obs["records"] == 24 and obs["coverage"]["status"] != "DONE"


def test_c1_a_reask_for_filters_answered_with_another_page_does_not_count_and_the_next_one_may(
    env: dict[str, Any], settings: Settings
) -> None:
    clock = Clock()
    site = _above_window(clock)
    site.on("03001", 1, "no_facets", "page_2_instead")
    run_id, status = c1.run(env, settings, site, clock)
    obs = c1.observe(env, run_id)
    c1.evidence("case3 c1 wrong page on re-ask", SYNTHETIC, {"asked_at": site.asked_at, "observed": obs})
    assert site.times("03001", 1) == 3
    assert _pages(obs) == [(1, "completed", "new"), (1, "refused", "wrong_page"), (1, "reasked", "new")]
    req = _request(obs, page=1)
    assert (req["state"], req["reasks_dispatched"]) == ("recovered", 2)
    assert req["attempts"][1]["verdict"] == "wrong_page" and req["attempts"][1]["returned"]["page"] == 2
    assert obs["distinct_records"] == 60 and status == "validated"


def test_control_replay_the_saved_frozen_first_page_names_nothing_to_subdivide_it_by() -> None:
    """REPLAY, read directly: Frozen page 1 as stage S3b saved it (2026-11-09 16:12Z): 273 results, 250
    reachable, no brand and no child listing in the page state. Cereal's page 1 of 2026-11-02 (397 results)
    names both: with those a listing above the window is subdivided."""
    import gzip

    from marianos_headless.sites.marianos.initial_state import parse_initial_state
    from marianos_headless.sites.marianos.search_state import brand_facets, listing_children, search_summary

    def state(path: Path) -> dict[str, Any]:
        return dict(parse_initial_state(gzip.decompress(path.read_bytes()).decode("utf-8")))

    frozen = state(FIX / "s3b_frozen_p1_no_filters.html.gz")
    summary = search_summary(frozen)
    assert summary is not None and (summary.total, summary.available) == (273, 250)
    assert brand_facets(frozen) == [] and listing_children(frozen, "18010") == []
    cereal = state(c1.FIXTURES / "oxylabs_2026-11-02" / "listing_03001_p1.html.gz")
    assert len(brand_facets(cereal)) > 1 and len(listing_children(cereal, "03001")) > 1


def test_c1_replay_frozen_answered_without_filters_and_with_a_repeated_page_2_stays_incomplete(
    env: dict[str, Any], settings: Settings
) -> None:
    """REPLAY of saved answers: Frozen (18010) as stage S3b met it on 2026-11-09 (16:12-16:14Z): a first page
    of 273 results without filters, and a page 2 that repeated page 1. No other answer for Frozen was saved
    that day, so each re-ask is served the same saved answer again: this shows what the collector does when
    the answers do not change (4 more submissions, nothing counted, nothing claimed), not what the site would
    have answered."""
    with env["factory"]() as s:
        ids = {c.csv_row_index: c.id for c in s.scalars(select(CategorySource))}
    nodes = [Node(10, "Natural Organic", ids[10], "Frozen", "18010", FROZEN + "?pzn=relevance")]
    clock = Clock()
    replay = Replay(
        {
            FROZEN: [FIX / "s3b_frozen_p1_no_filters.html.gz"] * 3,
            FROZEN + "?page=2": [FIX / "s3b_frozen_p2_repeats_p1.html.gz"] * 3,
        },
        clock,
    )
    run_id, status = c1.run(env, settings, replay, clock, nodes=nodes)
    obs = c1.observe(env, run_id, "18010")
    c1.evidence(
        "case3 c1 replay frozen",
        REPLAY,
        {"served": replay.asked_at, "sources": json.loads((FIX / "SOURCES.json").read_text("utf-8")),
         "run_status": status, "observed": obs},
    )  # fmt: skip
    assert replay.times(FROZEN) == 3 and replay.times(FROZEN + "?page=2") == 3
    assert all(g >= WAIT_S for g in replay.gaps(FROZEN) + replay.gaps(FROZEN + "?page=2"))
    assert _pages(obs, "18010") == [
        (1, "completed", "new"),
        (1, "reasked", "new"),
        (1, "reasked", "new"),
        (2, "stopped", "repeated"),
        (2, "stopped", "repeated"),
        (2, "stopped", "repeated"),
    ]
    assert (
        _request(obs, "18010", 1)["state"] == "exhausted"
        and _request(obs, "18010", 2)["state"] == "exhausted"
    )
    cov = obs["coverage"]
    assert cov["status"] == "INCOMPLETE" and (cov["seen"], cov["total"]) == (24, 273)
    assert "page 2 repeats an earlier page exactly" in cov["reason"]
    assert "names no child listing and no brand" in cov["reason"]
    assert obs["gates"]["G3"] == "FAIL" and status == "rejected"


# -- case 4: lanes, interruption and resume, the budget, the deadline ----------------------------------------


def test_c1_the_other_listings_are_read_before_a_request_set_aside_is_asked_again(
    env: dict[str, Any], settings: Settings
) -> None:
    clock = Clock()
    site = C1Site(
        {"03001": products(60), "03002": products(30, "0003805"), "03003": products(30, "0003806")}, clock
    )
    site.on("03001", 2, "repeat")
    run_id, status = c1.run(env, settings, site, clock, listings=("03001", "03002", "03003"))
    obs = c1.observe(env, run_id)
    c1.evidence("case4 c1 other listings first", SYNTHETIC, {"asked_at": site.asked_at, "observed": obs})
    assert site.asked == [
        ("03001", 1),
        ("03001", 2),  # repeats page 1: set aside
        ("03002", 1),
        ("03002", 2),
        ("03003", 1),
        ("03003", 2),
        ("03001", 2),  # asked again, five minutes after its first answer
        ("03001", 3),
    ]
    assert site.gaps("03001", 2) == [float(WAIT_S)]
    assert obs["distinct_records"] == 120 and status == "validated"


class Slow:
    """The site behind an asynchronous transport: each answer is held a moment; requests in flight are
    counted."""

    def __init__(self, site: C1Site, hold_s: float = 0.05):
        self.site, self.hold_s = site, hold_s
        self.inflight = self.max_inflight = 0

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        import asyncio

        self.inflight += 1
        self.max_inflight = max(self.max_inflight, self.inflight)
        try:
            await asyncio.sleep(self.hold_s)
            return self.site(request)
        finally:
            self.inflight -= 1


def test_c1_two_lanes_ask_each_request_set_aside_once_more_and_save_no_page_before_its_answer(
    env: dict[str, Any], settings: Settings
) -> None:
    clock = Clock()
    site = C1Site({"03001": products(60), "03002": products(60, "0003805")}, clock)
    site.on("03001", 2, "repeat")
    site.on("03002", 2, "repeat")
    slow = Slow(site)
    run_id, status = c1.run(env, settings, slow, clock, listings=("03001", "03002"), lanes=2)
    obs = c1.observe(env, run_id)
    c1.evidence(
        "case4 c1 two lanes",
        SYNTHETIC,
        {"asked_at": site.asked_at, "max_in_flight": slow.max_inflight, "observed": obs},
    )
    assert slow.max_inflight == 2
    assert site.times("03001", 2) == 2 and site.times("03002", 2) == 2
    assert site.times("03001", 1) == 1 and site.times("03002", 1) == 1  # no completed page asked again
    assert all(p["stored_page"] and p["sha256"] for p in obs["pages"])  # no row without its stored page
    assert {(d["taxonomy_id"], d["state"], d["reasks_dispatched"]) for d in obs["deferred_requests"]} == {
        ("03001", "recovered", 1),
        ("03002", "recovered", 1),
    }
    assert obs["records"] == 120 and obs["distinct_records"] == 120
    assert obs["gates"]["G13"] == "PASS" and obs["gates"]["G3"] == "PASS" and status == "validated"


@pytest.mark.parametrize("answers", [("fail", "ok"), ("fail", "fail")], ids=["fail-then-ok", "fail-twice"])
def test_c1_a_reask_the_provider_fails_is_one_submission_and_counts_among_the_two(
    env: dict[str, Any], settings: Settings, answers: tuple[str, str]
) -> None:
    """The transport's own retries (three attempts on a failure) do not apply to a re-ask: it is sent once."""
    clock = Clock()
    site = C1Site({"03001": products(60)}, clock)
    site.on(
        "03001",
        2,
        "repeat",
        *[a for a in answers if a != "ok"],
        *(["repeat"] * 6 if "ok" not in answers else []),
    )
    run_id, status = c1.run(env, settings, site, clock)
    obs = c1.observe(env, run_id)
    c1.evidence(
        f"case4 c1 failed re-ask {'-'.join(answers)}", SYNTHETIC, {"asked_at": site.asked_at, "observed": obs}
    )
    assert site.times("03001", 2) == 3  # the first answer and two re-asks: never 1 + 3 + 3
    sent = [u for u in obs["ledger"] if u[0].endswith("03001?page=2")]
    assert len(sent) == 3
    req = _request(obs)
    assert req["reasks_dispatched"] == 2 and req["attempts"][1]["verdict"] == "failed"
    assert req["attempts"][1]["returned"].startswith("unavailable:")  # nothing was brought: said so
    assert req["attempts"][1]["capture"]["sha256"].startswith("unavailable:")
    if answers[1] == "ok":
        assert _pages(obs, page=2) == [
            (2, "stopped", "repeated"),
            (2, "failed", "failed"),
            (2, "completed", "new"),
        ]
        assert req["state"] == "recovered" and obs["coverage"]["status"] == "DONE" and status == "validated"
    else:
        assert _pages(obs, page=2) == [
            (2, "stopped", "repeated"),
            (2, "failed", "failed"),
            (2, "failed", "failed"),
        ]
        assert req["state"] == "exhausted" and obs["coverage"]["status"] == "INCOMPLETE"
        assert obs["coverage"]["reason"].startswith(REPEAT_REASON) and obs["records"] == 24


def _pause_at_first_wait(env: dict[str, Any], clock: Clock, run_ref: list[str]) -> None:
    """The operator pauses the run as soon as it starts waiting for a request set aside."""

    def pause() -> None:
        if not run_ref:
            return
        with env["factory"]() as s:
            s.execute(update(Run).where(Run.id == run_ref[0]).values(pause_requested=True))
            s.commit()

    clock.on_sleep = pause


def _die_asking_again(env: dict[str, Any], run_id: str, clock: Clock) -> int:
    args = {
        "db": env["engine"].url.render_as_string(hide_password=False),
        "data": str(env["tmp"] / "data"),
        "run": run_id,
        "now": clock.now().isoformat(),
        "listings": {"03001": [60]},
        "listing": "03001",
        "page": 2,
        "nth": 1,
    }
    p = subprocess.run(
        [sys.executable, "-m", "tests.c1_site", json.dumps(args)],
        cwd=c1.ROOT,
        env=dict(os.environ),
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
        check=False,
    )
    assert p.returncode == 137, (p.returncode, p.stdout[-1500:], p.stderr[-1500:])
    return p.returncode


@pytest.mark.parametrize("last", ["ok", "repeat"])
def test_c1_a_worker_killed_while_a_reask_is_out_leaves_it_counted_and_the_ceiling_holds(
    env: dict[str, Any], settings: Settings, last: str
) -> None:
    """Paused while waiting; resumed by a worker that is killed with re-ask 1 out; resumed again. The killed
    re-ask stays counted (its answer is marked unavailable, its reservation kept as possibly charged), so one
    re-ask is left, five minutes later, and no page already completed is asked again."""
    clock = Clock()
    site = C1Site({"03001": products(60)}, clock)
    site.on("03001", 2, "repeat")
    pipe = c1.pipe_of(env, settings)
    run_id = c1.plan(env, pipe, c1.nodes_of(env, ("03001",)))
    _pause_at_first_wait(env, clock, [run_id])
    _, status = c1.run(env, settings, site, clock, run_id=run_id)
    paused = c1.observe(env, run_id)
    name = f"case4 c1 killed during re-ask then {last}"
    c1.evidence(
        name, SYNTHETIC, {"reached": "the first execution only", "asked": site.asked, "observed": paused}
    )
    assert status == "interrupted" and site.asked == [("03001", 1), ("03001", 2)]
    waiting = _request(paused)
    assert (waiting["state"], waiting["reasks_dispatched"]) == ("waiting", 0)
    clock.on_sleep = None
    clock.t = START + timedelta(seconds=WAIT_S + 1)
    _die_asking_again(env, run_id, clock)
    killed = c1.observe(env, run_id)
    out = _request(killed)
    assert (out["state"], out["reasks_dispatched"]) == ("waiting", 1)  # counted before it was sent
    assert out["attempts"][1]["answered"] is None
    with env["factory"]() as s:
        held = list(s.scalars(select(ProviderUsage).where(ProviderUsage.state == "reserved")))
        assert len(held) == 1 and held[0].target.endswith("03001?page=2")
    clock.t += timedelta(seconds=1)
    after = C1Site({"03001": products(60)}, clock)
    if last == "repeat":
        after.on("03001", 2, "repeat", "repeat", "repeat")
    _, status = c1.run(env, settings, after, clock, run_id=run_id)
    obs = c1.observe(env, run_id)
    c1.evidence(
        name,
        SYNTHETIC,
        {"before_kill": paused, "after_kill": killed, "asked_after_at": after.asked_at, "observed": obs},
    )
    assert after.times("03001", 1) == 0  # the completed page is never asked again
    assert after.times("03001", 2) == 1  # one re-ask was left: 1 first answer + 1 killed + 1 = the ceiling
    req = _request(obs)
    assert req["reasks_dispatched"] == 2 and [a["role"] for a in req["attempts"]] == [
        "first answer",
        "re-ask",
        "re-ask",
    ]
    lost = req["attempts"][1]
    assert lost["answered"] is False and lost["verdict"] == "unanswered" and lost["counted"] is False
    assert lost["returned"].startswith("unavailable:") and lost["provider_request_id"].startswith(
        "unavailable:"
    )
    # at least five minutes after the killed re-ask was sent
    assert after.asked_at[0][2] - (START + timedelta(seconds=WAIT_S + 1)) >= timedelta(seconds=WAIT_S)
    with env["factory"]() as s:
        rows = list(s.scalars(select(ProviderUsage).where(ProviderUsage.target.like("%03001?page=2"))))
        assert len(rows) == 3 and sum(1 for u in rows if u.state == "reserved") == 0
        unknown = [u for u in rows if u.cost_source == "unknown"]
        assert (
            len(unknown) == 1 and unknown[0].cost_usd > 0
        )  # the killed request: possibly charged, kept once
    if last == "ok":
        assert req["state"] == "recovered" and obs["distinct_records"] == 60 and status == "validated"
    else:
        assert req["state"] == "exhausted" and obs["records"] == 24 and status == "rejected"
        assert obs["coverage"]["reason"].startswith(REPEAT_REASON)


def test_c1_a_reask_the_spending_ceiling_refuses_is_not_sent_and_not_counted_and_is_asked_once_there_is_room(
    env: dict[str, Any], settings: Settings
) -> None:
    clock = Clock()
    site = C1Site({"03001": products(60)}, clock)
    site.on("03001", 2, "repeat")
    done = False

    def close_the_ceiling() -> None:
        nonlocal done
        if done:
            return
        done = True
        with env["factory"]() as s:  # the allowance is used up while the request waits
            used = oxylabs.usage_since(s, None)["submissions"]
            oxylabs.set_ceiling(
                s, submissions=used, usd=10, actor="test", reason="test", since=START - timedelta(days=400)
            )
            s.commit()

    clock.on_sleep = close_the_ceiling
    run_id, status = c1.run(env, settings, site, clock)
    stopped = c1.observe(env, run_id)
    with env["factory"]() as s:
        rows_before = oxylabs.usage_since(s, None)["submissions"]
    c1.evidence(
        "case4 c1 spending ceiling",
        SYNTHETIC,
        {"reached": "the first execution only", "asked": site.asked, "stopped": stopped},
    )
    assert status == "interrupted" and stopped["stop_code"] == "SPENDING_CEILING"
    assert site.times("03001", 2) == 1  # nothing was sent
    req = _request(stopped)
    assert (req["state"], req["reasks_dispatched"]) == ("waiting", 0)  # and nothing is counted
    assert [a["role"] for a in req["attempts"]] == ["first answer", "re-ask not sent"]
    assert stopped["ledger_rows"] == rows_before  # no reservation was written for it
    clock.on_sleep = None
    with env["factory"]() as s:
        oxylabs.set_ceiling(s, submissions=400, usd=10, actor="test", reason="test")
        s.commit()
    _, status = c1.run(env, settings, site, clock, run_id=run_id)
    obs = c1.observe(env, run_id)
    c1.evidence(
        "case4 c1 spending ceiling",
        SYNTHETIC,
        {"stopped": stopped, "asked_at": site.asked_at, "observed": obs},
    )
    assert site.times("03001", 2) == 2 and site.times("03001", 1) == 1
    req = _request(obs)
    assert (req["state"], req["reasks_dispatched"]) == ("recovered", 1)
    assert [a["role"] for a in req["attempts"]] == ["first answer", "re-ask not sent", "re-ask"]
    assert obs["distinct_records"] == 60 and status == "validated"


def test_c1_a_request_whose_wait_outlasts_the_daily_window_is_not_asked_after_it_and_keeps_its_history(
    env: dict[str, Any], settings: Settings
) -> None:
    """The deadline: a scheduled run whose daily window ends while a request waits. Nothing is sent after
    the window's end; the run pauses as for any window end; the next day's execution asks the request."""
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("America/Chicago")
    clock = Clock()
    end = (START + timedelta(seconds=200)).astimezone(tz)
    occurrence = {
        "day": START.astimezone(tz).date().isoformat(),
        "start": (START - timedelta(hours=3)).astimezone(tz).isoformat(),
        "window_start": (START - timedelta(hours=3)).astimezone(tz).isoformat(),
        "window_end": end.isoformat(),
    }
    site = C1Site({"03001": products(60)}, clock)
    site.on("03001", 2, "repeat")
    pipe = c1.pipe_of(env, settings)
    run_id = c1.plan(env, pipe, c1.nodes_of(env, ("03001",)), trigger="schedule", occurrence=occurrence)
    _, status = c1.run(env, settings, site, clock, run_id=run_id, trigger="schedule")
    stopped = c1.observe(env, run_id)
    c1.evidence(
        "case4 c1 deadline",
        SYNTHETIC,
        {"reached": "the first execution only", "asked": site.asked, "stopped": stopped},
    )
    assert status == "interrupted" and stopped["stop_code"] == "SCHEDULE_WINDOW_END"
    assert site.times("03001", 2) == 1  # not asked after the window's end
    req = _request(stopped)
    assert (req["state"], req["reasks_dispatched"], len(req["attempts"])) == ("waiting", 0, 1)
    assert req["attempts"][0]["verdict"] == "repeated" and req["original_reason"] == REPEAT_REASON
    with env["factory"]() as s:
        task = s.scalar(select(Task).where(Task.run_id == run_id, Task.kind == "listing_node"))
        assert task is not None and (task.cursor or {}).get("extra", {}).get("set_aside", {}).get("page") == 2
    clock.t = START + timedelta(days=1)  # the next day, inside its window
    _, status = c1.run(env, settings, site, clock, run_id=run_id, trigger="schedule")
    obs = c1.observe(env, run_id)
    c1.evidence(
        "case4 c1 deadline", SYNTHETIC, {"stopped": stopped, "asked_at": site.asked_at, "observed": obs}
    )
    assert site.asked == [("03001", 1), ("03001", 2), ("03001", 2), ("03001", 3)]
    req = _request(obs)
    assert (req["state"], req["reasks_dispatched"]) == ("recovered", 1)
    assert req["attempts"][0]["verdict"] == "repeated"  # the first answer is still there
    assert obs["distinct_records"] == 60 and obs["coverage"]["status"] == "DONE"


# -- case 5: ordinary pages and carried records --------------------------------------------------------------


def test_control_ordinary_pages_are_read_once_each_and_nothing_is_set_aside(
    env: dict[str, Any], settings: Settings
) -> None:
    clock = Clock()
    site = C1Site({"03001": products(60), "03002": products(30, "0003805")}, clock)
    run_id, status = c1.run(env, settings, site, clock, listings=("03001", "03002"))
    obs = c1.observe(env, run_id)
    c1.evidence("case5 control ordinary pages", SYNTHETIC, {"asked": site.asked, "observed": obs})
    assert site.asked == [("03001", 1), ("03001", 2), ("03001", 3), ("03002", 1), ("03002", 2)]
    assert clock.slept == 0 and obs["deferred_requests"] == []
    assert obs["records"] == 90 and obs["distinct_records"] == 90 and status == "validated"
    assert all(v == "PASS" for g, v in obs["gates"].items() if g in ("G1", "G3", "G13"))


def test_control_products_carried_from_an_earlier_run_keep_their_own_dates_when_a_page_repeats(
    env: dict[str, Any], settings: Settings
) -> None:
    """SYNTHETIC, and the earlier run's dates are set back by hand to tell them from today's: a run whose
    page 2 keeps repeating observes 24 of the listing's 60 products; the other 36 are carried from the
    earlier run unchanged, each with the date it was observed on, never today's."""
    first = _publish_first(env, settings)
    old = "2026-11-02"
    with env["factory"]() as s:
        for r in s.scalars(select(RecordRow).where(RecordRow.run_id == first)):
            r.record = {**r.record, "crawl_date": old}
            r.record_sha256 = record_sha256(ordered_record(r.record))
        s.execute(
            update(ProductObservation)
            .where(ProductObservation.run_id == first)
            .values(observed_at=START - timedelta(days=7))
        )
        s.commit()
    clock = Clock(START + timedelta(days=1))
    site = C1Site({"03001": products(60), "03002": products(30, "0003805")}, clock)
    site.on("03001", 2, "repeat", "repeat", "repeat", "repeat")
    run_id, _ = c1.run(env, settings, site, clock, listings=("03001", "03002"))
    with env["factory"]() as s:
        rows = list(s.scalars(select(RecordRow).where(RecordRow.run_id == run_id)))
    carried = [r for r in rows if r.status == "historical"]
    fresh = [r for r in rows if r.status == "valid"]
    c1.evidence(
        "case5 control carried dates",
        SYNTHETIC + "; the earlier run's dates set back by hand to 2026-11-02",
        {
            "fresh": len(fresh),
            "carried": len(carried),
            "carried_dates": sorted({r.record["crawl_date"] for r in carried}),
            "fresh_dates": sorted({r.record["crawl_date"] for r in fresh}),
            "observed": c1.observe(env, run_id),
        },
    )
    assert len(fresh) == 54 and len(carried) == 36  # 24 + 30 observed; 36 of 03001 not observed by this run
    assert {r.record["crawl_date"] for r in carried} == {old}
    assert old not in {r.record["crawl_date"] for r in fresh}
    assert all("CARRIED_FORWARD" in (r.flags or []) for r in carried)
