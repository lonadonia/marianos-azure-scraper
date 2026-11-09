# Real pages of 2026-11-02 (store 53100502, Marianos Vernon Hills, Pickup)

FIXTURE: pages captured live through the Oxylabs Web API by probes L1, L2, L9, L10, L18 and L20 and by the
qualification runs Q1 and Q1b (their first listing page, as the collector stored it) on 2026-11-02, and
replayed offline, each through the collector's own HTML sanitizer. A test that uses them is a replay, never a
live run.

| File | Probe | What | First 16 hex of the raw page's SHA-256 |
|---|---|---|---|
| search_cereal_p1.html.gz | L1 | the search for cereal, first page | 268a882dbe9adc46 |
| search_cereal_p2.html.gz | L18 | the search for cereal, page=2: the 24 products of page 1 again, ranks 25-48 | dec539d0551d92b7 |
| listing_03001_p1.html.gz | L2 | /pl/cereal-granola/03001, page 1, without rendering | b5f88112e1174f0f |
| listing_03001_p2_no_js.html.gz | L9 | the same listing, page=2, without rendering: page state without cards | 2796d942000b6305 |
| listing_03001_p2.html.gz | L10 | the same listing, page=2, rendered | 2b9de522a7813c60 |
| listing_0300100001_p1.html.gz | L11 | /pl/cold-cereal/0300100001, page 1 (no filter: 277 results, 250 reachable, 67 brands in its brand facet); added in release 1.9.0 for the filter-binding tests (M2) | 7e1cd75335695a14 |
| listing_0300100001_brand.html.gz | L20 | /pl/cold-cereal/0300100001?brandName=General%20Mills | a02839e37129d624 |
| listing_32001_p1.html.gz | Q1 | /pl/candles-home-fragrances/32001, page 1, rendered (qualification run 01M6E2XXQNX1FYXPM37FGTYCKQ of 1.8.0rc1): UPC 0019798100139's price is stated for no store | 808a1c340d72d1c4 (of the copy the collector stored, already sanitized) |
| listing_32001_p1_mini.html.gz | Q1b | the same page 13 minutes later (qualification run 01M6E3RDEBPZ39SVR37JR6PE8F of 1.8.0rc2): the same 24 products as mini-product-card-N cards | cadd60ee3cc6eb2d (of the copy the collector stored, already sanitized) |
