"""The four coupon examples of the client's review (M4), checked again in the saved source evidence only (no
request is made): what each saved source shows for UPCs 0001780014939, 0001780014941, 0002310014848 and
0003980014995, and whether any saved Coupons-page read names a coupon for their brands.

    python -I coupon_check_1100.py <published repository> <output json> [<private O1 captures folder>]

With the third argument, each saved answer's own statement of rendering (``results[0].metadata.run_js``) is
read from the privately kept raw answer, which the published answer record identifies by its SHA-256.

Sources read (all published with the 1.9.0 evidence; the raw answers are kept privately and identified by
their SHA-256 there): stage O1's product-page summary and answer records (2026-11-06), the fixture notes of
the Q2 cards (2026-11-02), and the Coupons-page read recorded by each run of 2026-11-09."""

from __future__ import annotations

import gzip
import hashlib
import json
import re
import sys
from pathlib import Path

UPCS = {
    "0001780014939": ("Purina ONE", "Coupon: Save $10.00 on 2 Purina ONE"),
    "0001780014941": ("Purina ONE", "Coupon: Save $10.00 on 2 Purina ONE"),
    "0002310014848": ("Temptations", "Coupon: $6.99 Temptations Cat Treats"),
    "0003980014995": ("Energizer", "Coupon: Save $1.00 on Energizer"),
}
# What a complete, product-bound coupon needs before its terms are exported as complete.
REQUIRED = (
    "coupon_id",
    "headline",
    "complete terms (quantity, eligibility, redemption limits)",
    "displayed expiry (validity)",
    "clipping instruction",
    "qualifying products naming this UPC's product (product-bound)",
)


def stated_run_js(private: Path | None, name: str, published_sha: str | None) -> object:
    """``results[0].metadata.run_js`` of a privately kept raw answer, checked against its published hash."""
    if private is None or not (private / name).is_file():
        return "unavailable: the raw answer is kept privately and was not given to this check"
    raw = gzip.decompress((private / name).read_bytes())
    if published_sha and hashlib.sha256(raw).hexdigest() != published_sha:
        return "unavailable: the private file does not match the published hash"
    env = json.loads(raw)
    first = (env.get("results") or [{}])[0]
    value = (first.get("metadata") or {}).get("run_js")
    return value if isinstance(value, bool) else "unavailable: the answer does not say"


def main() -> int:
    repo, out = Path(sys.argv[1]), Path(sys.argv[2])
    private = Path(sys.argv[3]) if len(sys.argv) > 3 else None
    live = repo / "evidence" / "1.9.0" / "live"
    summary = json.loads((live / "O1" / "PDP_SUMMARY_01-13.json").read_text("utf-8"))
    answers = {p.name: json.loads(p.read_text("utf-8")) for p in sorted((live / "O1" / "answers").glob("*.json"))}
    products: dict[str, dict[str, object]] = {}
    for upc, (brand, headline) in UPCS.items():
        pages = [(name, v) for name, v in summary.items() if isinstance(v, dict) and v.get("upc") == upc]
        entry: dict[str, object] = {"brand": brand, "q2_card_headline_2026-11-02": headline, "product_pages": []}
        for name, v in pages:
            answer = next((a for n, a in answers.items() if n.split(".")[0] == name.split(".")[0]), {})
            meta = (answer.get("result_metadata") or {}) if isinstance(answer, dict) else {}
            savings = v.get("savings") or []
            entry["product_pages"].append(  # type: ignore[union-attr]
                {
                    "stage": "O1 (2026-11-06)",
                    "capture": name,
                    "provider_request_id": answer.get("request_id"),
                    "requested_run_js": (answer.get("body_sent") or {}).get("run_js"),
                    "raw_answer_sha256": answer.get("raw_sha256"),
                    "seconds": answer.get("seconds"),
                    "provider_states_run_js": stated_run_js(private, name, answer.get("raw_sha256")),
                    "savings_rows": len(savings),
                    "coupons_on_page": [
                        {k: s.get(k) for k in ("coupon_id", "headline", "expiry_text", "clip_text") if k in s}
                        for s in savings
                    ],
                    "customer_facing_size": (v.get("facts") or {}).get("customerFacingSize"),
                }
            )
        saved = entry["product_pages"]
        assert isinstance(saved, list)
        if any(p["savings_rows"] for p in saved):
            entry["state"] = "COMPLETE in the saved source: a rendered product page shows the coupon with its terms"
        elif any(p["provider_states_run_js"] is True for p in saved):
            entry["state"] = (
                "UNREAD, AND NOT SHOWN ON ITS RENDERED PAGE: a saved product page whose answer states run_js "
                "true shows no Savings section, so the coupon the card showed on 2026-11-02 is not confirmed by "
                "the product's own page of 2026-11-06 (expired, withdrawn or not loaded: not established); no "
                "terms were read; the headline is kept as a headline and flagged, its price is not exported"
            )
        else:
            entry["state"] = (
                "UNREAD: no saved product page of this product was rendered (each answer states run_js false), "
                "which says nothing about its coupons; the card headline of 2026-11-02 is kept as a headline "
                "and flagged, its price is not exported"
            )
        products[upc] = entry
    # every product-page answer stage O1 saved, with its own statement of rendering
    all_pages = []
    for name, answer in answers.items():
        m = re.search(r"/p/[^?#]*/(\d{13})$", str(answer.get("target") or ""))
        if m is None:
            continue
        raw_name = str(answer.get("raw_file") or name.replace(".json", ".raw.gz"))
        row = summary.get(raw_name)
        all_pages.append(
            {
                "capture": raw_name,
                "upc": m.group(1),
                "asked_utc": answer.get("utc_start"),
                "provider_request_id": answer.get("request_id"),
                "raw_answer_sha256": answer.get("raw_sha256"),
                "seconds": answer.get("seconds"),
                "provider_states_run_js": stated_run_js(private, raw_name, answer.get("raw_sha256")),
                "savings_rows": len(row.get("savings") or [])
                if isinstance(row, dict)
                else "unavailable: not in the published page summary (a second sample)",
            }
        )
    reads = []
    for report in sorted(live.glob("*/run_*/exports/validation_report.json")):
        cr = (json.loads(report.read_text("utf-8")).get("counts") or {}).get("coupons_route") or {}
        named = [
            c
            for c in cr.get("coupons") or []
            if re.search(r"purina|temptations|energizer", json.dumps(c), re.I)
        ]
        reads.append(
            {
                "stage": report.parts[-4],
                "run": report.parts[-3].removeprefix("run_"),
                "status": cr.get("status"),
                "coupon_cards": cr.get("coupon_cards"),
                "store_check": cr.get("store_check"),
                "cards_naming_one_of_the_three_brands": named,
                "products_listed_by_the_page": cr.get("products_listed"),
            }
        )
    rendered = [p for p in all_pages if p["provider_states_run_js"] is True]
    body = {
        "what": "saved source evidence only; no request was made for this check",
        "stage_o1_product_pages": {
            "saved": len(all_pages),
            "answers_stating_run_js_true": len(rendered),
            "of_those_showing_savings_rows": sum(1 for p in rendered if p["savings_rows"] not in (0, None)),
            "rendered": rendered,
            "correction": "the 1.9.0 documents say the provider rendered 1 of 14 product pages on 2026-11-06; "
            "the saved answers state run_js true for the number given here",
            "pages": all_pages,
        },
        "required_for_a_complete_product_bound_coupon": list(REQUIRED),
        "products": products,
        "coupons_page_reads_2026-11-09": reads,
        "coupons_page_note": "the Coupons page lists offers, not the products each applies to: a card there "
        "is never attached to a product",
        "conclusion": {
            "complete": [u for u, p in products.items() if str(p["state"]).startswith("COMPLETE")],
            "unread": [u for u, p in products.items() if str(p["state"]).startswith("UNREAD")],
            "unread_and_not_shown_on_a_rendered_page": [
                u for u, p in products.items() if str(p["state"]).startswith("UNREAD, AND NOT SHOWN")
            ],
            "next_evidence": "a rendered product page of each unread UPC (the provider's answer stating run_js "
            "true) at store 53100502, Pickup, saved with its request ID and hash: a live request, not made here",
        },
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes((json.dumps(body, indent=1, ensure_ascii=False) + "\n").encode("utf-8"))
    for upc, p in products.items():
        print(upc, "|", str(p["state"])[:60], "| pages", len(p["product_pages"]))  # type: ignore[arg-type]
    print("O1 product pages:", len(all_pages), "| answers stating run_js true:", len(rendered))
    print("coupons-page reads:", [(r["stage"], r["coupon_cards"], len(r["cards_naming_one_of_the_three_brands"])) for r in reads])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
