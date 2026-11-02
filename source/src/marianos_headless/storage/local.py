r"""Filesystem storage under a root directory (local mode).

On Windows, files are opened through extended-length paths (``\\?\``), so a deep data folder never meets
the 260-character path limit.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

from marianos_headless.storage.base import StorageAdapter

LONG_PREFIX = "\\\\?\\"  # the four characters \\?\


def _long(p: Path) -> Path:
    """The path itself, or on Windows its extended-length form (no 260-character limit)."""
    if os.name != "nt" or str(p).startswith(LONG_PREFIX):
        return p
    return Path(LONG_PREFIX + str(p))


class LocalStorageAdapter(StorageAdapter):
    def __init__(self, root: Path | str):
        self.root = Path(root).resolve()
        _long(self.root).mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if self.root not in p.parents and p != self.root:
            raise ValueError(f"key escapes storage root: {key!r}")
        return _long(p)

    def _read(self, key: str) -> bytes | None:
        p = self._path(key)
        return p.read_bytes() if p.is_file() else None

    def _write(self, key: str, data: bytes, content_type: str, overwrite: bool) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        # Write to a temp file in the same directory, then rename: readers never see partial files.
        fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=".tmp-")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
            if not overwrite and p.exists():
                raise FileExistsError(key)
            os.replace(tmp, p)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    def list(self, prefix: str) -> Iterator[str]:
        base = _long(self.root)
        for path in sorted(base.rglob("*")):
            if path.is_file() and not path.name.startswith(".tmp-"):
                key = path.relative_to(base).as_posix()
                if key.startswith(prefix):
                    yield key

    def describe(self) -> str:
        return f"local:{self.root}"
