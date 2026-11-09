"""Reproduction of finding N09 (release 1.9.0rc3): what a record says about the digital coupon of a tile that shows
none, built by a given collector revision from the same real captures.

Usage: python tile_coupon_before_after.py COLLECTOR_ROOT FIXTURE_DIR OUT_JSONL

COLLECTOR_ROOT holds that revision's ``src`` and ``config``; FIXTURE_DIR is tests/fixtures/oxylabs_2026-11-06 (the
same bytes in 1.9.0rc2 and rc3). Three cases on the Purina ONE tiles of stage O2's search page (no savings zone):
the product page not read; 0001780014939's page as stage O1 saved it rendered (coupon 4257015 shown); 0001780014941's
page as O1 saved it unrendered. Only APIs present in both revisions are used."""

from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

ROOT, FIX, OUT = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve(), Path(sys.argv[3])
sys.path.insert(0, str(ROOT / "src"))

import marianos_headless  # noqa: E402

assert Path(marianos_headless.__file__).resolve().is_relative_to(ROOT), marianos_headless.__file__

from marianos_headless.assembly.private_label import PrivateLabelDetector  # noqa: E402
from marianos_headless.assembly.record_builder import CategoryAssignment, StoreFields  # noqa: E402
from marianos_headless.collection.live import build_card, grid_cards  # noqa: E402
from marianos_headless.core.settings import (  # noqa: E402
    BrowserProvider,
    load_private_label,
    load_settings,
    load_stores,
)
from marianos_headless.sites.marianos.initial_state import parse_initial_state  # noqa: E402
from marianos_headless.sites.marianos.pdp_savings import savings_document  # noqa: E402
from marianos_headless.sites.marianos.search_state import state_products  # noqa: E402
from marianos_headless.sites.marianos.source_json import (  # noqa: E402
    PDP_SAVINGS,
    PRODUCTS,
    ResponseRef,
    SourceIndex,
)

SEARCH = "o2_search_purina_one_tiles.html.gz"
PAGES = {"0001780014939": ("pdp_0001780014939_rendered.html.gz", True),
         "0001780014941": ("pdp_0001780014941_unrendered.html.gz", False)}
VH = StoreFields("60061", "Marianos Vernon Hills", "1720 N Milwaukee Ave, Vernon Hills, IL 60061",
                 "https://www.marianos.com/cdn/images/multiColor-4Jf6i6B.svg")


def page(name: str) -> str:
    return gzip.decompress((FIX / name).read_bytes()).decode("utf-8")


def index(pdp: dict[str, tuple[str, bool]]) -> SourceIndex:
    idx = SourceIndex()
    doc = {"data": {"products": state_products(parse_initial_state(page(SEARCH)))}}
    idx.add(PRODUCTS, json.dumps(doc), ResponseRef(PRODUCTS, "O2-search", "0" * 64, "2026-11-06T19:48:00Z"))
    for upc, (name, rendered) in pdp.items():
        sd = savings_document(page(name), upc=upc, rendered=rendered, requested_run_js=True)
        idx.add(PDP_SAVINGS, json.dumps(sd), ResponseRef(PDP_SAVINGS, "O1-" + upc, "d" * 64, "2026-11-06T18:40:00Z"))
    return idx


s = load_settings(ROOT / "config" / "settings.yaml")
settings = s.model_copy(update={"acquisition": s.acquisition.model_copy(
    update={"browser_provider": BrowserProvider.SCRAPFLY})})
store = next(x for x in load_stores(ROOT / "config" / "stores.yaml").stores if x.key == "marianos-53100502-pickup")
detector = PrivateLabelDetector(load_private_label(ROOT / "config" / "private_label_brands.yaml"),
                                settings.records.store_brand_positive_value)
_, cards, _, _ = grid_cards(page(SEARCH))
tiles = {c.upc: c for c in cards}
cases = [("page not read", "0001780014939", {}),
         ("page read rendered (O1)", "0001780014939", {"0001780014939": PAGES["0001780014939"]}),
         ("page brought unrendered (O1)", "0001780014941", {"0001780014941": PAGES["0001780014941"]})]
with OUT.open("a", encoding="utf-8") as f:
    for label, upc, pdp in cases:
        card = tiles[upc]
        b = build_card(card, fetch_id="F-search", observed_at="2026-11-06T19:48:00+00:00", store=store,
                       store_values=VH, store_provenance={}, category=CategoryAssignment("Pet Supplies", "Dog Food"),
                       crawl_date="2026-11-06", settings=settings, detector=detector, sources=index(pdp)).built
        row = {
            "collector_version": marianos_headless.__version__,
            "case": label,
            "upc": upc,
            "tile_layout": card.layout,
            "tile_savings_zone": None if card.zone is None else card.zone.text,
            "digital_deals_description": b.record["digital_deals_description"],
            "digital_deals_price": b.record["digital_deals_price"],
            "reason_description": b.missing.get("digital_deals_description", ""),
            "missing_kind_description": b.missing_kind.get("digital_deals_description", ""),
            "flags": sorted(str(x) for x in b.flags),
            "status": str(b.status),
        }
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(json.dumps(row, ensure_ascii=False)[:400])
