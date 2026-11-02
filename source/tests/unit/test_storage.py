from __future__ import annotations

from pathlib import Path

import pytest

from marianos_headless.storage.base import ArtifactNotFound, ImmutableWriteError, sha256_hex
from marianos_headless.storage.local import LocalStorageAdapter


def test_immutable_writes_and_idempotent_retry(tmp_path: Path) -> None:
    st = LocalStorageAdapter(tmp_path)
    ref = st.put_bytes("runs/s/r1/raw/f1.products_search.json.gz", b"abc", "application/gzip")
    assert ref.sha256 == sha256_hex(b"abc")
    assert st.put_bytes("runs/s/r1/raw/f1.products_search.json.gz", b"abc").sha256 == ref.sha256
    with pytest.raises(ImmutableWriteError):
        st.put_bytes("runs/s/r1/raw/f1.products_search.json.gz", b"different")
    assert st.get_bytes(ref.key) == b"abc"
    assert st.verify(ref)


def test_published_pointer_is_mutable(tmp_path: Path) -> None:
    st = LocalStorageAdapter(tmp_path)
    st.put_bytes("published/s/latest.json", b"1")
    st.put_bytes("published/s/latest.json", b"2")
    assert st.get_bytes("published/s/latest.json") == b"2"


@pytest.mark.parametrize("key", ["../x", "/abs", "a//b", "a\\b", "a/./b", ""])
def test_rejects_bad_keys(tmp_path: Path, key: str) -> None:
    with pytest.raises(ValueError):
        LocalStorageAdapter(tmp_path).put_bytes(key, b"x")


def test_list_and_missing(tmp_path: Path) -> None:
    st = LocalStorageAdapter(tmp_path)
    st.put_bytes("runs/a/1.json", b"1")
    st.put_bytes("runs/b/2.json", b"2")
    assert list(st.list("runs/a/")) == ["runs/a/1.json"]
    with pytest.raises(ArtifactNotFound):
        st.get_bytes("runs/none.json")
    assert not st.exists("runs/none.json")


def test_bytes_are_not_newline_translated(tmp_path: Path) -> None:
    st = LocalStorageAdapter(tmp_path)
    st.put_bytes("runs/x.json", b"a\nb\n")
    assert (tmp_path / "runs" / "x.json").read_bytes() == b"a\nb\n"
