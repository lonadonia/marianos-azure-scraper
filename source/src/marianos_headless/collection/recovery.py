"""Collection segments a worker left open (release 1.4.0).

A worker closes its own segment (``end_state`` ``ended``, with its end time). One stopped without closing
it (a forced kill, a lost machine) leaves it open; the next worker for the store, holding the store's lock
(so no other worker can still be writing to it), closes it as ``abandoned``. Its end is unknown: ``ended_at``
stays empty, the last heartbeat is the earliest time it can have ended and ``recovered_at`` the latest. A
provider request the dead worker had reserved and not settled may have been sent and billed: it is settled
as ``interrupted_unknown`` with its reserved cost kept and its cost source ``unknown`` (counted once, never
released and never charged again). Its pages are never trusted without their stored captures: the run
resumes from its last committed checkpoint.

Release 1.8.0: this runs before anything else a worker does for the store, because a reservation left by a
dead worker counts against the ceiling: a resume that first asked for room could be refused by its own dead
request and leave the segment open for ever. A reservation can also outlive its segment (a segment closed
while its request was still out): every reservation of the store's runs left unsettled is settled the same
way.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from marianos_headless.collection.limits import StopCode
from marianos_headless.core.timeutil import iso
from marianos_headless.db.models import CollectionSegment, Event, ProviderUsage, Run

INTERRUPTED = "interrupted_unknown"


def open_segments(s: Session, store_id: str, *, exclude: str | None = None) -> list[CollectionSegment]:
    q = select(CollectionSegment).where(
        CollectionSegment.store_id == store_id,
        CollectionSegment.ended_at.is_(None),
        CollectionSegment.end_state.is_(None),
    )
    if exclude is not None:
        q = q.where(CollectionSegment.id != exclude)
    return list(s.scalars(q.order_by(CollectionSegment.started_at)))


def recover_abandoned(
    s: Session, store_id: str, *, now: datetime, exclude: str | None = None
) -> list[dict[str, Any]]:
    """Close every segment of the store left open by a worker that is gone. Call only while holding the
    store's run lock. Returns what was recovered (also written as ``SEGMENT_ABANDONED`` events)."""
    out: list[dict[str, Any]] = []
    for seg in open_segments(s, store_id, exclude=exclude):
        pending = list(
            s.scalars(
                select(ProviderUsage).where(
                    ProviderUsage.state == "reserved",
                    or_(
                        ProviderUsage.segment_id == seg.id,
                        and_(ProviderUsage.segment_id.is_(None), ProviderUsage.run_id == seg.run_id),
                    ),
                )
            )
        )
        for u in pending:
            u.state, u.cost_source, u.outcome, u.settled_at = "settled", "unknown", INTERRUPTED, now
        seg.end_state, seg.recovered_at = "abandoned", now
        seg.stop_code = seg.stop_code or StopCode.TERMINATED.value
        bounds = {
            "segment": seg.id,
            "run_id": seg.run_id,
            "started_at": iso(seg.started_at),
            "ended_not_before": iso(seg.heartbeat_at or seg.started_at),
            "ended_not_after": iso(now),
            "ended_at": None,
            "end": "unknown",
            "steps_seen": seg.steps,
            "active_s_seen": seg.active_s,
            "reservations_unsettled": len(pending),
            "reservations_usd_kept": round(sum(float(u.cost_usd) for u in pending), 6),
            "reservation_ids": [u.id for u in pending],
        }
        seg.stop_detail = (
            f"abandoned: its worker stopped without closing it; ended between {bounds['ended_not_before']} "
            f"and {bounds['ended_not_after']} (exact end unknown); {len(pending)} unsettled provider "
            "request(s) kept as possibly billed"
        )
        s.add(
            Event(
                run_id=seg.run_id,
                level="WARN",
                code="SEGMENT_ABANDONED",
                message=seg.stop_detail[:500],
                data=bounds,
            )
        )
        out.append(bounds)
    s.flush()
    stray = list(
        s.scalars(
            select(ProviderUsage)
            .join(Run, ProviderUsage.run_id == Run.id)
            .where(
                ProviderUsage.state == "reserved",
                Run.store_id == store_id,
                *(
                    [or_(ProviderUsage.segment_id.is_(None), ProviderUsage.segment_id != exclude)]
                    if exclude
                    else []
                ),
            )
        )
    )
    for u in stray:
        u.state, u.cost_source, u.outcome, u.settled_at = "settled", "unknown", INTERRUPTED, now
        s.add(
            Event(
                run_id=u.run_id,
                level="WARN",
                code="RESERVATION_KEPT",
                message=f"a provider request of a closed segment was left unsettled: kept as possibly billed "
                f"(USD {u.cost_usd})",
                data={"reservation": u.id, "segment": u.segment_id, "usd": float(u.cost_usd)},
            )
        )
    s.flush()
    return out
