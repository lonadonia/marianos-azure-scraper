"""listing pages: the durable record of each listing response (release 1.8.0)

One row per response asked for as a listing's page: the listing and its CSV row, the page asked for and the
page the source says it returned, the store and fulfillment evidence, the identities, new products,
duplicates, exclusions and conflicts, the response's hash, and whether it counted. A resumed run continues
from the contiguous completed rows.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-02 06:30:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "listing_pages",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("run_id", sa.String(26), sa.ForeignKey("runs.id"), nullable=False, index=True),
        sa.Column("category_source_id", sa.String(26), sa.ForeignKey("category_sources.id"), nullable=False),
        sa.Column("csv_row_index", sa.Integer(), nullable=False),
        sa.Column("taxonomy_id", sa.String(64), nullable=False),
        sa.Column("parent_taxonomy_id", sa.String(64), nullable=False),
        sa.Column("partition_key", sa.String(200), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("route", sa.String(16), nullable=False),
        sa.Column("requested_page", sa.Integer(), nullable=False),
        sa.Column("requested_offset", sa.Integer(), nullable=False),
        sa.Column("returned_page", sa.Integer()),
        sa.Column("loaded_pages", JSONB(), nullable=False),
        sa.Column("provider_request_id", sa.String(64)),
        sa.Column("page_fetch_id", sa.String(26)),
        sa.Column("response_sha256", sa.String(64)),
        sa.Column("location_id", sa.String(32)),
        sa.Column("modality", sa.String(16)),
        sa.Column("returned_taxonomy_id", sa.String(64)),
        sa.Column("store_check", sa.String(8), nullable=False),
        sa.Column("total", sa.Integer()),
        sa.Column("available", sa.Integer()),
        sa.Column("identities", JSONB(), nullable=False),
        sa.Column("sponsored", JSONB(), nullable=False),
        sa.Column("children", JSONB(), nullable=False),
        sa.Column("new_count", sa.Integer(), nullable=False),
        sa.Column("duplicates", sa.Integer(), nullable=False),
        sa.Column("excluded", sa.Integer(), nullable=False),
        sa.Column("conflicts", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("verdict", sa.String(24), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("segment_id", sa.String(26)),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "run_id",
            "category_source_id",
            "taxonomy_id",
            "partition_key",
            "requested_page",
            "attempt",
            name="uq_listing_pages_key",
        ),
        sa.CheckConstraint(
            "state IN ('completed', 'failed', 'refused', 'capped', 'stopped')", name="ck_listing_pages_state"
        ),
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_listing_pages_completed ON listing_pages "
        "(run_id, category_source_id, taxonomy_id, partition_key, requested_page) WHERE state = 'completed'"
    )


def downgrade() -> None:
    op.drop_index("uq_listing_pages_completed", table_name="listing_pages")
    op.drop_table("listing_pages")
