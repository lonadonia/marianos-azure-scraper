# Accuracy checks

Each check below reads a run's own stored pages and export, offline; nothing here asked the site again. The live
runs are in [`../runs/`](../runs/): S6 (1.10.0rc3), L1 and L2 (1.10.0rc4) read rows 22 to 27, where Cat Food, the
price-per-measure examples and the digital-coupon examples are; the full run F2 (1.10.0rc5) is the one that can reach
the alcohol and deli rows of the offer and size examples.

| File | What it shows |
|---|---|
| [`CAT_FOOD_27021.txt`](CAT_FOOD_27021.txt) | Cat Food (row 22, listing 27021) page by page in S6, L1 and L2: every answer (asked page, attempt, verdict, stated total, products, the stored page's SHA-256), the slots counted, distinct products, products on two pages, and where 0002310014492 appears |
| [`PPM_DISPLAYED_AND_EMBEDDED_L1.txt`](PPM_DISPLAYED_AND_EMBEDDED_L1.txt) | the two price-per-measure traces of the client (0084024314377, 0001280052496): the tile's displayed per-measure text, the exported `ppm`, and the product data the same page loaded (equivalized unit price and its unit, customer-facing size, location), each capture named by its SHA-256 |
| [`NAMED_UPCS_L1_trace_record.txt`](NAMED_UPCS_L1_trace_record.txt) | for the six named UPCs of rows 22 to 27: the exported fields, the page, the tile, the stored page's hash checked, and the source's own text |
| [`NAMED_UPCS_L1_check_sample.txt`](NAMED_UPCS_L1_check_sample.txt) | the same six through `check_sample.py` (the reviewer's tool, [`../samples/check_sample.py`](../samples/check_sample.py)) |
| [`DIGITAL_EXAMPLES.md`](DIGITAL_EXAMPLES.md) | the client's four digital-coupon examples, each stated individually, earlier and today |
| [`DIGITAL_EXAMPLES_L1_TILES.txt`](DIGITAL_EXAMPLES_L1_TILES.txt) | the four products' tile text on L1's stored pages, and whether any coupon word appears in it |
| [`NAMED_OFFERS_F2.txt`](NAMED_OFFERS_F2.txt) | Cutwater, The Finnish Long Drink, Nutrl and the Avocado Green Goddess Dip in the full run F2's export |
| [`COUPONS_ROUTE_READINGS.txt`](COUPONS_ROUTE_READINGS.txt) | the Coupons row (row 0) as each run of the day read it: the collector's recorded verdict beside the stored page (SHA-256, coupon cards, the site's loading indicator) |

## Cat Food (row 22, listing 27021)

Q2 (1.8.0rc4, 2026-11-02) read 232 slots holding 231 distinct products, with 0002310014492 shown twice (page 7 slot
24 and page 8 slot 1). Today the listing stated **234** results in S6, L1 and L2 alike, and each run counted **10
pages, 234 slots, 234 distinct products, none on two pages**; 0002310014492 appears once, on page 7. S6 read the
ten pages straight through. L1 and L2 each met the site's repeated page twice on Cat Food (L1: page 5's first two
answers; L2: page 4's first answer, then page 6's first): C1 set each such request aside and asked it again after
its wait, until the page asked for came back. So the listing is complete as it stood today, without the duplicate
of 2026-11-02. Today's reads cannot say what the 232nd product of 2026-11-02 was.

## Price per measure (0084024314377 and 0001280052496)

Both are exported as the site displays them, and both are flagged, not altered:

- **0084024314377** (Blue Buffalo Tastefuls, 12 ct / 2.6 oz, $19.99): the tile displays "$19.99/oz" and the page's
  product data states an equivalized unit price of 19.99 DOLLAR PER OUNCE. Exported `ppm` "$19.99/oz", flagged
  `PPM_EQUALS_ITEM_PRICE`: the per-measure price equals the item price (for illustration, 12 × 2.6 oz is 31.2 oz,
  and $19.99 over 31.2 oz is about $0.64/oz). The collector exports the displayed value and computes no
  replacement.
- **0001280052496** (Rayovac headlight, 1 Count, $7.99 sale from $10.49): the tile displays "$7.99/oz" and the
  product data states 7.99 (promo) and 10.49 (regular) DOLLAR PER OUNCE. Exported "$7.99/oz", flagged
  `PPM_UNIT_FAMILY_MISMATCH`: a per-ounce price for a product sold by the count.

## The four digital-coupon examples

Stated one by one in [`DIGITAL_EXAMPLES.md`](DIGITAL_EXAMPLES.md). In short: 0001780014939's coupon 4257015 was read
complete on 2026-11-06 and has since expired by its own terms ("Exp. Nov. 10"); 0001780014941 and 0003980014995 were
never observed rendered; 0002310014848's rendered page of 2026-11-06 showed no Savings section. Today none of the four
tiles shows a coupon; no product page was read in this delivery, so all four export empty digital fields with the
flag `DIGITAL_COUPONS_UNOBSERVED`, and none is stated to have no coupon.

## Offers and serving size (Cutwater, The Finnish Long Drink, Nutrl, the dip)

From the full run F2's export ([`NAMED_OFFERS_F2.txt`](NAMED_OFFERS_F2.txt): every field, flag, missing-field reason, page and offer kept for each):

- **Cutwater Espresso Martini** (`0081675102373`): **not in F2's export** (its listing was not read before the collector stopped the run, or the product was not shown on the pages read)
- **The Finnish Long Drink** (`0086001079386`): **not in F2's export** (its listing was not read before the collector stopped the run, or the product was not shown on the pages read)
- **Nutrl Vodka Hard Seltzer** (`0001820020352`): **not in F2's export** (its listing was not read before the collector stopped the run, or the product was not shown on the pages read)
- **the Avocado Green Goddess Dip** (`0073679800140`): **not in F2's export** (its listing was not read before the collector stopped the run, or the product was not shown on the pages read)

None of the four was observed fresh on 1.10.0rc5. The rules for them ("Buy 1 Save $N" is a one-unit condition, not a volume offer; a serving such as "2 tbsp" is not the pack's size) are covered offline with real captures since 1.9 (`tests/` in [`../../source/`](../../source/)).

## The Coupons row (row 0): a defect found in this review

The Coupons row is not a listing: its page (`/savings/cl/coupons/`) is read once at the start of every run, rendered, for the same store and fulfillment, and its coupon cards are recorded with the run; it lists offers, not the products they apply to, so no coupon reaches a record from it. On 2026-11-16 it was read once in each of the 12 runs, every time with the store check PASS. In 5 (S6, S6b, L1, P2, P3) the coupon list loaded: 24 cards. In 7 (L2, F1, P1, F2d, P4, P5, P6) it had **not** loaded: the coupons tab holds the site's loading indicator and no card. **The collector recorded all 12 as `READ`, the 7 unloaded ones with 0 coupon cards.** An unloaded list must be recorded as not read, never as zero coupons: that is a defect of the collector's verdict on this page (the same code in 1.10.0rc3, 1.10.0rc4 and 1.10.0rc5), found in this review of the evidence and not corrected in this delivery. F2's own reading is one of the 7: its Coupons row is **not read**. Each reading beside its stored page (SHA-256, cards, the indicator): [`COUPONS_ROUTE_READINGS.txt`](COUPONS_ROUTE_READINGS.txt), written by [`../tools/coupons_route_check.py`](../tools/coupons_route_check.py).

Digital deals on the full run's tiles: 0 of F2's 8,104 records carry a digital deal from their tile; all leave the digital fields empty with their reason (no tile showed a coupon).
