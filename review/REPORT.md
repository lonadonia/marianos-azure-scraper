# Mariano's collector 1.10.0rc6: technical report (2026-11-17)

Prepared by Hamza. Store: Mariano's Vernon Hills, location 53100502, ZIP 60061, PICKUP. Previous delivery:
[`review-1.10.0rc5-20261116`](https://github.com/lonadonia/marianos-azure-scraper/tree/review-1.10.0rc5-20261116)
(commit `76e72ab`), whose report is that tag's `review/REPORT.md`; the 1.9 baseline queue of 302 listings is that of
[`review-1.10.0rc3-20261112`](https://github.com/lonadonia/marianos-azure-scraper/tree/review-1.10.0rc3-20261112).
Times are UTC. The entry point, with the answer in brief, the coverage table and the run table, is the
[`README`](../README.md); this report gives the detail behind it.

**NOT FINAL: a checkpoint for the client's review, not an accepted delivery. 1.10.0rc6 corrects the three defects found in 1.10.0rc5's review (OR-19, OR-20, OR-04), each with tests committed before the fix that fail before it and pass after, and is qualified on Hamza's VM; its full run R7 (01M7KQ5GZVF5VK1S9FGTG6YFC9) holds 2,518 distinct fresh valid UPCs in 8 categories but cannot complete on 1.10.0rc6: a listing the site links with a malformed address stopped six of its ten executions, each about 5 minutes in, and stops every resume (OR-22, OR-23), so R7 was not resumed after its fifth slice, with USD 4.4200 of the credit left. It stays interrupted and resumable; its gates, evaluated on an isolated copy finalized offline, give G3, G4 FAIL (coverage, and yield: the 19 categories R7 did not reach have no record) and G13 PASS, G14 PASS. The four defects R7 found (OR-21 to OR-24, among them two counted pages whose records the two lanes lost) are corrected on the branch marianos-1.10-next with tests that fail before and pass after, not released. No full-scope run exists to publish; the schedule, the two-week observation, the client's VM, the client's acceptance and the other items under What remains stay open**

## 1. Authority, money and the test host

**Authority.** Hamza's brief of 16 November 2026 (the closeout after 1.10.0rc5): USD 5 of free credit authorized
for Mariano's on the Oxylabs Web API credential he supplied, on his own infrastructure; no top-up, no paid overage,
no Oxylabs Classic, no other provider, not the client's VM, no client billing. It is written into the ledger's own
record (`authority` in [`evidence/ledger/META.csv`](../evidence/ledger/META.csv)) and every stage record names it
as its approval. His update of the same day, after speaking with the client, authorizes live Mariano's collection
with his credit, tests on his VM and scheduling on it.

**Money.** The supplied credential's fingerprint (masked `…022e50`) differs from the earlier trial key's (`…4aef98`);
whether it is a new account or credit on the earlier one cannot be read through the API. Per the brief it got its
own ledger, `oxylabs-marianos-20261116`, created at 22:14:48Z on 16 November: cap USD 5.00, USD 0.10 of headroom,
one envelope of **USD 4.90 for Mariano's**. Every submission is reserved in it before it is sent, at USD 0.0015 (the
provider's highest non-AI list price, read 2026-11-03; a list price, not a confirmed account rate), under a lease
that a second process cannot take; a submission whose outcome is unknown (in flight when a process stops) stays
charged until reconciled. The earlier campaign's Mariano's balance (USD 0.312) was not carried over, Walmart has no
envelope in it, and the provider documents no balance or usage API for this key: the ledger is the account. A
first initialization (22:08Z, USD 0.50 of headroom) was replaced before any reservation, as its record says.
At the end (R7c): 349 reservations, USD 0.4665 settled and USD 0.0135 held for 9 unknown outcome(s), USD 0.4800 committed of the USD 4.90 envelope, USD 4.4200 left; chain verified (1,087 events); active lease: none ([`evidence/ledger/`](../evidence/ledger/README.md)).

**The test host.** Hamza's own Azure test VM (Ubuntu 24.04, 2 vCPU, 3.8 GiB of RAM, PostgreSQL 16, Docker 29.1.3), the same
one as for 1.10.0rc5, and **the same target**: database and data folder of 1.10.0rc5, where F2 stopped and the
store was held; the hold was released for the new run only once 1.10.0rc6 was installed there and its identity
verified (section 3). The Walmart deployment had been removed from this VM before 1.10.0rc5's tests (recorded in
that delivery); nothing of Walmart's was touched for this one. The client's VM was not touched.

## 2. The candidate

1.10.0rc6 is 1.10.0rc5 (`bc19afe`) and twelve commits; each correction's tests were committed before its fix
(README section 2 gives each one's before and after; [`evidence/tests/`](../evidence/tests/README.md) the logs).

- **OR-19** (`39278be`: `collection/oxylabs_live.py`, `collection/pagination.py`). F2 was stopped not resumable
  (`STORE_NOT_VERIFIED`) by a re-ask of Coffee › Espresso Coffee page 2 that came back rendered with the page's own
  search made for store 53100502, Pickup, page 2, three cards drawn and no product in its data. A page whose search
  was made for the store but whose product data has not loaded now counts nothing and is asked again within the
  re-ask limit, keeping its original reason; a page of another store, another fulfillment or without store proof
  still stops the run.
- **OR-20** (`62af220`: `checks/source_check.py`, `operations.py`). `validate-export --run` held all of F2's 575
  stored pages in memory and was killed on the VM. It now reads each stored page once, before the next, and checks
  every record's capture and values against it; a page missing or altered after the run rejects the export.
- **OR-04** (`5f29c0d`: the collector's Coupons route, its parser, the reconciliation, the gate and the export).
  The Coupons route was recorded as read when its list had not loaded. It is now read only when its list has loaded
  (asked again while the site's loading indicator holds it), its verdict holds through the run and across a restart,
  and an unread Coupons route keeps the run from complete scope (G3); a product page still loading leaves its coupon
  unread, never "no coupon".
- **Run order and named product pages** (`b75201b`, `88e12e0`, `d77f306`: `cli.py`, `collection/config.py`,
  `collection/control.py`, `collection/oxylabs_live.py`, `db/queue.py`). Found in F2's traces: a listing's
  subdivisions waited behind the whole plan, and every product page was one more request. Subdivisions are now read
  right after their listing; `--rows-first` reads named rows first without changing the plan; `--term-upc` names
  the product pages to read, and only those are read. The full suite on `88e12e0` found an order regression (a
  cancellation test and a brand resumed after a kill), fixed by `d77f306`.

## 3. Qualification on Hamza's VM

| Check | Result | Evidence |
|---|---|---|
| Source | a clean extraction of the pinned development tree (`d77f306`, tree `b6b5f1d3`), its tree ID checked on the VM before anything ran | [`tests/vm_suites_d77f306/`](../evidence/tests/vm_suites_d77f306/) |
| Suites | unit 506 passed; `ruff check` clean, `ruff format` 188 files formatted; mypy clean (86 files); C1 cases 30; publication cases 6; the whole integration suite 247 passed, none skipped (27 min 44 s); every step exit 0 (22:39Z to 23:08Z) | [`tests/vm_suites_d77f306/SUITES.jsonl`](../evidence/tests/vm_suites_d77f306/SUITES.jsonl) |
| Each correction before and after | OR-19 5 failed → 8 passed; OR-20 3 failed (unit 2) → 4 passed (unit 2); OR-04 12 failed → 13 passed; run order 6 failed (unit 2) → 6 passed (unit 2); order regression on `88e12e0` 4 failed → 28 passed | [`tests/before_after/`](../evidence/tests/before_after/) |
| Install on the same target | backup of the target (dump SHA-256 recorded), restored into a scratch database with identical row counts in 26 tables; 1.10.0rc6 installed, `current` moved to it; migrations 0006 → 0006 (none added); `sync-config`, `validate-config`, `status` exit 0; rolled back to 1.10.0rc5 and forward again (23:09:35Z to 23:10:03Z) | [`install/vm_install_rc6.log`](../evidence/install/vm_install_rc6.log) |
| Identity | `current` is the 1.10.0rc6 release, its environment names commit `d77f3065c757…`; 93 of 93 files of the candidate's package identical to the installed ones, no other file installed (23:26:14Z) | [`install/identity_rc6.log`](../evidence/install/identity_rc6.log) |
| Container | image `sha256:92332ded100a78f325f45a05f10fa86e27bc1006a9be4ee27eb243e7b831c874` (127,661,412 bytes), build record `d77f306`; `--version` 1.10.0rc6, `validate-config`, `validate-config --check-db`, `status`: all exit 0; no container left | [`install/container_d77f306/`](../evidence/install/container_d77f306/) |
| OR-20 on F2 itself | `validate-export --run` of F2 by the installed 1.10.0rc6: exit 0 in 41.3 s, peak memory 330 MiB, 575 pages, 8,104 records, no silent mismatch, 142 recorded differences explained one by one | [`validation/`](../evidence/validation/README.md) |

## 4. The live stages, in order

| Stage | Revision | What it was for | Outcome |
|---|---|---|---|
| P7 | 1.10.0rc6 | a one-lane pilot of 1.10.0rc6 (rows 0 and 27: the Coupons route and the cat food row's listings), never a complete catalogue, never published | rejected; gates FAIL: G3, G14; 46 fresh valid |
| R6a | 1.10.0rc6 | the first slice of the full run R6 (every row, rows 22, 27, 23 to 26 and 15 first, the four product pages named), stopped at its ceiling at the site's busiest repeat hour | interrupted |
| R6 (finalized) | 1.10.0rc6 | R6 finalized without a request: validated and exported as an incomplete run, so R7 starts on its own | rejected; gates FAIL: G3, G4, G14; 448 fresh valid |
| R7a | 1.10.0rc6 | the full run R7's first slice (two lanes; rows 22, 27, 23 to 26 and 15 first; the four product pages named), from 03:00Z | interrupted |
| R7a2 | 1.10.0rc6 | R7's second slice: a resume from 04:00Z (the watcher's repeat rule had stopped R7a) | interrupted |
| P8 | 1.10.0rc6 | a one-lane pilot of 1.10.0rc6 on an isolated target of its own (R7 left resumable on its target), from 04:20Z: Dog Food 27017 and Hardware 33, to read again the three named product pages R7 had got unrendered; validated as a pilot, never published | validated |
| R7b | 1.10.0rc6 | R7's third slice, from 04:35Z: a hard kill (SIGKILL) of the worker after 15 collected pages, then the recovery of the same run in the same stage (R7b2, once the dead lease expired), until the repeat rule stopped it | interrupted |
| R7w | 1.10.0rc6 | R7's fourth slice, from 05:05Z: the recorded walkthrough, the operator's controls on the live run (a SIGTERM stop, a refused second start, a resume, a refused publication) | interrupted |
| R7c | 1.10.0rc6 | R7's fifth and last slice, from 05:22Z, capped at 150 submissions: two executions (the second a resume in the same stage), each stopped about 5 minutes in when Hard Cider 08194 failed again (OR-22, OR-23); no further resume once the stage's repeat share (8 of 18 page-2+ answers) was above the rule | interrupted |
| R7fin_copy | 1.10.0rc6 | R7's state at the end of R7c, finalized in an isolated copy of the target with no provider request (checks, gates, exports; its publication refused); R7 itself left interrupted and resumable on the target | rejected; gates FAIL: G3, G4; 2,518 fresh valid |

Each stage had its own ceiling in the collector (`set-ceiling`) and in the ledger, within the room left in the
envelope (the ledger refuses a stage above it; R7's slices were fitted to it before each was opened), its own
deadline and the operator's stops: a store mismatch, a site
refusal, more than two unknown outcomes, ten answered re-asks without a recovery, and (new for this delivery) a
share of repeated pages at or above 25 % once a slice has 16 answers to a page 2 or later.

## 5. The full run R7

R7 (run `01M7KQ5GZVF5VK1S9FGTG6YFC9`) is one logical run of 1.10.0rc6 (`d77f306`) over the client's whole list, rows 0 to 27, for 53100502 PICKUP, with two lanes. `--rows-first 22,27,23,24,25,26,15` read the rows the review depends on first, and `--term-upc` named the four product pages of the review; neither narrows the scope, so R7 is not a pilot. It ran in five slices on 2026-11-17, each a ledger stage of its own with its ceiling in the collector and in the ledger:

| Slice | UTC | Limit | Ended | Submissions (settled, unknown) | USD |
|---|---|---|---|---|---|
| R7a | 2026-11-17 03:00 to 03:04 | 160 subs | exit 75 | 46 (44, 2) | 0.0690 |
| R7a2 | 2026-11-17 04:00 to 04:14 | 160 subs | exit 75 | 76 (74, 2) | 0.1050 |
| R7b | 2026-11-17 04:35 to 04:55 | 610 subs | killed (SIGKILL), then exit 75 | 60 (57, 3) | 0.0780 |
| R7w | 2026-11-17 05:05 to 05:15 | 110 subs | exit 75, 75 | 35 (35, 0) | 0.0435 |
| R7c | 2026-11-17 05:22 to 05:35 | 150 subs | exit 75, 75 | 39 (39, 0) | 0.0495 |

R7a was stopped at 03:04:55Z by the watcher's repeat rule (7 of 16 answers to a page 2 or later repeated page 1) and resumed from 04:00Z as R7a2, which the same rule stopped at 04:14:04Z. In R7b the worker was killed (SIGKILL) at 04:38:48Z and the run recovered in the same stage at 04:40:26Z, once the dead lease had expired; two automatic resumes followed provider stops, and the repeat rule ended the slice at 04:55:09Z. R7w is the recorded walkthrough; R7c, capped at 150 submissions, ran two executions.

**Why R7 ended incomplete.** The site's menu links Hard Cider 08194 as `/pl/hard-cider08194`, an address the site does not serve. 1.10.0rc6 asks it as linked, the provider brings no page, and the run stops on the provider error (OR-22); every resume asks the same page again, so six of R7's ten executions stopped about 5 minutes after their start (OR-23). R7 cannot complete on 1.10.0rc6, and it was not resumed after R7c, with USD 4.4200 of the envelope left: its rest at R7's rate would cost 4,056 to 4,876 submissions (USD 6.0840 to 7.3140) and still could not end complete. R7 stays interrupted and resumable on its target. Its state at the end of R7c was finalized in an isolated copy of the target (its database restored into one of its own, no provider credential, no request): exports, checks and gates, then its publication, refused (exit 6).

**What R7 holds.** 2,518 distinct fresh valid UPCs in 8 categories, read by R7 itself (149 fresh records not valid; 7,869 records carried from earlier runs, exported with their own status and never counted as fresh; 10,536 in all). Gates on the copy: G1 PASS, G2 PASS, G3 FAIL, G4 FAIL, G5 PASS, G6 PASS, G7 PASS, G8 PASS, G9 PASS, G10 PASS, G11 PASS, G12 PASS, G13 PASS, G14 PASS; status **rejected**. Listing pages: 216 answers (failed 10, malformed 22, new 131, partial_overlap 1, repeated 52), 132 counted; requests set aside for a re-ask: 35 (exhausted 6, recovered 23, waiting 6). Nodes of the plan: DONE 29, EMPTY 2, INCOMPLETE 9, NOT_COLLECTED 270. Against the 302 listings of the 1.9 baseline: 21 complete (19 with products, 2 empty), 2 read to their last page but short in records (below), 6 incomplete and 273 not collected; CSV rows COMPLETE 5, INCOMPLETE 23 ([`../evidence/coverage/`](../evidence/coverage/README.md)).

**Four defects R7 found, corrected on a branch.** Each has tests committed before its fix that fail on 1.10.0rc6 and pass after, on the branch `marianos-1.10-next` (not released, not run live: [`../evidence/tests/`](../evidence/tests/README.md)):

- OR-21: a termination signal left the lanes running while the stop closed the provider session; only the lease check kept their late writes from failing tasks.
- OR-22: Hard Cider 08194, linked as `/pl/hard-cider08194`, is asked as `/pl/hard-cider/08194`.
- OR-23: a page the provider never brings stopped the run at every resume; once its attempts are spent after a resume, its listing now stays incomplete with the reason and the run goes on.
- OR-24: with two lanes, a page whose named product pages were being read kept none of its products although it counted as read: R7 kept no product of Dog Food 27017's page 7 (24, among them the named 0001780014939 and 0001780014941) and none of 20 products of Cat Treats 27022's page 2 (among them the named 0002310014848). The coverage file states both listings DONE; G3 counts them incomplete (coverage 0.893 and 0.615). No other counted page of R7 lost a product.

The next full run needs a candidate released from that branch; at R7's rate it costs 4,312 to 5,132 submissions, USD 6.4680 to 7.6980, about USD 2.0490 to 3.2790 more than is left (section 9).

## 6. Accuracy

Every check reads R7's own stored pages, offline ([`../evidence/accuracy/`](../evidence/accuracy/README.md), [`../evidence/samples/`](../evidence/samples/README.md), [`../evidence/validation/`](../evidence/validation/README.md)).

- **The export against its source.** `validate-export --run` on R7's copy: exit 0 in 48.1 s, 10,288 of the 10,536 exported records verified against the stored page and product data they were read from, 0 silent mismatches; the other 248 carry their difference in their own record (234 recorded price conflicts, 14 with the store not stated). Two draws of 20 records by `check_sample.py` (seed 1), one of R7's own records and one of every exported record: 0 differences each.
- **Cat Food 27021**: complete in R7, 234 distinct products of the 234 stated in 10 counted pages, none on two pages, 0002310014492 once (page 7).
- **Price per measure**: 0084024314377 ($19.99/oz, Cat Food page 10, 04:54:57Z) and 0001280052496 ($7.99/oz, Hardware Home Improvement 33 page 3, 04:02:02Z) exported exactly as their tiles display them, each traced to its stored page, whose hash matches the provenance.
- **The four product pages**: 0002310014848 rendered with no Savings section (03:02:58Z); 0003980014995 unrendered in R7, then rendered in the pilot P8 with no savings shown (04:21:54Z, its first rendered read); 0001780014939 and 0001780014941 not rendered in R7 or P8 (unread, nothing learnt). No page showed a coupon. R7 kept no record of 0002310014848, 0001780014939 or 0001780014941 (OR-24, below); P8, with one lane, exported the Dog Food pair, valid and flagged `DIGITAL_COUPONS_UNOBSERVED`.
- **Offers and size**: Cutwater 0081675102373 and The Finnish Long Drink 0086001079386 fresh and valid in R7 (Ready to Drink Cocktails 08193, page 1, 05:26:07Z): "Buy 1 Save" is a one-unit condition, so no volume deal is exported, and the weight is the pack's. Nutrl 0001820020352 and the dip 0073679800140 are on no page R7 counted.
- **The Coupons route** (row 0): read at its first answer (03:01:08Z), its list loaded, 24 cards drawn of the 447 the page states.
- **OR-24**: with two lanes, R7 lost the records of two counted pages (Dog Food 27017 page 7, 24 products; Cat Treats 27022 page 2, 20 products in no record of the run); every other counted page's products are in its export. Corrected on the branch `marianos-1.10-next` (tests failing before, passing after), not released.

## 7. Publication

The collector publishes a run only when it has ended complete and its blocking gates pass, and it publishes atomically; the code that does it is that of 1.10.0rc5 (unchanged in 1.10.0rc6), and what changed is what feeds the gates: G3 now fails a run whose plan names the Coupons route without reading it (OR-04). R7, incomplete, was refused on its copy finalized offline (2026-11-17T05:48:38Z) and on its own run target (05:59:31Z): exit 6 each, "a partial dataset: only complete runs are published"; the target holds no publication, and the state read after the refusal equals the one read before it (no pointer, no publication, no `published/` folder). Beside a published dataset, on a copy of 1.10.0rc5's isolated publication target made on 2026-11-17 at 02:54Z, 1.10.0rc6 refused P5's partial dataset (exit 6) and every published file, the pointer, the publications and `latest.json` stayed equal, with no request sent. The publication, the refusal and the rollback shown live on 1.10.0rc5 (P4, P5, P6) are carried evidence of the same code, not runs of 1.10.0rc6 ([`../evidence/publication/`](../evidence/publication/README.md)).

## 8. Operations

The operator's controls on 1.10.0rc6, all live on Hamza's VM through the credit's own ledger ([`../evidence/operations/`](../evidence/operations/README.md)): the store's hold from F2 released before the first run, its earlier reason kept in the record (2026-11-16T23:20:16Z, exit 0); a second start for the store refused while R6a's execution held it (exit 9 in 0.5 s, no request, no reservation, no lease); a scheduled firing with the schedule off (exit 0, `SCHEDULE_OFF`, nothing reserved); and R7a stopped resumably by SIGTERM when the watcher's repeat rule fired (exit 75, 2026-11-17T03:04:55Z). R7 was resumed nine times, each resume continuing the same run from its checkpoints: by the operator (R7a2 from 04:00Z, R7b at 04:35:21Z, in R7w at 05:05:39Z and 05:11:10Z, in R7c at 05:22:28Z and 05:30:05Z), by the collector itself after a provider stop (04:46:53Z, 04:54:23Z), and once as the recovery after a hard kill. In R7b the worker was killed with SIGKILL at 04:38:48Z while both lanes were working, after 15 pages in the slice: the run stayed `running` with its segment open; the recovery waited for the dead execution's ledger lease to expire (04:40:21Z), then resumed the same run in the same stage at 04:40:26Z, recording the killed segment as `abandoned` and holding its one submission in flight as an unknown outcome, charged against the ceiling. Six executions ended about 5 minutes in, when Hard Cider 08194 failed again (OR-22, OR-23: a resumable stop, exit 75). The walkthrough R7w recorded a SIGTERM stop (exit 75), a refused second start (exit 9 in 0.2 s, no submission attempted) and a refused publication of the unfinished run (exit 6) ([`../evidence/walkthrough/`](../evidence/walkthrough/README.md)).

Over R7's ten executions no completed page was asked again (`NO_REFETCH_R7.txt`: 216 listing-page rows, 132 completed, no request with a row after its completed one), and at most 2 requests were in flight at once in every slice (two lanes under one ledger lease: `PEAK_IN_FLIGHT.txt`). At a SIGTERM, 1.10.0rc6 does not cancel the lanes before the provider session closes; only the lease check kept their late writes from failing tasks (OR-21, corrected on the branch `marianos-1.10-next`). What the watcher's repeat rule measured is in the same folder, by hour.

## 9. Cost, the estimate and the schedule

**Cost.** Every live stage of 1.10.0rc6 together: 349 submissions, USD 0.4800 committed at the reservation rate (USD 0.0015 a submission): USD 0.4665 settled and USD 0.0135 held for 9 unknown outcomes, charged at the worst case until reconciled; USD 4.4200 of the USD 4.90 envelope left; the ledger's hash chain verified (1,087 events), no lease active ([`../evidence/ledger/`](../evidence/ledger/README.md)). R7: 256 submissions over five slices (USD 0.3345 settled, 7 unknown outcomes held), 1.939 submissions and 24.4 s of execution a counted page with two lanes, against F2's 1.43 and 6.02 s: the difference is the site's repeated pages (31% to 50% of R7's answers to a page 2 or later) and the waits before their re-asks.

**The estimate.** A full run reads 2,223 to 2,646 listing pages (the offline estimate). At R7's rate the rest of R7 would need 4,056 to 4,876 submissions (USD 6.0840 to 7.3140), but R7 cannot complete on 1.10.0rc6 (OR-22, OR-23); the next full run is that of a corrected candidate, from its first page: 4,312 to 5,132 submissions, USD 6.4680 to 7.6980, 15.1 to 18.0 hours of execution with two lanes, short by USD 2.0490 to 3.2790 of what is left ([`../evidence/estimate/`](../evidence/estimate/README.md)). These are the rates of R7's hours, not a bound.

**Schedule.** The approved Monday and Thursday 07:00 America/Chicago schedule may be enabled on Hamza's VM only after
a protected full-scope publication with enough verified credit. It was not enabled: R7 was not published (incomplete: G3, G4 fail on its copy finalized offline), and the USD 4.4200 left after it is short of one full run of a corrected candidate at R7's rate (4,312 to 5,132 submissions, USD 6.4680 to 7.6980), while the schedule fires twice a week. What was checked on the VM, with no request: the installed release ships the schedule off, and a firing with it off exits 0 with `SCHEDULE_OFF` and reserves nothing (the ledger's 9 reservations before and after); systemd's calendar for Monday and Thursday 07:00 America/Chicago gives 13:00Z through the winter and 12:00Z from Monday 15 March 2027, after the change to daylight time on 14 March (40 firings listed; [`../evidence/operations/schedule/`](../evidence/operations/schedule/)). The two weeks of observations
(genuine disappearances, stock transitions) therefore have not started, and nothing was simulated in their place.
Offline, the schedule's handling stays tested as in the earlier deliveries: the next run's time across daylight
saving and a cron expression covering standard and daylight time (unit tests); a scheduled occurrence that closes an
unfinished run and reads its backlog first, and a daily budget counted in the provider's own units (integration
tests). The one-shot start is the shipped deployment's (`deploy/vm/marianos --at`, a transient systemd timer). The
publication prerequisite is the operator's rule, not something the collector enforces; nothing was scheduled on the
VM.

## 10. The shared Classic probe

Unchanged since 1.10.0rc3: Mariano's pins the shared probe 1.7.3, live Classic is disabled, and no Classic request
was sent for this delivery (none is authorized). The reference for Walmart's corrected probe 1.7.4 stays pinned, not
adopted: [`classic-probe-1.7.4/`](https://github.com/lonadonia/walmart-azure-scraper/tree/review-1.6.8-probe174-20261111/classic-probe-1.7.4)
at Walmart's tag `review-1.6.8-probe174-20261111` (commit `00a18947668feb7d54bf5c019654d89bf0ad56a0`).

## 11. Corrections

Statements of the 1.10.0rc5 delivery (tag `review-1.10.0rc5-20261116`) that this one corrects or makes exact; the
earlier files stay unchanged at their tag.

- **Three listings were not "unplanned".** 1.10.0rc5's coverage against the 1.9 baseline (its README's G3 and
  coverage lines, `evidence/coverage/README.md`, `review/OUTSTANDING.csv` OR-01 and `review/ACCEPTANCE_MATRIX.csv`
  M09 and B28) counted 13013 Sushi (row 4), 18003 Produce (row 10) and 19007 Frozen
  Breakfast (row 12) as `NOT_PLANNED`, "not among the listings F2 planned from the department pages it read". Each
  was in F2's plan, under the earlier row whose subcategory is the same page: 13013 under row 3 (Seafood), 18003
  under row 1 (Produce), 19007 under row 9 (Frozen). The plan reads a page once and records the later row's entry
  as skipped, "same page as an earlier subcategory" (`config_snapshot.plan.skipped` in F2's `manifest.json`, at the
  1.10.0rc5 tag). F2 read 13013 to its end (54 of 54 products, 3 pages) and 19007 (195 of 195, 9 pages), and left
  18003 incomplete (127 of 128, 6 pages). Against the 302 baseline listings, F2 is therefore **96 complete (94 with
  products, 2 empty), 41 incomplete, 165 not read to an end and none unplanned**; 1.10.0rc5 said 94, 40, 165 and 3.
  [`evidence/coverage/QUEUE_190_VS_F2.csv`](../evidence/coverage/QUEUE_190_VS_F2.csv) is this delivery's comparison
  tool run on F2's published coverage file (byte-identical to the one at the 1.10.0rc5 tag), with the row each entry
  was read under (`matched_row_F2`). A product of such a page is one record, as the 22 fields require, with the
  earlier row's category; this delivery's coverage table names the row each shared page is read under.

## 12. What remains

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

[`OUTSTANDING.csv`](OUTSTANDING.csv) gives each open item's matrix rows, audit group, blocker, the exact evidence that
would close it and the next action; [`ACCEPTANCE_MATRIX.csv`](ACCEPTANCE_MATRIX.csv) and
[`AUDIT_29_RECONCILIATION.csv`](AUDIT_29_RECONCILIATION.csv) carry the 1.10.0rc6 columns beside the unchanged earlier
ones.

## 13. Reproduce

Offline: README section 9 and [`evidence/tests/README.md`](../evidence/tests/README.md). Records against their source:
README section 8 and [`evidence/samples/`](../evidence/samples/README.md). The ledger's hash chain:
[`evidence/ledger/README.md`](../evidence/ledger/README.md). The estimate:
[`evidence/estimate/README.md`](../evidence/estimate/README.md). The live stages cannot be re-run from here without
the provider and the credit; their complete records are in [`evidence/runs/`](../evidence/runs/).
