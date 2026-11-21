# Accuracy, rechecked offline from the saved evidence (2026-11-21)

No request was made. Every check reads files that earlier live runs stored, or the published R7 sample
(`evidence/samples/R7`: R7's 10,536 exported records, each with its source excerpt).

| File | What it checks |
|---|---|
| `EXPECTED_27021_R7.txt`, `EXPECTED_27017_R7.txt`, `EXPECTED_27022_R7.txt` | the distinct products listed on the counted pages of Cat Food, Dog Food and Cat Treats in R7, read again from the stored pages by the replay (`RPL-R7-76c0932dbc0a`); one UPC a line, leading zeros kept. These lists are independent of the export |
| `STRICT_27021_R7.txt`, `STRICT_27017_R7.txt`, `STRICT_27022_R7.txt` | `check_sample.py evidence/samples/R7 --strict --expect EXPECTED_<listing>_R7.txt`: Cat Food 234 the same, PASS (exit 0); Dog Food 200 the same and 24 missing from the export, FAIL (exit 1); Cat Treats 32 the same and 20 missing, FAIL (exit 1) |
| `NAMED_PRODUCTS_STRICT_R7.txt` | `check_sample.py --strict` on the two price-per-measure traces (0084024314377, 0001280052496), Cutwater 0081675102373, The Finnish Long Drink 0086001079386 and 0003980014995: 5 the same, PASS |
| `PRODUCT_PAGES_SAVINGS_R7_P8.txt` | the four named product pages' stored Savings documents (whether the provider rendered the page, whether a Savings section and coupon rows were present) and each product's record in R7 and P8 |
| `OFFER_EXAMPLES_ON_SAVED_PAGES.txt` | the client's four offer and size examples searched on every listing page row of the 25 saved run copies (R7c and R7fin_copy hold the same run R7: the last slice's copy and the copy finalized offline) |

Run from the repository root (Python 3.10 or later, standard library only):

    python3 -I evidence/samples/check_sample.py evidence/samples/R7 --strict --expect evidence/rc7/accuracy/EXPECTED_27017_R7.txt
    python3 -I evidence/samples/check_sample.py evidence/samples/R7 --strict 0084024314377 0001280052496 0081675102373 0086001079386 0003980014995
