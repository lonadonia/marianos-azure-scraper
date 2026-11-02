"""One bounded Oxylabs Web API probe of TEST_PLAN_180 section 2. Reserves in the ledger before dispatch, saves the
answer sanitized (no key, no Authorization header), appends one row to the hypothesis log.

    python -X utf8 probe180.py discover
    python -X utf8 probe180.py send <ID> <endpoint> '<json body without output/location>' [--hyp TEXT]

The key is read only through the collector's load_key(); only its fingerprint is printed.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, r"C:\m5\wt\headless\marianos-azure-headless\src")
sys.path.insert(0, r"C:\m6\tools")
import budget180  # noqa: E402
from marianos_headless.acquisition import oxylabs  # noqa: E402
from marianos_headless.sites.marianos.initial_state import parse_initial_state  # noqa: E402
from marianos_headless.sites.marianos.sanitize import sanitize_html  # noqa: E402
from marianos_headless.sites.marianos.search_state import price_location, search_summary, state_products  # noqa: E402

ROOT = Path(r"<projects>\marianos-scraper")
OUT = Path(r"C:\m6\ev\probes")
LOG = OUT / "hypotheses.jsonl"
BASE = "https://webapi.oxylabs.io"
RATE = 0.0015


def key():
    k = oxylabs.load_key({oxylabs.ENV_KEY_FILE: str(ROOT / "data" / "local" / "oxylabs.env")})
    if k is None:
        raise SystemExit("no key")
    return k


def stamp() -> str:
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def discover() -> None:
    k = key()
    print("key fingerprint", oxylabs.fingerprint(k))
    h = {"Authorization": f"Bearer {k.get_secret_value()}"}
    OUT.mkdir(parents=True, exist_ok=True)
    with httpx.Client(base_url=BASE, timeout=60) as c:
        r = c.get("/v1/scrapers", headers=h)
        print("GET /v1/scrapers", r.status_code, len(r.content))
        (OUT / f"{stamp()}_L0_scrapers.json").write_text(oxylabs.redact(r.text, k), encoding="utf-8")
        try:
            names = [x.get("name") or x.get("id") or x for x in (r.json().get("scrapers") or r.json().get("data") or [])]
            print(" marianos entries:", [n for n in names if "marian" in str(n).lower()][:10], "of", len(names))
        except Exception as exc:  # noqa: BLE001
            print(" list not parsed", type(exc).__name__)
        for ep in ("/v1/scrape/marianos", "/v1/scrape/marianos/search", "/v1/scrape/marianos/product"):
            r = c.options(ep, headers=h)
            name = ep.replace("/", "_")
            print("OPTIONS", ep, r.status_code, len(r.content))
            (OUT / f"{stamp()}_L0_options{name}.json").write_text(oxylabs.redact(r.text, k), encoding="utf-8")


def analyse(html: str) -> dict:
    out: dict = {"chars": len(html)}
    try:
        st = parse_initial_state(html)
    except Exception as exc:  # noqa: BLE001
        out["state"] = f"none ({type(exc).__name__})"
        out["head"] = html[:300]
        return out
    s = search_summary(st)
    prods = state_products(st)
    sa = (st.get("search") or {}).get("searchAll") or {}
    out["requestVars"] = {k: v for k, v in (sa.get("requestVars") or {}).items() if v not in ([], "", None)}
    out["summary"] = None if s is None else {k: v for k, v in s.as_dict().items() if k not in ("sub_commodities",)}
    out["state_products"] = len(prods)
    out["price_locations"] = sorted({str(price_location(p)) for p in prods})
    err = sa.get("error") or {}
    if err:
        cfg = err.get("config") or {}
        out["retailer_error"] = {"status": err.get("status"), "message": err.get("message"), "url": cfg.get("url"),
                                 "params": cfg.get("params")}
    return out


def send(pid: str, endpoint: str, body: dict, hyp: str) -> None:
    k = key()
    OUT.mkdir(parents=True, exist_ok=True)
    full = {**body, "location": "US", "output": ["html"]}
    rid = budget180.reserve("OXP", "L", RATE, note=f"{pid}: {hyp}"[:300])
    t0 = time.monotonic()
    at = stamp()
    try:
        with httpx.Client(base_url=BASE, timeout=180) as c:
            r = c.post(endpoint, json=full, headers={"Authorization": f"Bearer {k.get_secret_value()}"})
    except httpx.HTTPError as exc:
        budget180.settle(rid, RATE, outcome=f"{pid}: transport {type(exc).__name__}, possibly charged")
        print("TRANSPORT", type(exc).__name__)
        return
    secs = round(time.monotonic() - t0, 1)
    html, meta = oxylabs.envelope(r.content)
    kind = oxylabs.classify(r.status_code, r.content, html)
    charged = oxylabs.CHARGED.get(kind)
    usd = RATE if charged is None or charged else 0.0
    budget180.settle(rid, usd, outcome=f"{pid}: HTTP {r.status_code} kind {kind} charged {charged}")
    rec = {"id": pid, "at": at, "seconds": secs, "endpoint": endpoint, "request": full, "hypothesis": hyp, "status": r.status_code,
           "kind": kind, "charged": charged, "ledger": rid, "request_id": meta.get("request_id"),
           "problem": {x: meta[x] for x in ("title", "detail", "errors", "state") if x in meta},
           "result_metadata": meta.get("result_metadata"), "params_echo": meta.get("params")}
    if html:
        clean, _ = sanitize_html(html)
        rec["body_sha256"] = hashlib.sha256(clean.encode()).hexdigest()
        (OUT / f"{at}_{pid}.html.gz").write_bytes(gzip.compress(clean.encode("utf-8"), mtime=0))
        rec["analysis"] = analyse(html)
    else:
        rec["error_body"] = oxylabs.redact(r.text[:2000], k)
    (OUT / f"{at}_{pid}.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False), encoding="utf-8")
    with LOG.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps({x: rec.get(x) for x in ("id", "at", "seconds", "status", "kind", "charged", "request_id", "body_sha256")}) + "\n")
    print(json.dumps({x: v for x, v in rec.items() if x not in ("request", "error_body")}, ensure_ascii=False, indent=0)[:2800])
    if rec.get("error_body"):
        print("ERR", rec["error_body"][:500])


if __name__ == "__main__":
    if sys.argv[1] == "discover":
        discover()
    else:
        send(sys.argv[2], sys.argv[3], json.loads(sys.argv[4]), sys.argv[5] if len(sys.argv) > 5 else "")
