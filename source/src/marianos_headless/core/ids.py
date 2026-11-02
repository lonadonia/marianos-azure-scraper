"""ULID identifiers (sortable by creation time)."""

from __future__ import annotations

from ulid import ULID


def new_id() -> str:
    return str(ULID())
