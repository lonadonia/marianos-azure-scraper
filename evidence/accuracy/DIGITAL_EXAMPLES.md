# The client's four digital-coupon examples, one by one

What each example's own evidence says, earlier and today. Today's evidence is the live run L1 (1.10.0rc4, run
`01M7JEFZW4PY88RKT5FBMJMZWT`, 2026-11-16 15:09 to 15:28 UTC, store 53100502, PICKUP), whose stored listing pages are
in [`../runs/L1/`](../runs/L1/); S6 (03:44 UTC) and L2 (15:32 UTC) show the same for all four. The tiles' text is in
[`DIGITAL_EXAMPLES_L1_TILES.txt`](DIGITAL_EXAMPLES_L1_TILES.txt), read from the stored pages, each page's SHA-256
matching the run's provenance.

**No product page was read in this delivery.** A coupon's terms are on the product's own rendered page, and a
listing tile can omit a coupon that page shows (today none of the four tiles shows one). The 1.9 stage O1 saved 14 product-page answers, of which 3 state they were
rendered (`run_js` true; `review/TECHNICAL_REPORT_1.10.0.md`, corrections of the 1.9 publication); repeating that unchanged would spend the remaining credit on
a known failure, and other provider experiments are outside this delivery. The collector's product-page reading
(`coverage.read_product_terms`, off by default) reads every tile of a run within `--max-term-reads`; it cannot be
pointed at chosen UPCs. So every record below leaves the digital fields empty, with the reason, and carries the flag
`DIGITAL_COUPONS_UNOBSERVED`, rather than export a coupon without its terms or state that none applies.

| UPC | Product (today's tile) | Earlier evidence | Today (L1, the listing tile) | State |
|---|---|---|---|---|
| 0001780014939 | "Natural Dog Food, Chicken and Rice Formula Dry Dog food for Digestive and Gut Health Support", $54.99, Dog Food (27017) page 7 | **complete** on 2026-11-06 (stage O1, the rendered product page, request 7524540530412231682): coupon 4257015 "Save $10.00 on any TWO (2) Purina ONE Dry Dog Food bags (8 lb or larger) or Wet Dog Food 12-count packages (13 oz cans). Mix or match.", its legal text, "Exp. Nov. 10", "Sign In To Clip"; the cash-back offer 4257014 left out by the shipped setting | no coupon on the tile (its text: aisle, price twice, $1.77/lb, title, "Sign In to Add"); digital fields empty, flag `DIGITAL_COUPONS_UNOBSERVED` | the coupon read on 2026-11-06 expired by its own terms ("Exp. Nov. 10"); whether a coupon applies today is **unknown** (its product page was not read) |
| 0001780014941 | "ONE Natural Dog Food, Lamb and Rice Formula Dry Dog food for Digestive and Gut Health Support", $54.99, Dog Food (27017) page 7 | **unread**: its two saved product pages (2026-11-06) were brought without rendering and say nothing about coupons | no coupon on the tile; digital fields empty, flag `DIGITAL_COUPONS_UNOBSERVED` | **unknown**; never observed |
| 0002310014848 | "Temptations Birthday Adult Crunchy and Soft Cat Treats Lobster and Beef", $7.99 sale from $9.49, Cat Treats (27022) page 2 | its card showed "Coupon: $6.99 Temptations Cat Treats" on 2026-11-02 (Q2); its rendered product page of 2026-11-06 (request 7524541411266425857) **shows no Savings section** | no coupon on the tile; the sale price is exported ($7.99 from $9.49); digital fields empty, flag `DIGITAL_COUPONS_UNOBSERVED` | **not confirmed**: the product's own page of 2026-11-06 did not show the coupon its card had shown on 2026-11-02 |
| 0003980014995 | "Energizer Ultimate Child Shield 2032 3V Lithium Coin Batteries", $19.99 sale from $21.99, Hardware Home Improvement (33) page 2 | **unread**: its two saved product pages (2026-11-06) were brought without rendering | no coupon on the tile; the sale price is exported; digital fields empty, flag `DIGITAL_COUPONS_UNOBSERVED` | **unknown**; never observed |

The earlier evidence is published at tag `review-1.10.0rc3-20261112`: `review/TECHNICAL_REPORT_1.10.0.md` (the
coupon examples, "checked again in the saved sources only") and `evidence/1.10.0/coupons/COUPON_EVIDENCE_CHECK.json`.

What would settle all four: the product's own page, rendered, read on the day for this store, with the
coupon's ID, terms, expiry and qualifying products. That needs a provider path that renders product pages reliably,
a decision outside this delivery (see "What remains" in the [README](../../README.md)).
