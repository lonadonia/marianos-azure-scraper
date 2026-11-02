"""P1: the Kroger Public API alone, for Mariano's Lakeshore East (location 53100503).

The supplied CLIENT_ID/CLIENT_SECRET open only the certification environment (``api-ce.kroger.com``;
production answered 401 "invalid credentials" on 2026-10-28), so that is the base used and named in every
saved answer. Client credentials, scope ``product.compact`` (public product data only); the token is
requested again before it expires and after a 401. A 429 or a 5xx is retried at most twice (the Retry-After
header when given, else 2 s then 8 s). Each call is reserved in the ledger before it is sent.

    python -m probes.kroger_api sample --upcs FILE      # the matched sample: these UPCs, bulk and one by one
    python -m probes.kroger_api terms                   # one search per category, with and without ais
    python -m probes.kroger_api window --term chicken   # paging until the API stops
    python -m probes.kroger_api export                  # the API-only 22-field diagnostic from saved answers
    python -m probes.kroger_api diagnose                # production 401: environment, token endpoint, scope

Only CLIENT_ID and CLIENT_SECRET of ``krogerapi.env`` are read, and only here.
"""

from __future__ import annotations

import argparse
import base64
import csv
import json
import re
import time
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from probes.common import (
    CAPS,
    CapReached,
    Evidence,
    Ledger,
    out_dir,
    read_dotenv,
    revision,
    safe_headers,
    scrub,
    secrets_dir,
    utc_now,
)

BASE = "https://api-ce.kroger.com"
LOCATION = "53100503"
PHASE = "P1"
FIELDS = [
    "zipcode",
    "store_name",
    "store_location",
    "store_logo",
    "store_brand",
    "category",
    "sub_category",
    "product_title",
    "weight",
    "regular_price",
    "sale_price",
    "volume_deals_description",
    "volume_deals_price",
    "digital_deals_description",
    "digital_deals_price",
    "image_url",
    "url",
    "upc",
    "gupc",
    "ppm",
    "unit_price",
    "crawl_date",
]
TERMS = {  # CSV category: one search term for the diagnostic sample
    "Produce": "bananas",
    "Meat": "chicken breast",
    "Seafood": "salmon",
    "Deli": "sliced turkey",
    "Bakery": "bread",
    "Dairy": "milk",
    "Frozen": "frozen pizza",
    "Grocery": "pasta",
    "Beverages": "soda",
    "Breakfast": "cereal",
    "Coffee": "ground coffee",
    "Candy": "chocolate bar",
    "Beer Wine Liquor": "beer",
    "Health": "pain relief",
    "Personal Care": "shampoo",
    "Beauty": "lipstick",
    "Baby": "diapers",
    "Household": "paper towels",
    "Pet Supplies": "dog food",
    "Batteries": "batteries",
}
APPROX = re.compile(r"\b(approx\.?|approximately|avg\.?|average|about|est\.?|estimated)\b", re.I)


class Client:
    def __init__(self) -> None:
        env = read_dotenv(secrets_dir() / "krogerapi.env")
        self._id, self._secret = env["CLIENT_ID"], env["CLIENT_SECRET"]
        self._basic = base64.b64encode(f"{self._id}:{self._secret}".encode()).decode()
        self.rev = revision()
        self.out = out_dir() / "kroger_api"
        self.ev = Evidence(self.out / "evidence", [self._id, self._secret, self._basic])
        self.ledger = Ledger(out_dir() / "ledger.sqlite", CAPS)
        self.http = httpx.Client(timeout=60)
        self._token = ""
        self._token_until = 0.0

    def _reserve(self, purpose: str) -> Any:
        return self.ledger.reserve("kroger", PHASE, 1, purpose, self.rev["commit"])

    def token(self) -> str:
        if self._token and time.monotonic() < self._token_until:
            return self._token
        r_ = self._reserve("token")
        r = self.http.post(
            f"{BASE}/v1/connect/oauth2/token",
            headers={
                "Authorization": f"Basic {self._basic}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={"grant_type": "client_credentials", "scope": "product.compact"},
        )
        self.ledger.settle(r_, 1, str(r.status_code))
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        if r.status_code != 200 or not body.get("access_token"):
            self.ev.save("token_refused", {"at": utc_now(), "status": r.status_code, "body": r.text[:500]})
            raise SystemExit(f"token refused: HTTP {r.status_code}")
        self._token = body["access_token"]
        self.ev.add_secret(self._token)
        self._token_until = time.monotonic() + 0.9 * float(body.get("expires_in") or 1800)
        self.ev.save(
            "token",
            {
                "at": utc_now(),
                "base": BASE,
                "status": r.status_code,
                "expires_in": body.get("expires_in"),
                "token_type": body.get("token_type"),
                "scope_requested": "product.compact",
                "revision": self.rev,
            },
        )
        return self._token

    def get(self, path: str, params: dict[str, str], name: str) -> tuple[int, dict[str, Any]]:
        status, body = 0, {}
        for attempt in range(3):
            tok = self.token()
            r_ = self._reserve(f"GET {path}")
            t = utc_now()
            t0 = time.monotonic()
            try:
                r = self.http.get(
                    f"{BASE}{path}",
                    params=params,
                    headers={"Authorization": f"Bearer {tok}", "Accept": "application/json"},
                )
            except httpx.HTTPError as e:
                self.ledger.settle(r_, 1, f"transport {type(e).__name__}")
                self.ev.save(f"{name}_transport", {"at": t, "path": path, "params": params, "error": repr(e)})
                time.sleep((2, 8, 8)[attempt])
                continue
            ms = round((time.monotonic() - t0) * 1000)
            status = r.status_code
            self.ledger.settle(r_, 1, str(status))
            ct = r.headers.get("content-type", "")
            body = r.json() if ct.startswith("application/json") else {"_text": r.text[:4000]}
            self.ev.save(
                name,
                {
                    "requested_at": t,
                    "base": BASE,
                    "path": path,
                    "params": params,
                    "attempt": attempt + 1,
                    "status": status,
                    "elapsed_ms": ms,
                    "headers": safe_headers(r.headers),
                    "revision": self.rev["commit"],
                    "body": body,
                },
            )
            if status == 401 and attempt < 2:
                self._token = ""
                continue
            if (status == 429 or status >= 500) and attempt < 2:
                ra = r.headers.get("retry-after", "")
                time.sleep(min(float(ra), 60.0) if ra.replace(".", "", 1).isdigit() else (2, 8)[attempt])
                continue
            break
        return status, body


def _money(v: object) -> str:
    if v in (None, "") or Decimal(str(v)) == 0:
        return ""
    return str(Decimal(str(v)).quantize(Decimal("0.01")))


def api_only_row(d: dict[str, Any], category: str, loc: dict[str, Any], crawl_date: str) -> dict[str, str]:
    """The 22 fields from API data alone; a field the API does not carry stays empty, never invented."""
    it = (d.get("items") or [{}])[0]
    price = it.get("price") or {}
    regular, promo = _money(price.get("regular")), _money(price.get("promo"))
    sale = promo if promo and regular and Decimal(promo) < Decimal(regular) else ""
    img = ""
    for im in d.get("images") or []:
        if im.get("featured"):
            sizes = {s.get("size"): s.get("url") for s in im.get("sizes") or []}
            img = sizes.get("xlarge") or sizes.get("large") or next(iter(sizes.values()), "") or ""
    addr = loc.get("address") or {}
    return {
        "zipcode": str(addr.get("zipCode") or ""),
        "store_name": str(loc.get("name") or ""),
        "store_location": ", ".join(
            str(x) for x in (addr.get("addressLine1"), addr.get("city"), addr.get("state")) if x
        ),
        "store_logo": "",
        "store_brand": "",
        "category": category,
        "sub_category": "",
        "product_title": str(d.get("description") or ""),
        "weight": str(it.get("size") or ""),
        "regular_price": regular,
        "sale_price": sale,
        "volume_deals_description": "",
        "volume_deals_price": "",
        "digital_deals_description": "",
        "digital_deals_price": "",
        "image_url": img,
        "url": "",
        "upc": str(d.get("upc") or ""),
        "gupc": "",
        "ppm": "",
        "unit_price": "",
        "crawl_date": crawl_date,
    }


def cmd_location(c: Client) -> dict[str, Any]:
    status, body = c.get(f"/v1/locations/{LOCATION}", {}, "location")
    d = body.get("data") or {}
    print(f"location {LOCATION}: HTTP {status} {d.get('name')} | {json.dumps(d.get('address'))}")
    return d


def cmd_sample(c: Client, upcs: list[str]) -> None:
    loc = cmd_location(c)
    found: dict[str, Any] = {}
    for i in range(0, len(upcs), 50):
        chunk = upcs[i : i + 50]
        st, body = c.get(
            "/v1/products",
            {"filter.productId": ",".join(chunk), "filter.locationId": LOCATION},
            f"bulk_{i // 50}",
        )
        for d in body.get("data") or []:
            found[str(d.get("productId"))] = {"bulk": d}
        print(f"bulk {i // 50}: HTTP {st}, {len(body.get('data') or [])} of {len(chunk)} returned")
    for upc in upcs:
        st, body = c.get(f"/v1/products/{upc}", {"filter.locationId": LOCATION}, f"detail_{upc}")
        found.setdefault(upc, {})["detail"] = body.get("data") if st == 200 else None
        found[upc]["detail_status"] = st
    (c.out / "sample.json").write_bytes(
        json.dumps({"location": loc, "upcs": upcs, "found": found}, indent=1, ensure_ascii=False).encode(
            "utf-8"
        )
    )
    print(f"sample: {sum(1 for u in upcs if found.get(u, {}).get('detail'))} of {len(upcs)} have details")


def cmd_terms(c: Client) -> None:
    stats: dict[str, Any] = {}
    for cat, term in TERMS.items():
        base = {"filter.term": term, "filter.locationId": LOCATION, "filter.limit": "50"}
        sa, a = c.get("/v1/products", base | {"filter.fulfillment": "ais"}, f"terms_{cat}_ais")
        sb, b = c.get("/v1/products", base, f"terms_{cat}_all")
        ais = {d["productId"]: d for d in a.get("data") or []}
        alls = {d["productId"]: d for d in b.get("data") or []}
        not_in_store = [
            pid
            for pid, d in ais.items()
            if not ((d.get("items") or [{}])[0].get("fulfillment") or {}).get("inStore")
        ]
        stats[cat] = {
            "term": term,
            "ais_status": sa,
            "all_status": sb,
            "ais_total": (a.get("meta") or {}).get("pagination", {}).get("total"),
            "all_total": (b.get("meta") or {}).get("pagination", {}).get("total"),
            "ais_returned": len(ais),
            "all_returned": len(alls),
            "ais_items_without_inStore_flag": not_in_store,
            "returned_without_ais_only": sorted(set(alls) - set(ais)),
        }
        print(
            f"  {cat:17} {term:15} ais {sa} {len(ais):3}/{stats[cat]['ais_total']} | all {sb} "
            f"{len(alls):3}/{stats[cat]['all_total']} | ais but inStore false: {len(not_in_store)}"
        )
    (c.out / "terms.json").write_bytes(json.dumps(stats, indent=1).encode("utf-8"))


def cmd_window(c: Client, term: str) -> None:
    pages = []
    for start in range(1, 1000, 50):
        st, p = c.get(
            "/v1/products",
            {
                "filter.term": term,
                "filter.locationId": LOCATION,
                "filter.limit": "50",
                "filter.start": str(start),
            },
            f"window_{term}_{start}",
        )
        pages.append(
            {
                "start": start,
                "status": st,
                "returned": len(p.get("data") or []),
                "meta": p.get("meta"),
                "error": p.get("errors") or p.get("_text"),
            }
        )
        print(
            f"  start {start}: HTTP {st} returned {pages[-1]['returned']} "
            f"meta {json.dumps(p.get('meta'))[:120]}"
        )
        if st != 200 or not p.get("data"):
            break
    (c.out / f"window_{term}.json").write_bytes(json.dumps(pages, indent=1).encode("utf-8"))


def cmd_export(c: Client) -> None:
    """The API-only diagnostic export, from the saved sample and term answers (no new call)."""
    crawl_date = datetime.now(ZoneInfo("America/Chicago")).date().isoformat()
    sample = json.loads((c.out / "sample.json").read_text(encoding="utf-8"))
    loc = sample["location"]
    rows, excluded = [], []
    for upc in sample["upcs"]:
        d = (sample["found"].get(upc) or {}).get("detail")
        if not d:
            continue
        row = api_only_row(d, str((d.get("categories") or [""])[0]), loc, crawl_date)  # the API's own label
        if APPROX.search(row["weight"]):
            excluded.append({"upc": upc, "weight": row["weight"], "reason": "approximate weight wording"})
            continue
        rows.append(row)
    (c.out / "products_api_only.json").write_bytes(
        json.dumps(rows, indent=1, ensure_ascii=False).encode("utf-8")
    )
    with (c.out / "products_api_only.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    (c.out / "excluded.json").write_bytes(json.dumps(excluded, indent=1).encode("utf-8"))
    print(f"API-only export: {len(rows)} rows, {len(excluded)} excluded")


PRODUCTION = "https://api.kroger.com"
DIAGNOSE_PHASE = "Q0"


def cmd_diagnose(c: Client) -> None:
    """Why production refuses the credentials: the same client against both environments' token endpoints,
    with and without the scope and with the credentials in the form body, and each environment's token
    against the other environment's API. One call each (phase Q0); no credential or token is saved."""
    out = c.out / "diagnose"
    ev = Evidence(out, c.ev.secrets)
    rows: list[dict[str, Any]] = []
    tokens: dict[str, str] = {}

    def call(name: str, method: str, url: str, **kw: Any) -> httpx.Response | None:
        res = c.ledger.reserve("kroger", DIAGNOSE_PHASE, 1, f"diagnose {name}", c.rev["commit"])
        t = utc_now()
        try:
            r = c.http.request(method, url, **kw)
        except httpx.HTTPError as e:
            c.ledger.settle(res, 1, f"transport {type(e).__name__}")
            rows.append({"check": name, "at": t, "url": url, "status": f"transport {type(e).__name__}"})
            return None
        c.ledger.settle(res, 1, str(r.status_code))
        ct = r.headers.get("content-type", "")
        body: Any = r.json() if ct.startswith("application/json") else r.text[:1000]
        if isinstance(body, dict) and "access_token" in body:
            ev.add_secret(str(body["access_token"]))
            body = {k: v for k, v in body.items() if k != "access_token"} | {"access_token": "(received)"}
        record = {
            "check": name,
            "at": t,
            "method": method,
            "url": url,
            "form_fields": sorted((kw.get("data") or {}).keys()),
            "scope_requested": (kw.get("data") or {}).get("scope", ""),
            "auth": "basic"
            if "Authorization" in (kw.get("headers") or {}) and "Basic" in kw["headers"]["Authorization"]
            else (
                "bearer" if "Authorization" in (kw.get("headers") or {}) else "credentials in the form body"
            ),
            "status": r.status_code,
            "headers": safe_headers(r.headers),
            "body": body,
            "revision": c.rev["commit"],
        }
        ev.save(name, record)
        rows.append(
            {k: record[k] for k in ("check", "at", "url", "auth", "scope_requested", "status")}
            | {"answer": scrub(json.dumps(body), ev.secrets)[:300]}
        )
        return r

    basic = {"Authorization": f"Basic {c._basic}", "Content-Type": "application/x-www-form-urlencoded"}
    form = {"Content-Type": "application/x-www-form-urlencoded"}
    grant = {"grant_type": "client_credentials", "scope": "product.compact"}
    for env_name, base in (("production", PRODUCTION), ("certification", BASE)):
        r = call(
            f"{env_name}_token_basic_scope",
            "POST",
            f"{base}/v1/connect/oauth2/token",
            headers=basic,
            data=grant,
        )
        if r is not None and r.status_code == 200:
            tokens[env_name] = str(r.json().get("access_token") or "")
    call(
        "production_token_basic_no_scope",
        "POST",
        f"{PRODUCTION}/v1/connect/oauth2/token",
        headers=basic,
        data={"grant_type": "client_credentials"},
    )
    call(
        "production_token_form_credentials",
        "POST",
        f"{PRODUCTION}/v1/connect/oauth2/token",
        headers=form,
        data=grant | {"client_id": c._id, "client_secret": c._secret},
    )
    for env_name, tok in tokens.items():
        for api_name, base in (("production", PRODUCTION), ("certification", BASE)):
            call(
                f"{env_name}_token_on_{api_name}_api",
                "GET",
                f"{base}/v1/locations/{LOCATION}",
                headers={"Authorization": f"Bearer {tok}", "Accept": "application/json"},
            )
    with (out / "diagnose.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    for row in rows:
        print(row["check"], row["status"], row["answer"][:160])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="probes.kroger_api")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sample")
    s.add_argument("--upcs", type=Path, required=True)
    sub.add_parser("terms")
    w = sub.add_parser("window")
    w.add_argument("--term", default="chicken")
    sub.add_parser("export")
    sub.add_parser("location")
    sub.add_parser("diagnose")
    a = ap.parse_args(argv)
    c = Client()
    try:
        if a.cmd == "sample":
            upcs = [u.strip() for u in a.upcs.read_text(encoding="utf-8").split() if u.strip()]
            cmd_sample(c, upcs)
        elif a.cmd == "terms":
            cmd_terms(c)
        elif a.cmd == "window":
            cmd_window(c, a.term)
        elif a.cmd == "export":
            cmd_export(c)
        elif a.cmd == "diagnose":
            cmd_diagnose(c)
        else:
            cmd_location(c)
    except CapReached as e:
        print(f"stopped: {e}")
        return 4
    finally:
        phase = DIAGNOSE_PHASE if a.cmd == "diagnose" else PHASE
        print(
            f"kroger calls recorded in phase {phase}: {c.ledger.used('kroger', phase):g} "
            f"of {CAPS[('kroger', phase)]:g}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
