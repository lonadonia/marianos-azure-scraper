"""The continuation/backlog order of a scheduled run (release 1.5.0): pure function, no database."""

from __future__ import annotations

from datetime import UTC, datetime

from marianos_headless.collection.nodes import Node, backlog_first


def _node(i: int) -> Node:
    return Node(1, "Grocery", "cs", f"Sub {i}", f"0100{i}", f"https://example.test/pl/x/0100{i}")


NODES = [_node(i) for i in range(1, 7)]
MON = datetime(2026, 11, 2, 13, tzinfo=UTC)
THU = datetime(2026, 11, 5, 13, tzinfo=UTC)


def test_listings_an_unfinished_run_did_not_reach_are_read_first_by_the_next_run() -> None:
    # Monday's run read all six; Thursday's run was closed unfinished after the first three.
    last = {("cs", n.taxonomy_id): MON for n in NODES} | {("cs", n.taxonomy_id): THU for n in NODES[:3]}
    order, backlog = backlog_first(NODES, last)
    assert [n.taxonomy_id for n in order] == ["01004", "01005", "01006", "01001", "01002", "01003"]
    assert backlog == []  # every listing was read to its end once; the oldest come first


def test_a_listing_never_read_to_its_end_is_backlog_and_keeps_the_csv_order() -> None:
    last = {("cs", "01002"): MON, ("cs", "01004"): THU}
    order, backlog = backlog_first(NODES, last)
    assert backlog == ["01001", "01003", "01005", "01006"]
    assert [n.taxonomy_id for n in order] == ["01001", "01003", "01005", "01006", "01002", "01004"]


def test_with_no_history_the_order_is_the_csv_order() -> None:
    order, backlog = backlog_first(NODES, {})
    assert order == NODES and backlog == [n.taxonomy_id for n in NODES]


def test_the_same_listing_under_another_category_row_is_its_own_entry() -> None:
    other = Node(2, "Pantry", "cs2", "Sub 1", "01001", "https://example.test/pl/x/01001")
    order, backlog = backlog_first([NODES[0], other], {("cs", "01001"): MON})
    assert order == [other, NODES[0]] and backlog == ["01001"]
