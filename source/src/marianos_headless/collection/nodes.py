"""The listing pages a live run visits: one per client subcategory, from the saved site menu.

Each client category (a row of ``config/Marianos_Category_URLs.csv``) maps to the subcategory listing
pages of the site menu saved on 2026-10-17 (``config/taxonomy_seed.snapshot_2026-10-17.json``). A row with
no entry in that menu whose own URL is a listing page (``/pl/<slug>/<taxonomy id>``: Candles, Batteries,
Light Bulbs, School Office, Hardware) is that listing itself (kind ``row_listing``, no subcategory). Any
other row without listing pages (the coupons catalogue, which lists offers, not products) is reported as
not collected, with the reason, instead of guessed.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

from marianos_headless.core.paths import config_dir

SEED_FILE = "taxonomy_seed.snapshot_2026-10-17.json"
BASE = "https://www.marianos.com"
_ROW_LISTING = re.compile(r"^/pl/[^/]+/(?P<tax>\d+)/?$")


@dataclass(frozen=True)
class Node:
    row_index: int
    category: str  # the client's category name (CSV)
    category_source_id: str
    sub_category: str  # the site menu's subcategory title ("" until a landing page names it)
    taxonomy_id: str
    url: str
    # "listing": a page of products (every Mariano's node). Snapshots written before 1.1 have no kind.
    kind: str = "listing"
    excluded: tuple[str, ...] = ()  # subcategory names the client's category list excludes
    only: tuple[str, ...] = ()  # a landing page narrowed to these subcategory listings (URL or path id)
    # A child listing read because the parent listing is larger than the site's result window (kind
    # "partition"): the parent's taxonomy id, the child's name and the count the site reported for it.
    parent: str = ""
    partition_name: str = ""
    partition_count: int | None = None
    # Release 1.9.0 (M1): a filtered reading's full identity, as canonical JSON
    # (``pagination.partition_descriptor``); "" for a listing itself and for readings planned before 1.9.0.
    partition_filter: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Node:
        values = dict(d)
        values["excluded"] = tuple(values.get("excluded") or ())
        values["only"] = tuple(values.get("only") or ())
        return cls(**values)


def load_seed(path: Path | None = None) -> dict[str, Any]:
    p = path or config_dir() / SEED_FILE
    data: dict[str, Any] = json.loads(p.read_bytes()) if p.exists() else {}
    return data


def listing_url(base: str, href: str) -> str:
    """The site menu's own link on ``base``, unchanged (as the pilot opened it)."""
    return urljoin(base.rstrip("/") + "/", href.lstrip("/"))


def plan_nodes(
    seed: Mapping[str, Any],
    sources: Mapping[int, tuple[str, ...]],
    categories: Sequence[int],
    subcategories: Mapping[str, Sequence[str]],
    base: str = BASE,
) -> tuple[list[Node], list[dict[str, Any]]]:
    """(nodes to visit in CSV order, rows or subcategories left out with the reason).

    ``sources`` maps an enabled CSV row to (category name, category_sources.id[, the row's URL]).
    ``categories`` empty means every enabled row; ``subcategories`` optionally narrows a row to some
    taxonomy IDs."""
    rows = {int(r["row_index"]): r for r in seed.get("rows", [])}
    wanted = sorted(categories) if categories else sorted(sources)
    nodes: list[Node] = []
    skipped: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for row_index in wanted:
        if row_index not in sources:
            skipped.append({"row": row_index, "reason": "not an enabled client category"})
            continue
        name, source_id, *rest = sources[row_index]
        row_url = rest[0] if rest else ""
        menu = rows.get(row_index, {}).get("menu_nodes") or []
        chosen = {str(t) for t in subcategories.get(str(row_index), [])}
        if not menu:
            parts = urlsplit(row_url)
            m = _ROW_LISTING.match(parts.path)
            if m is not None and (not chosen or m.group("tax") in chosen):
                href = parts.path + (f"?{parts.query}" if parts.query else "")
                url = listing_url(base, href)
                if url not in seen_urls:
                    seen_urls.add(url)
                    nodes.append(
                        Node(row_index, name, source_id, "", m.group("tax"), url, kind="row_listing")
                    )
                continue
            skipped.append(
                {
                    "row": row_index,
                    "category": name,
                    "reason": "no listing page for this category in the saved site menu and the row's URL is "
                    "not a listing page (the coupons catalogue lists offers, not products); not collected",
                }
            )
            continue
        for n in menu:
            tax = str(n["taxonomy_id"])
            if chosen and tax not in chosen:
                continue
            url = listing_url(base, str(n["url"]))
            if url in seen_urls:
                skipped.append(
                    {
                        "row": row_index,
                        "category": name,
                        "sub_category": n["title"],
                        "reason": "same page as an earlier subcategory",
                    }
                )
                continue
            seen_urls.add(url)
            nodes.append(Node(row_index, name, source_id, str(n["title"]), tax, url))
    return nodes, skipped


# Listing statuses that mean a run read the listing to its end (directly, or through its child listings).
COMPLETE_NODE_STATUSES = ("DONE", "EMPTY", "PARTITIONED")


def backlog_first(
    nodes: Sequence[Node], last_complete: Mapping[tuple[str, str], datetime]
) -> tuple[list[Node], list[str]]:
    """The continuation/backlog order of a scheduled run (release 1.5.0): listings no earlier run of the store
    read to its end come first (the backlog, in the client's CSV order), then the others, the one read longest
    ago first. A run the next occurrence closed before it finished (``SUPERSEDED``) thus hands the listings it
    did not reach to that occurrence's run, which reads them first, instead of their waiting behind the
    listings it did read and possibly never being read. ``last_complete`` maps (category source, listing ID)
    to the start of the latest run that read it to its end. Returns the order and the backlog's IDs."""
    indexed = list(enumerate(nodes))
    backlog = [n for _, n in indexed if (n.category_source_id, n.taxonomy_id) not in last_complete]
    read = sorted(
        (
            (last_complete[(n.category_source_id, n.taxonomy_id)], i, n)
            for i, n in indexed
            if (n.category_source_id, n.taxonomy_id) in last_complete
        ),
        key=lambda t: (t[0], t[1]),
    )
    return [*backlog, *(n for _, _, n in read)], [n.taxonomy_id for n in backlog]
