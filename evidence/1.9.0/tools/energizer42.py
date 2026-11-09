"""M4: reconcile the 42 "Coupon: Save $1.00 on Energizer" descriptions of run Q1c (rc3, 01M6E49AHDXSQA04JQZ0HZ40GH)
with the captures of run Q2 (rc4, 01M6E5V6CASQ8F00VC8PE9TFYW), card by card, using the collector's own grid parser.
Read-only; writes a CSV and a JSON summary. Nothing is inferred about why a card changed: each row states what each
saved capture displays.

usage: python -I energizer42.py OUT_DIR
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

from marianos_headless.collection.live import grid_cards

DATA = Path("C:/m6/q180/data")
RUNS = {
    "Q1c": ("01M6E49AHDXSQA04JQZ0HZ40GH", "1.8.0rc3"),
    "Q2": ("01M6E5V6CASQ8F00VC8PE9TFYW", "1.8.0rc4"),
}
TEXT = "Coupon: Save $1.00 on Energizer"


def load(run: str) -> tuple[dict, dict]:
    base = DATA / "runs" / "marianos-53100502-pickup" / run / "exports"
    P = json.loads((base / "products.json").read_text(encoding="utf-8"))
    rows = P if isinstance(P, list) else P.get("records") or P.get("products") or []
    prov = json.loads((base / "provenance.json").read_text(encoding="utf-8")).get("records", {})
    return {r["upc"]: r for r in rows}, prov


_cache: dict[str, tuple[str, dict]] = {}


def cards_of(dom_key: str) -> tuple[str, dict]:
    if dom_key not in _cache:
        raw = (DATA / dom_key).read_bytes()
        html = gzip.decompress(raw).decode("utf-8")
        _, cards, _, _ = grid_cards(html)
        _cache[dom_key] = (hashlib.sha256(raw).hexdigest(), {c.upc: c for c in cards if c.upc})
    return _cache[dom_key]


def card_facts(prov_rec: dict, upc: str) -> dict:
    cap = prov_rec.get("capture") or {}
    key = cap.get("dom_key") or ""
    if not key or not (DATA / key).exists():
        return {"dom_key": key, "found": "capture not available"}
    sha, cards = cards_of(key)
    c = cards.get(upc)
    if c is None:
        return {"dom_key": key, "dom_gz_sha256": sha, "found": "card not on the saved page"}
    z = c.zone
    return {
        "dom_key": key,
        "dom_gz_sha256": sha,
        "dom_sha256_recorded": cap.get("dom_sha256"),
        "url": cap.get("url"),
        "fetched_at": cap.get("fetched_at"),
        "found": "card",
        "zone_label": z.label if z else "",
        "zone_text": z.text if z else "",
        "zone_clip_checkbox": z.requires_clip if z else None,
        "zone_details_button": z.details if z else None,
    }


def main() -> None:
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    q1_rows, q1_prov = load(RUNS["Q1c"][0])
    q2_rows, q2_prov = load(RUNS["Q2"][0])
    upcs = sorted(u for u, r in q1_rows.items() if r.get("digital_deals_description") == TEXT)
    table = []
    for u in upcs:
        a = card_facts(q1_prov.get(u, {}), u)
        r2 = q2_rows.get(u)
        b = card_facts(q2_prov.get(u, {}), u) if r2 is not None else {"found": "not recorded in Q2"}
        if r2 is None:
            verdict = "NOT_IN_Q2"
        elif b.get("found") != "card":
            verdict = "Q2_CARD_NOT_IN_SAVED_PAGE"
        elif not b.get("zone_text"):
            verdict = "Q2_CARD_SHOWS_NO_SAVINGS_ZONE"
        elif "Energizer" in b.get("zone_text", ""):
            verdict = (
                "Q2_CARD_SHOWS_SAME_COUPON_AND_RECORD_HAS_IT"
                if TEXT in (r2.get("digital_deals_description") or "")
                else "Q2_CARD_SHOWS_COUPON_BUT_RECORD_LACKS_IT"
            )
        else:
            verdict = "Q2_CARD_SHOWS_OTHER_OFFER"
        table.append(
            {
                "upc": u,
                "title": q1_rows[u]["product_title"],
                "q1c_url": a.get("url"),
                "q1c_fetched_at": a.get("fetched_at"),
                "q1c_dom_key": a.get("dom_key"),
                "q1c_dom_gz_sha256": a.get("dom_gz_sha256"),
                "q1c_card": a.get("found"),
                "q1c_zone": f"{a.get('zone_label')}: {a.get('zone_text')}" if a.get("zone_text") else "",
                "q2_record": "yes" if r2 is not None else "no",
                "q2_url": b.get("url"),
                "q2_fetched_at": b.get("fetched_at"),
                "q2_dom_key": b.get("dom_key"),
                "q2_dom_gz_sha256": b.get("dom_gz_sha256"),
                "q2_card": b.get("found"),
                "q2_zone": f"{b.get('zone_label')}: {b.get('zone_text')}" if b.get("zone_text") else "",
                "q2_digital_deals_description": (r2 or {}).get("digital_deals_description", ""),
                "verdict": verdict,
            }
        )
    with (out / "ENERGIZER_42_RECONCILIATION.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(table[0].keys()))
        w.writeheader()
        w.writerows(table)
    summary = {
        "q1c_run": RUNS["Q1c"],
        "q2_run": RUNS["Q2"],
        "description": TEXT,
        "q1c_records_with_it": len(upcs),
        "verdicts": Counter(t["verdict"] for t in table),
        "q1c_cards_found": Counter(t["q1c_card"] for t in table),
        "q1c_zone_texts": Counter(t["q1c_zone"] for t in table),
        "q2_zone_texts": Counter(t["q2_zone"] for t in table),
        "q1c_fetch_times": sorted({t["q1c_fetched_at"] or "" for t in table}),
        "q2_fetch_times": sorted({t["q2_fetched_at"] or "" for t in table}),
    }
    (out / "ENERGIZER_42_SUMMARY.json").write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
