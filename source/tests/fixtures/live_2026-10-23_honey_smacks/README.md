# Honey Smacks, 2026-10-23 (FIXTURE: captured live, replayed offline)

From release 1.2.0's live run `01M5NAQKQ0H28DCGK5BE8XCP2N` (Marianos Lakeshore East, store 53100503, In Store),
page step `01M5NC5JY5YSX2A07DEW223TYJ` (`/pl/cereal-granola/03001`, page 9, 2026-10-23T21:55:13Z):

- `grid_card.html`: the product's grid cell, unchanged, from the page copy
  `live/dom/01M5NC5JY5YSX2A07DEW223TYJ.html.gz` (gzip sha256 b54e741921f92fdb...). The card shows
  "Sale: $5.49 discounted from $8.78".
- `products_v2.json`: the product's object, unchanged, from the same page's own product response
  `live/raw/01M5NC5JY5YSX2A07DEW223TYJ.0123.products_v2.json.gz` (body sha256 2c6b49433665c373...,
  captured 21:55:20Z): regular `USD 8.79`, promo `USD 5.49` for location 53100503.

The two observations differ on the same page in the same store context: release 1.3.0 keeps both and does not
count the record as verified (`tests/unit/test_price_conflict.py`).
