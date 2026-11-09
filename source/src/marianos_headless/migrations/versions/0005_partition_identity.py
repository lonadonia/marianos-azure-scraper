"""partition identity and filter binding (release 1.9.0)

M1: a filtered reading of a listing (a brand of a listing above the source's window) is identified by a digest
of its full identity (retailer, store, fulfillment, listing, filter, exact value); its page rows carry that
identity in ``requested_filter`` and its full digest in ``partition_key``. Rows written before this release
keep their values: a brand reading planned by an earlier release (ID ``<listing>~<brand>`` cut at 64
characters) is never resumed by 1.9.0 (the collector refuses it), and its rows stay as recorded.

M2: ``binding`` keeps what each response states about the search it answers (its filters, its search ID and
the page's latest search ID, loaded / loading / error), so a page counts for a filtered reading only when it
states that very filter.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-06 17:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "listing_pages",
        sa.Column("requested_filter", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.add_column(
        "listing_pages",
        sa.Column("binding", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )


def downgrade() -> None:
    op.drop_column("listing_pages", "binding")
    op.drop_column("listing_pages", "requested_filter")
