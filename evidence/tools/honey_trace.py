"""The Honey Smacks one-cent case, stage by stage, from its saved capture through the current code. Offline.

usage: honey_trace.py OUT_JSON"""
import json
import re
import sys
from pathlib import Path

WT = Path(r"C:\m5\wt\headless\marianos-azure-headless")
sys.path.insert(0, str(WT / "src"))
from marianos_headless.collection.live import grid_cards  # noqa: E402
from marianos_headless.core.text import normalize_amount_str  # noqa: E402
from marianos_headless.sites.marianos.source_json import PRODUCTS, ResponseRef, SourceIndex  # noqa: E402

FIX = WT / "tests" / "fixtures" / "live_2026-10-23_honey_smacks"
UPC = "0004119211060"
html = (FIX / "grid_card.html").read_text("utf-8")
body = (FIX / "products_v2.json").read_text("utf-8")
_, cards, _, _ = grid_cards(html)
card = next(c for c in cards if c.upc == UPC)
visible = re.sub(r"<[^>]+>", " ", html)
visible = re.sub(r"\s+", " ", visible)
m = re.search(r"Sale:[^<]{0,80}", html)
data = json.loads(body)
prod = data if "item" in data else (data.get("data") or {}).get("products", [data])[0]
prices = (prod.get("price") or {}).get("storePrices") or {}
trace = {
    "capture": {
        "product": (prod.get("item") or {}).get("description") or card.title,
        "upc": UPC,
        "run": "01M5NAQKQ0H28DCGK5BE8XCP2N (release 1.2.0, live)",
        "page_fetch": "01M5NC5JY5YSX2A07DEW223TYJ",
        "page": "/pl/cereal-granola/03001, page step 9",
        "timestamp_card": "2026-10-23T21:55:13Z",
        "timestamp_structured": "2026-10-23T21:55:20Z",
        "store": "53100503 Marianos Lakeshore East",
        "fulfillment": "IN_STORE",
        "evidence": "tests/fixtures/live_2026-10-23_honey_smacks (the card and the product object, unchanged)",
    },
    "stage_1_displayed_text_in_the_page": {
        "screen_reader_or_label": m.group(0).strip() if m else "",
        "parser_original_text": card.price.original_text,
        "parser_current_text": card.price.current_text,
    },
    "stage_2_parser_number": {
        "regular_price": card.price.regular_price,
        "sale_price": card.price.sale_price,
        "normalized_from_text": normalize_amount_str(card.price.original_text.lstrip("$")),
    },
    "stage_3_structured_value_in_the_same_response": {
        "path": "price.storePrices.regular.price",
        "value": (prices.get("regular") or {}).get("price"),
        "promo_path": "price.storePrices.promo.price",
        "promo": (prices.get("promo") or {}).get("price"),
        "sourceLocationId": prices.get("sourceLocationId"),
    },
    "stage_4_arithmetic_pattern": {
        "formula": "floor(8.79 * 100) / 100 in binary floating point",
        "8.79*100": 8.79 * 100,
        "floor/100": int(8.79 * 100) / 100,
        "equals_displayed": int(8.79 * 100) / 100 == float(card.price.regular_price),
    },
    "collector_transformation": (
        "the collector reads the text the card shows and normalizes it to two decimals; no float arithmetic touches "
        "a displayed price, so '$8.78' becomes '8.78' and the export stays equal to the page text"
    ),
    "collector_caused": False,
    "attribution": (
        "Not established. The page reached the collector with the card text and the structured value already "
        "different. A page returned through a provider does not show whether the retailer, the provider or another "
        "upstream component produced the difference. The arithmetic pattern is a description, not a cause."
    ),
}
Path(sys.argv[1]).write_text(json.dumps(trace, indent=2, ensure_ascii=False), encoding="utf-8")
print(json.dumps(trace, indent=1, ensure_ascii=False)[:2600])
