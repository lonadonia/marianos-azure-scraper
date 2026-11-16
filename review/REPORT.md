# Mariano's collector 1.10.0rc5: technical report (2026-11-16)

Prepared by Hamza. Store: Mariano's Vernon Hills, location 53100502, ZIP 60061, PICKUP. Baseline: the delivery
[`review-1.10.0rc3-20261112`](https://github.com/lonadonia/marianos-azure-scraper/tree/review-1.10.0rc3-20261112)
(commit `e43cce2d7e0e898a2dd13b33d65d528995afd2c5`), whose report is
[`TECHNICAL_REPORT_1.10.0.md`](https://github.com/lonadonia/marianos-azure-scraper/blob/review-1.10.0rc3-20261112/review/TECHNICAL_REPORT_1.10.0.md).
Times are UTC. The entry point, with the answer in brief, the coverage table and the run table, is the
[`README`](../README.md); this report gives the detail behind it.

**NOT FINAL: a checkpoint for the client's review, not an accepted delivery. 1.10.0rc5 is qualified on Hamza's VM and its one logical full run F2 holds 7,678 fresh valid UPCs, but the collector stopped it, not resumable, before the full scope and before validation (STORE_NOT_VERIFIED on a re-asked page whose product data had not loaded: a defect found in this review), so its gates G3, G13 and G14 were never evaluated; the trial credit could not have paid for the rest in any case (94 of the 302 listings of the 1.9 queue complete), so no full-scope run exists to publish; the three defects found in this review, the schedule, the walkthrough on the client's VM, the client's acceptance and the other items under What remains stay open**

## 1. Authority, money and the test host

**Authority.** Hamza's update of 16 November 2026, after speaking with the client: live Mariano's collection with
Hamza's Oxylabs Web API credit, tests on Hamza's Azure VM and scheduling on that VM are authorized. The client's Azure
VM and Oxylabs Classic stay outside it. The update is recorded as an event of the shared trial ledger
(`authorization_update`); the hold entries written earlier keep what was authorized when they were written. Every
stage record names it as its approval.

**Money.** One trial credit of USD 5 shared with the Walmart project, accounted in one ledger (SQLite, a hash chain
over every event), moved to Hamza's VM for these stages. Every submission is reserved in it before it is sent, at
USD 0.0015 (the recorded rate), under a lease that a second process cannot take; a submission whose outcome is not
known (a request in flight when a process stops) stays charged until reconciled; Walmart's envelope is never spent.
Oxylabs documents no balance or usage API for this key: the ledger is the account. Before the first paid request
(03:06Z) Mariano's could spend USD 1.8405; the key on the workstation was the same trial (same fingerprint, masked
…4aef98), so no new allowance was assumed. At the end (2026-11-16T19:12:22.617945Z): chain verified (8692 events); Mariano's committed USD 1.9380 of its USD 2.25 envelope (settled 1.9140, unknown held 0.0240 for 16 submissions), spendable USD 0.3120; Walmart's envelope untouched (spendable USD 0.0030). The stages of this delivery reserved 1,022 submissions (USD 1.5285 with the unknown ones charged) ([`evidence/ledger/`](../evidence/ledger/README.md)).

**The test host.** Hamza's own Azure test VM (Ubuntu 24.04, 2 vCPU, 3.9 GB, PostgreSQL 16, Docker). Before any test
the Walmart deployment was removed from it (brief section 2): inventoried, backed up (files and both databases,
restored into scratch databases with identical row counts, hashed), copied off the VM and checked hash for hash,
then removed by explicit paths only (no wildcard, no Docker prune, the shared PostgreSQL cluster and base images
kept); a private backup that holds a proxy secret stays on the VM, recorded. The Walmart repository and tags were
not touched. Mariano's earlier databases and folders on the VM were kept.

## 2. The candidate

1.10.0rc5 is 1.10.0rc3 and seven commits (README section 1). 1.10.0rc4 changed tests only, made while qualifying on
Linux: a C1 replay that compared gzip bytes made on Windows (header byte 9 is the OS: 10 on Windows, 3 on Linux;
the content is identical), the test browser's sandbox where Ubuntu 24.04 restricts unprivileged user namespaces, and
a scheduled-run test that read the real clock and failed between 19:00 and 24:00 Chicago. Each has its before/after
in [`evidence/tests/1.10.0rc4/fixes/`](../evidence/tests/1.10.0rc4/fixes/). 1.10.0rc4's collector code is
1.10.0rc3's.

**1.10.0rc5: the one collector fix.** Found live: 1.10.0rc4's full run F1 was stopped by the collector after 158
submissions with `STORE_NOT_VERIFIED`. Page 3 of Frozen › Meat Alternatives came back before the site had made its
search: the page's search request held no variables, the page was still loading, stated no total and showed no
product and no card, while its header and state named Vernon Hills 53100502 and PICKUP and every other store check
passed. The check that reads the store out of the page's own search request failed on a request that did not
exist. In 1.10.0rc5 (`collection/oxylabs_live.py`, +27 −5) that one check is "not applicable" when, and only when,
the page has no search filters, is not loaded, states no total and shows no product and no card; the page is then
judged malformed and asked again within the existing retry limits. The tests were committed first (`a1385f8`):
on 1.10.0rc4's code 2 failed (the run stopped with `STORE_NOT_VERIFIED`) and 2 passed (the controls: a page without
its search that shows products, or that sits in another store's context, still stops the run); on 1.10.0rc5 all 4
pass and the whole file passes (33). The case came up again live in F2, on fresh fruit page 1: the page was asked
again, the store attestation of the run stayed PASS, and the run went on.

## 3. Qualification on Hamza's VM

| Check | Result | Evidence |
|---|---|---|
| Source | a clean extraction of the pinned development tree, its Git tree ID checked before anything was installed (`3f456703`) | [`install/build/`](../evidence/install/build/) |
| Suites | unit 494 passed; ruff check and format clean; mypy clean (86 files); C1 cases 28; publication-result cases 6; the whole integration suite 222 passed, none skipped (25 min 46 s); all exit 0 | [`tests/candidate_suites/`](../evidence/tests/candidate_suites/) |
| The fix, before and after | before: 2 failed, 2 passed; after: 4 passed | [`tests/rc5_fix/`](../evidence/tests/rc5_fix/) |
| C1 and the publication result against 1.9.0rc4 | C1: 21 failed and 7 passed on 1.9.0rc4, 28 passed on 1.10.0rc5; publication result: 3 failed and 3 passed, then 6 passed; every row as expected | [`tests/old_new/`](../evidence/tests/old_new/) |
| Install, migrations, backup, restore, rollback | backup of the previous target restored into a scratch database with identical row counts in 26 tables; 1.10.0rc5 installed in its own release folder on its own database, migrated to 0006; rolled back to 1.10.0rc4 and forward again | [`install/INSTALL_BACKUP_RESTORE_ROLLBACK.log`](../evidence/install/INSTALL_BACKUP_RESTORE_ROLLBACK.log) |
| Container | image `sha256:df52af770f1a2509cad91281f6a9dfbe4d58a4998bfb23fd01f9838df2eafcf9` (127,651,436 bytes); `--version` 1.10.0rc5, build record `bc19afe`, `validate-config`, `validate-config --check-db`, `status`: all exit 0; no container left | [`install/container/`](../evidence/install/container/) |

The two-lane `pending_fetches` guard (`test_two_lanes_never_save_a_page_whose_answer_has_not_arrived`), the
long-brand collision and filter tests, restart and exclusivity, and the refused publication's exit 6 with the last
good dataset intact all pass within these suites.

## 4. The live stages, in order

| Stage | Revision | What it was for | Outcome |
|---|---|---|---|
| S6 | 1.10.0rc3 | rows 22 to 27, one lane: does C1 recover later pages live? | 67 submissions; 17 listings: 14 complete, 2 empty, 1 incomplete (Candles: 58 slots, 57 distinct products, one shown at the end of page 2 and the start of page 3); 3 requests set aside, **3 recovered** (72 new products; re-asks at least 304.5 s apart); 1,141 fresh valid products; G13, G14 PASS; G3 FAIL (Candles); a pilot, never published |
| S6b | 1.10.0rc3 | row 10, Natural Organic › Frozen (18010), above the 250-result window | 21 submissions; 281 stated, 250 reachable: read through 12 filter-bound child listings whose union is 281, equal to the stated total; one request set aside and recovered; G1 to G13 PASS, G14 FAIL (one listing: 279 valid, under 500); validated, a pilot |
| L1 | 1.10.0rc4 | rows 22 to 27, one lane, for the comparison of lanes | 73 submissions; 17 listings, all complete (15 with products, 2 empty); 8 set aside, **8 recovered** (192 new products); 1,138 fresh valid products in 6 categories; **G1 to G14 all PASS**; validated, a pilot |
| L2 | 1.10.0rc4 | the same scope, two lanes | 72 submissions; 15 complete, 2 incomplete (Dog Treats page 4, Cat Litter page 2: both re-asks answered with the repeated page again); 9 set aside, 7 recovered, 2 spent; 1,018 fresh valid; G3 FAIL; a pilot |
| P1 to P3 | 1.10.0rc4 | publication, refusal and rollback on an isolated target | P1 published; P2 stopped at its ceiling, finalized as partial, publication refused (exit 6), published state unchanged; P3 published and rolled back to P1 with P1's files restored |
| F1 | 1.10.0rc4 | the full run | stopped by the collector after 158 submissions: `STORE_NOT_VERIFIED` (section 2), exit 7, rejected; the run's collection was held. This is what 1.10.0rc5 fixes |
| F2 | 1.10.0rc5 | **the full run of the final candidate** | section 5 |
| P4 to P6 | 1.10.0rc5 | publication, refusal and rollback on 1.10.0rc5 | section 7 |

Each stage had its own ceiling in the collector (`set-ceiling`) and in the ledger, its own deadline and its own
operator stops (a store mismatch, a site refusal, an abnormal answer, three unread pages in a row, a ledger refusal,
more than two unknown outcomes, ten answered re-asks without a recovery). None of these stops was reached in S6,
S6b, L1, L2 or F2; F1 stopped on the store check.

**C1 live, in sum.** requests set aside and asked again on the live site: 119 in S6, S6b, L1, L2 and F2 together, 85 recovered (a re-ask answered with the page asked for), 15 spent (both re-asks answered with the repeated page again), 19 still waiting when F2 ended; 1,624 new products came from re-asks; the shortest wait between two answers of one request was 303.8 s; S6: 3 set aside, 3 recovered; S6b: 1 set aside, 1 recovered; L1: 8 set aside, 8 recovered; L2: 9 set aside, 7 recovered; F2: 98 set aside, 66 recovered Every request set aside keeps every answer: the request asked, the store and
fulfillment returned, the page and filter returned, the products it showed, how many were new, the source hash and
the time ([`db_deferred_requests.csv`](../evidence/runs/F2d/db_deferred_requests.csv) of each run). Re-asks are
never closer than 300 s to the previous answer of the same request, and at most two are made. A repeated page adds
no product. Form A and form B (answers with and without the page's own filters) stay a diagnostic observation; the
cause is not established.

## 5. The full run F2 (1.10.0rc5)

Run `01M7JNB2HDFCNR3GHQVX8FYXX6`, store `marianos-53100502-pickup`, two lanes, the shipped configuration (every CSV row 0 to 27, every
root, child, brand partition and page, the Coupons route), no command-line narrowing or limit: not a pilot. The
trial credit cannot pay for the whole scope, so the run was read in slices of at most 200 submissions (USD 0.30),
one ledger stage and one collector ceiling per slice. In 1.10.0rc5 a stop at a spending ceiling finalizes the run,
so each slice but the last was ended by the operator with SIGTERM once its stage had 190 reservations (a resumable
stop, exit 75), and the next slice resumed the same run on the same revision. The last slice was planned to run to
its ceiling, where the collector finalizes a run as a partial dataset; the collector stopped the run first (The
stop, below).

| Slice | Stage | UTC | Submissions (settled, unknown) | How it ended | Exit |
|---|---|---|---|---|---|
| F2a | `M-F2a-full-run-110rc5-20261116` | 2026-11-16 17:09:10 to 17:22:58 | 190 (188, 2) | the operator's SIGTERM at 190 reservations; a second start during it refused (exit 9) | 75 |
| F2b | `M-F2b-full-run-110rc5-20261116` | 2026-11-16 17:36:39 to 17:49:48 | 191 (189, 2) | after the VM reboot; one automatic resume after a provider-error pause; SIGTERM at 190 | 75 |
| F2c | `M-F2c-full-run-110rc5-20261116` | 2026-11-16 17:55:58 to 18:09:04 | 190 (187, 3) | hard kill (SIGKILL) under two lanes after 40 pages; resumed after the dead lease expired; SIGTERM at 190 | 75 |
| F2d | `M-F2d-full-run-110rc5-20261116` | 2026-11-16 18:54:32 to 18:56:20 | 24 (22, 2) | the walkthrough: SIGTERM after 6 pages (75), a refused start (9), resumed; the collector then stopped the run, not resumable (7, STORE_NOT_VERIFIED: a defect, OR-19) | 75, 7 |

**Result.** 576 listing answers: 416 completed, 3 failed, 12 reasked, 18 refused, 127 stopped; store checks: FAIL 1, N/A 3, PASS 572 (PASS on every completed page; the FAIL is the stop page, not counted; N/A on answers that failed), locations 53100502, fulfillment PICKUP. Requests set aside: 98 ({"exhausted": 13, "recovered": 66, "waiting": 19}); 111 re-asks answered; 1,204 new products from them. Records: 8,104 retained, 7,678 fresh, 7,678 distinct fresh valid UPCs in 15 categories. Gates: not evaluated: the collector validates a run when the run ends; a run it stops as not resumable is rejected and its records kept as a partial export without validation (as F1's were), so F2's gates were never evaluated. Run status: rejected.

**The stop.** At 18:56:02Z the collector stopped F2, not resumable (`STORE_NOT_VERIFIED`, exit 7). A re-ask of Coffee › Espresso Coffee (0400300007, CSV row 13) page 2 came back rendered with the page's own search for store 53100502, Pickup, page 2 (45 results), 3 product cards drawn and 0 products in its data. 1.10.0rc5's price check fails a page that shows cards without their product data, and a failed store check stops the run. The store was not another one: the page was not counted and nothing from it was exported. A page of the same shape with no card drawn (P6's page 3: the same kind of search, no product data) is not judged by that check, and it was asked again and completed. It is the same family as F1's stop (1.10.0rc4): 1.10.0rc5 asks again a page brought before its search, not this one. The run is rejected, its records kept as a partial export (never published), and the store's collection is held until an operator releases it. The pages as the installed collector reads them: [`STORE_STOP_F2.txt`](../evidence/operations/STORE_STOP_F2.txt).

**The export validation.** F2's export validation did not complete. `validate-export --run` of F2 was killed by the VM's kernel for lack of memory, twice (about 3.3 GiB held, on a VM of 3.8 GiB without swap): it reads every stored listing page of a run into memory at once (F2: 575), so a full run could not be validated there either. The checks that need no stored page passed: the 22-field contract of both export files (8,104 and 7,678 rows, no duplicate UPC or URL). The collector's own check of every record against the stored pages did not complete for F2; sampled records are checked against their tiles in [`evidence/samples/`](../evidence/samples/README.md). The kernel's lines and the contract results: [`VALIDATE_EXPORT_OOM_F2.txt`](../evidence/operations/VALIDATE_EXPORT_OOM_F2.txt). A defect found in this review, open (What remains).

**Coverage.** 94 of the 302 product listings complete (92 with products, 2 empty), 40 incomplete, 165 not read to an end when the collector stopped the run (not reached, or begun and unfinished), 3 not among the listings the run planned from the department pages it read (13013 Sushi (row 4); 18003 Produce (row 10); 19007 Frozen Breakfast (row 12)); the 1.9 baseline was 42 complete By CSV row: README section 4; by listing: the run's
[`coverage_reconciliation.csv`](../evidence/runs/F2d/export/coverage_reconciliation.csv); against the 1.9 queue:
[`evidence/coverage/`](../evidence/coverage/README.md). No listing is called empty or exhausted because of a reached
page limit, a repeated page, a missing filter or an unread page: those stay INCOMPLETE with their reason.

## 6. Accuracy

**Cat Food (27021).** Q2 (2026-11-02) read 232 slots holding 231 products, 0002310014492 shown twice. On 2026-11-16 S6, L1 and L2 each read the listing to its stated total of 234: 10 pages, 234 slots, 234 distinct products, none on two pages, 0002310014492 once (page 7). L1 and L2 met the site's repeated page on it and C1 recovered each. F2 did not read row 22 (F2 ended before row 22: the collector stopped it while it read row 15 (row 22 in F2: 12 listings planned, 0 complete, no page read)).

**Price per measure.** 0084024314377 (12 ct / 2.6 oz, $19.99) displays "$19.99/oz", and the product data its page loaded states 19.99 DOLLAR PER OUNCE: exported as displayed, flagged `PPM_EQUALS_ITEM_PRICE`. 0001280052496 (1 Count, $7.99 from $10.49) displays "$7.99/oz", the product data 7.99 and 10.49 PER OUNCE: exported as displayed, flagged `PPM_UNIT_FAMILY_MISMATCH`. The collector computes no replacement value.

**The four digital examples**, each stated: 0001780014939's coupon 4257015 (complete terms read on 2026-11-06) has expired by its own terms; 0001780014941 and 0003980014995 were never observed rendered; 0002310014848's rendered page of 2026-11-06 showed no Savings section. None of their tiles showed a coupon on 2026-11-16 and no product page was read, so all four export empty digital fields flagged `DIGITAL_COUPONS_UNOBSERVED` (unknown, not absent). In F2: 0 of F2's 8,104 records carry a digital deal from their tile; all leave the digital fields empty with their reason (no tile showed a coupon).

**The offer and size examples** (Cutwater, The Finnish Long Drink, Nutrl, the Avocado Green Goddess Dip): not observed in F2 (none of the four is in its export).

**The Coupons row (a defect found in this review).** The Coupons row is not a listing: its page (`/savings/cl/coupons/`) is read once at the start of every run, rendered, for the same store and fulfillment, and its coupon cards are recorded with the run; it lists offers, not the products they apply to, so no coupon reaches a record from it. On 2026-11-16 it was read once in each of the 12 runs, every time with the store check PASS. In 5 (S6, S6b, L1, P2, P3) the coupon list loaded: 24 cards. In 7 (L2, F1, P1, F2d, P4, P5, P6) it had **not** loaded: the coupons tab holds the site's loading indicator and no card. **The collector recorded all 12 as `READ`, the 7 unloaded ones with 0 coupon cards.** An unloaded list must be recorded as not read, never as zero coupons: that is a defect of the collector's verdict on this page (the same code in 1.10.0rc3, 1.10.0rc4 and 1.10.0rc5), found in this review of the evidence and not corrected in this delivery. F2's own reading is one of the 7: its Coupons row is **not read**. Each reading beside its stored page (SHA-256, cards, the indicator): [`COUPONS_ROUTE_READINGS.txt`](../evidence/accuracy/COUPONS_ROUTE_READINGS.txt), written by [`../tools/coupons_route_check.py`](../evidence/tools/coupons_route_check.py).

Every check, file by file: [`evidence/accuracy/`](../evidence/accuracy/README.md).

## 7. Publication, refusal and rollback (P4 to P6, 1.10.0rc5)

On an isolated target (its own database and data folder; the full run's target was not touched), with the store's
categories set to `[27]` in its configuration, so that a run is not a pilot and is published when it validates:

| Step | What was done | Expected | Observed |
|---|---|---|---|
| P4 | a complete run of row 27 on 1.10.0rc5 (`01M7JRXD9P93HPNBRY3J0BVMSX`), then `publish` | validated, published (exit 0) | validated; publish exit 0 |
| P5 | a run stopped at its 4-submission ceiling (`01M7JSXE192AD3KH2SV0178F4A`), finalized by the collector as partial; then `publish` | refused (exit 6); every published file unchanged | publish exit 6; published state after vs before: EQUAL: every file under published/; exports of the published run; latest.json; pointer; publications; latest.json dataset fields ['publication_id', 'run_id', 'manifest_key', 'manifest_sha256', 'mode'] (result as expected) |
| P6 | a complete run (`01M7JTAC3J8TYR7RV93F2W7PG3`), `publish`, then `rollback-publication` | published (exit 0), then rolled back to P4 (exit 0) with P4's files and dataset fields | publish exit 0; rollback exit 0; after the rollback vs P4 published: EQUAL: exports of the published run; latest.json dataset fields ['publication_id', 'run_id', 'manifest_key', 'manifest_sha256', 'mode']; different: every file under published/; latest.json; pointer; publications (result as expected); the differences are by design: the pointer's and latest.json's version and time (and so latest.json's hash), and P6's own row among the publications |

The same three steps on 1.10.0rc4 (P1 to P3) gave the same results ([`evidence/publication/1.10.0rc4/`](../evidence/publication/1.10.0rc4/)).
On the full run's own target, F2's publication was refused (exit 6, its publication refused with exit 6, nothing published).

## 8. Operations

Every check below ran within the full run F2 on 1.10.0rc5, live; the records named are in [`evidence/operations/`](../evidence/operations/README.md).

| Check | Where | Expected | Observed | Record |
|---|---|---|---|---|
| Pause (a resumable stop) and resume | F2a, F2b, F2c | SIGTERM (`systemctl stop`) ends the execution with exit 75; the run stays interrupted and resumable; the next slice resumes the same run | each slice stopped by the operator's slice stopper at 190 reservations, exit 75 each; F2b, F2c and F2d resumed the same run `01M7JNB2HDFCNR3GHQVX8FYXX6` | `SLICE_STOP_F2a.log`, `SLICE_STOP_F2b.log`, `SLICE_STOP_F2c.log`; each run folder's `harness_runs.jsonl` |
| A second start refused before any paid call | F2a, 17:10:16Z, while the run was active | exit 9 (busy), no request, no reservation | exit 9 in 0.2 s ("has an unfinished run ... resume or finalize it"); the gate refused nothing because nothing was asked; all 190 of F2a's ledger rows belong to the running execution's lease (74): the refused start reserved nothing; again in F2d's walkthrough (exit 9) | `REFUSED_SECOND_START_F2a.log`; `../runs/F2a/ledger_reservations.csv`; `../walkthrough/` |
| A VM restart between slices | between F2a and F2b | services, database, ledger and the run's checkpoints identical before and after; the run resumes | reboot 17:33:01Z, up 17:33:11Z; run, tasks, listing pages, requests set aside, UPCs, segments, locks and ledger identical before and after; F2b resumed the run at 17:36:42Z | `REBOOT_BETWEEN_F2a_AND_F2b.log`, `REBOOT_STATE_BEFORE.txt`, `REBOOT_STATE_AFTER.txt` |
| Automatic resume after a provider-error pause | F2b, 17:38:56Z | after a provider error the run pauses at a checkpoint and resumes by itself after 60 s, at most 3 times a run | Crackers (01026) page 1 answered malformed three times (two in F2a, one in F2b: the page state lists 24 products and the grid shows 0 cards); at the third the run paused (PROVIDER_ERROR) and resumed automatically 60 s later (1 of 3); the fourth answer was read: 266 results, 250 reachable, read through 17 child listings | `AUTO_RESUME_F2b.txt`; `../runs/F2b/db_collection_segments.csv` |
| Hard kill and recovery under two lanes | F2c, 17:54:02Z | after SIGKILL the run is left running with leased tasks and a request in flight; once the dead lease expires, resume recovers the run, reclaims the tasks from their checkpoints, and keeps the request in flight as an unknown outcome charged against the ceiling | killed after 40 pages, with 2 tasks leased and 1 request dispatched; the dead lease (76) expired 17:55:52Z; resumed 17:55:58Z: RUN_RECOVERED, TASK_LEASE_RECLAIMED for both tasks, a new segment; the request became unknown (charged) | `KILL_RECOVER_F2c.log`; `../runs/F2c/` |
| Completed pages are not asked again | the whole run F2, every segment of the four slices | no completed request asked again, apart from C1's deliberate re-asks | 576 listing-page rows, 416 requests completed; 13 deliberate C1 re-asks of completed first pages for their filters (answers {'reasked/new': 12, 'refused/malformed': 1}); **0 re-fetched** | `NO_REFETCH_F2.txt` |
| At most as many requests in flight as lanes | every F2 slice (two lanes); L1 (one lane), L2 (two) | at most 2 with two lanes, 1 with one | peak 2 in every F2 slice and in L2, 1 in L1 | `PEAK_IN_FLIGHT.txt` (from the ledger rows) |
| Unknown outcomes kept and charged | every stop with a request in flight | a request whose outcome is unknown when its process stops stays charged at the worst case until reconciled | held as unknown: F2a 2, F2b 2, F2c 3, F2d 2 (F2c's include the request in flight at the kill) | each run folder's `ledger_reservations.csv`; `../ledger/` |
| A ceiling stop finalizes the run; its publication is refused | P5 (1.10.0rc5, isolated target) | at its ceiling the collector finalizes the run as a partial dataset (exit 4) and `publish` refuses it (exit 6), the published files unchanged | P5 stopped at its 4-submission ceiling (SPENDING_CEILING, exit 4), finalized as partial; publish exit 6; every section of the published state equal before and after | `../publication/` |
| The last slice to its ceiling (planned) | F2d (the walkthrough) | the run goes on to the slice's ceiling, where the collector finalizes it as a partial dataset (exit 4); `publish` refuses it (exit 6) | **not met**: F2d's executions ended with exit codes 75, 7: after the SIGTERM stop and the refused start, the collector stopped the run, not resumable, at 18:56:02Z (STORE_NOT_VERIFIED, the defect OR-19), 8 submissions into the resume; its publication refused with exit 6, nothing published | `STORE_STOP_F2.txt`, `../walkthrough/`, `../runs/F2d/` |

**One lane against two** (L1 and L2, 1.10.0rc4, the same scope): same scope (rows 22 to 27), 1.10.0rc4: one lane 73 submissions, 575.1 s with a request in flight, wall 1140 s; two lanes 72 submissions, 390.8 s in flight, wall 1166 s: both end on the 300 s re-ask waits, so the wall time does not shrink on this small scope while the time spent asking falls by 32%. On this scope both runs end on C1's waits (a request set aside is asked again at least 300 s after its previous answer), so the wall time is about the same; the time spent with a request in flight falls from 575.1 s to 390.8 s with two lanes, and the gate never let more requests fly than the stage's lanes. L2 left two listings incomplete where L1 completed them: their re-asks were answered with the repeated page again, an answer of the site, not of the lane count. The full run F2 ran with two lanes throughout (its slices' measures are in the estimate).

## 9. Cost, the full-cycle estimate and the schedule

**Cost.** 1,022 submissions over the stages of this delivery (USD 1.5285 at the recorded rate, unknown outcomes charged); F2 alone 595 (USD 0.8880). Walmart's envelope untouched; no top-up, no overage. Per stage, with its ceiling and its unknown outcomes: README section 5; the ledger's own account: [`evidence/ledger/`](../evidence/ledger/README.md).

**The full-cycle estimate, updated with F2.** one full run: 4,321 to 6,906 submissions (USD 6.48 to 10.36), from the historical 3,019 to 4,826 listing pages with F2's measured 1.43 submissions per completed page (re-asks, malformed answers and repeats included) instead of 1.3; 5.0 to 8.1 hours a run at F2's two-lane pace (6.0 s of execution per completed page). Shortfall: 3,726 to 6,311 more submissions (USD 5.59 to 9.47) to complete one run beyond F2, against Mariano's remaining trial credit of USD 0.3120. Inputs, formulas and caveats: [`evidence/estimate/`](../evidence/estimate/README.md).

**Schedule.** The approved Monday and Thursday 07:00 America/Chicago schedule may be enabled on Hamza's VM only after
a protected full-scope publication with enough verified credit. Neither exists: the schedule is **not enabled**, and
no scheduled occurrence was observed. The two weeks of observations (genuine disappearances, stock transitions)
therefore have not started; nothing was simulated in their place. The one-shot schedule path stays proven offline
(synthetic tests within the integration suite).

## 10. The shared Classic probe

Unchanged from 1.10.0rc3: Mariano's pins the shared probe 1.7.3, live Classic is disabled, and no Classic request
was sent for this delivery (none is authorized). As Darren asked, the reference for Walmart's corrected probe
1.7.4 is pinned here, without adopting it: source
[`classic-probe-1.7.4/`](https://github.com/lonadonia/walmart-azure-scraper/tree/review-1.6.8-probe174-20261111/classic-probe-1.7.4)
at Walmart's tag `review-1.6.8-probe174-20261111` (commit `00a18947668feb7d54bf5c019654d89bf0ad56a0`), and its
Windows regression (failing on 1.7.2, passing on 1.7.4)
[`evidence/offline-tests/1.7.4-classic-probe/`](https://github.com/lonadonia/walmart-azure-scraper/tree/review-1.6.8-probe174-20261111/evidence/offline-tests/1.7.4-classic-probe).
The probe 1.7.3 itself stays complete at `review-1.10.0rc3-20261112` (`classic-probe-1.7.3/`).

## 11. Corrections

Statements of the 1.10.0rc3 delivery (tag `review-1.10.0rc3-20261112`) that this one corrects or makes exact; the earlier files stay unchanged at their tag.

- "Tiles show no coupon since 2026-11-06" (`AUDIT_29_RECONCILIATION.csv` G4, `ACCEPTANCE_MATRIX.csv` M26) said more than was observed. What was observed: none of the four examples' tiles showed a coupon on 2026-11-06, 2026-11-09 or 2026-11-16; in F2: 0 of F2's 8,104 records carry a digital deal from their tile; all leave the digital fields empty with their reason (no tile showed a coupon). A tile can show a coupon (Q2's card did on 2026-11-02).
- The Coupons row: 1.10.0rc3 required that a page whose list did not load be recorded as not read, never as zero coupons (`OUTSTANDING_REQUIREMENTS_1.10.0.csv` OR-04). The collector does not do this, in 1.10.0rc3 as in 1.10.0rc5 (the same code): it records such a page as `READ` with 0 coupon cards (section 6). Found in this review; open, not corrected in this delivery.
- 1.10.0rc4's full run F1 was stopped by a defect of the collector (`STORE_NOT_VERIFIED` on a page brought before its search was made), not by another store: corrected in 1.10.0rc5 for that page (section 2). The correction was narrower than the defect: 1.10.0rc5's full run F2 was stopped by the same verdict on a page whose search had been made but whose product data had not loaded (section 5, OR-19). Found in this delivery; open.
- The operator's check that no completed page is asked again (`no_refetch.py`) first counted one of C1's deliberate re-asks as a re-fetch (F2c, Natural Organic 18012 page 1). Its rule now takes a later answer as deliberate only when a set-aside request names that answer among its own re-asks; the first rule's output is kept beside the corrected one ([`evidence/operations/`](../evidence/operations/README.md)).

## 12. What remains

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

[`OUTSTANDING.csv`](OUTSTANDING.csv) gives each open item's matrix rows, audit group, blocker, the exact evidence that
would close it and the next action; [`ACCEPTANCE_MATRIX.csv`](ACCEPTANCE_MATRIX.csv) and
[`AUDIT_29_RECONCILIATION.csv`](AUDIT_29_RECONCILIATION.csv) carry the 1.10.0rc5 columns beside the unchanged earlier
ones.

## 13. Reproduce

Offline: README section 8 and [`evidence/tests/README.md`](../evidence/tests/README.md). Records against their source:
README section 7. The live stages cannot be re-run from here without the provider and the trial credit; their
complete records are in [`evidence/runs/`](../evidence/runs/).
