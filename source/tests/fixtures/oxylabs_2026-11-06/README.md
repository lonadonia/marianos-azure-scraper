# Release 1.9.0 fixtures (M4 coupon terms, M6 offers): real saved pages, trimmed only

Store 53100502 (Marianos Vernon Hills), PICKUP. Built by `make_fixtures_190.py` (a release tool, published with the delivery's evidence tools); `SOURCES.json`
names each source file with its hash.

| File | What it is |
|---|---|
| `q2_cards_m4.html` | The grid cards of UPCs 0001780014939, 0001780014941, 0002310014848 and 0003980014995, as run Q2 (`01M6E5V6CASQ8F00VC8PE9TFYW`, 1.8.0rc4, 2026-11-02) saved them. Each card's outer HTML is unchanged; the rest of each page is left out. |
| `q2_state_products_m4.json` | The same four products' page-state data, from Q2's saved `products_v2` artifacts. |
| `pdp_0001780014939_rendered.html.gz` | The product page saved by gated stage O1 (2026-11-06, request 7524540530412231682). The provider's answer states `run_js: true`. Its Savings section shows coupons 4257015 ("Save $10.00 on 2 Purina ONE") and 4257014 ("$10.00 Cash Back on 2 Purina ONE"), with their complete terms, "Exp. Nov. 10", "4 days left!", the clipping action and the qualifying product. |
| `pdp_0001780014941_unrendered.html.gz` | Stage O1, request 7524541391263784961. The answer states `run_js: false`: the page has no Savings section, which says nothing about the product's coupons. |
| `pdp_0001820020352_unrendered_sale.html.gz` | Stage O1, request 7524541623041038337 (`run_js: false`). The page still shows its server-rendered "Sale: Buy 1 Save $2, Exp. Jan. 05" row (a promotion, not a coupon). |

M6 (built by `make_fixtures_190_m6.py` (a release tool, published with the delivery's evidence tools); sources and hashes in `SOURCES_M6.json`):

| File | What it is |
|---|---|
| `q2_cards_m6_sizes.html`, `q2_state_products_m6_sizes.json` | The grid cards and page-state data of the three sizes Q2 left unresolved (0001780010048 "4 lb." against 4.4 POUNDS, 0065922318120 "16.2 oz" against 18 OUNCES, 0087786900820 "1.3 oz" against 1.2 OUNCES), as Q2 saved them. |
| `o1_state_products_m6.json` | The product data in the page state of the seven M6 product pages saved by stage O1 on 2026-11-06: 0081675102373, 0086001079386 and 0001820020352 (the "Buy 1 Save" examples), 0073679800140 (the dip) and the three sizes above. All seven answers state `run_js: false`; the product data is part of the server-rendered page. |

Release 1.9.0rc2, the tile served since 2026-11-06 (built by `make_fixtures_190rc2.py` (a release tool, published with the delivery's evidence tools); origins, request
IDs, the provider's `run_js` statement and hashes in `SOURCES_TILES.json`). Whole pages, not trimmed: the S1 files
are the collector's own stored copies; the O2 answers went through the collector's sanitizer, as the collector
stores pages.

| File | What it is |
|---|---|
| `s1_catfood_p1_rendered_nogrid.html.gz` | Cat Food (27021) page 1 as the provider rendered it (`run_js: true`, asked for): the page state lists 24 products; no product tile and no grid. Source: stage S1, run `01M6S5MYBC05W3S308EC7XWTGV`, fetch `01M6S5N6KJTSK5GDR5W1TXMSTQ` (byte copy). |
| `s1_catfood_p1_tiles.html.gz` | Cat Food page 1, asked for rendered like the first, answered without rendering (the answer states `run_js: false`): 24 `horizontal-product-card-N` tiles (regular prices, "Everyday Low Price", one "Prices May Vary" without a price). Source: stage S1, run `01M6S5MYBC05W3S308EC7XWTGV`, fetch `01M6S5RDC5TP4XK2CV3TGTMG52` (byte copy). |
| `o2_cattreats_p1_tiles.html.gz` | Cat Treats (27022) page 1: sale tiles ("Sale: $2.99 discounted from $3.29", "Price Cut"); 0002310032784 whose product data states the size "N/A". Source: stage O2, request 7524557652697865217. |
| `o2_cattreats_p2_rendered_nogrid.html.gz` | Cat Treats page 2: the provider rendered it although `run_js` was not asked for: no tile, 24 products in the state. Source: stage O2, request 7524557833694627841. |
| `o2_search_bananas_tiles.html.gz` | Search "bananas": 23 `default-product-card-N` tiles; "about $1.45 each" (an estimated item price); two "Sponsored" tiles. Source: stage O2, request 7524558144228338689. |
| `o2_dogfood_p1_tiles.html.gz` | Dog Food (27017) page 1: a multi-unit regular price ("4 For $9.00" in the product data) shown as $2.25. Source: stage O2, request 7524558209143579649. |
| `o2_search_nutrl_tiles.html.gz` | Search "nutrl vodka seltzer": a savings zone ("Buy 1 Save $2", "View 1 Offer"); 0001820020352 shows $18.98 as its regular price while its product data states 18.99. Source: stage O2, request 7524558564300469249. |
| `o2_search_purina_one_tiles.html.gz` | Search "purina one dry dog food": the two products with digital coupons on their own pages (stage O1) show no coupon on their tiles. Source: stage O2, request 7524558596630121473. |

Release 1.9.0rc2 sizes (built by `make_fixtures_190rc2_sizes.py` (a release tool, published with the delivery's evidence tools); sources in `SOURCES_RC2_SIZES.json`):

| File | What it is |
|---|---|
| `q2_cards_rc2_no_quantity.html`, `q2_state_products_rc2_no_quantity.json` | The grid cards and page-state data of 0002310032784 (size "N/A") and 0019283330664 (size "Count"), whose weight run Q2 exported as those texts, as Q2 saved them (each card's outer HTML unchanged). |

The product pages went through the collector's own sanitizer (scripts removed except the page state), as the
collector stores pages. These are fixture data in tests. They are never a run's observation.
