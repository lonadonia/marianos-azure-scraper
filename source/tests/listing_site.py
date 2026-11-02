"""SYNTHETIC listing pages behind a fake Oxylabs Web API (an httpx mock transport, nothing leaves the
process).

The pages are shaped like the provider's ``/pl/`` pages of the probes of 2026-11-02: the store and fulfillment
as request parameters, ``?page=N``, the page's ``requestVars`` (page, taxonomy, store, modality),
``loadedPages``, each product's ``searchEngineRank`` (rank 0 for a sponsored placement), the result count and
the window (``availableCount``), the filter tree and the brand facet. Each ``(listing, page)`` can be given
what the provider or the site does instead of answering properly, once per request, in order.

Run as a module it is a worker that dies on purpose (``os._exit``, as a forced kill: nothing closes, nothing
commits): ``python -m tests.listing_site <json>``. See ``test_listing_pages.py``.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx

from tests import synthetic_marianos as syn

BASE = "https://www.marianos.com"
ROBOTS = "User-agent: *\nDisallow: /checkout$\nDisallow: /locations*\n"
SIZE = 24
KEY = "oxy-test-key-never-sent-0123456789abcdef"


def products(n: int, prefix: str = "0003800") -> list[syn.Product]:
    return [
        syn.Product(
            f"{prefix}{i:06d}", f"item-{prefix}-{i}", f"Item {prefix} {i}", "10 oz", "$2.99", ppm="$0.30/oz"
        )
        for i in range(1, n + 1)
    ]


class Site:
    """``listings``: the products of each listing (``03001``) or filtered reading (``03001~Brand``), in
    rank order."""

    def __init__(
        self,
        listings: dict[str, list[syn.Product]],
        *,
        location_id: str = "53100503",
        fulfillment: str = "in_store",
        modality: str = "IN_STORE",
        address: dict[str, str] | None = None,
        on_request: Callable[[str, int], None] | None = None,
    ):
        self.listings = listings
        self.location_id = location_id
        self.fulfillment = fulfillment
        self.modality = modality
        self.address = address
        self.on_request = on_request
        self.plan: dict[tuple[str, int], list[str]] = {}
        self.asked: list[tuple[str, int]] = []
        self.requests: list[dict[str, Any]] = []
        self.totals: dict[str, int] = {}
        self.available: dict[str, int] = {}
        self.children: dict[str, list[dict[str, Any]]] = {}
        self.brands: dict[str, list[dict[str, Any]]] = {}
        self.sponsored: dict[tuple[str, int], tuple[syn.Product, ...]] = {}

    def on(self, listing: str, page: int, *behaviour: str) -> None:
        self.plan.setdefault((listing, page), []).extend(behaviour)

    def _departments(self, key: str) -> list[dict[str, Any]] | None:
        kids = self.children.get(key)
        if kids is None:
            return None
        return [{"id": key[:2], "name": "D", "categories": [{"id": key, "name": "L", "subcategories": kids}]}]

    def _html(self, key: str, page: int, what: str) -> str:
        items = self.listings.get(key, [])
        total = self.totals.get(key, len(items))
        taxonomy = key.split("~", 1)[0]
        start = (page - 1) * SIZE
        rows = items[start : start + SIZE]
        first = items[:SIZE]
        kw: dict[str, Any] = {
            "page_number": page,
            "taxonomy_id": taxonomy,
            "available": self.available.get(key),
            "departments": self._departments(key),
            "brands": self.brands.get(key),
            "location_id": self.location_id,
            "modality": self.modality,
        }
        if self.address:  # the selected store the page shows: name, address line, postal code
            kw.update(
                store_name=self.address["name"],
                store_address=self.address["addressLine1"],
                store_postal=self.address["zip"],
            )
        if what == "repeat":
            rows = first
        elif what == "reorder":
            rows = list(reversed(first))
        elif what == "overlap":
            rows = first[: SIZE // 2] + rows[: SIZE // 2]
        elif what == "empty":
            rows = []
        elif what == "wrong_store":
            kw["location_id"] = "53100511"
        elif what == "wrong_fulfillment":
            kw["modality"] = "SHIP" if self.modality != "SHIP" else "PICKUP"
        elif what == "wrong_page":
            kw["page_number"] = 1
        elif what == "wrong_listing":
            kw["taxonomy_id"] = "99999"
        elif what == "no_metadata":
            kw["page_number"] = None
        elif what == "no_cards":
            kw["show_cards"] = False
        elif what == "total_up":
            self.totals[key] = total = total + 3
        ranks = {p.upc: start + i + 1 for i, p in enumerate(rows)}
        placed = self.sponsored.get((key, page), ())
        ranks.update({p.upc: 0 for p in placed if p.upc not in ranks})
        shown = [(p, taxonomy) for p in (*placed, *rows)]
        return syn.search_page(BASE, tuple(shown), query="", total=total, ranks=ranks, **kw)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append(body)
        n = len(self.requests)
        url = body.get("url", "")
        if request.url.path.endswith(
            "/search"
        ):  # the first page of a search, as release 1.7.0rc2 read a listing
            key = next(iter(self.listings))
            self.asked.append((key, 1))
            html = self._html(key, 1, "ok")
        elif "/search?" in url:  # that release's once-per-run page-2 check: page 1 again
            html = self._html(next(iter(self.listings)), 1, "ok")
        elif url.endswith("/robots.txt"):
            html = ROBOTS
        elif "/savings/cl/coupons" in url:
            html = syn.coupons_page(1)
        else:
            parts = urlsplit(url)
            query = parse_qs(parts.query)
            listing = parts.path.rstrip("/").rsplit("/", 1)[-1]
            key = f"{listing}~{query['brandName'][0]}" if "brandName" in query else listing
            page = int(query.get("page", ["1"])[0])
            assert "pzn" not in query, url  # one ordering for every page of a read
            assert body["store_id"] == self.location_id and body["fulfillment_type"] == self.fulfillment
            assert body.get("run_js") is True, url
            self.asked.append((key, page))
            if self.on_request is not None:
                self.on_request(key, page)
            todo = self.plan.get((key, page))
            what = todo.pop(0) if todo else "ok"
            if what == "fail":
                return httpx.Response(500, json={"detail": "REQUEST_FAILED_AFTER_TOO_MANY_RETRIES"})
            if what == "blocked":
                return httpx.Response(
                    200,
                    json={
                        "status": "done",
                        "results": [
                            {
                                "html": "<html><title>Access Denied</title></html>",
                                "metadata": {"status_code": 403},
                            }
                        ],
                        "metadata": {"request_id": f"req-{n}"},
                    },
                )
            html = self._html(key, page, what)
        return httpx.Response(
            200,
            json={
                "status": "done",
                "results": [{"html": html, "metadata": {"status_code": 200}}],
                "metadata": {"request_id": f"req-{n}", "timestamp": "2026-11-02T06:00:00Z"},
            },
        )


def plan_nodes(ids: dict[int, str], listings: Iterable[str]) -> list[Any]:
    from marianos_headless.collection.nodes import Node

    return [Node(12, "Breakfast", ids[12], f"Listing {x}", x, f"{BASE}/pl/listing-{x}/{x}") for x in listings]


def _killed(args: dict[str, Any]) -> None:
    """A worker that dies on purpose, in another process."""
    from pydantic import SecretStr
    from sqlalchemy import create_engine

    from marianos_headless.collection.config import CollectionConfig
    from marianos_headless.collection.oxylabs_live import OxylabsCollector
    from marianos_headless.core.settings import (
        AcquisitionSettings,
        BrowserProvider,
        Settings,
        load_private_label,
        load_stores,
    )
    from marianos_headless.storage.local import LocalStorageAdapter
    from marianos_headless.worker import runner
    from marianos_headless.worker.pipeline import Pipeline

    config = Path(args["config"])
    engine = create_engine(args["db"])
    store = next(s for s in load_stores(config / "stores.yaml").stores if s.key == args["store"])
    pipe = Pipeline(
        engine,
        LocalStorageAdapter(Path(args["data"])),
        Settings(acquisition=AcquisitionSettings(browser_provider=BrowserProvider.OXYLABS)),
        store,
        load_private_label(config / "private_label_brands.yaml"),
    )
    die_at = (args["listing"], int(args["page"]))

    def on_request(key: str, page: int) -> None:
        if args["moment"] == "request" and (key, page) == die_at:
            os._exit(137)  # the request is out, its reservation is in the ledger, nothing came back

    if args["moment"] == "checkpoint":
        real = runner.TaskContext.checkpoint

        def checkpoint(self: Any, cursor: Any, *a: Any, **k: Any) -> Any:
            if cursor.get("extra", {}).get("pages_read") == die_at[1]:
                os._exit(137)  # the page and its products are committed, the checkpoint is not
            return real(self, cursor, *a, **k)

        runner.TaskContext.checkpoint = checkpoint  # type: ignore[method-assign]

    site = Site(
        args["listings_n"] and {k: products(v) for k, v in args["listings_n"].items()}, on_request=on_request
    )

    async def nap(_: float) -> None:
        return None

    collector = OxylabsCollector(
        pipe,
        args["run"],
        api_key=SecretStr(KEY),
        transport=httpx.MockTransport(site),
        sleep=nap,
        config=CollectionConfig(),
        trigger="manual",
    )
    asyncio.run(pipe.execute(args["run"], "doomed-worker", collector=collector))
    os._exit(0)  # it was meant to die before this


def _killed_publishing(args: dict[str, Any]) -> None:
    """A publication that dies on purpose, inside its database transaction or just after it."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from marianos_headless.publishing.publish import publish_run
    from marianos_headless.storage.local import LocalStorageAdapter

    def fault(stage: str) -> None:
        if stage == args["stage"]:
            os._exit(137)

    publish_run(
        sessionmaker(create_engine(args["db"]), expire_on_commit=False),
        LocalStorageAdapter(Path(args["data"])),
        args["run"],
        "doomed-publisher",
        fault=fault,
    )
    os._exit(0)  # it was meant to die before this


if __name__ == "__main__":
    job = json.loads(sys.argv[1])
    if job.get("publish"):
        _killed_publishing(job)
    _killed(job)
