"""Safe publication through the real pipeline and its after-run publication path (SYNTHETIC pages on the
local mock site, a local Chromium standing in for Scrapfly's cloud browser, injected faults; nothing
reaches Scrapfly or Mariano's).

Each test runs in its own throwaway database and data folder: an isolated namespace that cannot touch an
operational dataset. A complete run of the store's configured scope (Grocery › Canned Foods on the mock
site, set in collector.yaml: not a pilot) is published first; a later run that is stopped part-way and
finalized, refused by the site, shown for another store, empty or suspiciously thin must not replace it.
The finalized, empty and thin runs are assembled with the earlier run's products carried forward into
their export, and are refused all the same: carry-forward never hides missing coverage. The publication
pointer, the published bytes (latest.json, the manifest it names and that manifest's products.json) and
the first run's product observations are compared before and after. An interrupted publication is
retried once and replaces the dataset atomically. With ``PUBLICATION_EVIDENCE_DIR`` set, each test writes
its before/after hashes there as JSON (the delivery's evidence of these checks).
"""

from __future__ import annotations

import hashlib
import json
import os
import signal
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any, ClassVar

import pytest
import yaml
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from marianos_headless import operations
from marianos_headless.db.models import ProductObservation, Publication, PublicationPointer, RecordRow, Store
from tests import synthetic_marianos as syn
from tests.conftest import STORE_KEY
from tests.integration import test_live_collector as mock
from tests.integration.test_live_collector import cloud_browser  # noqa: F401  (a fixture)
from tests.integration.test_operations import Env, _serve, env  # noqa: F401  (env is a fixture)

pytestmark = [pytest.mark.postgres, pytest.mark.browser, mock.requires_chromium]


class Fault:
    """The mock site's behaviour for the next requests (set between runs)."""

    mode: ClassVar[str] = "ok"
    signalled: ClassVar[list[str]] = []


def _handler() -> type[BaseHTTPRequestHandler]:
    base = mock.make_handler("ok")

    class H(base):  # type: ignore[valid-type, misc]
        def _context(self) -> tuple[str, str, str]:
            if Fault.mode == "wrong_store":  # every page shows another store, whatever was selected
                hdr = syn.header(
                    modality_word="Pickup", name="Marianos Frankfort", address="21001 S La Grange Rd"
                )
                return (
                    syn.default_store_state(),
                    hdr + syn.store_picker((mock.OTHER, mock.LAKESHORE)),
                    "53100509",
                )
            ctx: tuple[str, str, str] = super()._context()
            return ctx

        def do_GET(self) -> None:
            if Fault.mode == "site_refusal" and self.path.startswith("/pl/"):
                self._send(403, "<h1>Access Denied</h1>Reference #18.abc.123")
                return
            if Fault.mode == "stopped" and "page.offset=24" in self.path and not Fault.signalled:
                Fault.signalled.append(self.path)  # the first "Load More": the execution is terminated
                signal.raise_signal(signal.SIGTERM)
            super().do_GET()

    return H


@pytest.fixture
def site() -> Iterator[str]:
    Fault.mode, Fault.signalled = "ok", []
    yield from _serve(_handler())


def _scope(e: Env) -> None:
    """The store's configured scope (collector.yaml, not the command line): Grocery › Canned Foods."""
    data = yaml.safe_load(e.config.read_text(encoding="utf-8"))
    coll = data["collections"][STORE_KEY]
    coll["categories"], coll["subcategories"] = [7], {"7": ["01006"]}
    e.config.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _auto_publish(e: Env, on: bool) -> None:
    data = yaml.safe_load(e.config.read_text(encoding="utf-8"))
    data["publish"]["auto"] = on
    e.config.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def snapshot(e: Env, first_run: str) -> dict[str, Any]:
    """The published state: pointer, publication rows, latest.json, the manifest it names and that
    manifest's products.json, and the first run's observations."""
    factory = sessionmaker(e.engine, expire_on_commit=False)
    with factory() as s:
        store = s.scalar(select(Store).where(Store.key == STORE_KEY))
        assert store is not None
        ptr = s.get(PublicationPointer, store.id)
        pubs = int(s.scalar(select(func.count()).select_from(Publication)) or 0)
        obs = sorted(
            (o.upc, o.observed_at.isoformat(), json.dumps(o.provenance, sort_keys=True, default=str))
            for o in s.scalars(select(ProductObservation).where(ProductObservation.run_id == first_run))
        )
        recs = sorted(
            (r.upc, r.status, r.record_sha256)
            for r in s.scalars(select(RecordRow).where(RecordRow.run_id == first_run))
        )
    latest = (e.data / "published" / STORE_KEY / "latest.json").read_bytes()
    body = json.loads(latest)
    manifest = (e.data / body["manifest_key"]).read_bytes()
    assert _sha(manifest) == body["manifest_sha256"]
    products = (e.data / json.loads(manifest)["files"]["products.json"]["key"]).read_bytes()
    return {
        "pointer": {
            "publication_id": ptr.publication_id if ptr else None,
            "version": ptr.version if ptr else None,
        },
        "publications": pubs,
        "published_run": body.get("run_id"),
        "latest_json_sha256": _sha(latest),
        "manifest_sha256": _sha(manifest),
        "products_sha256": _sha(products),
        "published_products": len(json.loads(products)),
        "first_run_observations_sha256": _sha(json.dumps(obs).encode()),
        "first_run_records_sha256": _sha(json.dumps(recs).encode()),
        "first_run_observations": len(obs),
    }


def _evidence(name: str, data: dict[str, Any]) -> None:
    out = os.environ.get("PUBLICATION_EVIDENCE_DIR")
    if out:
        Path(out).mkdir(parents=True, exist_ok=True)
        (Path(out) / f"{name}.json").write_text(json.dumps(data, indent=1, default=str), encoding="utf-8")


def _first(e: Env) -> str:
    _scope(e)
    code, lines = e.cli("run", "--store", STORE_KEY)
    first = e.runs()[0]
    assert code == 0 and first.status == "published", (
        code,
        first.status,
        [(x["event"], x.get("message", "")[:120]) for x in lines if x.get("level") != "INFO"],
    )
    assert not first.config_snapshot["pilot"]
    return first.id


FAULTS = ("stopped_and_finalized", "site_refusal", "wrong_store", "empty", "thin")
CARRIES_FORWARD = ("stopped_and_finalized", "empty", "thin")  # assembled: the export holds carried rows


@pytest.mark.parametrize("fault", FAULTS)
def test_a_published_dataset_is_never_replaced_by_a_run_that_fails_its_checks(
    env: Env,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    first = _first(env)
    before = snapshot(env, first)
    title, products = mock.CATALOG["01006"]
    if fault == "stopped_and_finalized":
        Fault.mode = "stopped"
    elif fault in ("site_refusal", "wrong_store"):
        Fault.mode = fault
    elif fault == "empty":
        monkeypatch.setitem(mock.CATALOG, "01006", (title, ()))
    elif fault == "thin":  # all but five products gone: far below the last complete run
        monkeypatch.setitem(mock.CATALOG, "01006", (title, products[:5]))
    code2, _ = env.cli("run", "--store", STORE_KEY)
    finalize = None
    if fault == "stopped_and_finalized":
        assert code2 == 75 and env.runs()[-1].status == "interrupted"
        finalize, _ = env.cli("finalize", "--store", STORE_KEY)  # an operator closes the unfinished run
        assert finalize == 6  # a closed run reports its outcome, never the resumable code (75)
    second = env.runs()[-1]
    after = snapshot(env, first)
    with sessionmaker(env.engine, expire_on_commit=False)() as s:
        carried = int(
            s.scalar(
                select(func.count())
                .select_from(RecordRow)
                .where(RecordRow.run_id == second.id, RecordRow.status == "historical")
            )
            or 0
        )
    publish, _ = env.cli("publish", "--run", second.id)  # an explicit publication attempt as well
    after_publish = snapshot(env, first)
    _evidence(
        f"publication_refused_{fault}",
        {
            "fault": fault,
            "synthetic": True,
            "first_run": first,
            "second_run": second.id,
            "second_run_status": second.status,
            "second_run_stop_code": second.stop_code,
            "second_run_exit_code": code2,
            "finalize_exit_code": finalize,
            "publish_attempt_exit_code": publish,
            "second_run_carried_forward_rows": carried,
            "before": before,
            "after": after,
            "after_publish_attempt": after_publish,
            "unchanged": before == after == after_publish,
        },
    )
    assert second.id != first and second.status != "published" and publish != 0
    assert after == before == after_publish  # pointer, publication rows, published bytes, observations
    if fault in CARRIES_FORWARD:
        assert carried > 0  # the earlier run's products filled the export, and still the run was refused


def test_an_interrupted_publication_keeps_the_last_good_dataset_and_one_retry_publishes_atomically(
    env: Env,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _first(env)
    before = snapshot(env, first)
    _auto_publish(env, False)
    code, _ = env.cli("run", "--store", STORE_KEY)
    _auto_publish(env, True)
    second = env.runs()[-1]
    assert code == 0 and second.status == "validated", (code, second.status)
    real = operations.publish_run
    calls = {"n": 0}

    class Crash(Exception):
        pass

    def interrupted(*args: Any, **kwargs: Any) -> Any:
        calls["n"] += 1
        if calls["n"] == 1:

            def fault(stage: str) -> None:
                if stage == "inside_commit":
                    raise Crash(stage)

            return real(*args, **kwargs, fault=fault)
        return real(*args, **kwargs)

    monkeypatch.setattr(operations, "publish_run", interrupted)
    with pytest.raises(Crash):
        operations.after_run(operations.Context(env.config), STORE_KEY, second.id)
    middle = snapshot(env, first)
    assert middle == before and env.runs()[-1].status == "validated"  # nothing half-published
    code, _ = env.result("publish", "--run", second.id)
    after = snapshot(env, first)
    _evidence(
        "publication_interrupted_then_retried",
        {
            "synthetic": True,
            "first_run": first,
            "second_run": second.id,
            "before": before,
            "after_interruption": middle,
            "after_retry": after,
            "retry_exit_code": code,
        },
    )
    assert code == 0 and after["published_run"] == second.id
    assert after["pointer"]["version"] == before["pointer"]["version"] + 1
    assert after["publications"] == before["publications"] + 1  # exactly one new publication, no duplicate
    assert after["first_run_observations_sha256"] == before["first_run_observations_sha256"]
