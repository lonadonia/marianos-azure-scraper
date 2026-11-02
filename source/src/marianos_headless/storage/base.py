"""Artifact storage interface (brief §9.1, §9.3).

Writes are immutable: writing a key that already exists succeeds only if the bytes are identical
(idempotent retries), otherwise it raises. The only mutable object is the convenience pointer
``published/<store>/latest.json``; the database pointer is authoritative.
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass

MUTABLE_PREFIXES = ("published/",)


class ImmutableWriteError(RuntimeError):
    """A different payload was written to an existing immutable key."""


class ArtifactNotFound(KeyError):
    pass


@dataclass(frozen=True)
class ArtifactRef:
    key: str
    sha256: str
    size: int
    content_type: str


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_key(key: str) -> str:
    if not key or key.startswith("/") or "\\" in key:
        raise ValueError(f"invalid artifact key {key!r}")
    parts = key.split("/")
    if any(p in ("", ".", "..") for p in parts):
        raise ValueError(f"invalid artifact key {key!r}")
    return key


class StorageAdapter(ABC):
    @abstractmethod
    def _read(self, key: str) -> bytes | None: ...

    @abstractmethod
    def _write(self, key: str, data: bytes, content_type: str, overwrite: bool) -> None: ...

    @abstractmethod
    def list(self, prefix: str) -> Iterator[str]: ...

    @abstractmethod
    def describe(self) -> str: ...

    def exists(self, key: str) -> bool:
        return self._read(validate_key(key)) is not None

    def get_bytes(self, key: str) -> bytes:
        data = self._read(validate_key(key))
        if data is None:
            raise ArtifactNotFound(key)
        return data

    def put_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> ArtifactRef:
        validate_key(key)
        mutable = key.startswith(MUTABLE_PREFIXES)
        if not mutable:
            existing = self._read(key)
            if existing is not None:
                if existing != data:
                    raise ImmutableWriteError(f"{key} already exists with different content")
                return ArtifactRef(key, sha256_hex(data), len(data), content_type)
        self._write(key, data, content_type, overwrite=mutable)
        return ArtifactRef(key, sha256_hex(data), len(data), content_type)

    def verify(self, ref: ArtifactRef) -> bool:
        """Re-read from storage and compare the hash (publication step 2, §12)."""
        data = self._read(ref.key)
        return data is not None and sha256_hex(data) == ref.sha256
