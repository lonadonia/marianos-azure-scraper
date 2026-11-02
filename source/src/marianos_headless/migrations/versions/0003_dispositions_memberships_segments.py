"""record dispositions, membership context and abandoned segments (release 1.4.0)

* ``records.status`` gains ``eligible_unpriced`` (a verified product of the store's assortment that shows no
  fixed current price: unavailable, "Prices May Vary", or only an estimated item price) and
  ``price_conflict`` (the displayed price differs from the same product's own data for the store).
* ``memberships`` keeps where and when each placement was observed: the page, the collection segment, the
  observation time, and whether the placement was sponsored (part of the row's key, so a product shown both
  sponsored and in the results of the same page keeps both placements).
* ``collection_segments`` records how a segment ended: ``ended`` by its own worker, or ``abandoned`` (its
  worker stopped without closing it: a forced kill or a lost machine). An abandoned segment keeps
  ``ended_at`` empty (its end is unknown) and gets ``recovered_at``, the latest time it can have ended.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-29 12:30:00
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

OLD_STATUSES = "('valid', 'exported_not_valid', 'excluded', 'quarantined', 'historical')"
NEW_STATUSES = (
    "('valid', 'eligible_unpriced', 'price_conflict', 'exported_not_valid', 'excluded', 'quarantined', "
    "'historical')"
)


MEMBERSHIP_KEY: list[Any] = [
    "run_id",
    "upc",
    "category_source_id",
    sa.literal_column("coalesce(taxonomy_id, '')"),
    sa.literal_column("coalesce(coupon_id, '')"),
    "page_offset",
]


def upgrade() -> None:
    op.drop_constraint(op.f("ck_records_status"), "records", type_="check")
    op.create_check_constraint(op.f("ck_records_status"), "records", f"status IN {NEW_STATUSES}")

    op.add_column("memberships", sa.Column("page_fetch_id", sa.String(length=26), nullable=True))
    op.add_column("memberships", sa.Column("segment_id", sa.String(length=26), nullable=True))
    op.add_column("memberships", sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("memberships", sa.Column("placement", sa.String(length=12), nullable=True))
    op.drop_index("uq_memberships_key", table_name="memberships")
    op.create_index(
        "uq_memberships_key",
        "memberships",
        [*MEMBERSHIP_KEY, sa.literal_column("coalesce(placement, '')")],
        unique=True,
    )

    op.add_column(
        "collection_segments",
        sa.Column("end_state", sa.String(length=12), nullable=True),
    )
    op.add_column(
        "collection_segments",
        sa.Column("recovered_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute("UPDATE collection_segments SET end_state = 'ended' WHERE ended_at IS NOT NULL")
    op.create_check_constraint(
        op.f("ck_collection_segments_end_state"),
        "collection_segments",
        "end_state IS NULL OR end_state IN ('ended', 'abandoned')",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_collection_segments_end_state"), "collection_segments", type_="check")
    op.drop_column("collection_segments", "recovered_at")
    op.drop_column("collection_segments", "end_state")
    op.drop_index("uq_memberships_key", table_name="memberships")
    op.execute("DELETE FROM memberships WHERE placement = 'sponsored'")
    op.create_index("uq_memberships_key", "memberships", MEMBERSHIP_KEY, unique=True)
    for name in ("placement", "observed_at", "segment_id", "page_fetch_id"):
        op.drop_column("memberships", name)
    op.execute(
        "UPDATE records SET status = 'exported_not_valid' WHERE status IN ('eligible_unpriced', 'price_conflict')"
    )
    op.drop_constraint(op.f("ck_records_status"), "records", type_="check")
    op.create_check_constraint(op.f("ck_records_status"), "records", f"status IN {OLD_STATUSES}")
