"""OR-20 (release 1.10.0rc6): ``validate-export --run`` reads a run's stored sources one at a time, with
bounded memory, and checks every exported record's capture and source values.

Run F2 (1.10.0rc5, 2026-11-16) was validated on the operator's VM after its stop: the command read all 575
stored listing pages into memory before indexing any of them and was killed for lack of memory (about 3.3 GiB
of a 3.8 GiB VM without swap). These tests drive the command over a synthetic run (``tests/c1_site.py``: pages
behind a local mock transport, nothing reaches a provider) on a throwaway PostgreSQL.

Tests named ``test_or20_...`` state what 1.10.0rc6 adds and fail on 1.10.0rc5; ``test_control_...`` state
what must hold before and after."""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import Engine, select, update

from marianos_headless import operations
from marianos_headless.checks import source_check
from marianos_headless.core.settings import PrivateLabelConfig, Settings
from marianos_headless.db.models import Artifact, ExportRow, PageFetch
from tests import c1_site as c1
from tests.c1_site import C1Site, Clock
from tests.listing_site import products

pytestmark = [pytest.mark.postgres]


@pytest.fixture
def env(migrated_engine: Engine, tmp_path: Path, private_label: PrivateLabelConfig) -> dict[str, Any]:
    return c1.make_env(migrated_engine, tmp_path, private_label)


def _validated_run(env: dict[str, Any], settings: Settings) -> str:
    clock = Clock()
    site = C1Site({"03001": products(60)}, clock)
    run_id, status = c1.run(env, settings, site, clock)
    assert status == "validated", status
    return run_id


def _validate(env: dict[str, Any], run_id: str, storage: Any = None) -> tuple[int, dict[str, Any]]:
    ctx = SimpleNamespace(factory=env["factory"], storage=storage or env["storage"])
    code, report = operations.validate_export(ctx, None, run_id)  # type: ignore[arg-type]
    return int(code), report


def _page_keys(env: dict[str, Any], run_id: str) -> dict[str, str]:
    """The run's stored listing pages: page address -> storage key."""
    with env["factory"]() as s:
        return {
            url: key
            for url, key in s.execute(
                select(PageFetch.url, Artifact.key)
                .join(Artifact, PageFetch.dom_artifact_id == Artifact.id)
                .where(PageFetch.run_id == run_id, PageFetch.purpose == "listing")
            )
        }


def _rewrite_export(env: dict[str, Any], run_id: str, name: str, data: bytes) -> None:
    """Replace one exported file and re-seal it: the manifest states the new file's hash and size, and the
    run's record of the manifest the manifest's new hash. Only the file's content then differs."""
    root = env["tmp"] / "data"
    with env["factory"]() as s:
        manifest = s.scalar(
            select(Artifact)
            .join(ExportRow, ExportRow.artifact_id == Artifact.id)
            .where(ExportRow.run_id == run_id, ExportRow.kind == "manifest")
        )
        assert manifest is not None
        body = json.loads((root / manifest.key).read_bytes())
        entry = body["files"][name]
        (root / entry["key"]).write_bytes(data)
        entry.update(sha256=hashlib.sha256(data).hexdigest(), size=len(data))
        sealed = json.dumps(body, indent=2).encode("utf-8")
        (root / manifest.key).write_bytes(sealed)
        s.execute(
            update(Artifact)
            .where(Artifact.id == manifest.id)
            .values(sha256=hashlib.sha256(sealed).hexdigest())
        )
        s.commit()


class _Recorder:
    """The run's storage, noting each read of a stored listing page."""

    def __init__(self, inner: Any, pages: set[str], log: list[tuple[str, str]]) -> None:
        self.inner, self.pages, self.log = inner, pages, log

    def get_bytes(self, key: str) -> bytes:
        if key in self.pages:
            self.log.append(("read", key))
        return bytes(self.inner.get_bytes(key))

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)


def test_or20_validate_export_reads_each_stored_page_before_the_next_and_checks_every_records_capture(
    env: dict[str, Any], settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Expected to FAIL on 1.10.0rc5 (it reads every page before reading the product data of any, and has
    no capture check). Each stored page is read, and its product data taken, before the next page is read;
    every exported record's capture, as the published supporting log names it, is a stored page with that
    SHA-256."""
    run_id = _validated_run(env, settings)
    keys = set(_page_keys(env, run_id).values())
    assert len(keys) == 3
    log: list[tuple[str, str]] = []
    real = source_check.embedded_products

    def noted(html: str) -> list[dict[str, Any]]:
        found = real(html)
        log.append(("parsed", str(len(found))))
        return found

    monkeypatch.setattr(source_check, "embedded_products", noted)
    code, report = _validate(env, run_id, _Recorder(env["storage"], keys, log))
    kinds = [k for k, _ in log]
    assert kinds == ["read", "parsed"] * 3, kinds
    assert code == 6 and report["contract"]["problems"] == {"image host": 60}  # the mock site's picture host
    assert report["source_check"]["summary"]["verified"] == 60
    caps = report["captures"]
    counts = (caps["ok"], caps["missing"], caps["corrupted"], caps["unreadable"], caps["not_named"])
    assert counts == (60, 0, 0, 0, 0), caps
    assert report["resources"]["sources_read"] >= 3 and report["mismatches"]["total"] == 0


def test_or20_a_stored_page_missing_or_altered_after_the_run_rejects_its_export_and_names_the_records(
    env: dict[str, Any], settings: Settings
) -> None:
    """Expected to FAIL on 1.10.0rc5 (a missing page stops the command with an exception; an altered
    page's records are only reported unverified). A record whose capture is gone is ``missing``; one whose
    capture's bytes no longer have the hash the run recorded is ``corrupted``; both are named and the export
    rejected. (The run's stored product responses still state every record's prices: the source values are
    verified from them.)"""
    run_id = _validated_run(env, settings)
    pages = _page_keys(env, run_id)
    root = env["tmp"] / "data"
    two = next(k for u, k in pages.items() if u.endswith("page=2"))
    three = next(k for u, k in pages.items() if u.endswith("page=3"))
    (root / two).unlink()
    html = gzip.decompress((root / three).read_bytes()).decode("utf-8")
    (root / three).write_bytes(gzip.compress(html.replace("</body>", "<!-- altered --></body>").encode()))
    code, report = _validate(env, run_id)
    assert code == 6
    caps = report["captures"]
    assert (caps["ok"], caps["missing"], caps["corrupted"]) == (24, 24, 12), caps
    assert {p["key"] for p in caps["problems"]} == {two, three} and caps["problems_total"] == 36


def _priced_record(env: dict[str, Any], run_id: str) -> tuple[list[dict[str, Any]], int]:
    root = env["tmp"] / "data"
    [key] = [k for k in _keys_of(env, run_id) if k.endswith("/products.json")]
    records = json.loads((root / key).read_bytes())
    i = next(i for i, r in enumerate(records) if r.get("regular_price"))
    return records, i


def _keys_of(env: dict[str, Any], run_id: str) -> list[str]:
    root = env["tmp"] / "data"
    return [str(p.relative_to(root).as_posix()) for p in root.rglob("*") if run_id in p.as_posix()]


def test_control_a_record_whose_price_differs_from_its_stored_page_is_a_mismatch(
    env: dict[str, Any], settings: Settings
) -> None:
    """Before and after 1.10.0rc6: a record whose regular price differs from the price the stored page's own
    data states for the store is a mismatch, and the export is rejected. The products file is re-sealed in its
    manifest, so only the value differs."""
    run_id = _validated_run(env, settings)
    records, i = _priced_record(env, run_id)
    records[i]["regular_price"] = f"{float(records[i]['regular_price']) + 1:.2f}"
    _rewrite_export(env, run_id, "products.json", json.dumps(records, indent=2).encode("utf-8"))
    code, report = _validate(env, run_id)
    assert code == 6 and report["manifest"]["problems"] == []
    assert report["source_check"]["summary"]["mismatch"] == 1


def test_or20_a_mismatch_names_the_record_its_values_and_the_stored_page_that_states_otherwise(
    env: dict[str, Any], settings: Settings
) -> None:
    """Expected to FAIL on 1.10.0rc5 (it reports a count of mismatches by field, not the records). Each
    mismatch names the record, the values it states, the values its stored source states and that source."""
    run_id = _validated_run(env, settings)
    records, i = _priced_record(env, run_id)
    stated = records[i]["regular_price"]
    records[i]["regular_price"] = f"{float(stated) + 1:.2f}"
    _rewrite_export(env, run_id, "products.json", json.dumps(records, indent=2).encode("utf-8"))
    code, report = _validate(env, run_id)
    assert code == 6
    [m] = report["mismatches"]["first_200"]
    assert m["upc"] == records[i]["upc"] and m["mismatched_fields"] == ["regular_price"]
    assert m["record_values"]["regular_price"] == records[i]["regular_price"]
    assert m["source_values"]["store"] and float(m["source_values"]["regular"]) == float(stated)
    # the stored source that states it: the run's product response, preferred to the page's embedded data
    assert m["source"].startswith(f"runs/{env['store'].key}/{run_id}/live/")
