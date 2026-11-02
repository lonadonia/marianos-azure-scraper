"""Safe publication (brief §12, NN-4).

1. The run is ``validated`` and has no blocking FAIL findings. WARN findings need a recorded reason.
   Every record traces to this store's own live pages (:func:`lineage_problems`, release 1.8.0).
2. The manifest and every export are re-verified from storage.
3. One DB transaction inserts ``publications`` and moves ``publication_pointer`` with an optimistic
   ``version`` check.
4. After commit, ``published/<store>/latest.json`` is written. It is a convenience copy: the DB
   pointer is authoritative and :func:`sync_latest_json` repairs the file after a crash.

A failure at any step leaves the previous pointer untouched. There is no force-publish.

Rollback (release 1.4.0): :func:`rollback_publication` moves the pointer back to the publication the current
one replaced, in one transaction with the same optimistic ``version`` check, after re-verifying that
publication's manifest from storage; it is audited, and ``latest.json`` is rewritten after the commit. The
rolled-back run keeps its status and its files: nothing is deleted.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from marianos_headless.core.jsonio import dumps_bytes
from marianos_headless.core.timeutil import iso, utcnow
from marianos_headless.db.models import (
    Artifact,
    AuditLog,
    ExportRow,
    PageFetch,
    ProductObservation,
    Publication,
    PublicationPointer,
    RecordRow,
    Run,
    Store,
    ValidationFinding,
)
from marianos_headless.publishing.exports import verify_manifest
from marianos_headless.storage.base import StorageAdapter

NON_BLOCKING_GATES = frozenset({"G14"})


class PublicationRefused(RuntimeError):
    pass


class PointerConflict(RuntimeError):
    """Another publication moved the pointer concurrently."""


@dataclass(frozen=True)
class PublishResult:
    publication_id: str
    version: int
    previous_publication_id: str | None


def latest_key(store_key: str) -> str:
    return f"published/{store_key}/latest.json"


def _manifest(session: Session, run_id: str) -> Artifact:
    art = session.scalar(
        select(Artifact)
        .join(ExportRow, ExportRow.artifact_id == Artifact.id)
        .where(ExportRow.run_id == run_id, ExportRow.kind == "manifest")
    )
    if art is None:
        raise PublicationRefused("run has no manifest export")
    return art


def lineage_problems(s: Session, run: Run) -> list[str]:
    """Why a run's records may not stand as this store's live dataset (empty: they may).

    The gates judge what a dataset says; this asks where it came from. A fresh record needs an observation of
    this run on a page of this run. A carried-forward record needs an earlier live run of the same store, on
    one of that run's pages. So fixture data, another store's products and another run's pages cannot enter a
    published dataset by any path, and a product of Lakeshore East is never Vernon Hills' assortment."""
    rows = list(s.scalars(select(RecordRow).where(RecordRow.run_id == run.id)))
    seen: Counter[str] = Counter()
    observed: dict[str, set[str]] = {}
    for upc, fetch in s.execute(
        select(ProductObservation.upc, ProductObservation.page_fetch_id).where(
            ProductObservation.run_id == run.id
        )
    ).all():
        observed.setdefault(upc, set()).add(fetch)
    own_pages = set(s.scalars(select(PageFetch.id).where(PageFetch.run_id == run.id)))
    for row in rows:
        if row.mode != run.mode:
            seen[f"record marked {row.mode} in a {run.mode} run"] += 1
        if row.status != "historical":
            pages = observed.get(row.upc, set())
            if not pages:
                seen["fresh record with no observation of this run"] += 1
            elif not pages <= own_pages:
                seen["fresh record observed on a page of another run"] += 1
            continue
        origin = (row.provenance or {}).get("historical") or {}
        source = s.get(Run, origin.get("run_id")) if origin.get("run_id") else None
        if source is None:
            seen["carried record with no source run"] += 1
        elif source.mode != "LIVE":
            seen[f"carried record from a {source.mode} run"] += 1
        elif source.store_id != run.store_id:
            seen["carried record from another store"] += 1
        else:
            page = s.get(PageFetch, origin.get("page_fetch_id")) if origin.get("page_fetch_id") else None
            if page is None or page.run_id != source.id:
                seen["carried record whose page is not in its source run"] += 1
    return [f"{n} {what}" for what, n in sorted(seen.items())]


def publish_run(
    factory: sessionmaker[Session],
    storage: StorageAdapter,
    run_id: str,
    published_by: str,
    *,
    warn_override_reason: str | None = None,
    fault: Callable[[str], None] | None = None,
) -> PublishResult:
    hook = fault or (lambda _stage: None)
    with factory() as s:
        run = s.get(Run, run_id)
        if run is None:
            raise PublicationRefused("unknown run")
        if run.status != "validated":
            raise PublicationRefused(f"run status is {run.status!r}, not 'validated'")
        if run.mode != "LIVE":
            raise PublicationRefused("only LIVE runs are published")
        findings = list(s.scalars(select(ValidationFinding).where(ValidationFinding.run_id == run_id)))
        blocking = [f for f in findings if f.severity == "FAIL" and f.gate not in NON_BLOCKING_GATES]
        if blocking:
            raise PublicationRefused(f"{len(blocking)} FAIL finding(s); FAIL cannot be overridden")
        warns = [f for f in findings if f.severity == "WARN"]
        if warns and not (warn_override_reason and warn_override_reason.strip()):
            raise PublicationRefused(f"{len(warns)} WARN finding(s) need a recorded override reason")
        lineage = lineage_problems(s, run)
        if lineage:
            raise PublicationRefused("lineage check failed: " + "; ".join(lineage))
        store = s.get(Store, run.store_id)
        assert store is not None
        manifest = _manifest(s, run_id)
        manifest_key, manifest_sha = manifest.key, manifest.sha256
        store_id, store_key, mode = store.id, store.key, run.mode

    problems = verify_manifest(storage, manifest_key, manifest_sha)
    if problems:
        raise PublicationRefused("integrity check failed: " + "; ".join(problems))
    hook("before_commit")

    with factory() as s, s.begin():
        pointer = s.get(PublicationPointer, store_id, with_for_update=True)
        previous_id = pointer.publication_id if pointer else None
        version = pointer.version if pointer else 0
        pub = Publication(
            store_id=store_id,
            run_id=run_id,
            mode=mode,
            manifest_sha256=manifest_sha,
            published_by=published_by,
            previous_publication_id=previous_id,
        )
        s.add(pub)
        s.flush()
        if pointer is None:
            s.add(PublicationPointer(store_id=store_id, publication_id=pub.id, version=1))
        else:
            res = s.execute(
                update(PublicationPointer)
                .where(PublicationPointer.store_id == store_id, PublicationPointer.version == version)
                .values(publication_id=pub.id, version=version + 1)
            )
            if res.rowcount != 1:  # type: ignore[attr-defined]
                raise PointerConflict(store_id)
        s.execute(update(Run).where(Run.id == run_id, Run.status == "validated").values(status="published"))
        s.add(
            AuditLog(
                actor=published_by,
                action="publish",
                target=run_id,
                reason=warn_override_reason,
                data={
                    "publication_id": pub.id,
                    "version": version + 1,
                    "warns": len(warns),
                    "previous_publication_id": previous_id,
                },
            )
        )
        pub_id = pub.id
        hook("inside_commit")
    hook("after_commit")

    _write_latest(storage, store_key, pub_id, run_id, manifest_key, manifest_sha, version + 1, mode)
    return PublishResult(pub_id, version + 1, previous_id)


def rollback_publication(
    factory: sessionmaker[Session],
    storage: StorageAdapter,
    store_id: str,
    actor: str,
    reason: str,
    *,
    fault: Callable[[str], None] | None = None,
) -> PublishResult:
    """Point the store's published dataset back at the publication the current one replaced."""
    hook = fault or (lambda _stage: None)
    if not reason.strip():
        raise PublicationRefused("a rollback needs a recorded reason")
    with factory() as s:
        pointer = s.get(PublicationPointer, store_id)
        if pointer is None:
            raise PublicationRefused("nothing is published for this store")
        current = s.get(Publication, pointer.publication_id)
        assert current is not None
        if current.previous_publication_id is None:
            raise PublicationRefused(
                "the current publication replaced none: there is nothing to roll back to"
            )
        target = s.get(Publication, current.previous_publication_id)
        assert target is not None
        store = s.get(Store, store_id)
        assert store is not None
        manifest = _manifest(s, target.run_id)
        manifest_key, version = manifest.key, pointer.version
        current_id, target_id, target_run, target_sha = (
            current.id,
            target.id,
            target.run_id,
            target.manifest_sha256,
        )
        store_key, mode = store.key, target.mode
    problems = verify_manifest(storage, manifest_key, target_sha)
    if problems:
        raise PublicationRefused("integrity check of the earlier publication failed: " + "; ".join(problems))
    hook("before_commit")
    with factory() as s, s.begin():
        res = s.execute(
            update(PublicationPointer)
            .where(PublicationPointer.store_id == store_id, PublicationPointer.version == version)
            .values(publication_id=target_id, version=version + 1)
        )
        if res.rowcount != 1:  # type: ignore[attr-defined]
            raise PointerConflict(store_id)
        s.add(
            AuditLog(
                actor=actor,
                action="rollback",
                target=target_run,
                reason=reason,
                data={
                    "from_publication_id": current_id,
                    "to_publication_id": target_id,
                    "version": version + 1,
                },
            )
        )
        hook("inside_commit")
    hook("after_commit")
    _write_latest(storage, store_key, target_id, target_run, manifest_key, target_sha, version + 1, mode)
    return PublishResult(target_id, version + 1, current_id)


def _write_latest(
    storage: StorageAdapter,
    store_key: str,
    publication_id: str,
    run_id: str,
    manifest_key: str,
    manifest_sha: str,
    version: int,
    mode: str,
) -> None:
    storage.put_bytes(
        latest_key(store_key),
        dumps_bytes(
            {
                "publication_id": publication_id,
                "run_id": run_id,
                "manifest_key": manifest_key,
                "manifest_sha256": manifest_sha,
                "version": version,
                "mode": mode,
                "written_at": iso(utcnow()),
                "note": "convenience copy; the database publication_pointer is authoritative",
            }
        ),
        "application/json",
    )


def sync_latest_json(factory: sessionmaker[Session], storage: StorageAdapter, store_id: str) -> bool:
    """Rewrite ``latest.json`` from the DB pointer (repairs a crash between commit and file write)."""
    with factory() as s:
        pointer = s.get(PublicationPointer, store_id)
        if pointer is None:
            return False
        pub = s.get(Publication, pointer.publication_id)
        store = s.get(Store, store_id)
        assert pub is not None and store is not None
        manifest = _manifest(s, pub.run_id)
        _write_latest(
            storage,
            store.key,
            pub.id,
            pub.run_id,
            manifest.key,
            pub.manifest_sha256,
            pointer.version,
            pub.mode,
        )
        return True
