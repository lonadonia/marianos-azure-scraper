# Q2 dataset: Mariano's Vernon Hills Pickup, release candidate 1.8.0rc4

Run **Q2** `01M6E5V6CASQ8F00VC8PE9TFYW`, 2026-11-02 13:05:42Z to 14:10:40Z, collector **1.8.0rc4** (commit `9d16475`),
store 53100502 (Marianos Vernon Hills, 1720 N Milwaukee Ave, 60061), **PICKUP** only. The run's own evidence is in
[`evidence/live-runs/Q2_1.8.0rc4_01M6E5V6CASQ8F00VC8PE9TFYW/`](../../evidence/live-runs/Q2_1.8.0rc4_01M6E5V6CASQ8F00VC8PE9TFYW/).

Q2 was rejected by two of its gates: G3 (coverage: Cat Food 231 of 232) and G13 (integrity, the rc4 behaviour that
1.8.0rc5 corrects). It was never published, so the last-good publication stayed Q1c's. These files are Q2's own
export, byte for byte. 1.8.0rc5 has not produced a live dataset.

## Products

| File | Records | What it is |
|---|---|---|
| [`products_fresh.json`](products_fresh.json), [`.csv`](products_fresh.csv) | **1,137** | products observed in Q2 and valid (Q2 `exports/products_fresh.*`, unchanged) |
| [`products_retained.json`](products_retained.json), [`.csv`](products_retained.csv) | **1,160** | every product retained: 1,137 fresh valid, 23 fresh not valid, 0 carried (Q2 `exports/products.*`, renamed only) |

The 23 fresh products that are not valid are 10 price conflicts (one cent each), 10 eligible products without a
displayed price, and 3 with a price stated for no store
([`PRODUCT_DISPOSITION.csv`](PRODUCT_DISPOSITION.csv), one row per retained product).

**Schema:** 22 fields, in this order: `zipcode`, `store_name`, `store_location`, `store_logo`, `store_brand`,
`category`, `sub_category`, `product_title`, `weight`, `regular_price`, `sale_price`, `volume_deals_description`,
`volume_deals_price`, `digital_deals_description`, `digital_deals_price`, `image_url`, `url`, `upc`, `gupc`, `ppm`,
`unit_price`, `crawl_date`. The CSV files are UTF-8 with a byte-order mark, and they hold the same columns and values
as the JSON files.

**Checked for this publication:** both files have no duplicate UPC and no duplicate URL. Every record has
`store_name` "Marianos Vernon Hills", `zipcode` 60061 and `crawl_date` 2026-11-02. Each file is identical to the run's
export in the run folder. A random draw can be checked against the stored pages, offline:

```
python3 evidence/tools/check_records.py data/Q2-1.8.0rc4/products_fresh.json evidence/live-runs/Q2_1.8.0rc4_01M6E5V6CASQ8F00VC8PE9TFYW 10 <any number>
```

## Coverage and pages

| File | Rows | What it is |
|---|---|---|
| [`COVERAGE_BY_CSV_ROW.csv`](COVERAGE_BY_CSV_ROW.csv) | 28 | the client's CSV rows 0-27: rows 23-27 complete; row 22 Pet Supplies 11 of 12 listings complete; rows 0-21 not collected in Q2 |
| [`COVERAGE_BY_LISTING.csv`](COVERAGE_BY_LISTING.csv) | 17 | each listing: 14 DONE, 2 EMPTY (the site reports 0 results), 1 INCOMPLETE (Cat Food) |
| [`COVERAGE_RECONCILIATION.json`](COVERAGE_RECONCILIATION.json) | | the same reconciliation, with each listing's product identities |
| [`LISTING_PAGES.csv`](LISTING_PAGES.csv) | 61 | each page request: 58 completed, 2 failed and 1 refused as malformed (each retried until completed), with verdict, totals, new and repeated products and the page's SHA-256 |
| [`PRICE_CONFLICTS.csv`](PRICE_CONFLICTS.csv) | 10 | the price conflicts; their upstream cause is not known |
| [`RETENTION_Q1C_Q2.csv`](RETENTION_Q1C_Q2.csv) | 362 | the 362 products of the earlier run Q1c (1.8.0rc3) and their state in Q2: 320 unchanged, 42 changed only in `digital_deals_description` |
| [`DIGITAL_OFFER_CHANGES_Q1C_Q2.csv`](DIGITAL_OFFER_CHANGES_Q1C_Q2.csv) | 42 | the digital coupon present in Q1c's pages and absent from Q2's; the captures do not show whether the retailer or the provider changed the response |

How each file was produced and checked is in [`review/TECHNICAL_REPORT.md`](../../review/TECHNICAL_REPORT.md)
(sections 3, 5, 8 and 9).
