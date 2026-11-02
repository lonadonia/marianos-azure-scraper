"""Oxylabs Web API as a collection provider (release 1.3.0): the key, the spending ledger and the transport.

Documentation read 2026-10-26 and 2026-10-28 (developers.oxylabs.io, and the API's own OPTIONS answers):
``POST /v1/scrape/marianos/search`` (``query``) and ``POST /v1/scrape/marianos`` (``url``) take ``store_id``,
``fulfillment_type`` (``delivery``, ``in_store``, ``pickup``), ``delivery_zip``, ``location``, ``device``,
``run_js`` and ``output`` (a list: ``html``, ``markdown``, ``screenshot``, ``json``); the answer is
``{status, results[{html, ...}], params, metadata{timestamp, request_id}}`` or a problem document
(``application/problem+json``: ``title``, ``detail``, ``errors``). Troubleshooting: ``500
REQUEST_FAILED_AFTER_TOO_MANY_RETRIES`` ("a faulted scrape") is not charged; 408, 429 and 5xx are retried with
backoff, about three attempts; a 429 that lasts more than 30 s is an exhausted quota. Authentication is
``Authorization: Bearer <key>``. The price page (oxylabs.io/products/web-api) bills per 1,000 results.

This is the Web API with its Bearer key. The Classic Web Scraper API (realtime.oxylabs.io, an API username
and password) is another product, not used here.

Key. ``OXYLABS_WEB_API_KEY``, or ``OXYLABS_WEB_API_KEY_FILE`` naming a secret file that holds the key alone or
one ``NAME=value`` / ``NAME: value`` line (``OXYLABS_WEB_API_KEY``, ``OXYLABS_API`` or ``OXYLABS_API_KEY``).
Only its fingerprint is stored or shown; the key travels in the Authorization header only.

Ledger. Each submission (every attempt is one) is reserved in ``provider_usage`` at the configured rate,
under a transaction-scoped advisory lock, against the ceiling an operator set (``set-ceiling``: submissions
and US dollars counted from a start time). With no ceiling no request is sent. A 200 answer is settled as a
charged result; the documented free failure and an authentication refusal as not charged; any other answer,
and a request cut after it was sent, keeps its reserved cost as possibly charged ("unknown").
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import random
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from time import monotonic
from typing import Any

import httpx
from pydantic import SecretStr
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, sessionmaker

from marianos_headless.core.settings import OxylabsSettings
from marianos_headless.core.timeutil import iso, utcnow
from marianos_headless.db.models import ProviderUsage, SettingRow

PROVIDER = "oxylabs"
ENV_KEY = "OXYLABS_WEB_API_KEY"
ENV_KEY_FILE = "OXYLABS_WEB_API_KEY_FILE"
KEY_NAMES = (ENV_KEY, "OXYLABS_API", "OXYLABS_API_KEY")
SETTINGS_ROW = "provider:oxylabs"
REDACTED = "[REDACTED]"
RATE_LIMIT_PAUSE_S = 16.0  # three attempts then span more than 30 s: a 429 that lasts is a quota
QUOTA_AFTER_S = 30.0
ERROR_BODY_BYTES = 20_000
_LOCK_ID = int.from_bytes(hashlib.sha256(b"marianos_headless:provider:oxylabs").digest()[:4], "big")
_NAMED = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*[=:]\s*(.*)$")

# Answer kinds (None: a usable page) and whether the request is charged: True, False, or None (unknown).
CHARGED: dict[str | None, bool | None] = {None: True, "auth": False, "provider_failed_free": False}
# Kinds never retried: retrying the same request cannot change them.
FINAL_KINDS = frozenset({None, "auth", "entitlement", "bad_request", "empty_result", "quota"})


class CeilingReached(RuntimeError):
    """The operator's ceiling leaves no room for one more submission: nothing was sent."""


class OxylabsError(RuntimeError):
    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind


# -- the key -------------------------------------------------------------------------------------------


def _from_file(path: Path) -> str:
    raw = path.read_text(encoding="utf-8-sig").strip()
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    for ln in lines:
        m = _NAMED.match(ln)
        if m and m.group(1) in KEY_NAMES:
            return m.group(2).strip().strip('"').strip("'")
    return lines[0] if len(lines) == 1 and not _NAMED.match(lines[0]) else ""


def load_key(environ: Mapping[str, str] | None = None) -> SecretStr | None:
    env = os.environ if environ is None else environ
    value = (env.get(ENV_KEY) or "").strip()
    if not value and env.get(ENV_KEY_FILE):
        path = Path(env[ENV_KEY_FILE]).expanduser()
        if path.is_file():
            value = _from_file(path)
    return SecretStr(value) if value else None


def fingerprint(key: SecretStr) -> str:
    return hashlib.sha256(key.get_secret_value().encode("utf-8")).hexdigest()[:12]


def redact(text_: str, key: SecretStr | None) -> str:
    if key is not None and key.get_secret_value():
        text_ = text_.replace(key.get_secret_value(), REDACTED)
    return re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]{8,}", r"\1" + REDACTED, text_)


# -- the ceiling -----------------------------------------------------------------------------------------


def ceiling(s: Session) -> dict[str, Any]:
    row = s.get(SettingRow, SETTINGS_ROW)
    return dict((row.value or {}).get("ceiling") or {}) if row is not None else {}


def set_ceiling(
    s: Session, *, submissions: int, usd: float, actor: str, reason: str, since: datetime | None = None
) -> dict[str, Any]:
    value = {
        "submissions": int(submissions),
        "usd": float(usd),
        "since": iso(since or utcnow()),
        "set_by": actor,
        "reason": reason,
        "set_at": iso(utcnow()),
    }
    row = s.get(SettingRow, SETTINGS_ROW)
    if row is None:
        s.add(SettingRow(key=SETTINGS_ROW, value={"ceiling": value}, updated_by=actor))
    else:
        row.value, row.updated_by = {**(row.value or {}), "ceiling": value}, actor
    return value


def usage_since(s: Session, since: str | None) -> dict[str, Any]:
    q = select(
        func.count().filter(ProviderUsage.state != "released"),
        func.coalesce(func.sum(ProviderUsage.cost_usd).filter(ProviderUsage.state != "released"), 0.0),
        func.count().filter(ProviderUsage.cost_source == "unknown"),
        func.count().filter(ProviderUsage.state == "settled", ProviderUsage.cost_usd > 0),
    ).where(ProviderUsage.provider == PROVIDER)
    if since:
        q = q.where(ProviderUsage.reserved_at >= datetime.fromisoformat(since.replace("Z", "+00:00")))
    n, usd, unknown, charged = s.execute(q).one()
    return {
        "submissions": int(n),
        "usd": round(float(usd), 6),
        "unknown": int(unknown),
        "charged": int(charged),
    }


def room(s: Session) -> tuple[int | None, dict[str, Any]]:
    """Submissions still allowed under the ceiling (None: no ceiling set, so none are allowed)."""
    cap = ceiling(s)
    if not cap:
        return None, {"ceiling": None}
    used = usage_since(s, cap.get("since"))
    by_count = int(cap["submissions"]) - used["submissions"]
    return max(0, by_count), {"ceiling": cap, "used": used}


# -- the ledger --------------------------------------------------------------------------------------------


class Ledger:
    """Reservations and settlements in ``provider_usage`` (shared by every worker and process)."""

    def __init__(self, factory: sessionmaker[Session], settings: OxylabsSettings):
        self.factory = factory
        self.rate = settings.usd_per_result

    def reserve(
        self,
        *,
        run_id: str | None,
        segment_id: str | None,
        purpose: str,
        endpoint: str,
        target: str,
        attempt: int,
    ) -> str:
        with self.factory() as s:
            s.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _LOCK_ID})
            cap = ceiling(s)
            if not cap:
                raise CeilingReached(
                    "no Oxylabs ceiling is set (set-ceiling --provider oxylabs): nothing is sent"
                )
            used = usage_since(s, cap.get("since"))
            if used["submissions"] + 1 > int(cap["submissions"]):
                raise CeilingReached(
                    f"the Oxylabs ceiling of {cap['submissions']} submissions is reached "
                    f"({used['submissions']} used)"
                )
            if used["usd"] + self.rate > float(cap["usd"]) + 1e-9:
                raise CeilingReached(
                    f"the Oxylabs ceiling of USD {cap['usd']} is reached (USD {used['usd']} used or reserved)"
                )
            row = ProviderUsage(
                provider=PROVIDER,
                run_id=run_id,
                segment_id=segment_id,
                purpose=purpose[:48],
                endpoint=endpoint,
                target=target[:2000],
                attempt=attempt,
                reserved_at=utcnow(),
                units=1.0,
                cost_usd=self.rate,
                state="reserved",
                cost_source="reserved",
            )
            s.add(row)
            s.commit()
            return row.id

    def settle(self, row_id: str, *, status: int, kind: str | None, request_id: str | None) -> float:
        charged = CHARGED.get(kind)
        with self.factory() as s:
            row = s.get(ProviderUsage, row_id)
            assert row is not None
            row.settled_at, row.state, row.http_status = utcnow(), "settled", status
            row.outcome = (kind or "ok")[:48]
            row.request_id = (request_id or None) and request_id[:64]
            if charged is None:
                row.cost_source = "unknown"  # possibly charged: the reserved cost is kept
            else:
                row.cost_usd = self.rate if charged else 0.0
                row.cost_source = "rule"
            s.commit()
            return float(row.cost_usd)

    def release(self, row_id: str, *, sent: bool, outcome: str) -> None:
        """A reservation without an answer: never sent (no cost), or sent and unanswered (kept as possibly
        charged)."""
        with self.factory() as s:
            row = s.get(ProviderUsage, row_id)
            assert row is not None
            row.settled_at, row.outcome = utcnow(), outcome[:48]
            if sent:
                row.state, row.cost_source = "settled", "unknown"
            else:
                row.state, row.cost_usd, row.cost_source = "released", 0.0, "rule"
            s.commit()


# -- answers ----------------------------------------------------------------------------------------------


def classify(status: int, body: bytes, html: str | None) -> str | None:
    """None for a usable page; else the failure's kind (Troubleshooting: status codes)."""
    if status == 200:
        return None if html else "empty_result"
    if status == 401:
        return "auth"
    if status in (402, 403):
        return "entitlement"
    if status in (400, 404, 405, 422) or status == 202:
        return "bad_request"
    if status == 408:
        return "timeout"
    if status == 429:
        return "rate_limit"
    if status >= 500 and b"REQUEST_FAILED_AFTER_TOO_MANY_RETRIES" in body[:4000]:
        return "provider_failed_free"
    return "provider_failure"


def envelope(content: bytes) -> tuple[str | None, dict[str, Any]]:
    """The page's markup (``results[0].html``) and the answer's own metadata (no page content)."""
    try:
        env = json.loads(content) if content else None
    except ValueError:
        return None, {"envelope": "not JSON"}
    if not isinstance(env, dict):
        return None, {"envelope": type(env).__name__}
    meta: dict[str, Any] = {}
    md: dict[str, Any] = env["metadata"] if isinstance(env.get("metadata"), dict) else {}
    meta["request_id"] = str(md.get("request_id") or "")
    meta["timestamp"] = md.get("timestamp")
    for k in ("status", "state", "title", "detail", "errors"):
        if env.get(k) is not None:
            meta[k] = env[k]
    if isinstance(env.get("params"), dict):
        meta["params"] = env["params"]
    html: str | None = None
    results = env.get("results")
    if isinstance(results, list) and results and isinstance(results[0], dict):
        r0 = results[0]
        meta["result_metadata"] = r0.get("metadata")
        meta["result_formats"] = sorted(k for k, v in r0.items() if v is not None and k != "metadata")
        if isinstance(r0.get("html"), str):
            html = r0["html"]
    return html, meta


@dataclass
class Answer:
    endpoint: str
    body: dict[str, Any]  # the JSON body sent (never the key)
    status: int = 0
    kind: str | None = "not_sent"
    html: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)
    attempts: list[dict[str, Any]] = field(default_factory=list)
    cost_usd: float = 0.0
    cost_unknown: bool = False
    seconds: float = 0.0
    error_body: str = ""

    @property
    def ok(self) -> bool:
        return self.kind is None and bool(self.html)


class OxylabsClient:
    """Requests to the Web API, each attempt reserved in the ledger before it is sent."""

    def __init__(
        self,
        settings: OxylabsSettings,
        key: SecretStr,
        ledger: Ledger,
        *,
        run_id: str | None = None,
        segment_id: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Any = asyncio.sleep,
    ):
        self.settings = settings
        self.key = key
        self.ledger = ledger
        self.run_id = run_id
        self.segment_id = segment_id
        self.sleep = sleep
        self.submissions = 0  # attempts sent by this client (each reserved one result)
        self.http = httpx.AsyncClient(
            base_url=settings.api_base, timeout=settings.request_timeout_s, transport=transport
        )

    async def aclose(self) -> None:
        await self.http.aclose()

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.key.get_secret_value()}", "Content-Type": "application/json"}

    async def fetch(self, endpoint: str, body: dict[str, Any], *, purpose: str, target: str) -> Answer:
        answer = Answer(endpoint=endpoint, body=dict(body))
        t_all = monotonic()
        first_429: float | None = None
        for attempt in range(1, self.settings.max_attempts + 1):
            row_id = self.ledger.reserve(
                run_id=self.run_id,
                segment_id=self.segment_id,
                purpose=purpose,
                endpoint=endpoint,
                target=target,
                attempt=attempt,
            )
            t0 = monotonic()
            self.submissions += 1
            try:
                r = await self.http.post(endpoint, json=body, headers=self._headers())
            except asyncio.CancelledError:
                self.ledger.release(row_id, sent=True, outcome="cancelled")
                raise
            except httpx.HTTPError as exc:
                sent = not isinstance(exc, httpx.ConnectError)
                self.ledger.release(row_id, sent=sent, outcome=f"transport {type(exc).__name__}")
                answer.attempts.append(
                    {
                        "attempt": attempt,
                        "error": redact(f"{type(exc).__name__}: {exc}", self.key)[:300],
                        "seconds": round(monotonic() - t0, 2),
                        "possibly_charged": sent,
                    }
                )
                answer.kind, answer.cost_unknown = "transport", answer.cost_unknown or sent
                if attempt < self.settings.max_attempts:
                    await self.sleep(min(30.0, 2.0 * 2 ** (attempt - 1)) + random.uniform(0, 1))
                    continue
                break
            html, meta = envelope(r.content)
            kind = classify(r.status_code, r.content, html)
            cost = self.ledger.settle(
                row_id, status=r.status_code, kind=kind, request_id=meta.get("request_id")
            )
            answer.cost_usd += cost
            answer.cost_unknown = answer.cost_unknown or CHARGED.get(kind) is None
            answer.status, answer.kind, answer.meta = r.status_code, kind, meta
            answer.attempts.append(
                {
                    "attempt": attempt,
                    "status": r.status_code,
                    "kind": kind,
                    "request_id": meta.get("request_id"),
                    "seconds": round(monotonic() - t0, 2),
                    "usd": cost,
                }
            )
            if kind is None:
                answer.html = html
                break
            answer.error_body = redact(r.text[:ERROR_BODY_BYTES], self.key)
            if kind == "rate_limit":
                first_429 = first_429 if first_429 is not None else monotonic()
                if monotonic() - first_429 > QUOTA_AFTER_S:
                    answer.kind = "quota"
                    break
            if kind in FINAL_KINDS or attempt >= self.settings.max_attempts:
                break
            pause = RATE_LIMIT_PAUSE_S if kind == "rate_limit" else min(30.0, 2.0 * 2 ** (attempt - 1))
            await self.sleep(pause + random.uniform(0, 1))
        answer.seconds = round(monotonic() - t_all, 2)
        return answer


def search_body(settings: OxylabsSettings, *, query: str, store_id: str, fulfillment: str) -> dict[str, Any]:
    return {
        "query": query,
        "store_id": store_id,
        "fulfillment_type": fulfillment,
        "location": settings.location,
        "output": ["html"],
    }


def page_body(
    settings: OxylabsSettings, *, url: str, store_id: str, fulfillment: str, run_js: bool = False
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "url": url,
        "store_id": store_id,
        "fulfillment_type": fulfillment,
        "location": settings.location,
        "output": ["html"],
    }
    if run_js:
        body["run_js"] = True
    return body


def robots_body(settings: OxylabsSettings, *, url: str) -> dict[str, Any]:
    """robots.txt is not a store page: no store or fulfillment parameter. With them the Mariano's
    scraper fails the request (HTTP 500 after its retries, not charged: run of 2026-10-29 06:11Z);
    without them it brings the file (probe of 2026-10-28 19:12Z)."""
    return {"url": url, "location": settings.location, "output": ["html"]}


FULFILLMENT = {"IN_STORE": "in_store", "PICKUP": "pickup", "DELIVERY": "delivery"}
