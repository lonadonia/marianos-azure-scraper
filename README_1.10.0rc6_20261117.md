# Mariano's collector 1.10.0rc6: delivery for review (2026-11-17)

Prepared by Hamza. Store: Mariano's Vernon Hills, location **53100502** (ZIP 60061), **PICKUP**. Times are UTC.

**Status: NOT FINAL: a checkpoint for the client's review, not an accepted delivery. 1.10.0rc6 corrects the three defects found in 1.10.0rc5's review (OR-19, OR-20, OR-04), each with tests committed before the fix that fail before it and pass after, and is qualified on Hamza's VM; its full run R7 (01M7KQ5GZVF5VK1S9FGTG6YFC9) holds 2,518 distinct fresh valid UPCs in 8 categories but cannot complete on 1.10.0rc6: a listing the site links with a malformed address stopped six of its ten executions, each about 5 minutes in, and stops every resume (OR-22, OR-23), so R7 was not resumed after its fifth slice, with USD 4.4200 of the credit left. It stays interrupted and resumable; its gates, evaluated on an isolated copy finalized offline, give G3, G4 FAIL (coverage, and yield: the 19 categories R7 did not reach have no record) and G13 PASS, G14 PASS. The four defects R7 found (OR-21 to OR-24, among them two counted pages whose records the two lanes lost) are corrected on the branch marianos-1.10-next with tests that fail before and pass after, not released. No full-scope run exists to publish; the schedule, the two-week observation, the client's VM, the client's acceptance and the other items under What remains stay open**

The live work ran on **Hamza's own Azure test VM**, through the **Oxylabs Web API**, with a new credential's USD 5 of
free credit that Hamza supplied for this closeout (16 November 2026). His update of the same day, after speaking with
the client, authorizes live Mariano's collection with his credit, tests on that VM and scheduling on it. Every
submission was reserved in a spending ledger before it was sent: no top-up, no overage, nothing of Walmart's used.
Nothing here touched the client's Azure VM, and no Oxylabs Classic request was sent. Every result names its revision
and the kind of evidence it is (section 10).

This page is the one entry point. The technical report is [`review/REPORT.md`](review/REPORT.md).

## 1. The candidate

| | |
|---|---|
| Collector | **1.10.0rc6**, in [`source/`](source/): development commit `d77f3065c757b8b962524dbf8d9961dec212e72b`, Git tree `b6b5f1d395d444f808423cfcb01a17cb149b29b7`, published with one change: an old install note names the test VM's host, masked in `source/docs/AZURE_VM.md` ([`manifests/REDACTIONS.csv`](manifests/REDACTIONS.csv)), so `git rev-parse review-1.10.0rc6-20261117:source` prints `73607661dae6e205155f58c230a3e11d1ad4c546`; [`manifests/check_source_tree.py`](manifests/check_source_tree.py) checks it file by file |
| This delivery | the tag `review-1.10.0rc6-20261117` (annotated; the previous delivery `review-1.10.0rc5-20261116` and every earlier tag are unchanged) |
| Change since 1.10.0rc5 | twelve development commits ([`COMMITS_SINCE_1.10.0rc5.txt`](evidence/tests/COMMITS_SINCE_1.10.0rc5.txt)), each correction's tests committed before its fix |
| Whole difference | [`DIFF_SINCE_1.10.0rc5.patch`](evidence/tests/DIFF_SINCE_1.10.0rc5.patch): 41 files, +2,145 −90. Collector code: 21 files, +823 −82. Tests: 17 files (5 of them pages stored live, as fixtures), +1,285 −5. README, version and lock: 3 files. One patch per commit: [`evidence/tests/patches/`](evidence/tests/patches/) |

## 2. The corrections, each failing before and passing after

| | What was wrong | What 1.10.0rc6 does | Tests before → after | Seen live |
|---|---|---|---|---|
| **OR-19** | F2 (1.10.0rc5) was stopped by the collector, not resumable (`STORE_NOT_VERIFIED`), on a re-ask whose search had been made for the store but whose product data had not loaded | Such a page counts nothing and is asked again within the re-ask limit; the original reason is kept. A wrong store, a wrong fulfillment or a page without store proof still stops the run | 5 failed, 3 passed (the 3 controls) → 8 passed | R7: 22 malformed answers for the store (16 whose grid drew no card although the page's own state listed products, 4 stating no page number or result count, 2 whose grid drew one card fewer than the state) counted nothing and were asked again; 12 of their 14 pages completed later, and no page stopped the run on the store (132 counted pages, 136 attestations, all for 53100502 PICKUP) |
| **OR-20** | `validate-export --run` held all of F2's 575 stored pages in memory and was killed on the 3.8 GiB VM | Each stored page is read once, before the next, and every record's capture and values are checked against it | 3 failed, 1 passed; unit 2 failed → 4 passed; unit 2 passed | On F2 itself, by the installed 1.10.0rc6: exit 0 in 41.3 s, peak memory 330 MiB, 575 pages, 8,104 records, no silent mismatch, 142 recorded differences explained ([`evidence/validation/`](evidence/validation/README.md)) |
| **OR-04** | The Coupons route was recorded as read when its list had not loaded (0 cards) | The Coupons row is read only when its list has loaded, and its verdict holds through the run; an unread Coupons route keeps the run from complete scope; a product page still loading leaves its coupon unread, never "no coupon" | 12 failed, 1 passed (the control) → 13 passed | P7: the page read for the store, stating "448 Coupons", 24 cards drawn. R7: read at its first answer (2026-11-17T03:01:08Z), its list loaded, 24 cards drawn, the page stating "447 Coupons"; row 0 COMPLETE ([`evidence/accuracy/`](evidence/accuracy/README.md)) |
| **Run order** (found in F2's traces) | A listing's subdivisions waited behind the whole plan; every product page was one more request; the rows the review depends on came last | Subdivisions are read right after their listing; `--rows-first` reads named rows first without changing the plan; `--term-upc` reads only the named products' pages | 6 failed; unit 2 failed → 6 passed; unit 2 passed | R7: rows 22, 27, 23 to 26 and 15 read first, then the plan's own order (row 1); Red Wine 08120's and White Wine 08122's 11 subdivisions read right after their page 1; the four named product pages each read once, when R7 met its card (03:02:58Z to 04:01:59Z), and no other product page |
| Order regression (found by the full suite on `88e12e0`) | Two tests of cancellation and of a brand reading resumed after a kill failed | The plan's place first, then creation order within a listing's group (`d77f306`) | on `88e12e0`: 4 failed, 24 passed → 28 passed | |

Whole suites on the pinned candidate, on Hamza's VM: unit 506, the C1 cases 30, the publication cases 6 and the
**whole integration suite 247**, all passed; `ruff` and `mypy` clean. The workstation ran 218 integration tests
without the browser (all passed). Details, logs and how to reproduce each "before":
[`evidence/tests/`](evidence/tests/README.md).

## 3. Answer in brief

| Question | Answer |
|---|---|
| The full run of the final candidate | R7, run `01M7KQ5GZVF5VK1S9FGTG6YFC9`, of 1.10.0rc6 (`d77f306`) for 53100502 PICKUP: every row 0 to 27 in its plan, two lanes, five slices on 2026-11-17 (03:00Z to 05:35Z, ten executions), 256 submissions (USD 0.3345 settled, 7 unknown outcomes held). **Not complete:** on 1.10.0rc6 the Hard Cider listing 08194, which the site's menu links with a malformed address, stopped six of the ten executions, each about 5 minutes in (OR-22, OR-23), so R7 was not resumed after its fifth slice, with USD 4.4200 of the envelope left; it stays interrupted and resumable, and was finalized offline in an isolated copy: **rejected** ([`evidence/runs/`](evidence/runs/)) |
| Fresh valid products in one logical run | **2,518 distinct fresh valid UPCs in 8 categories**, all read by R7 itself on one revision (`d77f306`); 149 fresh records not valid; 7,869 records carried forward from earlier runs, exported with their own status (`carried_forward`) and never counted as fresh; 10,536 records in all ([`products_fresh.json`](evidence/runs/R7fin_copy/export/products_fresh.json)) |
| Scope gate G3 (reported apart) | **FAIL** on R7's copy finalized offline: of the 302 listings of the 1.9 baseline, 21 complete (19 with products, 2 empty), 2 read to their last page but short in records (Dog Food 27017 and Cat Treats 27022: OR-24), 6 incomplete and 273 not collected. G4 (yield) fails with it: 19 categories have no record. The Coupons route (row 0) was read, so G3 does not fail on it (OR-04) |
| G13 integrity, G14 contest readiness | **G13 PASS, G14 PASS** on R7's copy finalized offline; all gates: G1 PASS, G2 PASS, G3 FAIL, G4 FAIL, G5 PASS, G6 PASS, G7 PASS, G8 PASS, G9 PASS, G10 PASS, G11 PASS, G12 PASS, G13 PASS, G14 PASS ([`validation_report.json`](evidence/runs/R7fin_copy/export/validation_report.json)). The export checked against its stored pages: exit 0, 10,288 of 10,536 records verified against their source, 0 silent mismatches, the other 248 flagged in their own records ([`evidence/validation/`](evidence/validation/README.md)) |
| Coverage against the 302 listings of the 1.9 baseline | 21 of the 302 complete (19 with products, 2 empty) and 2 more read to their last page but short in records (OR-24: R7 kept 200 of Dog Food 27017's 224 products and 32 of Cat Treats 27022's 52; its coverage file states both DONE, G3 counts both incomplete); 6 incomplete; 273 not collected, 6 of them begun. CSV rows complete: 0 (Coupons), 23, 24, 26, 27; Cat Food 27021 complete (234 of 234). Above the window: Red Wine 08120 and White Wine 08122 read through 11 subdivisions (8 done, 3 incomplete), Shop Liquor 08121 and Fresh Vegetables 06112 at page 1 only ([`evidence/coverage/`](evidence/coverage/README.md)) |
| The site's repeated pages | For a page 2 or later the site sometimes answers with page 1's products: on 2026-11-16, 10% of such answers at 03Z, 28% at 17Z, 59% at 18Z and 85% at 23Z; on 2026-11-17 at 03Z, 44% (R7's first slice), so the hour alone does not predict it ([`REPEATED_PAGES_BY_HOUR.csv`](evidence/estimate/REPEATED_PAGES_BY_HOUR.csv)). A repeated page is asked again at most twice; when both re-asks repeat too, the listing stays incomplete and G3 fails (16 of 120 resolved requests on 2026-11-16, all between 15Z and 23Z: [`REASK_OUTCOMES_BY_HOUR.csv`](evidence/coverage/REASK_OUTCOMES_BY_HOUR.csv)). R6 was stopped after one slice at 23Z for that reason, and R7 was started at 03Z, the hour of the lowest share on 2026-11-16. R7 met 44% at 03Z, 31% at 04Z and 50% at 05Z on 2026-11-17; of the 35 requests it set aside, 23 were recovered by a re-ask, 6 had both re-asks repeated (each leaves one of the baseline's 6 incomplete listings incomplete) and 6 were still waiting at its end ([`REASK_OUTCOMES_BY_HOUR_RC6.csv`](evidence/operations/REASK_OUTCOMES_BY_HOUR_RC6.csv)). The re-ask limit is kept, as the brief requires; whether it may change is Hamza's decision. |
| Product pages and named checks | the four named product pages, each read once when R7 met its card, and the three it got unrendered read again in the pilot P8: 0002310014848 (R7, 03:02:58Z) and 0003980014995 (P8, 04:21:54Z) rendered and loaded, no savings shown; 0001780014939 and 0001780014941 not rendered by the provider in either run (unread: nothing learnt). R7 kept no record of 0002310014848, 0001780014939 or 0001780014941, although the pages that list them were counted (OR-24); P8, with one lane, exported the Dog Food pair, valid and flagged `DIGITAL_COUPONS_UNOBSERVED`. The named traces in R7: 0084024314377 ($19.99/oz) and 0001280052496 ($7.99/oz) exported exactly as their tiles display them; Cutwater and The Finnish Long Drink fresh and valid, with no volume deal ("Buy 1 Save" is a one-unit condition) and the pack's size; Nutrl and the dip on no page R7 counted ([`evidence/accuracy/`](evidence/accuracy/README.md)) |
| Publication | no full-scope run to publish: R7 is incomplete (it cannot complete on 1.10.0rc6) and stays interrupted and resumable; asked to publish it, the collector refused on its copy finalized offline (05:48Z) and on its own target (05:59Z), exit 6 each ("a partial dataset: only complete runs are published"), and the target, which holds no publication, held none after; on a copy of 1.10.0rc5's isolated target, 1.10.0rc6 refused a partial run beside the published dataset (exit 6), which stayed unchanged; the publication, refusal and rollback shown live on 1.10.0rc5 are carried, the publication code being unchanged ([`evidence/publication/`](evidence/publication/README.md)) |
| Operations (pause, kill, resume, refused start, rollback) | R6a: a second start refused before any request (exit 9); R7a: a resumable stop by SIGTERM (exit 75); R7 resumed nine times (by the operator, by the collector after provider stops, and after a hard kill), ten executions with no completed page asked again; R7b: a hard kill (SIGKILL) with both lanes working, recovered in the same stage once the dead lease had expired, its submission in flight held as unknown; R7w, recorded: a SIGTERM stop (exit 75), a refused second start (exit 9), a refused publication of the unfinished run (exit 6); rollback: 1.10.0rc5's live rollback on an isolated target, carried (the publication code is unchanged) ([`evidence/operations/`](evidence/operations/README.md), [`evidence/publication/`](evidence/publication/README.md)) |
| Cost | every live stage of 1.10.0rc6: 349 submissions, USD 0.4800 committed at the reservation rate (USD 0.4665 settled, USD 0.0135 held for 9 unknown outcomes); R7, 256 submissions over five slices, 1.939 a counted page; one full run of a corrected candidate at R7's rate: 4,312 to 5,132 submissions, USD 6.4680 to 7.6980, 15.1 to 18.0 hours with two lanes ([`evidence/ledger/`](evidence/ledger/README.md), [`evidence/estimate/`](evidence/estimate/README.md)) |
| Funding | USD 5 of free credit on the new Oxylabs Web API credential (fingerprint masked …022e50), authorized by Hamza for Mariano's on 16 November 2026: one ledger, an envelope of USD 4.90, no top-up and no paid overage ([`evidence/ledger/`](evidence/ledger/README.md)); USD 0.4800 committed when R7's last slice ended, USD 4.4200 left. R7 cannot complete on 1.10.0rc6, so the next full run is that of a corrected candidate: at R7's measured rate 4,312 to 5,132 submissions, USD 6.4680 to 7.6980, about USD 2.0490 to 3.2790 more than is left ([`evidence/estimate/`](evidence/estimate/README.md)); funding it is Hamza's decision |
| Schedule (Monday and Thursday 07:00 America/Chicago) | **not enabled: blocked.** It may be enabled only after a protected full-scope publication with verified credit for each occurrence; after R7 both are missing: no full-scope run has been published (R7 cannot complete on 1.10.0rc6), and the USD 4.4200 left does not fund one full run of a corrected candidate (USD 6.4680 to 7.6980 at R7's rate), let alone two a week. The release ships it off (`schedule.enabled: false`), and a firing with it off exits 0 (`SCHEDULE_OFF`) and reserves nothing; the same times across the daylight-saving change of 14 March 2027 (13:00Z in winter, 12:00Z from 15 March) are listed in [`evidence/operations/schedule/`](evidence/operations/schedule/) |
| The client's VM, Classic | not touched; no Classic request; the client-environment walkthrough and acceptance stay open |

## 4. Changes tied to Darren's findings

Darren's 29 audit items, in their ten groups (each group's full row:
[`review/AUDIT_29_RECONCILIATION.csv`](review/AUDIT_29_RECONCILIATION.csv), whose earlier columns are unchanged):

| Group | The finding | What 1.10.0rc6 changes | Still open |
|---|---|---|---|
| G1 (M01, M02) | the client's VM checks were not executed | the same procedure qualified on **Hamza's** VM for 1.10.0rc6: install from the lock, migrations (0006 to 0006), the suites (unit 506, integration 247, C1 30, publication 6; ruff and mypy clean), the container, a backup restored with equal row counts in 26 tables, a rollback to 1.10.0rc5 and forward again ([`evidence/install/`](evidence/install/README.md), [`evidence/tests/`](evidence/tests/README.md)); the client's VM was not touched | the client's VM window and key; acceptance there |
| G2 (M03 to M05) | T05, T06, T07 needed regressions | unchanged: corrected in 1.9; T06 and T07 pass within 1.10.0rc6's integration suite | none offline |
| G3 (M06 to M10) | rows 0 to 21, Cat Food and listings above the 250-result window not read completely | R7 read rows 0 to 27 in its plan, rows 22, 27, 23 to 26 and 15 first: rows 0, 23, 24, 26 and 27 complete, Cat Food 27021 complete (234 of 234), Red Wine 08120 and White Wine 08122 read through their 11 subdivisions (8 done), 21 of the 302 baseline listings complete; R7 cannot complete on 1.10.0rc6 (OR-22, OR-23); the Coupons row (0) gets its own verdict (OR-04) and a listing's subdivisions are read before the plan's next listing; 1.10.0rc5's count corrected: F2 completed 96 of the 302 baseline listings, not 94 (13013, 18003 and 19007 were read under rows 3, 1 and 9) | 273 baseline listings not collected and 6 incomplete; Dog Food 27017 and Cat Treats 27022 short in records (OR-24); OR-21 to OR-24 corrected on a branch, not released; a full run of the corrected candidate (credit) |
| G4 (M11 to M15) | digital terms, the offer and size examples, the two PPM traces | the four product pages read once each when R7 met their cards, three read again in P8: two rendered with no savings shown, two never rendered (unread); both PPM traces exported as displayed; Cutwater and The Finnish Long Drink fresh and valid, with no volume deal (one-unit conditions); the Coupons route read, 24 cards | rendered pages for 0001780014939 and 0001780014941; records of three of the four product pages, lost in R7 (OR-24); Nutrl and the dip (on no page R7 counted) |
| G5 (M16 to M19) | qualification of the final version, retention, recovery, protected full publication | 1.10.0rc6 qualified (G1); `validate-export --run` reads one stored page at a time (OR-20): on F2's 575 stored pages it ended exit 0 in 41 s, peak 338,148 KiB under a 3 GiB bound ([`evidence/validation/`](evidence/validation/README.md)); 1.10.0rc6 refused a partial run beside a published dataset, on a copy of the isolated target, the published state unchanged ([`evidence/publication/`](evidence/publication/README.md)); R7, finalized in an isolated copy: G13 and G14 PASS, G3 and G4 FAIL (rejected); its export validated against its stored pages (exit 0 in 48.1 s, 0 silent mismatches); its publication refused on the copy and on its target (exit 6) | a complete full-scope run and its protected publication; retention over two weeks of scheduled runs; the client's VM |
| G6 (M20 to M25) | census, concurrency, cadence, cost, Classic | R7 read with two lanes under one ledger lease, at most 2 requests in flight in every slice, 1.939 submissions a counted page; with two lanes it lost the records of two counted pages (OR-24, corrected on a branch); every submission reserved before dispatch in a new ledger for the new credit ([`evidence/ledger/`](evidence/ledger/README.md)); the schedule not enabled (no protected full-scope publication); Classic disabled, nothing sent | the schedule (blocked); the client's cadence and Classic decisions |
| G7 (M26) | mutation commitment | done in 1.9; each 1.10.0rc6 correction's tests were committed before its fix, fail on the code before it and pass after ([`evidence/tests/`](evidence/tests/README.md)) | none |
| G8 (M27) | stale statements | 1.10.0rc5's statements corrected in [`review/REPORT.md`](review/REPORT.md) section 11 (F2 completed 96 of the 302 baseline listings, not 94; none was unplanned) | none |
| G9 (M28) | optional providers and stores | not chosen, not used | the client's choice |
| G10 (M29) | owners, data preservation, support and IP | Hamza owns the publication and the evidence; the stored pages kept private, each named by its SHA-256; no tag moved | support and IP terms |

## 5. Coverage by CSV row (run R7, 1.10.0rc6)

From the run's own export [`coverage_by_csv_row.csv`](evidence/runs/R7fin_copy/export/coverage_by_csv_row.csv) (listing
by listing: [`coverage_reconciliation.csv`](evidence/runs/R7fin_copy/export/coverage_reconciliation.csv)). A listing is
DONE only when every page was read and judged; a repeated page whose re-asks are spent, a missing filter, an unread
page or a stop leaves it INCOMPLETE or NOT_COLLECTED, never empty.

| Row | Category | Listings planned | Complete | Incomplete | Not read | Pages completed | Distinct products | Status |
|---|---|---|---|---|---|---|---|---|
| 0 | Coupons | 0 | 0 | 0 | 0 | 1 | 0 | COMPLETE |
| 1 | Produce | 10 | 1 | 0 | 9 | 5 | 122 | INCOMPLETE |
| 2 | Meat | 16 | 0 | 0 | 16 | 0 | 0 | INCOMPLETE |
| 3 | Seafood | 6 | 0 | 0 | 6 | 0 | 0 | INCOMPLETE |
| 4 | Deli | 10 | 0 | 0 | 10 | 0 | 0 | INCOMPLETE |
| 5 | Bakery | 15 | 0 | 0 | 15 | 0 | 0 | INCOMPLETE |
| 6 | Floral | 6 | 0 | 0 | 6 | 0 | 0 | INCOMPLETE |
| 7 | Grocery | 14 | 0 | 0 | 14 | 0 | 0 | INCOMPLETE |
| 8 | Dairy | 10 | 0 | 0 | 10 | 0 | 0 | INCOMPLETE |
| 9 | Frozen | 16 | 0 | 0 | 16 | 0 | 0 | INCOMPLETE |
| 10 | Natural Organic | 11 | 0 | 0 | 11 | 0 | 0 | INCOMPLETE |
| 11 | Beverages | 10 | 0 | 0 | 10 | 0 | 0 | INCOMPLETE |
| 12 | Breakfast | 8 | 0 | 0 | 8 | 0 | 0 | INCOMPLETE |
| 13 | Coffee | 10 | 0 | 0 | 10 | 0 | 0 | INCOMPLETE |
| 14 | Candy | 8 | 0 | 0 | 8 | 0 | 0 | INCOMPLETE |
| 15 | Beer Wine Liquor | 16 | 7 | 4 | 5 | 34 | 1580 | INCOMPLETE |
| 16 | Health | 26 | 0 | 0 | 26 | 0 | 0 | INCOMPLETE |
| 17 | Personal Care | 9 | 0 | 0 | 9 | 0 | 0 | INCOMPLETE |
| 18 | Beauty | 18 | 0 | 0 | 18 | 0 | 0 | INCOMPLETE |
| 19 | Baby | 7 | 0 | 0 | 7 | 0 | 0 | INCOMPLETE |
| 20 | Household | 40 | 0 | 0 | 40 | 0 | 0 | INCOMPLETE |
| 21 | Kitchen Dining | 16 | 0 | 0 | 16 | 0 | 0 | INCOMPLETE |
| 22 | Pet Supplies | 12 | 11 | 1 | 0 | 33 | 666 | INCOMPLETE |
| 23 | Candles Home Fragrances | 1 | 1 | 0 | 0 | 3 | 55 | COMPLETE |
| 24 | Batteries | 1 | 1 | 0 | 0 | 4 | 96 | COMPLETE |
| 25 | Light Bulbs | 1 | 0 | 1 | 0 | 3 | 72 | INCOMPLETE |
| 26 | School Office | 1 | 1 | 0 | 0 | 5 | 103 | COMPLETE |
| 27 | Hardware Home Improvement | 1 | 1 | 0 | 0 | 3 | 65 | COMPLETE |

Row 0 is the Coupons route: read at its first answer (03:01:08Z), its list loaded, 24 coupon cards drawn of the 447 the page states. Row 22's 11 complete listings include Dog Food 27017 and Cat Treats 27022, which R7 read to their last page but did not keep in full (OR-24: 200 of 224 and 32 of 52 products in its records); G3 counts both incomplete. Row 22's incomplete listing is Dog Treats 27018 (its page 3 repeated page 1 through both re-asks), and row 25's Light Bulbs 26002 (page 4 likewise). Row 15: 7 listings complete; Red Wine 08120, White Wine 08122, Champagne & Sparkling Wine 08180 and Hard Seltzers 08183 incomplete; of the other 5, Rose & Blush Wine 08181, Flavored Malt Beverages 08192, Shop Liquor 08121 and Shop All 08184 were begun, and Hard Cider 08194 was never read (OR-22). Row 1: Fresh Herbs 06122 complete, Fresh Vegetables 06112 and Organic Produce 18003 begun, Fresh Fruit 06111 asked once with nothing counted. Rows 2 to 14 and 16 to 21 were not reached.

## 6. The runs

Every live run of this delivery, with its UTC times, run ID, revision, store, configuration hash, limits, outcome and
cost. Each run's full evidence (its run report, database rows, ledger rows, journal, export, validation and the
SHA-256 of every stored page) is in [`evidence/runs/<stage>/`](evidence/runs/).

The validation gates, as the collector names them (`validation/gates.py`): G1 location (every page attested to the
store and fulfillment), G2 access (no challenge), **G3 coverage** (every listing complete or genuinely empty), G4
yield, G5 schema, G6 formats, G7 duplicates, G8 completeness of fields, G9 canaries, G10 price reconciliation, G11
promotion sanity, G12 site contract, **G13 integrity** (every task ended, every stored page's hash verified, the
manifest complete) and **G14 contest readiness** (live data, at least 500 valid records in at least 3 categories).
Any FAIL except G14 makes a run ineligible for publication. A pilot (any command-line narrowing) is never published,
whatever its gates. `--rows-first` and `--term-upc` do not narrow the scope: they order the plan and name product
pages.

| Stage | UTC | Run | Revision | Config | Limit | Outcome | Submissions (settled, unknown) | USD |
|---|---|---|---|---|---|---|---|---|
| P7 | 2026-11-16 23:20 to 23:38 | `01M7KAJZTFXAWFA8AHXRQ343TT` | 1.10.0rc6 `d77f306` | `16c02db0f386` | 20 subs / USD 0.030 (pilot) | rejected; gates FAIL: G3, G14; 46 fresh valid | 9 (9, 0) | 0.0135 |
| R6a | 2026-11-16 23:40 to 23:49 | `01M7KBQ3XXMP3W3FK2EXE525EA` | 1.10.0rc6 `d77f306` | `8b291b7aaaaf` | 160 subs / USD 0.240 | interrupted | 65 (63, 2) | 0.0930 |
| R6 (finalized) | 2026-11-17 00:03 (offline) | `01M7KBQ3XXMP3W3FK2EXE525EA` | 1.10.0rc6 `d77f306` | `8b291b7aaaaf` | none (no request) | rejected; gates FAIL: G3, G4, G14; 448 fresh valid | the same stage's rows | no request |
| R7a | 2026-11-17 03:00 to 03:04 | `01M7KQ5GZVF5VK1S9FGTG6YFC9` | 1.10.0rc6 `d77f306` | `8b291b7aaaaf` | 160 subs / USD 0.240 | interrupted | 46 (44, 2) | 0.0690 |
| R7a2 | 2026-11-17 04:00 to 04:14 | `01M7KQ5GZVF5VK1S9FGTG6YFC9` | 1.10.0rc6 `d77f306` | `8b291b7aaaaf` | 160 subs / USD 0.240 | interrupted | 76 (74, 2) | 0.1050 |
| P8 | 2026-11-17 04:20 to 04:23 | `01M7KVRMP5X4THRJ8EE50PVKSK` | 1.10.0rc6 `d77f306` | `16c02db0f386` | 30 subs / USD 0.045 (pilot) | validated | 19 (19, 0) | 0.0285 |
| R7b | 2026-11-17 04:35 to 04:55 | `01M7KQ5GZVF5VK1S9FGTG6YFC9` | 1.10.0rc6 `d77f306` | `8b291b7aaaaf` | 610 subs / USD 0.915 | interrupted | 60 (57, 3) | 0.0780 |
| R7w | 2026-11-17 05:05 to 05:15 | `01M7KQ5GZVF5VK1S9FGTG6YFC9` | 1.10.0rc6 `d77f306` | `8b291b7aaaaf` | 110 subs / USD 0.165 | interrupted | 35 (35, 0) | 0.0435 |
| R7c | 2026-11-17 05:22 to 05:35 | `01M7KQ5GZVF5VK1S9FGTG6YFC9` | 1.10.0rc6 `d77f306` | `8b291b7aaaaf` | 150 subs / USD 0.225 | interrupted | 39 (39, 0) | 0.0495 |
| R7fin_copy | 2026-11-17 05:47 to 05:51 (offline, a copy) | `01M7KQ5GZVF5VK1S9FGTG6YFC9` | 1.10.0rc6 `d77f306` | `8b291b7aaaaf` | none (no request) | rejected; gates FAIL: G3, G4; 2,518 fresh valid | the same stage's rows | no request |

UTC: the stage's executions, first start to last end (a finalization: its own time). Config: the first 12 hex digits of the SHA-256 of the stage's configuration files' SHA-256 values, sorted by name (each file's own hash is in the stage's `stage_record.json`). Limit: the stage's ceiling in the collector and in the ledger. Unknown: submissions whose outcome was not known when a process stopped, charged at the worst case until reconciled. USD at the reservation rate (0.0015 per submission). Store: `marianos-53100502-pickup` (location 53100502, PICKUP) for every run.

## 7. Where each output is

| Output | Where (run R7; every other run has the same layout) |
|---|---|
| Records, all retained (JSON, CSV) | [`products.json.gz`](evidence/runs/R7fin_copy/export/products.json.gz) (gzip-compressed, above 8 MB: the run folder's `COMPRESSED.csv` gives the uncompressed SHA-256), [`products.csv`](evidence/runs/R7fin_copy/export/products.csv) |
| Fresh records only (JSON, CSV) | [`products_fresh.json`](evidence/runs/R7fin_copy/export/products_fresh.json), [`products_fresh.csv`](evidence/runs/R7fin_copy/export/products_fresh.csv) |
| Category memberships, offers | [`memberships.json`](evidence/runs/R7fin_copy/export/memberships.json), [`offers.json`](evidence/runs/R7fin_copy/export/offers.json) |
| Provenance of every record (page, source hash, observation time) | [`provenance.json.gz`](evidence/runs/R7fin_copy/export/provenance.json.gz) (gzip-compressed, above 8 MB: the run folder's `COMPRESSED.csv` gives the uncompressed SHA-256) |
| Every listing page asked and its verdict | [`listing_pages.csv`](evidence/runs/R7fin_copy/export/listing_pages.csv) |
| Requests set aside and asked again (C1) | [`db_deferred_requests.csv`](evidence/runs/R7fin_copy/db_deferred_requests.csv) |
| Coverage by CSV row and by listing | [`coverage_by_csv_row.csv`](evidence/runs/R7fin_copy/export/coverage_by_csv_row.csv), [`coverage_reconciliation.csv`](evidence/runs/R7fin_copy/export/coverage_reconciliation.csv) |
| Validation report (gates G1 to G14) | [`validation_report.json`](evidence/runs/R7fin_copy/export/validation_report.json) |
| The run report (every slice of R7) | [`RUN_REPORT.md`](evidence/runs/R7fin_copy/RUN_REPORT.md), [`RUN_FACTS.json`](evidence/runs/R7fin_copy/RUN_FACTS.json) |
| Product pages, coupons, price per measure | [`evidence/accuracy/`](evidence/accuracy/README.md) |
| Spending ledger | [`evidence/ledger/`](evidence/ledger/README.md) |
| Stored pages (private) | listed by SHA-256 in each run's `STORED_PAGES_PRIVATE.csv`; kept by Hamza and produced on request |
| SHA-256 of every file | [`manifests/SHA256SUMS.txt`](manifests/SHA256SUMS.txt); origin of every file: [`manifests/FILE_MAP.csv`](manifests/FILE_MAP.csv); identifiers masked: [`manifests/REDACTIONS.csv`](manifests/REDACTIONS.csv) |
| The recorded walkthrough | [`evidence/walkthrough/`](evidence/walkthrough/README.md) |

## 8. Check records against their source yourself

No VM and nothing to install beyond Python 3.10 or later:

```
python3 -I evidence/samples/check_sample.py evidence/samples/R7 --random 20 --seed 1   # 20 records at random
python3 -I evidence/samples/check_sample.py evidence/samples/R7 <UPC> [<UPC> ...]     # the UPCs you choose
```

Each record's exported title, prices and price per measure are printed beside what the product's own tile showed in
the stored page it was read from, with that page's URL, observation time and SHA-256
([`evidence/samples/`](evidence/samples/README.md)). The live site can be compared too, by the record's URL, keeping
in mind that prices change over time.

## 9. Reproduce offline

```
git clone https://github.com/lonadonia/marianos-azure-scraper.git && cd marianos-azure-scraper
git checkout review-1.10.0rc6-20261117
python3 -I manifests/check_source_tree.py                 # source/ is 1.10.0rc6's tree, file for file (one host masked)
cd source && uv sync --frozen
uv run pytest -q tests/unit                               # 506 passed
uv run ruff check . && uv run ruff format --check . && uv run mypy
uv run pytest -q tests/integration/test_validate_export_or20.py tests/integration/test_coupons_route_or04.py \
    tests/integration/test_run_order_rc6.py
uv run pytest -q tests/integration/test_listing_pages.py tests/integration/test_reask_c1.py -k or19
```

The integration suite needs PostgreSQL 16 server binaries on the path and Chromium (`uv run playwright install
--with-deps chromium`); the whole suite took 27 min 44 s on the VM. Each correction's "before" can be reproduced by
reversing its patch ([`evidence/tests/README.md`](evidence/tests/README.md)). Nothing in these commands sends a
request anywhere.

## 10. Kinds of evidence

| Kind | In this delivery |
|---|---|
| Offline tests (synthetic pages, mock transport) | the suites and each correction's before and after ([`evidence/tests/`](evidence/tests/)) |
| Pages stored live, replayed | the OR-19, OR-04 and run-order tests replay byte copies of pages the collector stored on 2026-11-16, labelled as replays, never as live |
| Live, on Hamza's VM (owner VM) | P7, R6, R7 and the pilot P8 on 1.10.0rc6 ([`evidence/runs/`](evidence/runs/)); OR-20's validation of F2 (stored pages, no request) |
| Scheduled observations | **none**: the schedule is not enabled (section 3) |
| Client acceptance | **none**: the client has not reviewed or accepted 1.10.0rc6; nothing ran on the client's VM |

## 11. What remains

One row per open obligation, with its owner, blocker and next action:
[`review/OUTSTANDING.csv`](review/OUTSTANDING.csv); every original requirement with its evidence:
[`review/ACCEPTANCE_MATRIX.csv`](review/ACCEPTANCE_MATRIX.csv) (the earlier columns unchanged, the 1.10.0rc6 columns
added). In short:

| Open item | Owner | What blocks it | Next action |
|---|---|---|---|
| Full coverage (G3) and a protected full-scope publication | Hamza, then the client | R7 cannot complete on 1.10.0rc6 (OR-22, OR-23), and the corrections are on the branch `marianos-1.10-next`, not released; credit: a full run at R7's rate needs USD 6.4680 to 7.6980, USD 2.0490 to 3.2790 more than the USD 4.4200 left; the site's repeated pages (next row) | release the corrected candidate from the branch (build, install, identity check), fund its full run and run it with two lanes; publish it only if every blocking gate passes |
| How often a repeated page may be asked again (two re-asks, at least 300 s apart) | Hamza (the acceptance owner) | the brief keeps the retry limits; in R7, 6 requests had both re-asks answered with the repeated page, leaving 6 listings of the baseline incomplete: Dog Treats 27018, Light Bulbs 26002, Champagne & Sparkling Wine 08180, Hard Seltzers 08183, and Red Wine 08120 and White Wine 08122 through one subdivision each | decide whether such a page may be asked more often (one submission, USD 0.0015, per re-ask), or whether such listings are read again at another time |
| The Coupons route (row 0) read live by 1.10.0rc6 | Hamza | met in R7: read at its first answer (03:01:08Z), its list loaded, 24 cards of the 447 stated | none (each full run reads it again) |
| Coupon terms of the four digital examples | Hamza / the client | 0002310014848 and 0003980014995 rendered with no savings shown (R7, P8); 0001780014939 and 0001780014941 not rendered by the provider in R7 or P8 (unread); R7 kept no record of three of the four (OR-24) | decide a supported rendering path for these product pages, or accept unread terms flagged as such (`DIGITAL_COUPONS_UNOBSERVED`); records of all four in a full run of the corrected candidate |
| The offer and size examples observed live | Hamza | Cutwater and The Finnish Long Drink observed in R7 (one-unit conditions: no volume deal exported; the pack's size); Nutrl and the dip on no page R7 counted | read them in a full run of the corrected candidate |
| The schedule; two weeks of observations (scheduled occurrences, disappearances, stock transitions, retention, a coupon that becomes unavailable and is kept as historical) | Hamza, then time | no protected full-scope publication; credit for every occurrence (one full run of a corrected candidate: USD 6.4680 to 7.6980 at R7's rate) | enable the Monday and Thursday 07:00 America/Chicago schedule after a protected full-scope publication, with credit for every occurrence, then observe for two weeks |
| The client's VM: install, suites, Docker, release, the walkthrough there, acceptance | the client, then Hamza | the client's window and access (outside this authorization) | the client names a window |
| The client's review of the records and sign-off | the client | the client's review | check records against the stored pages they were read from (`evidence/samples/check_sample.py`), then accept or reject |
| Classic, optional providers and stores, support and IP terms | the client | the client's decisions | - |

The operator's commands (start, pause, resume, stop, status, logs, export, publication, rollback) and the acceptance
procedure for the client's VM: [`review/ACCEPTANCE_RUNBOOK.md`](review/ACCEPTANCE_RUNBOOK.md) and
[`source/README.md`](source/README.md).

## 12. Earlier deliveries

The default branch keeps only this delivery. Every earlier one stays complete at its own review tag:
[`EARLIER_DELIVERIES.md`](EARLIER_DELIVERIES.md).
