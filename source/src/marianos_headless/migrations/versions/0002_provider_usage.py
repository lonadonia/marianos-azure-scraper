"""provider usage ledger (release 1.3.0: Oxylabs Web API submissions, Kroger Public API calls)

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-28 19:45:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "provider_usage",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("provider", sa.String(length=16), nullable=False),
        sa.Column("run_id", sa.String(length=26), nullable=True),
        sa.Column("segment_id", sa.String(length=26), nullable=True),
        sa.Column("purpose", sa.String(length=48), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("target", sa.Text(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("reserved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("units", sa.Float(), nullable=False),
        sa.Column("cost_usd", sa.Float(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("cost_source", sa.String(length=16), nullable=False),
        sa.Column("outcome", sa.String(length=48), nullable=True),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.CheckConstraint(
            "state IN ('reserved', 'settled', 'released')", name=op.f("ck_provider_usage_state")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_provider_usage")),
    )
    op.create_index(op.f("ix_provider_usage_run_id"), "provider_usage", ["run_id"], unique=False)
    op.create_index(
        "ix_provider_usage_provider_reserved_at", "provider_usage", ["provider", "reserved_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_provider_usage_provider_reserved_at", table_name="provider_usage")
    op.drop_index(op.f("ix_provider_usage_run_id"), table_name="provider_usage")
    op.drop_table("provider_usage")
