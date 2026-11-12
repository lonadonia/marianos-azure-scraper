# Release 1.10.0 fixtures (C1): pages the collector stored during the live stages of 2026-11-09

Store 53100502 (Marianos Vernon Hills), PICKUP. Each file is a byte copy of a page the collector itself stored
(sanitized markup, gzip) during a live stage of 2026-11-09; `SOURCES.json` gives each one's stage, collector
revision, run, request time, provider request ID and SHA-256, which is the hash the 1.9.0 paging census lists
for it (`evidence/1.9.0/live/PAGING_CENSUS_190.csv` in the delivery). Built by `make_fixtures_1100.py` (a release
tool, published with the delivery's evidence tools).

| File | What it is |
|---|---|
| `s4_batteries_p1.html.gz` | Batteries (26003) page 1, stage S4, 14:36:08Z: 24 products of 96. Its page state names no brand and no child listing. |
| `s4_batteries_p2_repeats_p1.html.gz` | Batteries, page 2 asked, stage S4, 14:36:19Z: the answer states page 2, `loadedPages` [2] and ranks 25 to 48, has a search ID of its own, and lists page 1's 24 products. |
| `s5a_batteries_p2.html.gz`, `s5a_batteries_p3.html.gz`, `s5a_batteries_p4.html.gz` | Batteries pages 2, 3 and 4, stage S5a, 14:42:52Z to 14:43:10Z: 24 other products each (with 4, 3 and 5 sponsored placements). With S4's page 1 they are the listing's 96 products. |
| `s3b_frozen_p1_no_filters.html.gz` | Frozen (18010) page 1, stage S3b, 16:12:16Z: 273 results, 250 reachable; no brand and no child listing in the page state. |
| `s3b_frozen_p2_repeats_p1.html.gz` | Frozen, page 2 asked, stage S3b, 16:13:52Z: the answer lists page 1's 24 products. |

No answer for Frozen with its filters was saved that day, and no later answer for Frozen's page 2: a test that
needs one uses a synthetic page and says so.

These are fixture data in tests. A test that serves them again is an offline replay: it shows what the collector
does with these answers, never that the site would answer so again.
