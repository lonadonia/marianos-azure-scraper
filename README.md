# Mariano's collector 1.10.0rc5: delivery for review (2026-11-16)

Prepared by Hamza. Store: Mariano's Vernon Hills, location **53100502** (ZIP 60061), **PICKUP**. Times are UTC.

**Status: NOT FINAL: a checkpoint for the client's review, not an accepted delivery. 1.10.0rc5 is qualified on Hamza's VM and its one logical full run F2 holds 7,678 fresh valid UPCs, but the collector stopped it, not resumable, before the full scope and before validation (STORE_NOT_VERIFIED on a re-asked page whose product data had not loaded: a defect found in this review), so its gates G3, G13 and G14 were never evaluated; the trial credit could not have paid for the rest in any case (94 of the 302 listings of the 1.9 queue complete), so no full-scope run exists to publish; the three defects found in this review, the schedule, the walkthrough on the client's VM, the client's acceptance and the other items under What remains stay open**

The live work ran on **Hamza's own Azure test VM**, through the **Oxylabs Web API** with Hamza's trial credit, under
Hamza's update of 16 November 2026 (after speaking with the client): live Mariano's collection with that credit,
tests on that VM and scheduling on it are authorized. Nothing here touched the client's Azure VM, and no Oxylabs
Classic request was sent. Every result names its revision and the kind of evidence it is (section 9).

This page is the one entry point. The technical report is [`review/REPORT.md`](review/REPORT.md).

## 1. The candidate

| | |
|---|---|
| Collector | **1.10.0rc5**, in [`source/`](source/): development commit `bc19afe60c1016cf5d08d055abd96bc69c9d3dd1`, Git tree `3f4567038890db47e83e73880e934620fdca6024`, published with one change: an old install note names the test VM's host, masked in `source/docs/AZURE_VM.md` ([`manifests/REDACTIONS.csv`](manifests/REDACTIONS.csv)), so `git rev-parse review-1.10.0rc5-20261116:source` prints `8fe051cd015381265d1002e9381e885822fcb68d`; [`manifests/check_source_tree.py`](manifests/check_source_tree.py) checks it file by file |
| This delivery | the tag `review-1.10.0rc5-20261116` (annotated; the previous delivery `review-1.10.0rc3-20261112` and every earlier tag are unchanged) |
| Change since 1.10.0rc3 | seven development commits ([`COMMITS_SINCE_1.10.0rc3.txt`](evidence/tests/COMMITS_SINCE_1.10.0rc3.txt)); collector logic: **one fix**, in `collection/oxylabs_live.py` (below); the rest is tests, the version, one comment and the README |
| Whole difference | [`DIFF_SINCE_1.10.0rc3.patch`](evidence/tests/DIFF_SINCE_1.10.0rc3.patch): the development diff, 12 files, +156 −19. `git diff review-1.10.0rc3-20261112 review-1.10.0rc5-20261116 -- source` shows the same plus the masked host line in `docs/AZURE_VM.md` (13 files, +157 −20) |

| Commit | Version | What changed | Collector source |
|---|---|---|---|
| `3beaf89` | (tests only) | the C1 Batteries replay compares the stored page with the saved answer's body | none |
| `9a27999` | 1.10.0rc4 | the version (1.10.0rc4's collector code is 1.10.0rc3's) | the version string |
| `dc926d4` | 1.10.0rc4 | a comment within the line limit (`acquisition/capture.py`) | one comment |
| `1838de7` | 1.10.0rc4 (tests only) | the test browser starts where unprivileged user namespaces are restricted (Ubuntu 24.04) | none |
| `570ff7c` | 1.10.0rc4 (tests only) | the scheduled-run test's collector clock starts at its occurrence | none |
| `a1385f8` | 1.10.0rc5 (tests only) | the regression for the fix below, committed first: it **fails on 1.10.0rc4's code** | none |
| `bc19afe` | **1.10.0rc5** | **the fix**: a listing page brought back before its search request was made is asked again, instead of stopping the run as a page of another store | `oxylabs_live.py`: +27 −5 |

**Why the fix.** 1.10.0rc4's full run (F1) was stopped by the collector after 158 submissions with
`STORE_NOT_VERIFIED`: one page came back before the site had made its search (no request, not loaded, no total, no
product, no card) although its header and state named the right store and fulfillment. In 1.10.0rc5 the check that
reads the store out of the page's own search request is "not applicable" only for such an empty, unfinished page,
which is then asked again; a page without its search that shows products, or that sits in another store's context,
still stops the run (two controls that pass before and after). Before the fix, with the new tests: 2 failed, 2
passed; after: 4 passed ([`evidence/tests/rc5_fix/`](evidence/tests/rc5_fix/)). The same case came up live in the
full run F2 on 1.10.0rc5 (fresh fruit, page 1): the page was asked again and the run went on. A narrower case stopped
F2 later: a page whose search had been made for the store but whose product data had not loaded (OR-19, section 2).

## 2. Answer in brief

| Question | Answer |
|---|---|
| The full run of the final candidate | **F2**, run `01M7JNB2HDFCNR3GHQVX8FYXX6` on 1.10.0rc5 only, two lanes, every CSV row 0 to 27 as configured (no command-line narrowing: not a pilot), read in four slices of at most 200 submissions, one logical run: 595 submissions (USD 0.8880), 416 listing pages completed, 7,678 distinct fresh valid UPCs; stopped by the collector at 18:56:02Z, not resumable (`STORE_NOT_VERIFIED`, exit 7), on a re-asked page whose product data had not loaded: a defect of 1.10.0rc5 found in this review; its records kept as a partial export (rejected), never published |
| Fresh valid products in one logical run | **7,678** distinct fresh valid UPCs (the collector's classification of each record) from 15 categories, every counted page attested to store 53100502 and PICKUP; **G13 and G14 not evaluated**: the collector validates a run when the run ends; a run it stops as not resumable is rejected and its records kept as a partial export without validation (as F1's were), so F2's gates were never evaluated |
| Scope gate G3 (reported apart) | **not evaluated** (F2 was stopped before validation); by the coverage file, 94 of the 302 listings of the 1.9 queue complete. F2 was stopped by the collector at 18:56:02Z, not resumable (`STORE_NOT_VERIFIED`, exit 7), on a re-asked page whose product data had not loaded: a defect of 1.10.0rc5 found in this review (OR-19); its records are kept as a partial export, which is never published (its publication refused with exit 6, nothing published). The trial credit pays for part of the scope only |
| F2's export validation | `validate-export --run` of F2 was killed by the VM's kernel for lack of memory, twice (about 3.3 GiB held, on a VM of 3.8 GiB without swap): it reads every stored listing page of a run into memory at once (F2: 575) (OR-20); the 22-field contract of both export files passed (8,104 and 7,678 rows) |
| Coverage against the 1.9 baseline | the baseline: 42 of 302 product listings complete (40 with products, 2 empty), 38 stopped on repeats, 222 not collected. **F2: 94 of the 302 product listings complete (92 with products, 2 empty), 40 incomplete, 165 not read to an end when the collector stopped the run (not reached, or begun and unfinished), 3 not among the listings the run planned from the department pages it read (13013 Sushi (row 4); 18003 Produce (row 10); 19007 Frozen Breakfast (row 12)); the 1.9 baseline was 42 complete** (section 4; listing by listing in [`COVERAGE_VS_1.9_QUEUE.csv`](evidence/coverage/COVERAGE_VS_1.9_QUEUE.csv)) |
| C1 live (a request answered with earlier products, or without the filters needed to subdivide it, asked again later) | requests set aside and asked again on the live site: 119 in S6, S6b, L1, L2 and F2 together, 85 recovered (a re-ask answered with the page asked for), 15 spent (both re-asks answered with the repeated page again), 19 still waiting when F2 ended; 1,624 new products came from re-asks; the shortest wait between two answers of one request was 303.8 s; S6: 3 set aside, 3 recovered; S6b: 1 set aside, 1 recovered; L1: 8 set aside, 8 recovered; L2: 9 set aside, 7 recovered; F2: 98 set aside, 66 recovered |
| Publication, refusal, rollback | on an isolated target, on 1.10.0rc5 (P4 to P6): P4 published (exit 0); P5's partial run refused (exit 6) with the published dataset unchanged; P6 published and rolled back to P4 (exit 0), P4's files restored |
| Operations | within F2 on 1.10.0rc5, live: resumable SIGTERM stops (exit 75), each resumed on the same run; a second start refused before any paid call (exit 9, nothing reserved); the run's state identical across a VM reboot; one automatic resume after a provider-error pause; recovery after a hard kill under two lanes (the dead lease expired, its tasks reclaimed, the request in flight kept as a charged unknown); no completed page asked again, apart from C1's deliberate re-asks; never more requests in flight than lanes; a run stopped at its ceiling finalized and its publication refused (P5); the last slice, planned to its ceiling, was stopped by the collector instead (a defect) and F2's publication refused ([`evidence/operations/`](evidence/operations/README.md)) |
| One lane against two | same scope (rows 22 to 27), 1.10.0rc4: one lane 73 submissions, 575.1 s with a request in flight, wall 1140 s; two lanes 72 submissions, 390.8 s in flight, wall 1166 s: both end on the 300 s re-ask waits, so the wall time does not shrink on this small scope while the time spent asking falls by 32% |
| Named checks | Cat Food 27021: 234 of 234 distinct in S6, L1 and L2, none on two pages (the duplicate of 2026-11-02 gone); the PPM traces 0084024314377 and 0001280052496 exported as displayed and flagged; the four digital examples stated one by one, none confirmed today (no product page read); Cutwater, The Finnish Long Drink, Nutrl and the dip: not observed in F2 (none of the four is in its export); the Coupons row: the Coupons page loaded in 5 of 12 runs; in the other 7, F2's included, it had not loaded and the collector still recorded it as read with 0 cards: a defect, open ([`evidence/accuracy/`](evidence/accuracy/README.md)) |
| Cost | 1,022 submissions over the stages of this delivery (USD 1.5285 at the recorded rate, unknown outcomes charged); F2 alone 595 (USD 0.8880). Walmart's envelope untouched; no top-up, no overage |
| Full-run estimate | one full run: 4,321 to 6,906 submissions (USD 6.48 to 10.36), from the historical 3,019 to 4,826 listing pages with F2's measured 1.43 submissions per completed page (re-asks, malformed answers and repeats included) instead of 1.3; 5.0 to 8.1 hours a run at F2's two-lane pace (6.0 s of execution per completed page). Shortfall: 3,726 to 6,311 more submissions (USD 5.59 to 9.47) to complete one run beyond F2, against Mariano's remaining trial credit of USD 0.3120 |
| Schedule (Monday and Thursday 07:00 America/Chicago) | **not enabled: blocked.** It may be enabled only after a protected full-scope publication, which does not exist (G3 fails for lack of credit). The schedule's one-shot path stays tested offline only |
| The client's VM, Classic | not touched; no Classic request; the client-environment walkthrough and acceptance stay open |

## 3. Changes tied to Darren's findings

Darren's 29 audit items, in their ten groups (each group's full row:
[`review/AUDIT_29_RECONCILIATION.csv`](review/AUDIT_29_RECONCILIATION.csv), whose earlier columns are unchanged):

| Group | The finding | What this delivery changes | Still open |
|---|---|---|---|
| G1 (M01, M02) | the client's VM checks were not executed | the same procedure (install from the lock, migrations, suites, container, backup, restore, rollback) qualified on **Hamza's** VM for 1.10.0rc5 ([`evidence/install/`](evidence/install/)); the client's VM was not touched | the client's VM window and key; acceptance there |
| G2 (M03 to M05) | T05, T06, T07 needed regressions | unchanged: corrected in 1.9; T06 and T07 pass within 1.10.0rc5's integration suite | none offline |
| G3 (M06 to M10) | rows 0 to 21, Cat Food and listings above the 250-result window not read completely | C1 ran live: S6 (rows 22 to 27, 1.10.0rc3), S6b (an above-window listing through its filters), the pilots L1 and L2 and the full run F2 (1.10.0rc5); F2 completed 94 of the 302 listings of the 1.9 queue (the baseline: 42), reading the rows in order until the collector stopped it (a defect, see What remains); above the window, 27 listings reached by F2 stated more results than the 250 a listing shows; 0 reconciled complete through the child listings or filters their pages name, 27 incomplete, 0 not read to an end when the run stopped; Cat Food (27021) read complete in S6, L1 and L2 (234 of 234 distinct, none on two pages) | full coverage: the store-check defect (OR-19), then the credit |
| G4 (M11 to M15) | digital terms, the offer and size examples, the two PPM traces | the two PPM traces exported as displayed, flagged and traced to the product data their page loaded; the four digital examples stated one by one (none confirmed today, no product page read); the offer and size examples: not observed in F2 (none of the four is in its export); the Coupons row: the Coupons page loaded in 5 of 12 runs; in the other 7, F2's included, it had not loaded and the collector still recorded it as read with 0 cards: a defect, open | coupon terms from rendered product pages (a provider decision); the Coupons row's verdict (a correction); the offer and size examples observed live (the store-check defect, then credit (OR-19, OR-01): the collector stopped F2 before it read them) |
| G5 (M16 to M19) | qualification of the final version, retention, recovery, protected full publication | 1.10.0rc5 qualified (suites, fix before/after, install, container, backup, restore, rollback); F2: 7,678 fresh valid UPCs, stopped by the collector before validation (G13 and G14 not evaluated; OR-19), its export validation killed for lack of memory (OR-20); recovery after a hard kill under two lanes and across a VM reboot in the same run; publication, refusal and rollback on an isolated target | the two corrections (OR-19, OR-20); a validated, protected full-scope publication (G3); natural retention (two complete runs) |
| G6 (M20 to M25) | census, concurrency, cadence, cost, Classic | one lane against two measured (L1, L2); the census of every listing F2 reached; cost measured per slice and the estimate updated; Classic disabled, nothing sent | the schedule (blocked); the client's cadence and Classic decisions |
| G7 (M26) | mutation commitment | done in 1.9; the 1.10.0rc5 fix has its own fail-before/pass-after | none |
| G8 (M27) | stale statements | corrected statements listed in [`review/REPORT.md`](review/REPORT.md) section 11 | none |
| G9 (M28) | optional providers and stores | not chosen, not used | the client's choice |
| G10 (M29) | owners, data preservation, support and IP | Hamza owns the publication and the evidence; private captures kept and named by SHA-256; no tag moved | support and IP terms |

## 4. Coverage by CSV row (run F2, 1.10.0rc5)

From the run's own export [`coverage_by_csv_row.csv`](evidence/runs/F2d/export/coverage_by_csv_row.csv) (listing by
listing: [`coverage_reconciliation.csv`](evidence/runs/F2d/export/coverage_reconciliation.csv)). A listing is DONE
only when every page was read and judged; a repeated page, a missing filter, an unread page or a spent ceiling
leaves it INCOMPLETE or NOT_COLLECTED, never empty.

| Row | Category | Listings planned | Complete | Incomplete | Not read | Pages completed | Distinct products | Status |
|---|---|---|---|---|---|---|---|---|
| 0 | Coupons | 0 | 0 | 0 | 0 | 0 | 0 | NOT_ATTEMPTED |
| 1 | Produce | 10 | 7 | 3 | 0 | 34 | 762 | INCOMPLETE |
| 2 | Meat | 16 | 14 | 2 | 0 | 53 | 1071 | INCOMPLETE |
| 3 | Seafood | 6 | 4 | 2 | 0 | 20 | 410 | INCOMPLETE |
| 4 | Deli | 10 | 8 | 2 | 0 | 22 | 457 | INCOMPLETE |
| 5 | Bakery | 15 | 14 | 1 | 0 | 21 | 314 | INCOMPLETE |
| 6 | Floral | 6 | 6 | 0 | 0 | 6 | 47 | COMPLETE |
| 7 | Grocery | 14 | 3 | 11 | 0 | 27 | 642 | INCOMPLETE |
| 8 | Dairy | 10 | 8 | 2 | 0 | 38 | 805 | INCOMPLETE |
| 9 | Frozen | 16 | 14 | 2 | 0 | 74 | 1595 | INCOMPLETE |
| 10 | Natural Organic | 11 | 5 | 5 | 1 | 32 | 766 | INCOMPLETE |
| 11 | Beverages | 10 | 3 | 6 | 1 | 37 | 858 | INCOMPLETE |
| 12 | Breakfast | 8 | 4 | 2 | 2 | 21 | 449 | INCOMPLETE |
| 13 | Coffee | 10 | 2 | 0 | 8 | 16 | 393 | INCOMPLETE |
| 14 | Candy | 8 | 2 | 2 | 4 | 12 | 275 | INCOMPLETE |
| 15 | Beer Wine Liquor | 16 | 0 | 0 | 16 | 5 | 120 | INCOMPLETE |
| 16 | Health | 26 | 0 | 0 | 26 | 0 | 0 | INCOMPLETE |
| 17 | Personal Care | 9 | 0 | 0 | 9 | 0 | 0 | INCOMPLETE |
| 18 | Beauty | 18 | 0 | 0 | 18 | 0 | 0 | INCOMPLETE |
| 19 | Baby | 7 | 0 | 0 | 7 | 0 | 0 | INCOMPLETE |
| 20 | Household | 40 | 0 | 0 | 40 | 0 | 0 | INCOMPLETE |
| 21 | Kitchen Dining | 16 | 0 | 0 | 16 | 0 | 0 | INCOMPLETE |
| 22 | Pet Supplies | 12 | 0 | 0 | 12 | 0 | 0 | INCOMPLETE |
| 23 | Candles Home Fragrances | 1 | 0 | 0 | 1 | 0 | 0 | INCOMPLETE |
| 24 | Batteries | 1 | 0 | 0 | 1 | 0 | 0 | INCOMPLETE |
| 25 | Light Bulbs | 1 | 0 | 0 | 1 | 0 | 0 | INCOMPLETE |
| 26 | School Office | 1 | 0 | 0 | 1 | 0 | 0 | INCOMPLETE |
| 27 | Hardware Home Improvement | 1 | 0 | 0 | 1 | 0 | 0 | INCOMPLETE |

F2 read the rows in order, two lanes at a time, and was stopped by the collector while it read row 15 (Beer Wine Liquor) and the rows just before it: rows 1 to 15 were read, 1 of them completely (row 6, Floral); rows 16 to 27 were not read at all (their 133 listings planned from the department pages, no page read). Row 0 (Coupons) has no listing pages: its route is read once per run (see the accuracy checks). Runs of the same day that are **not** part of F2, and are not added to it: rows 22 to 27 were
read by the pilot L1 (1.10.0rc4: 17 listings, all complete, 1,138 fresh valid UPCs), by L2 and by S6 (1.10.0rc3);
row 10's Frozen listing (18010) by S6b (1.10.0rc3).

## 5. The runs

Every live run of this delivery, with its UTC times, run ID, revision, store, configuration hash, limits, outcome and
cost. Each run's full evidence (its run report, database rows, ledger rows, journal, export, validation and the
SHA-256 of every stored page) is in [`evidence/runs/<stage>/`](evidence/runs/).

The validation gates, as the collector names them (`validation/gates.py`): G1 location (every page attested to the
store and fulfillment), G2 access (no challenge), **G3 coverage** (every listing complete or genuinely empty), G4
yield, G5 schema, G6 formats, G7 duplicates, G8 completeness of fields, G9 canaries, G10 price reconciliation, G11
promotion sanity, G12 site contract, **G13 integrity** (every task ended, every stored page's hash verified, the
manifest complete) and **G14 contest readiness** (live data, at least 500 valid records in at least 3 categories).
Any FAIL except G14 makes a run ineligible for publication; G14 marks a small run "not contest-ready" without
blocking it (so the one-listing publication tests P1, P3, P4 and P6 publish with G14 FAIL). A pilot (any
command-line narrowing) is never published, whatever its gates.

| Stage | UTC | Run | Revision | Config | Limit | Outcome | Submissions (settled, unknown) | USD |
|---|---|---|---|---|---|---|---|---|
| S6 | 2026-11-16 03:44:29 to 04:01:19 | `01M7H79NGE1BT9KH49QR8EV4QJ` | 1.10.0rc3 `a1040f7` | `16c02db0f386` | 130 subs / USD 0.195 (pilot) | rejected; gates FAIL: G3; 1,141 fresh valid | 67 (67, 0) | 0.1005 |
| S6b | 2026-11-16 04:02:21 to 04:08:18 | `01M7H8ABYFGRJPHK2YJ5MSAJQC` | 1.10.0rc3 `a1040f7` | `16c02db0f386` | 86 subs / USD 0.129 (pilot) | validated; gates FAIL: G14; 279 fresh valid | 21 (21, 0) | 0.0315 |
| L1 | 2026-11-16 15:09:31 to 15:28:31 | `01M7JEFZW4PY88RKT5FBMJMZWT` | 1.10.0rc4 `570ff7c` | `16c02db0f386` | 130 subs / USD 0.195 (pilot) | validated; gates: all PASS; 1,138 fresh valid | 73 (73, 0) | 0.1095 |
| L2 | 2026-11-16 15:32:46 to 15:52:12 | `01M7JFTHRTJ1ZKPZ9C7Y0Y301S` | 1.10.0rc4 `570ff7c` | `8b291b7aaaaf` | 130 subs / USD 0.195 (pilot) | rejected; gates FAIL: G3; 1,018 fresh valid | 72 (72, 0) | 0.108 |
| P1 | 2026-11-16 15:55:40 to 16:02:11 | `01M7JH4G03W52YEZMES5QSWVC4` | 1.10.0rc4 `570ff7c` | `e0544702946f` | 12 subs / USD 0.018 | published; gates FAIL: G14; 62 fresh valid | 6 (6, 0) | 0.009 |
| P2 | 2026-11-16 16:03:25 to 16:04:17 | `01M7JHJNGQJ67ABVGR9X8MPEGP` | 1.10.0rc4 `570ff7c` | `e0544702946f` | 4 subs / USD 0.006 | rejected; gates FAIL: G3, G14; 47 fresh valid | 4 (4, 0) | 0.006 |
| P3 | 2026-11-16 16:06:24 to 16:07:03 | `01M7JHR4GE1PZMY8D8J2DA6R4P` | 1.10.0rc4 `570ff7c` | `e0544702946f` | 12 subs / USD 0.018 | published; gates FAIL: G14; 62 fresh valid | 5 (5, 0) | 0.0075 |
| F1 | 2026-11-16 16:08:52 to 16:20:06 | `01M7JHWNC5EGHRMNMCJQ14P8DR` | 1.10.0rc4 `570ff7c` | `8b291b7aaaaf` | 200 subs / USD 0.300 | stopped by the collector: STORE_NOT_VERIFIED (exit 7), rejected; 1.10.0rc5 asks such a page again | 158 (158, 0) | 0.237 |
| F2a | 2026-11-16 17:09:10 to 17:22:58 | `01M7JNB2HDFCNR3GHQVX8FYXX6` | 1.10.0rc5 `bc19afe` | `8b291b7aaaaf` | 200 subs / USD 0.300 | slice ended resumable (SIGTERM, exit 75); the run continues in the next slice | 190 (188, 2) | 0.285 |
| F2b | 2026-11-16 17:36:39 to 17:49:48 | `01M7JNB2HDFCNR3GHQVX8FYXX6` | 1.10.0rc5 `bc19afe` | `8b291b7aaaaf` | 200 subs / USD 0.300 | slice ended resumable (SIGTERM, exit 75); the run continues in the next slice | 191 (189, 2) | 0.2865 |
| F2c | 2026-11-16 17:55:58 to 18:09:04 | `01M7JNB2HDFCNR3GHQVX8FYXX6` | 1.10.0rc5 `bc19afe` | `8b291b7aaaaf` | 200 subs / USD 0.300 | slice ended resumable (SIGTERM, exit 75); the run continues in the next slice | 190 (187, 3) | 0.2805 |
| F2d | 2026-11-16 18:54:32 to 18:56:20 | `01M7JNB2HDFCNR3GHQVX8FYXX6` | 1.10.0rc5 `bc19afe` | `8b291b7aaaaf` | 200 subs / USD 0.300 | the whole run F2: stopped by the collector, STORE_NOT_VERIFIED (exit 7), not resumable: rejected; 7,678 fresh valid; records kept as a partial export, never published | 24 (22, 2) | 0.036 |
| P4 | 2026-11-16 18:11:37 to 18:27:36 | `01M7JRXD9P93HPNBRY3J0BVMSX` | 1.10.0rc5 `bc19afe` | `e0544702946f` | 12 subs / USD 0.018 | validated; gates FAIL: G14; 62 fresh valid | 8 (8, 0) | 0.012 |
| P5 | 2026-11-16 18:29:06 to 18:34:33 | `01M7JSXE192AD3KH2SV0178F4A` | 1.10.0rc5 `bc19afe` | `e0544702946f` | 4 subs / USD 0.006 | rejected; gates FAIL: G3, G4, G14; 22 fresh valid | 4 (4, 0) | 0.006 |
| P6 | 2026-11-16 18:36:10 to 18:52:24 | `01M7JTAC3J8TYR7RV93F2W7PG3` | 1.10.0rc5 `bc19afe` | `e0544702946f` | 12 subs / USD 0.018 | validated; gates FAIL: G14; 62 fresh valid | 9 (9, 0) | 0.0135 |

UTC: the stage's executions, first start to last end. Config: the first 12 hex digits of the SHA-256 of the stage's configuration files' SHA-256 values, sorted by name (each file's own hash is in the stage's `stage_record.json`). Limit: the stage's ceiling in the collector and in the ledger. Unknown: submissions whose outcome was not known when a process stopped, charged at the worst case until reconciled. USD at the recorded rate (0.0015 per submission). Store: `marianos-53100502-pickup` (location 53100502, PICKUP) for every run.

## 6. Where each output is

| Output | Where (run F2; every other run has the same layout) |
|---|---|
| Records, all retained (JSON, CSV) | [`products.json`](evidence/runs/F2d/export/products.json), [`products.csv`](evidence/runs/F2d/export/products.csv) |
| Fresh records only (JSON, CSV) | [`products_fresh.json`](evidence/runs/F2d/export/products_fresh.json), [`products_fresh.csv`](evidence/runs/F2d/export/products_fresh.csv) |
| Category memberships, offers | [`memberships.json`](evidence/runs/F2d/export/memberships.json), [`offers.json`](evidence/runs/F2d/export/offers.json) |
| Provenance of every record (page, source hash, observation time) | [`provenance.json.gz`](evidence/runs/F2d/export/provenance.json.gz) (gzip-compressed: above 8 MB; `COMPRESSED.csv` in the run folder gives the uncompressed SHA-256) |
| Every listing page asked and its verdict | [`listing_pages.csv`](evidence/runs/F2d/export/listing_pages.csv) |
| Requests set aside and asked again (C1) | [`db_deferred_requests.csv`](evidence/runs/F2d/db_deferred_requests.csv) (the run's rows; a stopped run's partial export has no `deferred_requests.json`) |
| Coverage by CSV row and by listing | [`coverage_by_csv_row.csv`](evidence/runs/F2d/export/coverage_by_csv_row.csv), [`coverage_reconciliation.csv`](evidence/runs/F2d/export/coverage_reconciliation.csv) |
| Validation report (gates G1 to G14) | [`validation_report.json`](evidence/runs/F2d/export/validation_report.json) |
| The run report (every slice of F2) | [`RUN_REPORT.md`](evidence/runs/F2d/RUN_REPORT.md), [`RUN_FACTS.json`](evidence/runs/F2d/RUN_FACTS.json) |
| Publication state before and after each step | [`evidence/publication/`](evidence/publication/) |
| Stored pages (private) | listed by SHA-256 in each run's `STORED_PAGES_PRIVATE.csv`; kept by Hamza and produced on request |
| SHA-256 of every file | [`manifests/SHA256SUMS.txt`](manifests/SHA256SUMS.txt); origin of every file: [`manifests/FILE_MAP.csv`](manifests/FILE_MAP.csv); identifiers masked: [`manifests/REDACTIONS.csv`](manifests/REDACTIONS.csv) |
| The recorded walkthrough | [`evidence/walkthrough/`](evidence/walkthrough/) |

## 7. Check records against their source yourself

No VM and nothing to install beyond Python 3.10 or later:

```
python3 -I evidence/samples/check_sample.py evidence/samples/F2 --random 20 --seed 1   # 20 records at random
python3 -I evidence/samples/check_sample.py evidence/samples/F2 <UPC> [<UPC> ...]     # the UPCs you choose
```

Each record's exported title, prices and price per measure are printed beside what the product's own tile showed in
the stored page it was read from, with that page's URL, observation time and SHA-256
([`evidence/samples/`](evidence/samples/README.md)). The live site can be compared too, by the record's URL, keeping
in mind that prices change over time.

## 8. Reproduce offline

```
git clone https://github.com/lonadonia/marianos-azure-scraper.git && cd marianos-azure-scraper
git checkout review-1.10.0rc5-20261116
python3 -I manifests/check_source_tree.py                 # source/ is 1.10.0rc5's tree, file for file (one host masked)
cd source && uv sync --frozen
uv run pytest -q tests/unit                               # 494 passed
uv run ruff check . && uv run ruff format --check . && uv run mypy
uv run pytest -q tests/integration/test_reask_c1.py tests/integration/test_publication_result.py   # 28 + 6
uv run pytest -q tests/integration/test_listing_pages.py -k "before_its_search_was_made or without_its_search"
```

The integration suite needs PostgreSQL 16 server binaries on the path and Chromium (`uv run playwright install
--with-deps chromium`); the whole suite took about 26 minutes on the VM. The "before" side of the fix and of C1:
[`evidence/tests/README.md`](evidence/tests/README.md). Nothing in these commands sends a request anywhere.

## 9. Kinds of evidence

| Kind | In this delivery |
|---|---|
| Offline tests (synthetic pages, mock transport) | the suites, the C1 and publication cases, the fix's before/after ([`evidence/tests/`](evidence/tests/)) |
| Replay of answers saved earlier | four C1 tests replay answers saved on 2026-11-09; labelled as replays, never as live |
| Live, on Hamza's VM (owner VM) | S6, S6b (1.10.0rc3); L1, L2, P1 to P3, F1 (1.10.0rc4); F2, P4 to P6 (1.10.0rc5) ([`evidence/runs/`](evidence/runs/)) |
| Scheduled observations | **none**: the schedule is not enabled (section 2) |
| Client acceptance | **none**: the client has not reviewed or accepted 1.10.0rc5; nothing ran on the client's VM |

## 10. What remains

One row per open obligation, with its owner, blocker and next action:
[`review/OUTSTANDING.csv`](review/OUTSTANDING.csv); every original requirement with its evidence:
[`review/ACCEPTANCE_MATRIX.csv`](review/ACCEPTANCE_MATRIX.csv) (the earlier columns unchanged, the 1.10.0rc5 columns
added). In short:

| Open item | Owner | What blocks it | Next action |
|---|---|---|---|
| Full coverage (G3) and a protected full-scope publication | Hamza, then the client | the store check's verdict below (it stopped F2), and credit: one full run is estimated at 4,321 to 6,906 submissions; Mariano's trial envelope has USD 0.3120 left | correct the verdict; fund about 3,726 to 6,311 more submissions (USD 5.59 to 9.47 at the recorded rate); then one logical full run on one revision, validated and published |
| The store check's verdict on a page whose product data has not loaded (a defect found in F2) | Hamza | 1.10.0rc5 stops a run, not resumable, when a page whose own search is for the store draws some cards without their product data | correct it with a regression that fails before and passes after (offline, no credit): such a page is not counted and is asked again within the limits, as one with no card is; a stated price or a search of another store still stops the run |
| The export validation's memory (a defect found in F2's validation) | Hamza | `validate-export --run` reads every stored listing page of a run into memory at once and was killed for lack of memory on F2 (575 pages) | read and index the pages one at a time, with a regression that bounds the memory (offline, no credit); then validate F2's export again |
| The Coupons row's verdict (a defect found in this review) | Hamza | 1.10.0rc5 records a Coupons page whose list has not loaded as read, with 0 coupon cards | correct it with a regression that fails before and passes after (offline, no credit), then read the route in the next funded run |
| Coupon terms of the four digital examples | Hamza / the client | rendered product pages are not obtained reliably through the Web API as configured (1.9: 3 of 14) | decide a supported rendering path, or accept unread terms flagged as such |
| The offer and size examples observed live | Hamza | the store-check defect, then credit (OR-19, OR-01): the collector stopped F2 before it read them | within the next full run |
| The schedule; two weeks of observations (disappearances, stock transitions, retention) | Hamza, then time | no protected full-scope publication | enable the Monday and Thursday 07:00 America/Chicago schedule after it |
| The client's VM: install, suites, Docker, release, the walkthrough there, acceptance | the client, then Hamza | the client's window and access (outside this authorization) | the client names a window |
| Classic, optional providers and stores, support and IP terms | the client | the client's decisions | - |

The operator's commands (start, pause, resume, stop, status, logs, export, publication, rollback) and the acceptance
procedure for the client's VM: [`review/ACCEPTANCE_RUNBOOK.md`](review/ACCEPTANCE_RUNBOOK.md) and
[`source/README.md`](source/README.md).

## 11. Earlier deliveries

The default branch keeps only this delivery. Every earlier one stays complete at its own review tag:
[`EARLIER_DELIVERIES.md`](EARLIER_DELIVERIES.md).
