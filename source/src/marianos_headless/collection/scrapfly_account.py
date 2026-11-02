"""The Scrapfly API key (from the environment) and the account's API-credit balance.

Key. ``SCRAPFLY_API_KEY`` (in Azure, a Container Apps secret reference to Key Vault), or
``SCRAPFLY_API_KEY_FILE`` naming a mounted secret file that holds the key alone or a
``SCRAPFLY_API_KEY=…`` line. It is never stored in the database, logged, put in a URL or exported: the
collector refers to it only by a short fingerprint (the first 12 hex digits of its SHA-256).

Balance. Scrapfly's Account API, ``GET https://api.scrapfly.io/account``
(https://scrapfly.io/docs/account; fields confirmed on a live read-only call on 2026-10-20):
``subscription.usage.scrape.limit`` / ``current`` / ``remaining`` / ``extra`` are API credits for the
billing period, for the whole account (every project and product that uses the key). Reading the account
uses no credits and never contacts the retailer. The last reading is kept in the database (without the
key) for ``status``.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import SecretStr
from sqlalchemy.orm import Session

from marianos_headless.acquisition import scrapfly
from marianos_headless.core.settings import ScrapflyBrowserSettings
from marianos_headless.core.timeutil import iso, utcnow
from marianos_headless.db.models import SettingRow

STATUS_ROW = "scrapfly_status"
STALE_AFTER_S = 30 * 60
ENV_KEY = "SCRAPFLY_API_KEY"
ENV_KEY_FILE = "SCRAPFLY_API_KEY_FILE"


def load_key(environ: Mapping[str, str] | None = None) -> SecretStr | None:
    """The configured key: ``SCRAPFLY_API_KEY``, else the file named by ``SCRAPFLY_API_KEY_FILE`` (the
    key alone on one line, or a ``SCRAPFLY_API_KEY=…`` line). None when neither is set."""
    env = os.environ if environ is None else environ
    key = scrapfly.load_api_key(None, env)
    if key is not None:
        return key
    path = (env.get(ENV_KEY_FILE) or "").strip()
    if not path or not Path(path).is_file():
        return None
    key = scrapfly.load_api_key(Path(path), {})
    if key is not None:
        return key
    lines = [x.strip() for x in Path(path).read_text(encoding="utf-8-sig").splitlines() if x.strip()]
    return SecretStr(lines[0]) if len(lines) == 1 and "=" not in lines[0] else None


def fingerprint(key: SecretStr) -> str:
    return hashlib.sha256(key.get_secret_value().encode()).hexdigest()[:12]


def masked(key: SecretStr | None) -> str | None:
    return f"…{fingerprint(key)[-6:]}" if key is not None else None


def key_info(environ: Mapping[str, str] | None = None) -> dict[str, Any]:
    env = os.environ if environ is None else environ
    key = load_key(env)
    source = None
    if key is not None:
        source = ENV_KEY if (env.get(ENV_KEY) or "").strip() else ENV_KEY_FILE
    return {"configured": key is not None, "fingerprint": masked(key), "source": source}


def classify(usage: scrapfly.AccountUsage) -> tuple[str, str]:
    """(connection state, message) for an account reading. States: ok, invalid_key, suspended,
    exhausted, unavailable."""
    if usage.http_status is None:
        return "unavailable", f"Scrapfly could not be reached: {usage.error or 'no answer'}"
    if usage.http_status in (401, 403):
        return "invalid_key", f"Scrapfly refused the key (HTTP {usage.http_status}). Check the key."
    if usage.http_status != 200 or usage.error:
        return (
            "unavailable",
            f"Scrapfly's account service answered HTTP {usage.http_status}; try again later.",
        )
    if usage.suspended:
        return "suspended", "Scrapfly reports this account as suspended."
    if usage.credits_remaining is not None and usage.credits_remaining <= 0:
        if usage.extra_usage_allowed:
            return (
                "ok",
                "The period's API credits are used up; extra usage is enabled on the account "
                "(billed by Scrapfly).",
            )
        return "exhausted", "The account's API credits for this billing period are used up."
    return "ok", "Connected."


def balance_view(usage: scrapfly.AccountUsage) -> dict[str, Any]:
    return {
        "unit": "API credits",
        "scope": "account-wide",
        "plan": usage.plan or None,
        "allowance": usage.credits_limit,
        "consumed": usage.credits_used,
        "remaining": usage.credits_remaining,
        "extra": usage.credits_extra,
        "extra_usage_allowed": usage.extra_usage_allowed,
        "period_start": usage.period_start or None,
        "period_end": usage.period_end or None,
        "concurrency_limit": usage.concurrency_limit,
        "observed_at": usage.observed_at,
    }


def _put(session: Session, value: dict[str, Any], actor: str) -> None:
    row = session.get(SettingRow, STATUS_ROW)
    if row is None:
        session.add(SettingRow(key=STATUS_ROW, value=value, updated_by=actor))
    else:
        row.value, row.updated_by = value, actor


def remember_balance(
    session: Session, usage: scrapfly.AccountUsage, actor: str, key: SecretStr
) -> dict[str, Any]:
    """Store a reading (without the key). A failed reading keeps the last good balance."""
    connection, message = classify(usage)
    balance = balance_view(usage) if usage.http_status == 200 and not usage.error else None
    row = session.get(SettingRow, STATUS_ROW)
    previous = dict(row.value) if row is not None else {}
    now = iso(utcnow())
    value = {
        "connection": connection,
        "message": scrapfly.redact(message, key),
        "checked_at": now,
        "fingerprint": masked(key),
        "balance": balance or previous.get("balance"),
        "balance_at": now if balance is not None else previous.get("balance_at"),
    }
    _put(session, value, actor)
    return value


def check_account(
    session: Session, settings: ScrapflyBrowserSettings, actor: str, *, get: Callable[..., Any] | None = None
) -> dict[str, Any]:
    """Read the account with the configured key (free) and record it."""
    key = load_key()
    if key is None:
        return {"connection": "not_configured", "message": "No Scrapfly API key is configured."}
    usage = scrapfly.read_account(settings, key, get=get)
    return remember_balance(session, usage, actor, key)


def status(session: Session) -> dict[str, Any]:
    """The key (fingerprint only) and the last account reading, with its age."""
    row = session.get(SettingRow, STATUS_ROW)
    st = dict(row.value) if row is not None else {}
    age = None
    if st.get("balance_at"):
        age = max(
            0,
            int((utcnow() - datetime.fromisoformat(st["balance_at"].replace("Z", "+00:00"))).total_seconds()),
        )
    return {
        "key": key_info(),
        "connection": st.get("connection") or "not_checked",
        "message": st.get("message"),
        "checked_at": st.get("checked_at"),
        "balance": st.get("balance"),
        "balance_at": st.get("balance_at"),
        "balance_age_s": age,
        "balance_stale": age is None or age > STALE_AFTER_S,
    }
