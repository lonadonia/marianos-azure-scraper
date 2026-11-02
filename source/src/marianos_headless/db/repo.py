"""Small repository helpers: config → DB synchronisation (CSV rows, stores) and audit entries."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from marianos_headless.core.settings import StoresFile
from marianos_headless.db.models import AuditLog, CategorySource, Store
from marianos_headless.sites.marianos.csv_sources import CategorySource as CsvRow


@dataclass(frozen=True)
class SyncResult:
    inserted: int
    updated: int
    disabled: int


def audit(
    session: Session,
    actor: str,
    action: str,
    target: str | None,
    data: dict[str, Any] | None = None,
    reason: str | None = None,
) -> None:
    session.add(AuditLog(actor=actor, action=action, target=target, data=data or {}, reason=reason))


def import_category_sources(
    session: Session,
    rows: Sequence[CsvRow],
    csv_sha256: str,
    actor: str,
    retailer: str = "marianos",
) -> SyncResult:
    """Upsert one retailer's CSV rows by category name. Rows of that retailer no longer in the CSV are
    disabled, never deleted; other retailers' rows are not touched."""
    existing = {
        c.category_name: c
        for c in session.scalars(select(CategorySource).where(CategorySource.retailer == retailer))
    }
    inserted = updated = 0
    names = set()
    for row in rows:
        names.add(row.category_name)
        values = {
            "csv_row_index": row.row_index,
            "url": row.url,
            "scope": row.scope,
            "notes": row.notes,
            "kind": row.kind.value,
            "landing_slug": row.landing_slug,
            "taxonomy_id": row.taxonomy_id,
            "enabled": True,
            "csv_sha256": csv_sha256,
        }
        cur = existing.get(row.category_name)
        if cur is None:
            session.add(CategorySource(retailer=retailer, category_name=row.category_name, **values))
            inserted += 1
        elif any(getattr(cur, k) != v for k, v in values.items()):
            for k, v in values.items():
                setattr(cur, k, v)
            updated += 1
    disabled = 0
    for name, cur in existing.items():
        if name not in names and cur.enabled:
            cur.enabled = False
            disabled += 1
    audit(
        session,
        actor,
        "csv_import",
        "category_sources",
        {
            "retailer": retailer,
            "csv_sha256": csv_sha256,
            "rows": len(rows),
            "inserted": inserted,
            "updated": updated,
            "disabled": disabled,
        },
    )
    return SyncResult(inserted, updated, disabled)


def sync_stores(session: Session, stores: StoresFile, actor: str) -> SyncResult:
    existing = {s.key: s for s in session.scalars(select(Store))}
    inserted = updated = 0
    for cfg in stores.stores:
        values = {
            "retailer": cfg.retailer,
            "location_id": cfg.location_id,
            "division_number": cfg.division_number,
            "store_number": cfg.store_number,
            "expected_display_name": cfg.expected.display_name,
            "expected_postal_code": cfg.expected.postal_code,
            "expected_address_line1": cfg.expected.address_line1,
            "modality": cfg.modality.value,
            "timezone": cfg.timezone,
            "enabled": cfg.enabled,
            "is_contest_store": cfg.is_contest_store,
        }
        cur = existing.get(cfg.key)
        if cur is None:
            session.add(Store(key=cfg.key, **values))
            inserted += 1
        elif any(getattr(cur, k) != v for k, v in values.items()):
            for k, v in values.items():
                setattr(cur, k, v)
            updated += 1
    audit(session, actor, "stores_sync", "stores", {"inserted": inserted, "updated": updated})
    return SyncResult(inserted, updated, 0)
