"""deferred requests: a listing request set aside and asked again later in the same run (release 1.10.0, C1)

A later page answered with an earlier page's products, or the first page of a listing above the source's
window answered without the filters needed to subdivide it, is set aside; the same request is asked again
after a wait, a bounded number of times (``collection.reask``). ``deferred_requests`` holds one row per such
request: what is asked again (address, page, filter, store and fulfillment), the first answer's verdict and
the reason the listing ended with before this release, the number of re-asks sent (raised before each one is
sent, and bounded by the table's own constraints), the earliest time of the next one, and every answer.

``listing_pages.state`` gains ``reasked``: an answer to a first page asked again only for the listing's
filters. Rows written before this release keep their values.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-11 20:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

STATES_1_9 = "state IN ('completed', 'failed', 'refused', 'capped', 'stopped')"
STATES_1_10 = "state IN ('completed', 'failed', 'refused', 'capped', 'stopped', 'reasked')"


def upgrade() -> None:
    op.create_table(
        "deferred_requests",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("run_id", sa.String(26), sa.ForeignKey("runs.id"), nullable=False, index=True),
        sa.Column("category_source_id", sa.String(26), sa.ForeignKey("category_sources.id"), nullable=False),
        sa.Column("csv_row_index", sa.Integer(), nullable=False),
        sa.Column("taxonomy_id", sa.String(64), nullable=False),
        sa.Column("partition_key", sa.String(200), nullable=False),
        sa.Column("requested_page", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("requested_filter", JSONB(), nullable=False),
        sa.Column("store_context", JSONB(), nullable=False),
        sa.Column("original_listing_page_id", sa.String(26)),
        sa.Column("original_verdict", sa.String(24), nullable=False),
        sa.Column("original_reason", sa.Text(), nullable=False),
        sa.Column("max_reasks", sa.Integer(), nullable=False),
        sa.Column("min_wait_s", sa.Integer(), nullable=False),
        sa.Column("reasks_dispatched", sa.Integer(), nullable=False),
        sa.Column("not_before", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("attempts", JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "run_id",
            "category_source_id",
            "taxonomy_id",
            "partition_key",
            "requested_page",
            name="uq_deferred_requests_key",
        ),
        sa.CheckConstraint("kind IN ('repeated_page', 'missing_facets')", name="ck_deferred_requests_kind"),
        sa.CheckConstraint(
            "state IN ('waiting', 'recovered', 'exhausted')", name="ck_deferred_requests_state"
        ),
        sa.CheckConstraint(
            "reasks_dispatched >= 0 AND reasks_dispatched <= max_reasks", name="ck_deferred_requests_ceiling"
        ),
        sa.CheckConstraint("max_reasks >= 0 AND max_reasks <= 2", name="ck_deferred_requests_max_reasks"),
    )
    op.drop_constraint("ck_listing_pages_state", "listing_pages", type_="check")
    op.create_check_constraint("ck_listing_pages_state", "listing_pages", STATES_1_10)


def downgrade() -> None:
    # A page asked again only for its filters has no meaning before this release: such rows go with the
    # table that explains them.
    op.execute("DELETE FROM listing_pages WHERE state = 'reasked'")
    op.drop_constraint("ck_listing_pages_state", "listing_pages", type_="check")
    op.create_check_constraint("ck_listing_pages_state", "listing_pages", STATES_1_9)
    op.drop_table("deferred_requests")
