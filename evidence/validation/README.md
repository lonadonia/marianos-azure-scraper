# The export validation (OR-20): F2, and 1.10.0rc6's own runs R6 and R7

**Before (1.10.0rc5).** `validate-export --run 01M7JNB2HDFCNR3GHQVX8FYXX6` was killed by the kernel for lack of
memory, twice, with no output ([`BEFORE_rc5_VALIDATE_EXPORT_OOM_F2.txt`](BEFORE_rc5_VALIDATE_EXPORT_OOM_F2.txt)).
1.10.0rc5 read the decompressed text of all 575 stored listing pages into memory before checking any record.

**After (1.10.0rc6, commits `fdda7b2` and `62af220`).** The same command reads each stored page once, one at a time,
and still checks every record. It ran on Hamza's VM on 2026-11-16 from 23:15:03Z to 23:15:44Z
([`vm_or20.sh`](vm_or20.sh)). The run was offline, with no provider request, under a 3 GB memory limit with no swap,
on a VM with 3.8 GiB of RAM.

| Measured | Value |
|---|---|
| Exit status | **0** ([`VALIDATE_EXPORT_F2_rc6.json`](VALIDATE_EXPORT_F2_rc6.json), [`OR20_SUMMARY.json`](OR20_SUMMARY.json)) |
| Run time | **41.3 s** wall clock (38.5 s of CPU) |
| Peak memory | **338,148 KiB** maximum resident set (GNU time, [`GNU_TIME_F2_rc6.txt`](GNU_TIME_F2_rc6.txt)); the unit's own memory peak was 414.8 MB; the kernel logged no out-of-memory line ([`KERNEL_OOM_LINES_F2_rc6.txt`](KERNEL_OOM_LINES_F2_rc6.txt) is empty) |
| Read | 575 listing pages, 562 product-data responses, 42,486 price statements, 8,178 products in the sources |
| Records checked | **8,104** of the export (every record): 7,962 verified against their source |
| Captures | 8,104 present with their hash; 0 missing, 0 corrupted, 0 unreadable |
| Contract | both export files pass the 22-field contract: `products.json`, 8,104 rows; `products_fresh.json`, 7,678 rows |
| Mismatches | **0 silent mismatches**; **142 recorded differences**: 132 regular prices, 10 stores |

## Every recorded difference, investigated

[`OR20_RECORDED_DIFFERENCES_F2.csv`](OR20_RECORDED_DIFFERENCES_F2.csv) lists all 142 records, one row each. Each row
gives the exported value, the product data's value, and the price text of the product's own card as its stored page
shows it. It also gives the page's URL, fetch ID and SHA-256, and the product data's SHA-256. The script that
produced it is [`or20_mismatches.py`](or20_mismatches.py), and its summary is in
[`OR20_RECORDED_DIFFERENCES_F2_SUMMARY.json`](OR20_RECORDED_DIFFERENCES_F2_SUMMARY.json). It checks that its counts
are validate-export's counts, and they are.

| Field | Records | What the stored sources show | How the export treats them |
|---|---|---|---|
| regular price | 132 | The card shows "Sale: $X discounted from $Y". The product data loaded with the same page states a regular price **1 cent higher** than $Y (for example, card $8.28, product data $8.29). The difference is −1 cent in all 132. The sale price agrees in all 132, and every card shows the exported value. | The export keeps the displayed value and marks each record `price_conflict` (flag `PRICE_DOM_JSON_MISMATCH`). None of the 132 is counted as a valid record. |
| store | 10 | The product data states **no price location and no fulfillment** for the store. All 10 are `TEMPORARILY_OUT_OF_STOCK`. | The export marks each record `exported_not_valid` (flag `PRICE_STORE_NOT_STATED`). None is counted as valid. |

Neither difference is an error of the collector: each one is a disagreement inside the site's own data, recorded
before export. The 7,678 fresh valid records exclude all 142.

## F2's gates stay unevaluated

F2 was stopped by the collector before validation (STORE_NOT_VERIFIED, OR-19), so its gates G1 to G14 were never
evaluated. The rc6 validation changes nothing in the run:
- The run's status after the validation ([`F2_STATUS_AFTER_rc6_VALIDATION.txt`](F2_STATUS_AFTER_rc6_VALIDATION.txt))
  is `rejected`, with `outcome`, `collection_complete`, `records_by_status` and `historical` all null.
- The export manifest still has the SHA-256 published with rc5 (`12512c59…`) and its modification time of
  18:56:19Z.

## The same validation of 1.10.0rc6's own runs, R6 and R7

`validate-export --run` of each, by the installed 1.10.0rc6, offline, with the same memory bound (MemoryMax=3G, no
swap) through [`vm_validate_run6.sh`](../tools/vm_validate_run6.sh): R6 once finalized, R7 on its copy finalized
offline (R7 itself stays interrupted and resumable on its target). Each record is checked against
the stored page and product data it was read from, a carried record against the earlier run's own page. A
difference the collector recorded in the record (status `price_conflict` or flag `PRICE_DOM_JSON_MISMATCH`; flag
`PRICE_STORE_NOT_STATED`, never valid) is counted apart from a silent mismatch, which fails the check. R6's status
after the validation ([`R6/R6_STATUS_AFTER_rc6_VALIDATION.txt`](R6/R6_STATUS_AFTER_rc6_VALIDATION.txt)) is the one
its run folder recorded before it (`status_run.jsonl` in [`../runs/R6fin/`](../runs/R6fin/)), field for field. R7's
copy was dropped once its validation had ended (05:54:37Z), so R7's status after the validation was not read; the
validation only reads, and the copy's status before it is `status_run.jsonl` in
[`../runs/R7fin_copy/`](../runs/R7fin_copy/).

| Run | Records (by status) | Verified against their source | Silent mismatches | Recorded differences | Captures | 22-field contract | Read | Time, peak memory | Exit |
|---|---|---|---|---|---|---|---|---|---|
| R6 (`01M7KBQ3XXMP3W3FK2EXE525EA`) | 8,513 (historical 8,032, valid 448, price_conflict 24, eligible_unpriced 5, exported_not_valid 4) | 8,350 | **0** | 163 (regular_price 150, store 13), each flagged in the record | 8,513 ok, 0 missing, corrupted or unreadable | `products.json` 8,513 rows, `products_fresh.json` 448: pass | 639 listing pages, 622 product-data responses | 40.4 s, 184,936 KiB | 0 |
| R7 (`01M7KQ5GZVF5VK1S9FGTG6YFC9`) | 10,536 (historical 7,869, valid 2,518, price_conflict 111, eligible_unpriced 32, exported_not_valid 6) | 10,288 | **0** | 248 (regular_price 234, store 14), each flagged in the record | 10,536 ok, 0 missing, corrupted or unreadable | `products.json` 10,536 rows, `products_fresh.json` 2,518: pass | 783 listing pages, 764 product-data responses | 47.4 s, 233,816 KiB | 0 |

Time is the collector's own measure of the validation; GNU time's wall clock for the whole command, start-up
included, is in each folder's `time.txt` (R6 0:41.03, R7 0:48.07).

The files: [`R6/`](R6/) and [`R7/`](R7/) (the command's JSON output and stderr, GNU time's record, the kernel's
out-of-memory lines, none, and the summary).
