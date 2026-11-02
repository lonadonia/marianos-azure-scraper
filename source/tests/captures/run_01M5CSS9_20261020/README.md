# Authentic Mariano's responses, checked offline

Captured from marianos.com through Scrapfly's cloud browser on 2026-10-20 (started 14:00 UTC) by the
scheduled run `01M5CSS9M30WBFTASHHCAWXKPS` of the application this collector derives from (parser 1.0.1),
store 53100503 Marianos Lakeshore East, In Store, listings Produce › Fresh Fruit and Fresh Vegetables:

* `raw/*.products_v2.json.gz`: the site's own product responses (`/atlas/v1/product/v2/products`) its
  verified page steps received, as stored by that run;
* `products.json`: the 166 records that run exported (its own export, unchanged).

`tests/unit/test_captures.py` checks those records against those responses with
`marianos_headless.checks.source_check` and the 22-field contract with `checks.contract`. These are
earlier captures, not new evidence: no test reaches Mariano's or Scrapfly.
