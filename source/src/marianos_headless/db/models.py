"""PostgreSQL data model (brief §10). Migrations live in ``migrations/`` (Alembic).

IDs are ULIDs. Status-like columns are strings with CHECK constraints rather than PG enums, so new
states need only a migration that rewrites the constraint. ``mode`` (LIVE | FIXTURE) is stored on runs
and on every table derived from them so the two can never be blended.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from marianos_headless.core.ids import new_id

NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

RUN_STATUSES = (
    "queued",
    "preflight",
    "running",
    "interrupted",
    "validating",
    "validated",
    "rejected",
    "published",
    "cancelled",
)
TASK_STATES = ("pending", "leased", "running", "succeeded", "retry_wait", "failed", "blocked", "skipped")
TASK_KINDS = (
    "preflight",
    "attest",
    "census",
    "listing_node",
    "pdp",
    "coupons_catalogue",
    "coupon_items",
    "assemble",
    "validate",
    "export",
)
MODES = ("LIVE", "FIXTURE")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)
    type_annotation_map: ClassVar[dict[Any, Any]] = {dict[str, Any]: JSONB, list[str]: ARRAY(Text)}


def _id() -> Mapped[str]:
    return mapped_column(String(26), primary_key=True, default=new_id)


def _created() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


def _updated() -> Mapped[datetime]:
    return mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


def _mode() -> Mapped[str]:
    return mapped_column(String(8), nullable=False)


class Store(Base):
    __tablename__ = "stores"
    id: Mapped[str] = _id()
    key: Mapped[str] = mapped_column(String(64), unique=True)
    retailer: Mapped[str] = mapped_column(String(32))
    location_id: Mapped[str] = mapped_column(String(8))
    division_number: Mapped[str] = mapped_column(String(3))
    store_number: Mapped[str] = mapped_column(String(5))
    expected_display_name: Mapped[str] = mapped_column(Text)
    expected_postal_code: Mapped[str] = mapped_column(String(10))
    expected_address_line1: Mapped[str | None] = mapped_column(Text)
    modality: Mapped[str] = mapped_column(String(16))
    timezone: Mapped[str] = mapped_column(String(64))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_contest_store: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()
    __table_args__ = (CheckConstraint(_in("modality", ("IN_STORE", "PICKUP")), name="modality"),)


class CategorySource(Base):
    __tablename__ = "category_sources"
    id: Mapped[str] = _id()
    retailer: Mapped[str] = mapped_column(String(32), default="marianos", server_default=text("'marianos'"))
    csv_row_index: Mapped[int] = mapped_column(Integer)
    category_name: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    scope: Mapped[str] = mapped_column(Text)
    notes: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String(32))
    landing_slug: Mapped[str | None] = mapped_column(Text)
    taxonomy_id: Mapped[str | None] = mapped_column(String(10))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    csv_sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()
    __table_args__ = (
        UniqueConstraint("retailer", "category_name", name="uq_category_sources_retailer_name"),
    )


class Run(Base):
    __tablename__ = "runs"
    id: Mapped[str] = _id()
    store_id: Mapped[str] = mapped_column(ForeignKey("stores.id"))
    trigger: Mapped[str] = mapped_column(String(16))  # manual | schedule | test
    status: Mapped[str] = mapped_column(String(16), default="queued")
    mode: Mapped[str] = _mode()
    config_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    site_version: Mapped[str | None] = mapped_column(String(64))
    parser_version: Mapped[str] = mapped_column(String(32))
    robots_sha256: Mapped[str | None] = mapped_column(String(64))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    counts: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    resumed_from_run_id: Mapped[str | None] = mapped_column(String(26))
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    pause_requested: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    # Live collection: why the run last stopped (a limit, the operator, the site, the provider) and the
    # operator's requests to the collector service (resume; stop collecting and finalize).
    stop_code: Mapped[str | None] = mapped_column(String(48))
    stop_detail: Mapped[str | None] = mapped_column(Text)
    resume_requested: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    finish_requested: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()
    __table_args__ = (
        CheckConstraint(_in("status", RUN_STATUSES), name="status"),
        CheckConstraint(_in("mode", MODES), name="mode"),
        Index("ix_runs_store_status", "store_id", "status"),
    )


class StoreAttestation(Base):
    __tablename__ = "store_attestations"
    id: Mapped[str] = _id()
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    mode: Mapped[str] = _mode()
    phase: Mapped[str] = mapped_column(String(16))
    observed_location_id: Mapped[str | None] = mapped_column(String(8))
    observed_name: Mapped[str | None] = mapped_column(Text)
    observed_postal_code: Mapped[str | None] = mapped_column(String(10))
    modality: Mapped[str | None] = mapped_column(String(16))
    modality_source: Mapped[str | None] = mapped_column(Text)
    is_trusted: Mapped[bool | None] = mapped_column(Boolean)
    laf_store_id: Mapped[str | None] = mapped_column(String(8))
    cms_scope: Mapped[str | None] = mapped_column(Text)
    result: Mapped[str] = mapped_column(String(8))
    checks: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    evidence_artifact_ids: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created()
    __table_args__ = (
        CheckConstraint(_in("phase", ("preflight", "task_start", "periodic", "final")), name="phase"),
        CheckConstraint(_in("result", ("PASS", "FAIL")), name="result"),
    )


class RunLock(Base):
    __tablename__ = "run_locks"
    store_id: Mapped[str] = mapped_column(ForeignKey("stores.id"), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"))
    holder: Mapped[str] = mapped_column(Text)
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[str] = _id()
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"))
    kind: Mapped[str] = mapped_column(String(24))
    idem_key: Mapped[str] = mapped_column(Text)
    category_source_id: Mapped[str | None] = mapped_column(ForeignKey("category_sources.id"))
    taxonomy_id: Mapped[str | None] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(16), default="pending")
    priority: Mapped[int] = mapped_column(Integer, default=100)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    lease_owner: Mapped[str | None] = mapped_column(Text)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    not_before: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cursor: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()
    __table_args__ = (
        UniqueConstraint("run_id", "idem_key", name="uq_tasks_run_idem"),
        CheckConstraint(_in("state", TASK_STATES), name="state"),
        CheckConstraint(_in("kind", TASK_KINDS), name="kind"),
        Index("ix_tasks_run_state", "run_id", "state", "priority"),
    )


class Artifact(Base):
    __tablename__ = "artifacts"
    id: Mapped[str] = _id()
    run_id: Mapped[str | None] = mapped_column(ForeignKey("runs.id"), index=True)
    key: Mapped[str] = mapped_column(Text, unique=True)
    sha256: Mapped[str] = mapped_column(String(64))
    size: Mapped[int] = mapped_column(BigInteger)
    content_type: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = _created()


class PageFetch(Base):
    __tablename__ = "page_fetches"
    id: Mapped[str] = _id()
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"))
    url: Mapped[str] = mapped_column(Text)
    purpose: Mapped[str] = mapped_column(String(32))
    http_status: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    challenge: Mapped[bool] = mapped_column(Boolean, default=False)
    dom_artifact_id: Mapped[str | None] = mapped_column(ForeignKey("artifacts.id"))
    screenshot_artifact_id: Mapped[str | None] = mapped_column(ForeignKey("artifacts.id"))


class CapturedResponse(Base):
    __tablename__ = "captured_responses"
    id: Mapped[str] = _id()
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    page_fetch_id: Mapped[str] = mapped_column(ForeignKey("page_fetches.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    url: Mapped[str] = mapped_column(Text)
    status: Mapped[int] = mapped_column(Integer)
    request_location_id: Mapped[str | None] = mapped_column(String(8))
    request_taxonomies: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    body_sha256: Mapped[str] = mapped_column(String(64))
    artifact_id: Mapped[str | None] = mapped_column(ForeignKey("artifacts.id"))
    schema_ok: Mapped[bool | None] = mapped_column(Boolean)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ProductObservation(Base):
    __tablename__ = "product_observations"
    id: Mapped[str] = _id()
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"))
    mode: Mapped[str] = _mode()
    upc: Mapped[str] = mapped_column(String(40))  # product identity key (see retailers.py)
    page_fetch_id: Mapped[str] = mapped_column(ForeignKey("page_fetches.id"))
    source: Mapped[str] = mapped_column(String(16))
    displayed: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    structured: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    flags: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    parser_version: Mapped[str] = mapped_column(String(32))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("run_id", "upc", "page_fetch_id", "source", name="uq_product_observations_key"),
        CheckConstraint(_in("source", ("card", "pdp", "coupon_items")), name="source"),
        Index("ix_product_observations_run_upc", "run_id", "upc"),
        Index("ix_product_observations_observed_at", "observed_at"),  # per-day product limits
    )


class OfferObservationRow(Base):
    __tablename__ = "offer_observations"
    id: Mapped[str] = _id()
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"))
    mode: Mapped[str] = _mode()
    upc: Mapped[str] = mapped_column(String(40))  # product identity key (see retailers.py)
    page_fetch_id: Mapped[str | None] = mapped_column(ForeignKey("page_fetches.id"))
    source: Mapped[str] = mapped_column(String(16))
    tag: Mapped[str] = mapped_column(Text, default="")
    headline: Mapped[str] = mapped_column(Text, default="")
    description: Mapped[str] = mapped_column(Text, default="")
    expiry_text: Mapped[str] = mapped_column(Text, default="")
    requires_clip: Mapped[bool] = mapped_column(Boolean)
    kind: Mapped[str] = mapped_column(String(16))
    explicit_price: Mapped[str] = mapped_column(String(16), default="")
    modalities: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    flags: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    __table_args__ = (Index("ix_offer_observations_run_upc", "run_id", "upc"),)


class MembershipRow(Base):
    __tablename__ = "memberships"
    id: Mapped[str] = _id()
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"))
    mode: Mapped[str] = _mode()
    upc: Mapped[str] = mapped_column(String(40))  # product identity key (see retailers.py)
    category_source_id: Mapped[str] = mapped_column(ForeignKey("category_sources.id"))
    taxonomy_id: Mapped[str | None] = mapped_column(String(64))
    coupon_id: Mapped[str | None] = mapped_column(Text)
    page_offset: Mapped[int] = mapped_column(Integer)
    position: Mapped[int] = mapped_column(Integer)
    via: Mapped[str] = mapped_column(String(8))
    # Where and when the placement was observed (release 1.4.0; empty on rows of earlier releases).
    page_fetch_id: Mapped[str | None] = mapped_column(String(26))
    segment_id: Mapped[str | None] = mapped_column(String(26))
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    placement: Mapped[str | None] = mapped_column(String(12))  # organic | sponsored
    __table_args__ = (
        CheckConstraint(_in("via", ("organic", "paid", "curated", "coupon")), name="via"),
        Index(
            "uq_memberships_key",
            "run_id",
            "upc",
            "category_source_id",
            text("coalesce(taxonomy_id, '')"),
            text("coalesce(coupon_id, '')"),
            "page_offset",
            text("coalesce(placement, '')"),
            unique=True,
        ),
    )


# valid: a verified product with a fixed displayed price that agrees with its own data for the store;
# eligible_unpriced: a verified product of the store's assortment showing no fixed current price (unavailable,
# "Prices May Vary", or only an estimated item price); price_conflict: the displayed price differs from the
# product's own data (both kept, the displayed one exported); exported_not_valid: an incomplete identity
# (no title, link or category); historical: an earlier run's observation carried forward (release 1.4.0).
RECORD_STATUSES = (
    "valid",
    "eligible_unpriced",
    "price_conflict",
    "exported_not_valid",
    "excluded",
    "quarantined",
    "historical",
)


class RecordRow(Base):
    __tablename__ = "records"
    id: Mapped[str] = _id()
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"))
    mode: Mapped[str] = _mode()
    upc: Mapped[str] = mapped_column(String(40))  # product identity key (see retailers.py)
    record: Mapped[dict[str, Any]] = mapped_column(JSONB)
    record_sha256: Mapped[str] = mapped_column(String(64))
    primary_category_source_id: Mapped[str | None] = mapped_column(ForeignKey("category_sources.id"))
    status: Mapped[str] = mapped_column(String(24))
    reasons: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    flags: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    # Why a record is what it is beyond its status: a kept earlier local observation (``historical``) and
    # its age, or one too old to keep. Never part of the 22-field product file.
    provenance: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    __table_args__ = (
        UniqueConstraint("run_id", "upc", name="uq_records_run_upc"),
        CheckConstraint(_in("status", RECORD_STATUSES), name="status"),
    )


class ValidationFinding(Base):
    __tablename__ = "validation_findings"
    id: Mapped[str] = _id()
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    scope: Mapped[str] = mapped_column(String(16))
    ref: Mapped[str | None] = mapped_column(Text)
    gate: Mapped[str] = mapped_column(String(8))
    severity: Mapped[str] = mapped_column(String(8))
    code: Mapped[str] = mapped_column(String(48))
    message: Mapped[str] = mapped_column(Text)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = _created()
    __table_args__ = (
        CheckConstraint(_in("severity", ("INFO", "WARN", "FAIL")), name="severity"),
        CheckConstraint(_in("scope", ("run", "category", "node", "record")), name="scope"),
    )


class ExportRow(Base):
    __tablename__ = "exports"
    id: Mapped[str] = _id()
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    mode: Mapped[str] = _mode()
    kind: Mapped[str] = mapped_column(String(32))
    artifact_id: Mapped[str] = mapped_column(ForeignKey("artifacts.id"))
    record_count: Mapped[int | None] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = _created()


class Publication(Base):
    __tablename__ = "publications"
    id: Mapped[str] = _id()
    store_id: Mapped[str] = mapped_column(ForeignKey("stores.id"))
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), unique=True)
    mode: Mapped[str] = _mode()
    manifest_sha256: Mapped[str] = mapped_column(String(64))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published_by: Mapped[str] = mapped_column(Text)
    previous_publication_id: Mapped[str | None] = mapped_column(ForeignKey("publications.id"))


class PublicationPointer(Base):
    __tablename__ = "publication_pointer"
    store_id: Mapped[str] = mapped_column(ForeignKey("stores.id"), primary_key=True)
    publication_id: Mapped[str] = mapped_column(ForeignKey("publications.id"))
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = _updated()


class Event(Base):
    __tablename__ = "events"
    id: Mapped[str] = _id()
    run_id: Mapped[str | None] = mapped_column(ForeignKey("runs.id"))
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    level: Mapped[str] = mapped_column(String(8))
    code: Mapped[str] = mapped_column(String(48))
    message: Mapped[str] = mapped_column(Text)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    __table_args__ = (Index("ix_events_run_ts", "run_id", "ts"),)


class SettingRow(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB)
    updated_by: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = _updated()


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[str] = _id()
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actor: Mapped[str] = mapped_column(Text)
    action: Mapped[str] = mapped_column(String(48))
    target: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class NodeCoverage(Base):
    """Per-run, per-node listing totals vs captured UPCs (completeness proof, §5.6)."""

    __tablename__ = "node_coverage"
    id: Mapped[str] = _id()
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"))
    category_source_id: Mapped[str] = mapped_column(ForeignKey("category_sources.id"))
    taxonomy_id: Mapped[str] = mapped_column(String(64))
    total_count: Mapped[int | None] = mapped_column(Integer)
    organic_upcs: Mapped[int] = mapped_column(Integer, default=0)
    coverage_ratio: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(16))
    partition: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    __table_args__ = (
        UniqueConstraint("run_id", "category_source_id", "taxonomy_id", name="uq_node_coverage_key"),
    )


class ListingPage(Base):
    """One response asked for as a page of a listing (release 1.8.0; ``collection.pagination``)."""

    __tablename__ = "listing_pages"
    id: Mapped[str] = _id()
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    category_source_id: Mapped[str] = mapped_column(ForeignKey("category_sources.id"))
    csv_row_index: Mapped[int] = mapped_column(Integer)
    taxonomy_id: Mapped[str] = mapped_column(String(64))
    parent_taxonomy_id: Mapped[str] = mapped_column(String(64), default="")
    partition_key: Mapped[str] = mapped_column(String(200), default="")
    url: Mapped[str] = mapped_column(Text)
    route: Mapped[str] = mapped_column(String(16))
    requested_page: Mapped[int] = mapped_column(Integer)
    requested_offset: Mapped[int] = mapped_column(Integer)
    returned_page: Mapped[int | None] = mapped_column(Integer)
    loaded_pages: Mapped[list[int]] = mapped_column(JSONB, default=list)
    provider_request_id: Mapped[str | None] = mapped_column(String(64))
    page_fetch_id: Mapped[str | None] = mapped_column(String(26))
    response_sha256: Mapped[str | None] = mapped_column(String(64))
    location_id: Mapped[str | None] = mapped_column(String(32))
    modality: Mapped[str | None] = mapped_column(String(16))
    returned_taxonomy_id: Mapped[str | None] = mapped_column(String(64))
    store_check: Mapped[str] = mapped_column(String(8), default="N/A")
    total: Mapped[int | None] = mapped_column(Integer)
    available: Mapped[int | None] = mapped_column(Integer)
    identities: Mapped[list[str]] = mapped_column(JSONB, default=list)
    sponsored: Mapped[list[str]] = mapped_column(JSONB, default=list)
    # The subdivisions the response's own filter tree names: read by a resume, without asking again.
    children: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    new_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicates: Mapped[int] = mapped_column(Integer, default=0)
    excluded: Mapped[int] = mapped_column(Integer, default=0)
    conflicts: Mapped[int] = mapped_column(Integer, default=0)
    state: Mapped[str] = mapped_column(String(16))
    verdict: Mapped[str] = mapped_column(String(24))
    detail: Mapped[str] = mapped_column(Text, default="")
    segment_id: Mapped[str | None] = mapped_column(String(26))
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "category_source_id",
            "taxonomy_id",
            "partition_key",
            "requested_page",
            "attempt",
            name="uq_listing_pages_key",
        ),
        CheckConstraint(
            "state IN ('completed', 'failed', 'refused', 'capped', 'stopped')", name="ck_listing_pages_state"
        ),
        Index(
            "uq_listing_pages_completed",
            "run_id",
            "category_source_id",
            "taxonomy_id",
            "partition_key",
            "requested_page",
            unique=True,
            postgresql_where=text("state = 'completed'"),
        ),
    )


class CollectionSegment(Base):
    """One stretch of live collection by the collector service (start or resume until it stops).

    Limits are enforced from these rows: active time per run, provider credits per run
    and per day (``day`` is the local date in the collection timezone when the segment started), and
    the account's remaining credits seen at the start and the end."""

    __tablename__ = "collection_segments"
    id: Mapped[str] = _id()
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    store_id: Mapped[str] = mapped_column(ForeignKey("stores.id"))
    trigger: Mapped[str] = mapped_column(String(16))  # manual | schedule | resume | recovery | finish
    day: Mapped[str] = mapped_column(String(10))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active_s: Mapped[float] = mapped_column(Float, default=0.0)
    credits_estimated: Mapped[float] = mapped_column(Float, default=0.0)
    browser_sessions: Mapped[int] = mapped_column(Integer, default=0)
    browsers_closed: Mapped[int] = mapped_column(Integer, default=0)
    steps: Mapped[int] = mapped_column(Integer, default=0)
    products_verified: Mapped[int] = mapped_column(Integer, default=0)
    account_remaining_start: Mapped[int | None] = mapped_column(Integer)
    account_remaining_end: Mapped[int | None] = mapped_column(Integer)
    stop_code: Mapped[str | None] = mapped_column(String(48))
    stop_detail: Mapped[str | None] = mapped_column(Text)
    # ended: closed by its own worker (``ended_at`` is then its end); abandoned: its worker stopped without
    # closing it (forced kill, lost machine). An abandoned segment's end is unknown: ``ended_at`` stays empty,
    # ``heartbeat_at`` is the last time it was seen working and ``recovered_at`` the latest time it can have
    # ended (when a later worker found it). NULL: still open (release 1.4.0).
    end_state: Mapped[str | None] = mapped_column(String(12))
    recovered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        Index("ix_collection_segments_store_day", "store_id", "day"),
        CheckConstraint("end_state IS NULL OR end_state IN ('ended', 'abandoned')", name="end_state"),
    )


PROVIDER_USAGE_STATES = ("reserved", "settled", "released")


class ProviderUsage(Base):
    """One request to a provider billed per request (release 1.3.0: Oxylabs Web API submissions, Kroger
    Public API calls). Reserved before it is sent, under an advisory lock and against the operator's ceiling
    (``set-ceiling``); settled from its answer. A request cancelled or cut after it was sent keeps its
    reserved cost as possibly charged (``cost_source`` "unknown")."""

    __tablename__ = "provider_usage"
    id: Mapped[str] = _id()
    provider: Mapped[str] = mapped_column(String(16))
    run_id: Mapped[str | None] = mapped_column(String(26), index=True)
    segment_id: Mapped[str | None] = mapped_column(String(26))
    purpose: Mapped[str] = mapped_column(String(48))
    endpoint: Mapped[str] = mapped_column(Text)
    target: Mapped[str] = mapped_column(Text, default="")
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    reserved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    units: Mapped[float] = mapped_column(Float, default=1.0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    state: Mapped[str] = mapped_column(String(16))
    cost_source: Mapped[str] = mapped_column(String(16))  # reserved | rule | unknown
    outcome: Mapped[str | None] = mapped_column(String(48))
    http_status: Mapped[int | None] = mapped_column(Integer)
    request_id: Mapped[str | None] = mapped_column(String(64))
    __table_args__ = (
        CheckConstraint(_in("state", PROVIDER_USAGE_STATES), name="state"),
        Index("ix_provider_usage_provider_reserved_at", "provider", "reserved_at"),
    )
