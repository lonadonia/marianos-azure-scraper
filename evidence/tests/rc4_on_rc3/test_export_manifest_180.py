"""Release 1.8.0rc4: defects found in the export of live qualification run Q1c (1.8.0rc3, 2026-11-02).

Q1c's manifest listed its four coverage files with their SHA-256, but `export` copied only the product files and
verify_manifest never read the coverage files back; and the manifest's collector version said 1.7.0. SYNTHETIC:
records built here, a throwaway folder as storage.
"""

from __future__ import annotations

import re
from pathlib import Path

from marianos_headless import __version__
from marianos_headless.core.paths import PARSER_VERSION
from marianos_headless.core.schema import build_record
from marianos_headless.publishing.exports import ExportSet, manifest_files, verify_manifest, write_exports
from marianos_headless.storage.local import LocalStorageAdapter

# Named here, not imported, so that this file also runs against 1.8.0rc3 (where both tests below fail).
COVERAGE_FILES = ("coverage_reconciliation.json", "coverage_reconciliation.csv", "coverage_by_csv_row.csv", "listing_pages.csv")
COVERAGE = {name: f"{name}: rows\r\n".encode() for name in COVERAGE_FILES}


def _export(storage: LocalStorageAdapter, supporting: dict[str, bytes] | None) -> ExportSet:
    record = build_record(
        {
            "upc": "0001234500001",
            "product_title": "Test product",
            "category": "Batteries",
            "url": "https://www.marianos.com/p/test/0001234500001",
            "regular_price": "1.00",
            "crawl_date": "2026-11-02",
        }
    )
    return write_exports(
        storage,
        store_key="marianos-53100502-pickup",
        run_id="01TESTRUN000000000000000000",
        mode="LIVE",
        products=[record],
        memberships=[],
        offers=[],
        provenance={},
        validation_report={"gates": []},
        config_snapshot={},
        versions={"collector": PARSER_VERSION},
        site_version=None,
        fresh_products=[record],
        supporting=supporting,
    )


def test_the_coverage_files_are_read_back_with_the_export(tmp_path: Path) -> None:
    storage = LocalStorageAdapter(tmp_path)
    ex = _export(storage, COVERAGE)
    files = manifest_files(ex.manifest_body)
    assert [n for n in files if n in COVERAGE] == list(COVERAGE_FILES)
    assert verify_manifest(storage, ex.manifest.key, ex.manifest.sha256) == []
    # A coverage file changed after the export is caught (it was never read back before 1.8.0rc4).
    (tmp_path / ex.files["listing_pages.csv"].key).write_bytes(b"changed\r\n")  # storage itself is write-once
    assert verify_manifest(storage, ex.manifest.key, ex.manifest.sha256) == ["listing_pages.csv hash mismatch"]


def test_an_export_written_before_the_coverage_files_still_verifies(tmp_path: Path) -> None:
    storage = LocalStorageAdapter(tmp_path)
    ex = _export(storage, None)
    assert not set(manifest_files(ex.manifest_body)) & set(COVERAGE_FILES)
    assert verify_manifest(storage, ex.manifest.key, ex.manifest.sha256) == []


def test_the_parser_version_names_the_release_series() -> None:
    # Q1c's manifest said {"collector": "1.7.0"} for a 1.8.0rc3 run.
    m = re.match(r"\d+\.\d+\.\d+", __version__)
    assert m is not None and PARSER_VERSION == m.group(0)
