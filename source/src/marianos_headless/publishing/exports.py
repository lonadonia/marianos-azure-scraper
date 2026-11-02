"""Run exports and manifest.

Files are written under ``runs/<store_key>/<run_id>/exports/``: the products with exactly the 22 fields
(``products.json`` and ``products.csv``: the store's retained dataset, i.e. the products this run observed
and the store's products verified by earlier runs and carried forward unchanged), the products this run
observed itself (``products_fresh.json`` and ``products_fresh.csv``, the same 22 fields), memberships,
offers, the supporting log (``provenance.json``, which tells each record's kind) and the validation report.
``manifest.json`` is written last, lists the sha256 of every other export and the dataset's label
(``complete``, ``pilot`` or ``partial``), so it can be verified from storage before publication. Only a
complete, validated run is published to ``published/<store_key>/``.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from marianos_headless.core.jsonio import dumps_bytes
from marianos_headless.core.schema import OUTPUT_FIELDS, shape_violations
from marianos_headless.core.timeutil import iso, utcnow
from marianos_headless.storage.base import ArtifactRef, StorageAdapter

EXPORT_FILES = (
    "products.json",
    "products.csv",
    "memberships.json",
    "offers.json",
    "provenance.json",
    "validation_report.json",
)
# Written by release 1.2.0 and later; verified whenever a manifest lists them (older runs have none).
FRESH_EXPORT_FILES = ("products_fresh.json", "products_fresh.csv")
# The coverage reconciliation (release 1.8.0): written with every export and listed in its manifest.
# Verified and copied whenever the manifest lists them (release 1.8.0rc4; before it they were listed but
# never read back).
COVERAGE_EXPORT_FILES = (
    "coverage_reconciliation.json",
    "coverage_reconciliation.csv",
    "coverage_by_csv_row.csv",
    "listing_pages.csv",
)


def manifest_files(manifest: Mapping[str, Any]) -> list[str]:
    """The export files a manifest covers: the required ones, then the fresh-only and coverage files it
    lists."""
    listed = manifest.get("files") or {}
    return [*EXPORT_FILES, *(n for n in (*FRESH_EXPORT_FILES, *COVERAGE_EXPORT_FILES) if n in listed)]


def export_prefix(store_key: str, run_id: str) -> str:
    return f"runs/{store_key}/{run_id}/exports"


def sort_records(records: Sequence[Mapping[str, str]], csv_order: Mapping[str, int]) -> list[dict[str, str]]:
    """Stable order for diffs: CSV order of category, then sub_category, product_title, upc (§6.1)."""
    return sorted(
        (dict(r) for r in records),
        key=lambda r: (csv_order.get(r["category"], 10**6), r["sub_category"], r["product_title"], r["upc"]),
    )


def canonical_products_bytes(records: Sequence[Mapping[str, str]]) -> bytes:
    for r in records:
        if shape_violations(r):
            raise ValueError(f"record {r.get('upc')!r} violates the output schema")
        if list(r) != list(OUTPUT_FIELDS):
            raise ValueError("record keys out of order")
    return dumps_bytes(list(records))


def products_csv_bytes(records: Sequence[Mapping[str, str]]) -> bytes:
    """The same records as CSV: the 22 fields as columns in order, every value a string (UTF-8 with a byte
    order mark, so spreadsheet programs read the text as written, leading zeros included)."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(OUTPUT_FIELDS)
    for r in records:
        w.writerow([r[f] for f in OUTPUT_FIELDS])
    return ("\ufeff" + buf.getvalue()).encode("utf-8")


def record_sha256(record: Mapping[str, str]) -> str:
    return hashlib.sha256(
        json.dumps(record, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class ExportSet:
    files: dict[str, ArtifactRef]
    manifest: ArtifactRef
    manifest_body: dict[str, Any]


def write_exports(
    storage: StorageAdapter,
    *,
    store_key: str,
    run_id: str,
    mode: str,
    products: Sequence[Mapping[str, str]],
    memberships: Sequence[Mapping[str, Any]],
    offers: Sequence[Mapping[str, Any]],
    provenance: Mapping[str, Any],
    validation_report: Mapping[str, Any],
    config_snapshot: Mapping[str, Any],
    versions: Mapping[str, Any],
    site_version: str | None,
    dataset: str = "partial",
    prefix: str | None = None,
    fresh_products: Sequence[Mapping[str, str]] | None = None,
    supporting: Mapping[str, bytes] | None = None,
) -> ExportSet:
    prefix = prefix or export_prefix(store_key, run_id)
    bodies = {
        "products.json": canonical_products_bytes(products),
        "products.csv": products_csv_bytes(products),
        "memberships.json": dumps_bytes(list(memberships)),
        "offers.json": dumps_bytes(list(offers)),
        "provenance.json": dumps_bytes(dict(provenance)),
        "validation_report.json": dumps_bytes({"mode": mode, **dict(validation_report)}),
    }
    if fresh_products is not None:
        bodies["products_fresh.json"] = canonical_products_bytes(fresh_products)
        bodies["products_fresh.csv"] = products_csv_bytes(fresh_products)
    bodies.update(supporting or {})
    refs = {
        name: storage.put_bytes(
            f"{prefix}/{name}", data, "text/csv" if name.endswith(".csv") else "application/json"
        )
        for name, data in bodies.items()
    }
    manifest = {
        "mode": mode,
        "run_id": run_id,
        "store_key": store_key,
        "created_at": iso(utcnow()),
        "record_count": len(products),
        # Records this run observed itself (products_fresh.json); the rest of products.json is carried.
        **({"fresh_record_count": len(fresh_products)} if fresh_products is not None else {}),
        "dataset": dataset,
        "files": {
            name: {"key": ref.key, "sha256": ref.sha256, "size": ref.size} for name, ref in refs.items()
        },
        "config_snapshot": dict(config_snapshot),
        "versions": dict(versions),
        "site_version": site_version,
    }
    mref = storage.put_bytes(f"{prefix}/manifest.json", dumps_bytes(manifest), "application/json")
    return ExportSet(refs, mref, manifest)


def verify_manifest(
    storage: StorageAdapter, manifest_key: str, expected_sha256: str | None = None
) -> list[str]:
    """Re-read every exported file from storage and compare hashes (§12 publication step 2)."""
    problems: list[str] = []
    try:
        raw = storage.get_bytes(manifest_key)
    except KeyError:
        return [f"manifest {manifest_key} missing"]
    if expected_sha256 and hashlib.sha256(raw).hexdigest() != expected_sha256:
        problems.append("manifest hash mismatch")
    body = json.loads(raw)
    for name in manifest_files(body):
        entry = body.get("files", {}).get(name)
        if entry is None:
            problems.append(f"{name} not in manifest")
            continue
        try:
            data = storage.get_bytes(entry["key"])
        except KeyError:
            problems.append(f"{name} missing from storage")
            continue
        if hashlib.sha256(data).hexdigest() != entry["sha256"]:
            problems.append(f"{name} hash mismatch")
    return problems
