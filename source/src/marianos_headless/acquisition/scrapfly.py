"""Scrapfly Cloud Browser: connection, credentials, account usage and credit metering (ADR-008).

The API key is read from the environment or a git-ignored env file and kept in a ``SecretStr``. The
WebSocket endpoint that carries it exists only in memory; every message that could contain it passes
through :func:`redact`. Failures on the provider's side (authentication, quota, concurrency, rejected
parameters, our own credit cap, proxy/network) are :class:`ProviderError`, kept apart from the
retailer's own answers (challenge pages, HTTP 403/429), which stay ``ChallengeDetected``.

Billing model (https://scrapfly.io/docs/cloud-browser-api/billing, free plan): 1 credit per 30 s
started, bandwidth per MB (7 credits datacenter, 52 residential), at least 5 credits per browser.
:class:`CreditMeter` estimates that from the bytes the page reports over CDP; the account API gives
the billed figure afterwards.
"""

from __future__ import annotations

import logging
import math
import os
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from time import monotonic
from typing import Any
from urllib.parse import urlencode, urlsplit

from pydantic import SecretStr

from marianos_headless.core.settings import ScrapflyBrowserSettings
from marianos_headless.core.timeutil import iso, utcnow

ENV_KEY = "SCRAPFLY_API_KEY"
REDACTED = "[REDACTED]"
_KEY_PARAM = re.compile(r"(?i)\b(api_key|key)=[^&\s'\"<>]+")


class ProviderErrorKind(StrEnum):
    AUTH = "auth"  # key missing, invalid, revoked or account suspended
    QUOTA = "quota"  # credits or plan limit exhausted
    CONCURRENCY = "concurrency"  # too many browsers at once
    CONFIG = "config"  # parameters rejected
    BUDGET = "budget"  # this run's own credit cap
    NETWORK = "network"  # provider or its proxy unreachable
    SESSION = "session"  # the cloud browser went away mid-run (provider timeout, closed)
    PROVIDER = "provider"  # any other provider-side failure


class ProviderError(RuntimeError):
    def __init__(self, kind: ProviderErrorKind, message: str):
        super().__init__(f"{kind.value}: {message}")
        self.kind = kind


def redact(text: str, secret: SecretStr | str | None = None) -> str:
    """Remove the key, and any ``key=``/``api_key=`` query value, from a message."""
    value = secret.get_secret_value() if isinstance(secret, SecretStr) else secret
    if value:
        text = text.replace(value, REDACTED)
    return _KEY_PARAM.sub(lambda m: f"{m.group(1)}={REDACTED}", text)


def load_api_key(env_file: Path | None, environ: Mapping[str, str] | None = None) -> SecretStr | None:
    """``SCRAPFLY_API_KEY`` from the environment, else from a ``KEY=value`` line of ``env_file``."""
    env = os.environ if environ is None else environ
    value = (env.get(ENV_KEY) or "").strip()
    if not value and env_file is not None and env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            name, sep, raw = line.strip().removeprefix("export ").partition("=")
            if sep and name.strip() == ENV_KEY:
                value = raw.strip().strip('"').strip("'")
                break
    return SecretStr(value) if value else None


def _flag(value: bool) -> str:
    return "true" if value else "false"


def connection_params(settings: ScrapflyBrowserSettings) -> dict[str, str]:
    """Every connection parameter except the key (safe to record as evidence)."""
    return {
        "proxy_pool": settings.proxy_pool,
        "country": settings.country,
        **({"os": settings.browser_os} if settings.browser_os else {}),
        **({"browser_brand": settings.browser_brand} if settings.browser_brand else {}),
        "target_url": settings.target_url,
        "auto_close": "true",  # the browser stops when this client disconnects
        "timeout": str(settings.session_timeout_s),
        "block_images": _flag(settings.block_images),
        "block_fonts": _flag(settings.block_fonts),
        "block_media": _flag(settings.block_media),
        "block_styles": _flag(settings.block_styles),
        "blacklist": _flag(settings.blacklist),
        "cache": _flag(settings.cache),
    }


def ws_endpoint(settings: ScrapflyBrowserSettings, api_key: SecretStr) -> str:
    """The authenticated CDP endpoint. Never log or store it; use :func:`public_endpoint`."""
    params = {"api_key": api_key.get_secret_value(), **connection_params(settings)}
    return f"{settings.endpoint}?{urlencode(params)}"


def public_endpoint(settings: ScrapflyBrowserSettings) -> str:
    return f"{settings.endpoint}?{urlencode({'api_key': REDACTED, **connection_params(settings)})}"


_CONNECT_RULES: tuple[tuple[re.Pattern[str], ProviderErrorKind], ...] = (
    (
        re.compile(r"ERR::\w+::CONFIG|CONFIG_ERROR|\b(400|422)\b|invalid param", re.I),
        ProviderErrorKind.CONFIG,
    ),
    (re.compile(r"\b401\b|unauthori[sz]ed|invalid (api )?key|ERR::AUTH", re.I), ProviderErrorKind.AUTH),
    (
        re.compile(r"\b402\b|quota|credits?\b|ERR::(ACCOUNT|SUBSCRIPTION|QUOTA)|payment", re.I),
        ProviderErrorKind.QUOTA,
    ),
    (re.compile(r"\b429\b|concurren|too many", re.I), ProviderErrorKind.CONCURRENCY),
    (re.compile(r"\b403\b|forbidden|suspended", re.I), ProviderErrorKind.AUTH),
    (
        re.compile(r"timeout|timed out|ECONNREFUSED|ENOTFOUND|ECONNRESET|getaddrinfo|socket hang up", re.I),
        ProviderErrorKind.NETWORK,
    ),
)


def classify_connect_error(message: str) -> ProviderErrorKind:
    for rx, kind in _CONNECT_RULES:
        if rx.search(message):
            return kind
    return ProviderErrorKind.PROVIDER


_PROXY_NET_ERRORS = re.compile(
    r"ERR_TUNNEL_CONNECTION_FAILED|ERR_PROXY_CONNECTION_FAILED|ERR_PROXY_AUTH|ERR_NO_SUPPORTED_PROXIES"
    r"|ERR_PROXY_CERTIFICATE|ERR_MANDATORY_PROXY",
    re.I,
)
_SESSION_GONE = re.compile(
    r"Target page, context or browser has been closed|Browser has been closed|browser has disconnected"
    r"|Connection closed|Target closed",
    re.I,
)


_TIMEOUT = re.compile(r"Timeout \d+ms exceeded", re.I)


def classify_navigation_error(message: str) -> str:
    """``provider`` (proxy or cloud browser failure), ``timeout`` (no answer in time: neither a refusal
    nor a provider error, but the run stops all the same), ``client`` (the collector's own resource policy
    or traffic ceiling aborted the page), or ``origin_network`` (the connection to the site was
    reset/closed/refused: possibly the site's edge, possibly the path to it; a refusal)."""
    if "ERR_BLOCKED_BY_CLIENT" in message:
        return "client"
    if _PROXY_NET_ERRORS.search(message) or _SESSION_GONE.search(message):
        return "provider"
    if _TIMEOUT.search(message):
        return "timeout"
    return "origin_network"


_PROVIDER_PAGE = re.compile(r"ERR::[A-Z_]+::[A-Z_]+")


def provider_error_in_document(html: str) -> str | None:
    """A provider error code shown instead of the site's page (e.g. ``ERR::PROXY::...``)."""
    m = _PROVIDER_PAGE.search(html[:50_000])
    return m.group(0) if m else None


# -- account ----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class AccountUsage:
    """The parts of ``GET /account`` this project needs. No account ID, timezone or e-mail is kept."""

    observed_at: str
    http_status: int | None
    plan: str = ""
    period_start: str = ""
    period_end: str = ""
    credits_limit: int | None = None
    credits_used: int | None = None
    credits_remaining: int | None = None
    credits_extra: int | None = None
    extra_usage_allowed: bool | None = None
    project_allow_extra_usage: bool | None = None
    project_budget_limit: Any = None
    concurrency_limit: int | None = None
    concurrency_in_use: int | None = None
    suspended: bool | None = None
    error: str | None = None


def _dig(obj: Any, *path: str) -> Any:
    for key in path:
        if not isinstance(obj, Mapping):
            return None
        obj = obj.get(key)
    return obj


def account_usage_from_json(body: Mapping[str, Any], status: int) -> AccountUsage:
    usage = _dig(body, "subscription", "usage", "scrape") or {}
    return AccountUsage(
        observed_at=iso(utcnow()),
        http_status=status,
        plan=str(_dig(body, "subscription", "plan_name") or ""),
        period_start=str(_dig(body, "subscription", "period", "start") or ""),
        period_end=str(_dig(body, "subscription", "period", "end") or ""),
        credits_limit=usage.get("limit"),
        credits_used=usage.get("current"),
        credits_remaining=usage.get("remaining"),
        credits_extra=usage.get("extra"),
        extra_usage_allowed=_dig(body, "subscription", "extra_scrape_allowed"),
        project_allow_extra_usage=_dig(body, "project", "allow_extra_usage"),
        project_budget_limit=_dig(body, "project", "budget_limit"),
        concurrency_limit=usage.get("concurrent_limit"),
        concurrency_in_use=usage.get("concurrent_usage"),
        suspended=_dig(body, "account", "suspended"),
    )


def read_account(
    settings: ScrapflyBrowserSettings, api_key: SecretStr, get: Callable[..., Any] | None = None
) -> AccountUsage:
    """Read-only account check (no credits). ``get`` is ``httpx.get``-like (injectable for tests).

    The key travels in the ``Authorization: Bearer`` header, which the Account API accepts besides the
    ``key`` query parameter (its own 401 answer says so; confirmed on 2026-10-20), so it is never part
    of a URL that a log line could show."""
    if get is None:
        import httpx

        logging.getLogger("httpx").setLevel(logging.WARNING)  # request lines stay out of the logs
        get = httpx.get
    try:
        headers = {"Authorization": f"Bearer {api_key.get_secret_value()}"}
        resp = get(settings.account_url, headers=headers, timeout=30)
        body = resp.json()
    except Exception as exc:  # network failure or a non-JSON answer: report, never raise the key
        return AccountUsage(
            observed_at=iso(utcnow()), http_status=None, error=redact(str(exc), api_key)[:300]
        )
    if not isinstance(body, Mapping) or resp.status_code != 200:
        text = redact(str(body), api_key)[:300]
        return AccountUsage(observed_at=iso(utcnow()), http_status=resp.status_code, error=text)
    return account_usage_from_json(body, resp.status_code)


# -- credit meter -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class CreditEstimate:
    elapsed_s: float
    bytes_seen: int
    time_credits: int
    bandwidth_mb: float
    bandwidth_credits: float
    credits: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "elapsed_s": round(self.elapsed_s, 1),
            "bytes_seen": self.bytes_seen,
            "time_credits": self.time_credits,
            "bandwidth_mb": round(self.bandwidth_mb, 3),
            "bandwidth_credits": self.bandwidth_credits,
            "credits": self.credits,
        }


@dataclass
class CreditMeter:
    """Running estimate of a cloud-browser session's credits from the bytes the page received.

    The page meter cannot see everything the provider bills (cross-origin frames, TLS, uploads), so
    bytes are scaled by ``overhead``. Bandwidth is priced per fractional MB: the published "per started
    MB" rounding did not show in the account (sessions of a few kilobytes were billed the 5-credit
    minimum), so each run is calibrated against the account afterwards instead.
    """

    rate_per_mb: float
    overhead: float = 1.3
    clock: Callable[[], float] = monotonic
    started: float = field(default=-1.0)
    bytes_seen: int = 0
    responses: int = 0
    by_host: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.started < 0:
            self.started = self.clock()

    def add(self, url: str, n: int) -> None:
        n = max(0, int(n))
        self.bytes_seen += n
        self.responses += 1
        host = urlsplit(url).hostname or "(other)"
        self.by_host[host] = self.by_host.get(host, 0) + n

    def estimate(self, extra_bytes: int = 0, extra_s: float = 0.0) -> CreditEstimate:
        elapsed = max(0.0, self.clock() - self.started) + extra_s
        time_credits = max(1, math.ceil(elapsed / 30))
        total = self.bytes_seen + max(0, extra_bytes)
        mb = total * self.overhead / 1_000_000
        bw = float(math.ceil(mb * self.rate_per_mb))
        return CreditEstimate(elapsed, total, time_credits, mb, bw, max(5.0, time_credits + bw))

    def top_hosts(self, n: int = 15) -> list[dict[str, Any]]:
        rows = sorted(self.by_host.items(), key=lambda kv: kv[1], reverse=True)[:n]
        return [{"host": h, "bytes": b} for h, b in rows]


def rate_per_mb(settings: ScrapflyBrowserSettings) -> float:
    if settings.proxy_pool == "residential":
        return settings.credits_per_mb_residential
    return settings.credits_per_mb_datacenter
