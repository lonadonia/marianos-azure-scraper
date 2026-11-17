# Release 1.10.0rc6 fixtures (OR-19, OR-04): pages the collector stored on 2026-11-16

Store 53100502 (Marianos Vernon Hills), PICKUP, through the Oxylabs Web API. Each file is a byte copy of a page
the collector itself stored (sanitized markup, gzip) during run P2 (1.10.0rc4) or run F2 (1.10.0rc5);
`SOURCES.json` gives each one's stage, collector revision, run, page fetch, request time, provider request ID
(where the answer carried one), the collector's verdict at the time, the storage key it was copied from and its
SHA-256. Built by `make_fixtures_1116.py` (a release tool, published with the delivery's evidence tools).

| File | What it is |
|---|---|
| `f2_espresso_p1.html.gz` | Espresso Coffee (0400300007, Coffee, CSV row 13) page 1, run F2, 18:00:21Z: 28 products of 45, priced for 53100502 Pickup. Completed. |
| `f2_espresso_p2_repeats_p1.html.gz` | The same listing, page 2 asked, 18:00:25Z: the answer lists page 1's products again. Set aside and asked again later (C1). |
| `f2_espresso_p2_reask1_products_not_loaded.html.gz` | Page 2, re-ask 1, 18:55:26Z: its own search was made for 53100502 Pickup (page 2, 45 results, 25 result UPCs listed), but its page state carries no product's data and its grid drew 3 cards. 1.10.0rc5 took it for another store's page (`price_locations` observed nothing) and stopped run F2, not resumable (`STORE_NOT_VERIFIED`, exit 7): defect OR-19. |
| `coupons_loaded_24_cards.html.gz` | The Coupons page (CSV row 0), run P2, 16:03:35Z, rendered with its list loaded: "450 Coupons", 24 coupon cards, no loading indicator. |
| `coupons_not_loaded_spinner.html.gz` | The Coupons page, run F2, 17:09:27Z, rendered before its list loaded: the coupons tab shows the site's loading indicator, no count and no card. 1.10.0rc5 recorded it as read with 0 coupons: defect OR-04 (seven of twelve earlier runs had such a page). |

No page of 2026-11-16 shows the Coupons list loaded and empty (a count of 0 and no card): a test that needs one
derives it from `coupons_loaded_24_cards.html.gz` by removing the cards and setting the count, and says so.

These are fixture data in tests. A test that serves them again is an offline replay: it shows what the collector
does with these answers, never that the site would answer so again.
