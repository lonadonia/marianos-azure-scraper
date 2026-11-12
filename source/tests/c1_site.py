"""What the C1 cases share (release 1.10.0): the SYNTHETIC site of ``tests/listing_site.py`` at the client's
store (53100502, Pickup) with two more behaviours, a fake clock, a replay of saved answers, and a run driven
through the collector's public path (``Pipeline.execute``). Nothing leaves the process.

Written to load on 1.9.0rc4 as well as on 1.10: the same case files then run on both, and what C1 adds shows
as the tests that fail there. On 1.9.0rc4 the limits and the queue timer of C1 do not exist, so they are left
out (:data:`C1`), and no request is ever asked again.

Run as a module it is a worker that dies on purpose while a chosen request is out (``os._exit``, as a forced
kill): ``python -m tests.c1_site <json>``.
"""

from __future__ import annotations

import asyncio
import gzip
import json
import os
import sys
from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from pathlib import Path
from typing import Any

import httpx
from pydantic import SecretStr
from sqlalchemy import Engine, create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from marianos_headless import __version__
from marianos_headless.acquisition import oxylabs
from marianos_headless.collection.config import CollectionConfig, Limits
from marianos_headless.collection.oxylabs_live import OxylabsCollector
from marianos_headless.core.settings import (
    AcquisitionSettings,
    BrowserProvider,
    OxylabsSettings,
    PrivateLabelConfig,
    Settings,
    StoreConfig,
    load_private_label,
    load_settings,
    load_stores,
)
from marianos_headless.core.version import source_version
from marianos_headless.db.models import (
    CategorySource,
    ListingPage,
    NodeCoverage,
    ProviderUsage,
    PublicationPointer,
    RecordRow,
    Run,
    Store,
    Task,
)
from marianos_headless.storage.local import LocalStorageAdapter
from marianos_headless.worker.pipeline import Pipeline
from tests.listing_site import KEY, ROBOTS, Site, plan_nodes

try:  # 1.10: the task queue's clock and wait
    from marianos_headless.worker.runner import Timer
except ImportError:  # 1.9.0rc4
    Timer = None  # type: ignore[assignment,misc]

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config"
FIXTURES = ROOT / "tests" / "fixtures"
TARGET = "marianos-53100502-pickup"
VERNON = {"name": "Marianos Vernon Hills", "addressLine1": "1720 N Milwaukee Ave", "zip": "60061"}
START = datetime(2026, 11, 9, 16, 0, tzinfo=UTC)
WAIT_S = 300
# True when this build has C1 (the limits exist); False on 1.9.0rc4.
C1 = "max_reasks_per_request" in Limits.model_fields
SYNTHETIC = "SYNTHETIC pages (tests/listing_site.py, tests/c1_site.py) behind a local mock transport"
REPLAY = "OFFLINE REPLAY of answers saved by the live stages of 2026-11-09, behind a local mock transport"


class Clock:
    """A clock that moves only when something waits on it."""

    def __init__(self, start: datetime = START):
        self.t = start
        self.slept = 0.0
        self.on_sleep: Callable[[], None] | None = None

    def now(self) -> datetime:
        return self.t

    async def sleep(self, seconds: float) -> None:
        self.t += timedelta(seconds=max(0.0, float(seconds)))
        self.slept += max(0.0, float(seconds))
        if self.on_sleep is not None:
            self.on_sleep()


class C1Site(Site):
    """The synthetic site at Vernon Hills, Pickup. More behaviours of a ``(listing, page)``:

    ``no_facets``: the answer names no child listing and no brand (the page is otherwise as asked);
    ``page_2_instead``: the answer is the listing's page 2 (for a first page asked again).
    Every listing request is noted with the clock's time."""

    def __init__(self, listings: dict[str, list[Any]], clock: Clock | None = None, **kw: Any):
        super().__init__(
            listings,
            location_id="53100502",
            fulfillment="pickup",
            modality="PICKUP",
            address=VERNON,
            on_request=self._note,
            **kw,
        )
        self.clock = clock or Clock()
        self.asked_at: list[tuple[str, int, datetime]] = []
        self.before_answer: Callable[[str, int, int], None] | None = None

    def _note(self, key: str, page: int) -> None:
        self.asked_at.append((key, page, self.clock.now()))
        if self.before_answer is not None:
            self.before_answer(key, page, self.times(key, page))

    def times(self, key: str, page: int) -> int:
        return sum(1 for k, p, _ in self.asked_at if (k, p) == (key, page))

    def gaps(self, key: str, page: int) -> list[float]:
        at = [t for k, p, t in self.asked_at if (k, p) == (key, page)]
        return [(b - a).total_seconds() for a, b in pairwise(at)]

    def _html(self, key: str, page: int, what: str) -> str:
        if what == "no_facets":
            kids, brands = self.children.pop(key, None), self.brands.pop(key, None)
            try:
                return super()._html(key, page, "ok")
            finally:
                if kids is not None:
                    self.children[key] = kids
                if brands is not None:
                    self.brands[key] = brands
        if what == "page_2_instead":
            return super()._html(key, 2, "ok")
        return super()._html(key, page, what)


class Replay:
    """Saved answers served again, in the order given for each address; an address with nothing left to
    serve gets the provider's documented free failure (the fixture holds no answer for it). The store and
    fulfillment of every request are checked."""

    def __init__(self, pages: dict[str, list[Path]], clock: Clock | None = None):
        self.pages = {url: list(files) for url, files in pages.items()}
        self.clock = clock or Clock()
        self.requests: list[dict[str, Any]] = []
        self.asked_at: list[tuple[str, datetime, str]] = []

    def times(self, url: str) -> int:
        return sum(1 for u, _, _ in self.asked_at if u == url)

    def gaps(self, url: str) -> list[float]:
        at = [t for u, t, _ in self.asked_at if u == url]
        return [(b - a).total_seconds() for a, b in pairwise(at)]

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append(body)
        url = body["url"]
        n = len(self.requests)
        if url.endswith("/robots.txt"):
            html = ROBOTS
        elif self.pages.get(url):
            assert body["store_id"] == "53100502" and body["fulfillment_type"] == "pickup", body
            assert "run_js" not in body, body  # listing pages are asked without rendering since 1.9.0rc2
            src = self.pages[url].pop(0)
            self.asked_at.append((url, self.clock.now(), src.name))
            html = gzip.decompress(src.read_bytes()).decode("utf-8")
        else:
            if url in self.pages:
                self.asked_at.append((url, self.clock.now(), "(nothing left to serve)"))
            return httpx.Response(500, json={"detail": "REQUEST_FAILED_AFTER_TOO_MANY_RETRIES"})
        return httpx.Response(
            200,
            json={
                "status": "done",
                "results": [{"html": html, "metadata": {"status_code": 200, "run_js": False}}],
                "metadata": {"request_id": f"replay-{n}", "timestamp": "2026-11-09T16:00:00Z"},
            },
        )


# -- a run through the public path ---------------------------------------------------------------------------


def target_store() -> StoreConfig:
    return next(s for s in load_stores(CONFIG / "stores.yaml").stores if s.key == TARGET)


def make_env(
    engine: Engine, tmp: Path, private_label: PrivateLabelConfig, ceiling: int = 400
) -> dict[str, Any]:
    from tests.integration.helpers import seed

    factory, _ = seed(engine)
    with factory() as s:
        oxylabs.set_ceiling(s, submissions=ceiling, usd=10, actor="test", reason="test")
        s.commit()
    return {
        "engine": engine,
        "factory": factory,
        "storage": LocalStorageAdapter(tmp / "data"),
        "store": target_store(),
        "private_label": private_label,
        "tmp": tmp,
    }


def pipe_of(env: dict[str, Any], settings: Settings) -> Pipeline:
    acq = AcquisitionSettings(browser_provider=BrowserProvider.OXYLABS, oxylabs=OxylabsSettings())
    return Pipeline(
        env["engine"],
        env["storage"],
        Settings(acquisition=acq, records=settings.records, attestation=settings.attestation),
        env["store"],
        env["private_label"],
    )


def plan(
    env: dict[str, Any],
    pipe: Pipeline,
    nodes: Iterable[Any],
    *,
    trigger: str = "console",
    occurrence: dict[str, str] | None = None,
) -> str:
    nodes = list(nodes)
    snapshot: dict[str, Any] = {
        "plan": {"nodes": [n.as_dict() for n in nodes], "skipped": []},
        "started_by": "test",
        "provider": "oxylabs",
    }
    if occurrence is not None:
        snapshot["occurrence"] = occurrence
    with env["factory"]() as s:
        run_id = pipe.create_live_run(s, nodes, trigger=trigger, snapshot=snapshot)
        s.commit()
    return str(run_id)


def nodes_of(env: dict[str, Any], listings: Iterable[str]) -> list[Any]:
    with env["factory"]() as s:
        ids = {c.csv_row_index: c.id for c in s.scalars(select(CategorySource))}
    return plan_nodes(ids, listings)


def limits_of(**values: Any) -> Limits:
    """The limits a case asks for; those this build does not know (C1's, on 1.9.0rc4) are left out."""
    return Limits(**{k: v for k, v in values.items() if k in Limits.model_fields})


async def _no_sleep(_: float) -> None:
    return None


def collector_of(
    pipe: Pipeline,
    run_id: str,
    handler: Any,
    clock: Clock,
    *,
    lanes: int = 1,
    max_reasks: int | None = 2,
    trigger: str = "manual",
    **limits: Any,
) -> OxylabsCollector:
    kw: dict[str, Any] = {}
    if Timer is not None:
        kw["timer"] = Timer(clock.now, clock.sleep)
    return OxylabsCollector(
        pipe,
        run_id,
        api_key=SecretStr(KEY),
        transport=httpx.MockTransport(handler),
        sleep=_no_sleep,
        clock=clock.now,
        config=CollectionConfig(
            limits=limits_of(
                max_concurrent_listings=lanes,
                max_reasks_per_request=max_reasks,
                reask_min_wait_seconds=WAIT_S if max_reasks else None,
                **limits,
            )
        ),
        trigger=trigger,
        **kw,
    )


def run(
    env: dict[str, Any],
    settings: Settings,
    handler: Any,
    clock: Clock,
    *,
    listings: tuple[str, ...] = ("03001",),
    nodes: list[Any] | None = None,
    run_id: str | None = None,
    **options: Any,
) -> tuple[str, str]:
    """A run (or, with ``run_id``, its resume) to wherever it ends."""
    pipe = pipe_of(env, settings)
    resume = run_id is not None
    if run_id is None:
        run_id = plan(env, pipe, nodes if nodes is not None else nodes_of(env, listings))
    collector = collector_of(pipe, run_id, handler, clock, **options)
    status = asyncio.run(pipe.execute(run_id, "test-collector", resume=resume, collector=collector))
    return run_id, str(status)


# -- what a run left, read from the database -----------------------------------------------------------------


def deferred(s: Session, run_id: str) -> list[dict[str, Any]]:
    """The requests the run set aside (none on a build without C1: the table does not exist)."""
    if not C1:
        return []
    rows = s.execute(
        text(
            "SELECT taxonomy_id, requested_page, kind, state, reasks_dispatched, max_reasks, min_wait_s, "
            "original_verdict, original_reason, original_listing_page_id, outcome, attempts, url, "
            "requested_filter, store_context FROM deferred_requests WHERE run_id = :r "
            "ORDER BY taxonomy_id, requested_page"
        ),
        {"r": run_id},
    ).mappings()
    return [dict(r) for r in rows]


def observe(env: dict[str, Any], run_id: str, listing: str = "03001") -> dict[str, Any]:
    """The persisted state a case is judged on."""
    with env["factory"]() as s:
        run = s.get(Run, run_id)
        assert run is not None
        pages = [
            {
                "listing": p.taxonomy_id,
                "page": p.requested_page,
                "attempt": p.attempt,
                "state": p.state,
                "verdict": p.verdict,
                "new": p.new_count,
                "duplicates": p.duplicates,
                "identities": len(p.identities or []),
                "sha256": p.response_sha256,
                "request_id": p.provider_request_id,
                "stored_page": p.page_fetch_id is not None,
                "id": p.id,
            }
            for p in s.scalars(
                select(ListingPage)
                .where(ListingPage.run_id == run_id)
                .order_by(ListingPage.taxonomy_id, ListingPage.requested_page, ListingPage.attempt)
            )
        ]
        records = list(s.scalars(select(RecordRow).where(RecordRow.run_id == run_id)))
        cov = s.scalar(
            select(NodeCoverage).where(NodeCoverage.run_id == run_id, NodeCoverage.taxonomy_id == listing)
        )
        usage = [
            (u.target, u.state, u.cost_source, u.outcome)
            for u in s.scalars(
                select(ProviderUsage)
                .where(ProviderUsage.run_id == run_id)
                .order_by(ProviderUsage.reserved_at)
            )
        ]
        store = s.scalar(select(Store).where(Store.key == TARGET))
        pointer = s.get(PublicationPointer, store.id) if store is not None else None
        tasks = {
            str((t.cursor or {}).get("node", {}).get("taxonomy_id")): t.state
            for t in s.scalars(select(Task).where(Task.run_id == run_id, Task.kind == "listing_node"))
        }
        upcs = [r.upc for r in records]
        return {
            "collector_version": __version__,
            "source_revision": source_version(),
            "c1_in_this_build": C1,
            "run_status": run.status,
            "stop_code": run.stop_code,
            "gates": dict((run.counts or {}).get("gates") or {}),
            "pages": pages,
            "records": len(upcs),
            "distinct_records": len(set(upcs)),
            "records_by_status": dict(sorted(_count(r.status for r in records).items())),
            "coverage": None
            if cov is None
            else {
                "status": cov.status,
                "seen": cov.organic_upcs,
                "total": cov.total_count,
                "reason": (cov.partition or {}).get("reason", ""),
            },
            "listing_tasks": tasks,
            "deferred_requests": deferred(s, run_id),
            "ledger_rows": len(usage),
            "ledger": usage,
            "published_pointer": None
            if pointer is None
            else {"publication_id": pointer.publication_id, "version": pointer.version},
        }


def _count(values: Iterable[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for v in values:
        out[v] = out.get(v, 0) + 1
    return out


def evidence(case: str, kind: str, data: dict[str, Any]) -> None:
    """With ``C1_EVIDENCE_DIR`` set, what the case observed is written there before it is judged, so the
    same case leaves its record on a build where it fails."""
    out = os.environ.get("C1_EVIDENCE_DIR")
    if not out:
        return
    Path(out).mkdir(parents=True, exist_ok=True)
    body = {
        "case": case,
        "evidence_type": kind,
        "live_request_sent": False,
        "collector_version": __version__,
        "source_revision": source_version(),
        "c1_in_this_build": C1,
        **data,
    }
    name = "".join(c if c.isalnum() or c in "-_" else "_" for c in case)[:150]
    (Path(out) / f"{name}.json").write_bytes(
        (json.dumps(body, indent=1, default=str, ensure_ascii=False) + "\n").encode("utf-8")
    )


# -- a worker that dies on purpose ---------------------------------------------------------------------------


def _killed(args: dict[str, Any]) -> None:
    from tests.listing_site import products

    engine = create_engine(args["db"])
    settings = load_settings(CONFIG / "settings.yaml")
    env = {
        "engine": engine,
        "factory": sessionmaker(engine, expire_on_commit=False),
        "storage": LocalStorageAdapter(Path(args["data"])),
        "store": target_store(),
        "private_label": load_private_label(CONFIG / "private_label_brands.yaml"),
    }
    clock = Clock(datetime.fromisoformat(args["now"]))
    site = C1Site({k: products(*v) for k, v in args["listings"].items()}, clock)
    for (listing, page), todo in ((tuple(k.split("|")), v) for k, v in (args.get("plan") or {}).items()):
        site.on(listing, int(page), *todo)
    die = (args["listing"], int(args["page"]), int(args["nth"]))

    def before(key: str, page: int, nth: int) -> None:
        if (key, page, nth) == die:
            os._exit(137)  # the request is out, its reservation is in the ledger, nothing came back

    site.before_answer = before
    pipe = pipe_of(env, settings)
    collector = collector_of(pipe, args["run"], site, clock, max_reasks=args.get("max_reasks", 2))
    asyncio.run(pipe.execute(args["run"], "doomed-worker", resume=True, collector=collector))
    os._exit(0)  # it was meant to die before this


if __name__ == "__main__":
    _killed(json.loads(sys.argv[1]))
