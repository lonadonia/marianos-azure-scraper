"""K1: a free lead for the Vernon Hills location ID from the Kroger certification host. A lead only: it never proves
what a retailer page serves, and no Kroger data enters a record. Prints no credential."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, r"C:\m5\wt\headless\marianos-azure-headless")
sys.path.insert(0, r"C:\m6\tools")
import budget180  # noqa: E402
from probes.common import read_dotenv  # noqa: E402

ROOT = Path(r"<projects>\marianos-scraper")
BASE = "https://api-ce.kroger.com"
env = read_dotenv(ROOT / "data" / "local" / "krogerapi.env")
rid = budget180.reserve("KR", "K", 0, requests=2, note="K1: token and locations near 60061 (lead only)")
with httpx.Client(base_url=BASE, timeout=40) as c:
    t = c.post("/v1/connect/oauth2/token", data={"grant_type": "client_credentials", "scope": "product.compact"},
               auth=(env["CLIENT_ID"], env["CLIENT_SECRET"]))
    print("token", t.status_code)
    if t.status_code != 200:
        budget180.settle(rid, 0, requests=1, outcome=f"token {t.status_code}")
        raise SystemExit(1)
    tok = t.json()["access_token"]
    r = c.get("/v1/locations", params={"filter.zipCode.near": "60061", "filter.radiusInMiles": "15", "filter.limit": "20"},
              headers={"Authorization": f"Bearer {tok}"})
budget180.settle(rid, 0, requests=2, outcome=f"token 200, locations {r.status_code}")
print("locations", r.status_code, len(r.content))
out = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "host": BASE, "status": r.status_code, "items": []}
for it in (r.json().get("data") or []) if r.status_code == 200 else []:
    a = it.get("address") or {}
    row = {k: it.get(k) for k in ("locationId", "chain", "name", "divisionNumber", "storeNumber")}
    row.update({"addressLine1": a.get("addressLine1"), "city": a.get("city"), "zipCode": a.get("zipCode")})
    out["items"].append(row)
    print(row)
Path(r"C:\m6\ev\probes").mkdir(parents=True, exist_ok=True)
Path(r"C:\m6\ev\probes\K1_locations_lead.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
