"""PRIVATE OPS (owner VM, as the collector's user, with the release's own Python): how 1.10.0rc5 read stored pages
when judging their store, for the stop of the full run F2 (STORE_NOT_VERIFIED, 2026-11-16 18:56:02Z). No network.

    /opt/marianos-collector/current/venv/bin/python -I store_stop_check.py LABEL=DOM_FILE [LABEL=DOM_FILE ...]

For each stored page (live/dom/<fetch id>.html.gz): its SHA-256 as stored, the page's own search as the collector
reads it (search.searchAll.requestVars and productsInfo: page, store, fulfillment, results, loaded), the products its
page state holds, and the product cards drawn in its grid, read with the installed collector's own functions. Then
the two inputs of the price check of 1.10.0rc5 (collection/oxylabs_live.py, StoreVerifier.verify):

    shows = purpose != "coupons" and bool(products or grid cards)
    price_locations = (stated == {store}) if stated else (False if shows and not products else None)

False is a failed required check: the run stops with STORE_NOT_VERIFIED, not resumable. None: the check does not
apply, and the listing step judges the page (not counted, asked again within the limits). Nothing is inferred.
"""

from __future__ import annotations

import gzip
import hashlib
import sys
from collections import Counter
from pathlib import Path

from marianos_headless.collection.live import grid_cards
from marianos_headless.sites.marianos.initial_state import InitialStateNotFound, parse_initial_state
from marianos_headless.sites.marianos.search_state import price_location, search_summary, state_products

STORE = "53100502"


def main() -> int:
    for arg in sys.argv[1:]:
        label, _, path = arg.partition("=")
        raw = Path(path).read_bytes()
        html = (gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw).decode("utf-8", "replace")
        try:
            state = parse_initial_state(html)
        except (InitialStateNotFound, ValueError):
            state = {}
        s = search_summary(state)
        products = state_products(state)
        present, cards, _sponsored, displayed = grid_cards(html)
        shows = bool(products or cards)
        stated = {x for x in Counter(price_location(p) for p in products) if x}
        verdict = (stated == {STORE}) if stated else (False if shows and not products else None)
        print(f"=== {label}")
        print(f"stored page: {Path(path).name}  sha256 {hashlib.sha256(raw).hexdigest()}  ({len(raw)} bytes)")
        if s is None:
            print("its search: none in the page state")
        else:
            print(f"its search: page {s.page}, store {s.location_id}, fulfillment {s.modality}, results {s.total} "
                  f"(reachable {s.available}), result UPCs {len(s.upcs)}, loaded {s.loaded}, loading {s.loading}, "
                  f"request variables {'present' if s.filters is not None else 'none'}")
        print(f"products in the page state: {len(products)}; their stated price stores: {sorted(stated) or 'none'}")
        print(f"product grid: {'present' if present else 'absent'}; cards drawn: {len(cards)}; displayed results: "
              f"{displayed}")
        for c in cards[:4]:
            print(f"  card {c.card_testid}: {c.upc} {c.title!r}")
        print(f"price check of 1.10.0rc5: shows={shows}, products={len(products)} -> "
              + {True: "PASS", False: "FAIL (required): the run stops, STORE_NOT_VERIFIED, not resumable",
                 None: "not applicable: the listing step judges the page (not counted, asked again)"}[verdict])
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
