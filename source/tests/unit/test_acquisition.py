from __future__ import annotations

import asyncio
import random

import pytest

from marianos_headless.acquisition.capture import REQUEST_HEADER_ALLOWLIST, classify_url, redact_headers
from marianos_headless.acquisition.challenge import detect_document_challenge
from marianos_headless.acquisition.pacing import LatencyWatch, NavigationBudgetExceeded, Pacer
from marianos_headless.acquisition.robots import parse_robots

ROBOTS = """
User-agent: *
Disallow: /checkout*
Disallow: /clickstream*
Disallow: /locations*
Disallow: /in-stores/
Disallow: /recipes/api/v1/*
Disallow: /*.pdf$
Allow: /in-stores/ok
Sitemap: https://www.marianos.com/sitemap.xml

User-agent: BadBot
Disallow: /
"""


@pytest.mark.parametrize(
    ("url", "allowed"),
    [
        ("https://www.marianos.com/d/produce", True),
        ("https://www.marianos.com/pl/batteries/26003?pzn=relevance", True),
        ("https://www.marianos.com/p/diet-coke/0004900006722", True),
        ("https://www.marianos.com/savings/cl/coupons/", True),
        ("https://www.marianos.com/checkout/cart", False),
        ("https://www.marianos.com/locations/il", False),
        ("https://www.marianos.com/in-stores/x", False),
        ("https://www.marianos.com/in-stores/ok", True),  # longer Allow wins
        ("https://www.marianos.com/recipes/api/v1/x", False),
        ("https://www.marianos.com/weekly-ad.pdf", False),
        ("https://www.marianos.com/weekly-ad.pdf?x=1", True),  # "$" anchors the end
    ],
)
def test_robots(url: str, allowed: bool) -> None:
    policy = parse_robots(ROBOTS)
    assert policy.allowed(url) is allowed
    assert policy.sitemaps == ["https://www.marianos.com/sitemap.xml"]


def test_robots_specific_agent_group() -> None:
    assert not parse_robots(ROBOTS, "BadBot").allowed("https://www.marianos.com/d/produce")


def test_challenge_detection() -> None:
    ok = "<html><script>window.__INITIAL_STATE__ = JSON.parse('{}')</script></html>"
    assert not detect_document_challenge(200, ok).is_challenge
    denied = "<html><h1>Access Denied</h1>Reference #18.6f2d3e17.1729180000.abc</html>"
    v = detect_document_challenge(403, denied)
    assert v.is_challenge and "http_403" in v.reasons and "akamai_reference_id" in v.reasons
    assert detect_document_challenge(200, "<html><body></body></html>").is_challenge  # empty shell
    assert detect_document_challenge(429, ok).is_challenge
    # "Access Denied" in ordinary copy alone is not a challenge
    assert not detect_document_challenge(200, ok + "<p>Access Denied items</p>").is_challenge


def test_capture_classification_and_redaction() -> None:
    assert classify_url(
        "https://www.marianos.com/atlas/v1/search/v1/products-search?filter.locationId=1"
    ) == ("products_search")
    assert (
        classify_url("https://www.marianos.com/atlas/v1/product/v2/products?filter.gtin13s=1")
        == "products_v2"
    )
    assert classify_url("https://www.marianos.com/static/app.js") is None
    headers = {"Cookie": "x", "X-Laf-Object": "[]", "authorization": "y", "Accept": "*/*", "akamai-bot": "z"}
    assert redact_headers(headers, REQUEST_HEADER_ALLOWLIST) == {"x-laf-object": "[]", "accept": "*/*"}


def test_pacer_enforces_interval_and_budget() -> None:
    now = [0.0]
    slept: list[float] = []

    async def fake_sleep(s: float) -> None:
        slept.append(s)
        now[0] += s

    pacer = Pacer(4.0, 1.0, max_navigations=3, clock=lambda: now[0], sleep=fake_sleep, rng=random.Random(1))

    async def run() -> None:
        await pacer.wait_turn()
        now[0] += 1.0
        await pacer.wait_turn()
        await pacer.wait_turn()
        with pytest.raises(NavigationBudgetExceeded):
            await pacer.wait_turn()

    asyncio.run(run())
    assert len(slept) == 2 and all(s >= 4.0 - 1.0 for s in slept[:1]) and all(s >= 4.0 for s in slept[1:])
    with pytest.raises(ValueError):
        Pacer(0.5, 0)


def test_latency_watch() -> None:
    w = LatencyWatch(window=3, factor=3.0)
    flags = [w.add(x) for x in [1, 1, 1, 1, 1, 1]]
    assert not any(flags)
    assert [w.add(x) for x in [5, 5, 5]][-1]
