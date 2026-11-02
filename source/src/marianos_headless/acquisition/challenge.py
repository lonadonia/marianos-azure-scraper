"""Challenge / denial detection (brief §3.4, §5.11). A detection stops the affected work; it is never
retried in a way meant to get around it and never treated as an empty category."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

_DENIAL_MARKERS = [
    (re.compile(r"Access Denied", re.I), "access_denied_text"),
    (re.compile(r"Reference\s*#\s*[\w.]+", re.I), "akamai_reference_id"),
    (re.compile(r"errors\.edgesuite\.net", re.I), "edgesuite_error_page"),
    (re.compile(r"sec-if-cpt-container|_sec/cp_challenge|sec-cpt-if", re.I), "akamai_challenge_container"),
    (re.compile(r"Powered and protected by", re.I), "protection_interstitial"),
    (re.compile(r"<iframe[^>]+(captcha|hcaptcha|recaptcha|arkoselabs|funcaptcha)", re.I), "captcha_iframe"),
    (re.compile(r"Request unsuccessful\. Incapsula", re.I), "incapsula"),
    (re.compile(r"Pardon Our Interruption", re.I), "interruption_page"),
    # PerimeterX / HUMAN (Walmart): the "Robot or human?" page with its press-and-hold CAPTCHA.
    (re.compile(r"Robot or human\?", re.I), "perimeterx_robot_or_human"),
    (re.compile(r"\bpx-captcha\b|captcha\.px-cdn\.net", re.I), "perimeterx_captcha"),
    (re.compile(r"Press (?:&amp;|&) Hold", re.I), "press_and_hold_captcha"),
]
# The data every content page of a site embeds: a page without it is a shell or an interstitial.
MARIANOS_STATE_MARKER = "window.__INITIAL_STATE__"
WALMART_STATE_MARKER = 'id="__NEXT_DATA__"'


@dataclass(frozen=True)
class ChallengeVerdict:
    is_challenge: bool
    reasons: tuple[str, ...] = field(default_factory=tuple)
    http_status: int | None = None


def detect_document_challenge(
    status: int | None,
    html: str,
    *,
    expect_initial_state: bool = True,
    state_marker: str = MARIANOS_STATE_MARKER,
) -> ChallengeVerdict:
    """Classify a top-level document response.

    ``expect_initial_state``: the site's content pages always embed their page data (``state_marker``:
    Mariano's ``window.__INITIAL_STATE__``, Walmart's ``__NEXT_DATA__`` script); a page without it is a
    shell or interstitial, not content.
    """
    reasons: list[str] = []
    if status in (401, 403, 407):
        reasons.append(f"http_{status}")
    if status == 429:
        reasons.append("http_429_rate_limited")
    # The start and the end of the document: a challenge dialog may be added at the end of a large page
    # (Walmart, live 2026-10-20: "Robot or human?" appended after 400 kB of store page).
    scanned = html if len(html) <= 400_000 else html[:200_000] + "\n" + html[-200_000:]
    for rx, name in _DENIAL_MARKERS:
        if rx.search(scanned):
            reasons.append(name)
    # "Access Denied" alone can appear in normal copy; require a second signal or a bad status.
    strong = [r for r in reasons if r not in ("access_denied_text",)]
    if expect_initial_state and state_marker not in html:
        strong.append("missing_initial_state")
        reasons.append("missing_initial_state")
    return ChallengeVerdict(bool(strong), tuple(dict.fromkeys(reasons)), status)


# A data request answered by the bot manager instead of the site (PerimeterX/HUMAN, live on Walmart
# 2026-10-20: {"redirectUrl":"/blocked?url=…","appId":"PX…","blockScript":"/px/…/captcha/captcha.js…"}).
_BLOCKED_RESPONSE = re.compile(
    rb'"blockScript"\s*:\s*"[^"]*captcha|"redirectUrl"\s*:\s*"/blocked\?|"appId"\s*:\s*"PX[A-Za-z0-9]+"[^}]*"captcha',
    re.I,
)


def blocked_response(body: bytes) -> bool:
    """A data response that is the bot manager's block (a refusal), not the site's own data."""
    return bool(_BLOCKED_RESPONSE.search(body[:20_000]))


def is_rate_limited(verdict: ChallengeVerdict) -> bool:
    return verdict.http_status == 429


_RATE_LIMIT_ONLY = {"http_429_rate_limited", "missing_initial_state"}


def is_rate_limit_only(verdict: ChallengeVerdict) -> bool:
    """A plain HTTP 429 (slow down), with no denial or CAPTCHA marker that would make it a block."""
    return verdict.http_status == 429 and set(verdict.reasons) <= _RATE_LIMIT_ONLY


def parse_retry_after(value: str | None, now: datetime) -> float | None:
    """Seconds an HTTP ``Retry-After`` header asks for: delay-seconds or an HTTP-date (RFC 9110 §10.2.3).
    None when the header is absent or unreadable; never negative."""
    if value is None:
        return None
    text = value.strip()
    if text.isdigit():
        return float(int(text))
    try:
        when = parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max(0.0, (when - now).total_seconds())
