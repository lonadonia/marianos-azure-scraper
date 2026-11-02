# Oxylabs Web API pages, 2026-10-28 (FIXTURE: captured live, replayed offline)

Captured by the P3 probes (`probes/oxylabs_web.py`, revision 056c41d) through the Oxylabs Web API with
`store_id=53100503` and `fulfillment_type=in_store` (Marianos Lakeshore East, In Store):

| File | Request | Captured (UTC) | Raw page sha256 |
|---|---|---|---|
| `search_cereal.html.gz` | `/v1/scrape/marianos/search`, query `cereal` | 2026-10-28T18:56:09Z | 8018d52ded34bc4f... |
| `coupons_run_js.html.gz` | `/v1/scrape/marianos`, `/savings/cl/coupons/`, `run_js` | 2026-10-28T19:00:11Z | d0b66dee60be2536... |
| `robots.txt` | `/v1/scrape/marianos`, `/robots.txt` | 2026-10-28T19:12:45Z | ede5900550221646... |

The two pages are stored after the collector's own sanitizer (`sanitize_html`), gzip-compressed; robots.txt is
unchanged. `tests/integration/test_oxylabs_replay.py` serves them to the collector through a mock transport:
these are replays of earlier live answers, never a live run.
