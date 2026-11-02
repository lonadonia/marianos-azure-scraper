"""Idempotent observation writes: re-processing a page after a crash never doubles counts (§11)."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from marianos_headless.core.ids import new_id
from marianos_headless.db.models import MembershipRow, ProductObservation


def insert_memberships(session: Session, rows: Iterable[Mapping[str, Any]]) -> int:
    values = [{"id": new_id(), **r} for r in rows]
    if not values:
        return 0
    res = session.execute(insert(MembershipRow).values(values).on_conflict_do_nothing())
    return int(res.rowcount or 0)  # type: ignore[attr-defined]


def insert_product_observations(session: Session, rows: Iterable[Mapping[str, Any]]) -> int:
    values = [{"id": new_id(), **r} for r in rows]
    if not values:
        return 0
    res = session.execute(
        insert(ProductObservation)
        .values(values)
        .on_conflict_do_nothing(constraint="uq_product_observations_key")
    )
    return int(res.rowcount or 0)  # type: ignore[attr-defined]
