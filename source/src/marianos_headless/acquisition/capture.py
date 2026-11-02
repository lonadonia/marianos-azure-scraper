"""Passive capture of the JSON responses the page itself requests (brief §5.10).

Bodies are stored unchanged (gzip) under the run's ``raw/`` prefix. Request and response headers are
kept only after allowlist redaction: no cookies, authorization or bot-manager headers (§3.7).
"""

from __future__ import annotations

import gzip
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, urlsplit

CAPTURE_PATTERNS: dict[str, re.Pattern[str]] = {
    "products_search": re.compile(r"/atlas/v1/search/v1/products-search(?:\?|$)"),
    "products_v2": re.compile(r"/atlas/v1/product/v2/products(?:\?|$)"),
    # The coupons of a page's products (live 2026-10-20: /atlas/v1/savings-coupons/v2/coupons?filter.upc=…).
    "coupons": re.compile(r"/atlas/v1/savings-coupons/v\d+/coupons(?:\?|$)"),
    "amp_experiences": re.compile(r"/atlas/v1/dynamic-experience/v1/amp-experiences"),
    "modality": re.compile(r"/atlas/v1/modality/|/modality-preferences|/atlas/v1/.*modalit", re.I),
    "stores": re.compile(r"/atlas/v1/stores/|/atlas/v1/store-search|/atlas/v1/.*locations?\b", re.I),
    "offers": re.compile(r"/offers/engagement/v1/offers"),
    "atlas_other": re.compile(r"/atlas/v1/"),
}

REQUEST_HEADER_ALLOWLIST = frozenset(
    {
        "accept",
        "content-type",
        "x-kroger-channel",
        "x-laf-object",
        "x-modality",
        "x-modality-type",
        "x-geo-location-v1",
        "x-call-origin",
    }
)
RESPONSE_HEADER_ALLOWLIST = frozenset({"content-type", "content-length", "date", "cache-control", "age"})
# Top-level documents also keep the edge's server name and any pause it asks for.
DOCUMENT_HEADER_ALLOWLIST = RESPONSE_HEADER_ALLOWLIST | {"server", "retry-after"}


def classify_url(url: str) -> str | None:
    for kind, rx in CAPTURE_PATTERNS.items():
        if rx.search(url):
            return kind
    return None


def redact_headers(headers: dict[str, str], allow: frozenset[str]) -> dict[str, str]:
    return {k.lower(): v for k, v in headers.items() if k.lower() in allow}


def query_values(url: str, name: str) -> list[str]:
    return parse_qs(urlsplit(url).query).get(name, [])


@dataclass
class CapturedResponse:
    seq: int
    fetch_id: str
    kind: str
    url: str
    method: str
    status: int
    request_location_id: str | None
    request_taxonomies: list[str]
    request_headers: dict[str, str]
    response_headers: dict[str, str]
    body_sha256: str | None
    body_bytes: int
    artifact_key: str | None
    observed_at: str
    error: str | None = None
    json_ok: bool | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def gzip_bytes(data: bytes) -> bytes:
    # mtime=0 keeps the gzip wrapper deterministic, so identical bodies give identical artifacts.
    return gzip.compress(data, mtime=0)
