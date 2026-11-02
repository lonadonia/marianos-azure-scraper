"""Run lifecycle (state machine) and persistence of validation results and exports."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from marianos_headless.core import logs
from marianos_headless.core.paths import PARSER_VERSION
from marianos_headless.core.settings import Settings
from marianos_headless.core.timeutil import utcnow
from marianos_headless.db.models import Artifact, Event, ExportRow, Run, Store, ValidationFinding
from marianos_headless.publishing.exports import ExportSet
from marianos_headless.validation.gates import ValidationOutcome

TRANSITIONS: dict[str, frozenset[str]] = {
    "queued": frozenset({"preflight", "interrupted", "cancelled"}),
    "preflight": frozenset({"running", "interrupted", "rejected", "cancelled"}),
    "running": frozenset({"interrupted", "validating", "cancelled", "rejected"}),
    "interrupted": frozenset({"running", "cancelled"}),
    "validating": frozenset({"validated", "rejected"}),
    "validated": frozenset({"published"}),
    "rejected": frozenset(),
    "published": frozenset(),
    "cancelled": frozenset(),
}


class InvalidTransition(RuntimeError):
    pass


def create_run(
    session: Session,
    store: Store,
    settings: Settings,
    *,
    mode: str,
    trigger: str,
    resumed_from_run_id: str | None = None,
) -> Run:
    if mode != "LIVE":
        raise ValueError("this collector creates LIVE runs only")
    run = Run(
        store_id=store.id,
        trigger=trigger,
        status="queued",
        mode=mode,
        config_snapshot=settings.snapshot(),
        parser_version=PARSER_VERSION,
        resumed_from_run_id=resumed_from_run_id,
    )
    session.add(run)
    session.flush()
    event(session, run.id, "INFO", "RUN_CREATED", f"{mode} run for {store.key}", {"trigger": trigger})
    return run


def transition(session: Session, run_id: str, to: str) -> Run:
    run = session.get(Run, run_id, with_for_update=True)
    if run is None:
        raise InvalidTransition(f"unknown run {run_id}")
    if to not in TRANSITIONS[run.status]:
        raise InvalidTransition(f"{run.status} -> {to} is not allowed")
    previous = run.status
    run.status = to
    now = utcnow()
    if to in ("preflight", "running") and run.started_at is None:
        run.started_at = now
    if to in ("validated", "rejected", "cancelled", "published"):
        run.finished_at = now
    event(session, run_id, "INFO", f"RUN_{to.upper()}", f"{previous} -> {to}")
    return run


def request_cancel(session: Session, run_id: str) -> None:
    run = session.get(Run, run_id, with_for_update=True)
    if run is None:
        raise InvalidTransition(f"unknown run {run_id}")
    run.cancel_requested = True
    event(session, run_id, "INFO", "CANCEL_REQUESTED", "cooperative cancel requested")


def request_pause(session: Session, run_id: str) -> None:
    """Ask the worker to stop at its next checkpoint and leave the run resumable (``interrupted``)."""
    run = session.get(Run, run_id, with_for_update=True)
    if run is None:
        raise InvalidTransition(f"unknown run {run_id}")
    if run.status not in ("queued", "preflight", "running"):
        raise InvalidTransition(f"run is {run.status}; only active runs can pause")
    run.pause_requested = True
    event(session, run_id, "INFO", "PAUSE_REQUESTED", "pause requested; the run stops at its next checkpoint")


def clear_pause(session: Session, run_id: str) -> None:
    run = session.get(Run, run_id, with_for_update=True)
    if run is not None:
        run.pause_requested = False


def event(
    session: Session,
    run_id: str | None,
    level: str,
    code: str,
    message: str,
    data: dict[str, Any] | None = None,
) -> None:
    """A run event: recorded in the database and written as a structured log line."""
    session.add(Event(run_id=run_id, level=level, code=code, message=message, data=data or {}))
    logs.log(level, code, run_id=run_id, message=message, data=data or {})


def record_validation(
    session: Session, run_id: str, outcome: ValidationOutcome, *, apply_status: bool = True
) -> str:
    for r in outcome.results:
        for f in r.findings:
            session.add(
                ValidationFinding(
                    run_id=run_id,
                    scope=f.scope,
                    ref=f.ref,
                    gate=f.gate,
                    severity=f.severity.value,
                    code=str(f.code),
                    message=f.message,
                    metrics=dict(f.metrics),
                )
            )
    status = "validated" if outcome.publishable else "rejected"
    if apply_status:
        transition(session, run_id, status)
    return status


def register_exports(session: Session, run_id: str, mode: str, exports: ExportSet) -> None:
    def add(kind: str, key: str, sha: str, size: int, count: int | None) -> None:
        existing = session.scalar(select(Artifact).where(Artifact.key == key))
        art = existing or Artifact(
            run_id=run_id,
            key=key,
            sha256=sha,
            size=size,
            content_type="text/csv" if key.endswith(".csv") else "application/json",
        )
        if existing is None:
            session.add(art)
            session.flush()
        session.add(
            ExportRow(run_id=run_id, mode=mode, kind=kind, artifact_id=art.id, record_count=count, sha256=sha)
        )

    for name, ref in exports.files.items():
        add(
            name.removesuffix(".json").replace(".", "_"),
            ref.key,
            ref.sha256,
            ref.size,
            exports.manifest_body["record_count"] if name == "products.json" else None,
        )
    m = exports.manifest
    add("manifest", m.key, m.sha256, m.size, exports.manifest_body["record_count"])
