"""The Kroger Public API probe client (TEST_PLAN P1): an expired token is renewed, a 429 waits for its
Retry-After, the calls are counted before they are sent, and no credential or token reaches a saved file.
A mock transport stands in for Kroger: nothing leaves the process."""

from __future__ import annotations

import base64
from pathlib import Path

import httpx
import pytest

from probes import kroger_api as kp

CLIENT_ID, SECRET = "probe-client-id-test", "probe-client-secret-test-0123"
TOKENS = ("tok-one-aaaaaaaaaaaaaaaa", "tok-two-bbbbbbbbbbbbbbbb")


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[kp.Client, list[str], list[float]]:
    secrets = tmp_path / "secrets"
    secrets.mkdir()
    (secrets / "krogerapi.env").write_text(
        f"CLIENT_ID={CLIENT_ID}\nCLIENT_SECRET={SECRET}\n", encoding="utf-8"
    )
    monkeypatch.setenv("MARIANOS_PROBE_SECRETS", str(secrets))
    monkeypatch.setenv("MARIANOS_PROBE_OUT", str(tmp_path / "out"))
    sleeps: list[float] = []
    monkeypatch.setattr(kp.time, "sleep", sleeps.append)
    issued = iter(TOKENS)
    sent: list[str] = []

    def kroger(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/connect/oauth2/token":
            assert (
                request.headers["Authorization"]
                == "Basic " + base64.b64encode(f"{CLIENT_ID}:{SECRET}".encode()).decode()
            )
            return httpx.Response(200, json={"access_token": next(issued), "expires_in": 1800})
        sent.append(request.headers["Authorization"])
        if len(sent) == 1:
            return httpx.Response(401, json={"error": "invalid_token"})  # the token expired
        if len(sent) == 2:
            return httpx.Response(429, headers={"Retry-After": "3"}, json={"errors": {"reason": "rate"}})
        return httpx.Response(200, json={"data": [{"productId": "0001111041700"}], "meta": {}})

    c = kp.Client()
    c.http = httpx.Client(transport=httpx.MockTransport(kroger))
    return c, sent, sleeps


def test_an_expired_token_is_renewed_and_a_429_waits_for_its_retry_after(
    client: tuple[kp.Client, list[str], list[float]], tmp_path: Path
) -> None:
    c, sent, sleeps = client
    status, body = c.get("/v1/products", {"filter.term": "milk", "filter.locationId": "53100503"}, "t")
    assert status == 200 and body["data"][0]["productId"] == "0001111041700"
    assert sent == [f"Bearer {TOKENS[0]}", f"Bearer {TOKENS[1]}", f"Bearer {TOKENS[1]}"]
    assert sleeps == [3.0]
    assert c.ledger.used("kroger", kp.PHASE) == 5  # two tokens and three product calls, each reserved first
    basic = base64.b64encode(f"{CLIENT_ID}:{SECRET}".encode()).decode()
    saved = [p for p in (tmp_path / "out").rglob("*") if p.is_file() and p.suffix != ".sqlite"]
    assert saved
    for path in saved:
        data = path.read_bytes()
        for secret in (CLIENT_ID, SECRET, basic, *TOKENS):
            assert secret.encode() not in data, (path, secret)


def test_a_rate_limit_that_persists_is_returned_not_retried_forever(
    client: tuple[kp.Client, list[str], list[float]], monkeypatch: pytest.MonkeyPatch
) -> None:
    c, _, sleeps = client
    c.http = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(429, json={})))
    c._token, c._token_until = "tok-cached-cccccccccccc", kp.time.monotonic() + 600
    status, _ = c.get("/v1/products", {"filter.term": "milk"}, "t")
    assert status == 429 and sleeps == [2, 8]  # three attempts in all, then the answer is the caller's
