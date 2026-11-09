"""Challenge / denial detection (brief §3.4, §5.11). A detection stops the affected work; it is never
retried in a way meant to get around it and never treated as an empty category.

A challenge is recognised from the structure of the response, never from words a legitimate page can
contain:

* its HTTP status (401, 403, 407; 429 asks to slow down);
* the bot manager's own elements: its CAPTCHA container, script or frame (PerimeterX ``px-captcha``,
  Akamai's ``sec-if-cpt`` container, CAPTCHA iframes), an edge error page, a ``/blocked`` page's data;
* a response that is not the site's content: the page data every content page embeds is missing.

Denial wording ("Access Denied", "Reference #...", "Robot or human?", "Pardon Our Interruption", ...)
makes a challenge only beside one of those signals. It is never read inside the page's data scripts
(``application/json``, JSON-LD): their strings are the site's content, such as customer reviews (on
2026-10-26 a brand's reply to a review on item 15353921746's page, "provide the reference #48395435", was
taken for an Akamai reference id and the page for a refusal). Wording outside the data on a page that has
its data and no challenge signal is reported as ``ambiguous_wording:<marker>``, not as a challenge: the
page is read like any other and its own data decides (a page without the expected item or store fails
those checks)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

# The bot manager's own elements and pages: each alone is a challenge.
_STRUCTURE = [
    (re.compile(r"errors\.edgesuite\.net", re.I), "edgesuite_error_page"),
    (re.compile(r"sec-if-cpt-container|_sec/cp_challenge|sec-cpt-if", re.I), "akamai_challenge_container"),
    (re.compile(r"<iframe[^>]+(captcha|hcaptcha|recaptcha|arkoselabs|funcaptcha)", re.I), "captcha_iframe"),
    (re.compile(r"Request unsuccessful\. Incapsula", re.I), "incapsula"),
    # PerimeterX / HUMAN (Walmart): the press-and-hold CAPTCHA's container and script.
    (re.compile(r"\bpx-captcha\b|captcha\.px-cdn\.net", re.I), "perimeterx_captcha"),
]
# Wording of a challenge or denial page: a challenge only beside a signal above, a bad status, or on a
# response without the site's page data.
_WORDING = [
    (re.compile(r"Access Denied", re.I), "access_denied_text"),
    (re.compile(r"Reference\s*#\s*[\w.]+", re.I), "akamai_reference_id"),
    (re.compile(r"Powered and protected by", re.I), "protection_interstitial"),
    (re.compile(r"Pardon Our Interruption", re.I), "interruption_page"),
    (re.compile(r"Robot or human\?", re.I), "perimeterx_robot_or_human"),
    (re.compile(r"Press (?:&amp;|&) Hold", re.I), "press_and_hold_captcha"),
]
# The page's data scripts: their strings are the site's content (reviews, descriptions), never a challenge.
_DATA_SCRIPT = re.compile(
    r"<script\b[^>]*\btype\s*=\s*[\"']application/(?:ld\+)?json[\"'][^>]*>.*?</script\s*>", re.I | re.S
)
# A Next.js page whose own route is the bot manager's block page (walmart.com/blocked).
_BLOCKED_PAGE_DATA = re.compile(r'"page"\s*:\s*"/blocked"')
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
    """Classify a top-level document response (see the module docstring).

    ``expect_initial_state``: the site's content pages always embed their page data (``state_marker``:
    Mariano's ``window.__INITIAL_STATE__``, Walmart's ``__NEXT_DATA__`` script); a page without it is a
    shell or interstitial, not content. Without it (robots.txt), a missing page data is no challenge by
    itself, but denial wording on such a response is.
    """
    strong: list[str] = []
    notes: list[str] = []
    if status in (401, 403, 407):
        strong.append(f"http_{status}")
    if status == 429:
        strong.append("http_429_rate_limited")
    # Everything but the data scripts, whole: a challenge dialog may be added at the end of a large page
    # (Walmart, live 2026-10-20: "Robot or human?" appended after 400 kB of store page).
    markup = _DATA_SCRIPT.sub(" ", html)
    strong.extend(name for rx, name in _STRUCTURE if rx.search(markup))
    if _BLOCKED_PAGE_DATA.search(html):
        strong.append("blocked_page_data")
    has_data = state_marker in html
    wording = [name for rx, name in _WORDING if rx.search(markup)]
    if wording:
        if strong or not has_data:
            strong.extend(wording)
        else:
            notes.extend(f"ambiguous_wording:{w}" for w in wording)
    # Wording inside the page's own data (a review, a description): recorded, never a signal.
    notes.extend(
        f"in_page_data:{name}"
        for rx, name in _WORDING
        if name not in wording and any(rx.search(m.group(0)) for m in _DATA_SCRIPT.finditer(html))
    )
    if expect_initial_state and not has_data:
        strong.append("missing_initial_state")
    return ChallengeVerdict(bool(strong), tuple(dict.fromkeys([*strong, *notes])), status)


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


def signals(verdict: ChallengeVerdict) -> tuple[str, ...]:
    """The verdict's challenge signals, without its notes (``ambiguous_wording:…``, ``in_page_data:…``)."""
    return tuple(r for r in verdict.reasons if ":" not in r)


def notes(verdict: ChallengeVerdict) -> tuple[str, ...]:
    """Wording seen on a page that was not taken for a challenge, recorded with the page's capture."""
    return tuple(r for r in verdict.reasons if ":" in r)


def is_rate_limit_only(verdict: ChallengeVerdict) -> bool:
    """A plain HTTP 429 (slow down), with no denial or CAPTCHA marker that would make it a block."""
    return verdict.http_status == 429 and set(signals(verdict)) <= _RATE_LIMIT_ONLY


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
