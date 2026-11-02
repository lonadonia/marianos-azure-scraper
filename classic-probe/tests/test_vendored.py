"""The vendored readers are the collectors' files, unchanged but for a recorded import line (OFFLINE)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "src" / "classic_probe" / "vendor"
RECORD = json.loads((VENDOR / "VENDORED.json").read_text("utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def test_each_vendored_file_is_the_recorded_copy() -> None:
    listed = {f["vendored"] for f in RECORD["files"]}
    present = {p.relative_to(ROOT).as_posix() for p in VENDOR.glob("*.py") if p.name != "__init__.py"}
    assert listed == present
    for f in RECORD["files"]:
        data = (ROOT / f["vendored"]).read_bytes()
        assert _sha(ROOT / f["vendored"]) == f["sha256"], f["vendored"]
        rewrite = f.get("import_rewrite")
        if rewrite:  # back to the origin's own bytes: the recorded git object of the collector's file
            data = data.replace(rewrite["to"].encode(), rewrite["from"].encode())
            assert hashlib.sha256(data).hexdigest() == f["origin_sha256"], f["vendored"]
        assert _git_blob(data) == f["git_blob"], f["vendored"]


def _as_vendored(f: dict[str, str]) -> str:
    data = (ROOT.parent / f["origin"]).read_bytes()
    rewrite = f.get("import_rewrite")
    if rewrite:
        assert data.count(rewrite["from"].encode()) == 1, f["origin"]  # type: ignore[index]
        data = data.replace(rewrite["from"].encode(), rewrite["to"].encode())  # type: ignore[index]
    return hashlib.sha256(data).hexdigest()


@pytest.mark.parametrize("collector", ["walmart-azure-headless", "marianos-azure-headless"])
def test_the_vendored_files_are_still_the_collectors_files(collector: str) -> None:
    if not (ROOT.parent / collector).is_dir():
        pytest.skip(f"{collector}'s source is not beside this probe (a probe-only extraction)")
    text = (ROOT.parent / collector / "pyproject.toml").read_text("utf-8")
    release = f"{collector} " + text.split('version = "', 1)[1].split('"', 1)[0]
    entries = [f for f in RECORD["files"] if f["origin"].startswith(collector + "/")]
    if entries and entries[0]["origin_release"] != release:
        pytest.skip(
            f"the collector beside this probe is {release}; the copies were taken from "
            f"{entries[0]['origin_release']} (each copy is checked against its recorded git object above)"
        )
    for f in entries:
        assert _as_vendored(f) == f["sha256"], f"{f['origin']} changed: copy it again"
