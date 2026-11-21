"""Release 1.10.0rc7: ``validate-export --file`` reads the client's ``products.csv`` as well as
``products.json``.

Until 1.10.0rc6 a CSV was read as JSON and refused with a decoding error (exit 2), so the file the client
receives could not be checked offline by itself. The CSV here is written by the export's own writer
(``products_csv_bytes``: UTF-8 with a byte order mark, CRLF) from REAL records of a stored run."""

from __future__ import annotations

import json
from pathlib import Path

from marianos_headless.checks import contract
from marianos_headless.core.schema import OUTPUT_FIELDS
from marianos_headless.publishing.exports import products_csv_bytes
from tests.conftest import CAPTURES

RUN = CAPTURES / "run_01M5CSS9_20261020"


def _write(tmp: Path, data: bytes, name: str = "products.csv") -> Path:
    p = tmp / name
    p.write_bytes(data)
    return p


def test_the_csv_and_the_json_of_one_export_pass_the_same_contract(tmp_path: Path) -> None:
    records = json.loads((RUN / "products.json").read_text("utf-8"))
    as_csv = contract.check(_write(tmp_path, products_csv_bytes(records)))
    as_json = contract.check(RUN / "products.json")
    assert as_csv["passed"] and as_json["passed"]
    for k in ("rows", "problems", "duplicate_upc", "duplicate_url", "leading_zero_upcs", "populated"):
        assert as_csv[k] == as_json[k], k


def test_a_csv_whose_leading_zeros_were_lost_fails(tmp_path: Path) -> None:
    records = json.loads((RUN / "products.json").read_text("utf-8"))
    zeros = [r for r in records if r["upc"].startswith("0")]
    assert zeros
    damaged = [dict(r, upc=r["upc"].lstrip("0")) if r is zeros[0] else r for r in records]
    report = contract.check(_write(tmp_path, products_csv_bytes(damaged)))
    assert not report["passed"] and report["problems"]["upc not 13 digits"] == 1


def test_a_csv_with_another_header_or_a_short_row_fails(tmp_path: Path) -> None:
    records = json.loads((RUN / "products.json").read_text("utf-8"))
    body = products_csv_bytes(records).decode("utf-8-sig").split("\r\n")
    head = body[0].split(",")
    head[0], head[1] = head[1], head[0]
    swapped = "\r\n".join([",".join(head), *body[1:]]).encode("utf-8")
    report = contract.check(_write(tmp_path, swapped, "swapped.csv"))
    assert not report["passed"] and report["problems"]["csv header"] == 1
    short = "\r\n".join([body[0], body[1].rsplit(",", 1)[0], *body[2:]]).encode("utf-8")
    report = contract.check(_write(tmp_path, short, "short.csv"))
    assert not report["passed"] and report["problems"]["row width"] == 1
    assert next(iter(OUTPUT_FIELDS)) == "zipcode"
