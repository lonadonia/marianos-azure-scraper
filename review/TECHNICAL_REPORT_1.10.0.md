# Mariano's collector 1.10.0rc3: the offline C1 candidate (technical report, 2026-11-12)

Prepared by Hamza. Store: Marianos Vernon Hills, location 53100502, PICKUP. Baseline: the delivery
[`review-1.9.0rc4-20261109`](https://github.com/lonadonia/marianos-azure-scraper/tree/review-1.9.0rc4-20261109)
(commit `039fb14fa20ce31734660159f0b9c56bc3f296cb`), whose report is
[`TECHNICAL_REPORT_1.9.0.md`](TECHNICAL_REPORT_1.9.0.md).

**This is an offline candidate for review. It is not a final release, the client has not accepted it, and nothing
is in production.** No live request was sent for it: no provider, no retailer, no trial credit, no client account,
no VM, no SSH. Schedules and Classic stay off. Every result below names its revision, where it ran and what kind
of evidence it is. Times are UTC.

## 1. Answer in brief

| Question | Answer |
|---|---|
| What is delivered | Collector **1.10.0rc3** in [`source/`](../source/): development commit `a1040f79919b8e876e0b69cd909cecf9363780b4`, tree `22ebcf96cdb2021347f0e0e4d7506ad4c36d2c10`. It is 1.9.0rc4 plus five commits (§2) |
| C1 | Implemented as one change (the first commit). A later page answered with products of earlier pages, and the first page of a listing above the 250-result window answered without the filters needed to subdivide it, are set aside; the run's other listings go first; the very same request is asked again at least five minutes later, at most twice more in the run (§3) |
| How C1 is proved | **Offline only.** 28 tests drive the collector's public path on PostgreSQL through a mock transport and a fake clock: 21 state what C1 adds, 7 are controls. The same file was run on 1.9.0rc4: its 7 controls pass there and its 21 C1 cases fail; all 28 pass on the candidate (§4). Four tests use answers saved on 2026-11-09 (two C1 cases replay them through the collector, two controls read them directly); the others use synthetic pages and say so |
| What C1 does not show | That the live site answers a re-ask properly. On 2026-11-09 it did so for some listings six minutes later and not at all from 15:16Z; the cause is not established. Only a live stage measures it (§9); none is approved |
| The publication result | Confirmed and corrected, in its own commit: a complete validated run whose automatic publication was refused ended with exit code 0 as a success. It now ends with exit code 6 and an ERROR line; the last published dataset was never replaced, before or after (§5) |
| Verification on the exact candidate | Unit 494 passed; integration with PostgreSQL 218 passed; ruff, format and mypy clean; the unit suite, both case files and the lint checks again in a clean extraction of its tree (§6). One failed first attempt is on record: the unit suite on 1.10.0rc2 failed one test (the parser version), corrected in 1.10.0rc3 |
| Live coverage | **Unchanged**, as on 2026-11-09: 42 of 302 product listings complete, 38 stopped at a repeated page, 222 not collected; the Coupons route apart. An offline change adds no coverage (§7) |
| Corrections of the 1.9 publication | Stage O1's saved answers state `run_js` true for **3 of 14** product pages, not 1 of 14; one of the client's coupon examples (0002310014848) was read on a rendered page that shows no Savings section; the audit file's row G7 is re-quoted; 85 evidence files whose line ends 1.9 converted without a record are now listed with their originals' hashes (§8) |
| What needs a decision | Hamza: whether and when to run S6 and S6b (§9). The client: the VM window and key, the account for a full run, schedules, Classic, support and IP terms (§11) |

## 2. What the candidate is

1.10.0rc3 is 1.9.0rc4 (development commit `8abc2c1297b8005d162721b6ddbf66bf8684d548`, tree
`7a4dfa05e526bddefdfeab9777b9616890e129ea`) and these commits, in order (messages and trees in
[`COMMITS.txt`](../evidence/1.10.0/diffs/COMMITS.txt)):

| Commit | Version | What | Source lines |
|---|---|---|---|
| `454b79d` | 1.10.0rc1 | **C1**, with its tests, fixtures and documents | `src/`: +1594 −46 in 10 files, two of them new (`collection/reask.py` and the migration `0006_deferred_requests.py`) |
| `8158b49` | 1.10.0rc1 | notes only: stage O1's rendering count corrected (§8) | 2 docstrings, 2 notes |
| `cf3b8eb` | 1.10.0rc2 | the publication result (§5), with its tests | `operations.py`: +56 −4; the version |
| `87086c1` | 1.10.0rc2 | tests only: three C1 cases write what they observed before their first check | none |
| `a1040f7` | 1.10.0rc3 | the parser version names the release series (1.10.0); found by the unit suite on 1.10.0rc2 | 1 constant and its comment; the version |

The C1 diff against 1.9.0rc4 is
[`C1_454b79d_source_config_docs.diff`](../evidence/1.10.0/diffs/C1_454b79d_source_config_docs.diff) (source,
configuration, documents) and [`C1_454b79d_tests.diff`](../evidence/1.10.0/diffs/C1_454b79d_tests.diff) (tests; the
seven saved pages are binary fixtures). Everything since the baseline:
`git diff review-1.9.0rc4-20261109 review-1.10.0rc3-20261112 -- source`.

Much of C1's source records evidence (what was asked, what each answer states) rather than deciding anything. The
parts that decide are short: when a request is set aside (`oxylabs_live.py`, in the page loop), the
gate that says wait, ask or stop (`reask.gate`), the count raised before a re-ask is sent (`reask.reserve`), and
the task's wait (`TaskDeferred`, `queue.defer`).

**What C1 leaves alone.** The `pending_fetches` guard of 1.9.0rc4 (`acquisition/oxylabs_session.py`,
`collection/live.py`: a fetch is written to the database only once its answer is processed) is unchanged, and its
regression (`test_two_lanes_never_save_a_page_whose_answer_has_not_arrived`) passes on the candidate with the rest
of the integration suite (§6). The rules that judge a page (`pagination.judge`), bind a brand reading to its
filter, build records, prices and offers, carry records forward and gate publication are unchanged: C1 calls them,
it does not replace them.

## 3. C1

### 3.1 What was seen, and what is not known

On 2026-11-09 (report 1.9.0 §3): 54 answers to a listing's page N listed exactly its page 1's products while
stating the page asked for, ranks from 24(N−1)+1 and a search ID of their own; and the first page of Frozen (273
results, 250 reachable) named no brand and no child listing. In the same answers the page state lacked the
listing's filters (called form B there); the answers that paged properly had them (form A). That is an observed
correlation over one day. **What decides which answer comes (the site, the provider's route, the time) is not
established**, and C1 depends on no cause: it reacts to what an answer contains.

### 3.2 When a request is set aside

With `limits.max_reasks_per_request` above 0 (shipped: 2 for `marianos-53100502-pickup`; empty or 0 for any other
store, which is the behaviour of every earlier release):

1. **A later page that lists nothing new.** The page loop judges every answer as before. When an answer to page N
   (N ≥ 2) lists only products of the listing's earlier pages (`repeated`, or `reordered_repeat` when the order
   differs), 1.9 ended the listing there. C1 sets the request aside instead.
2. **A first page without its filters.** When the first page of a listing reports more results than the source's
   window lets a reader reach and names no child listing and no brand, the listing cannot be subdivided. Its
   products are counted as before (it is the listing's page 1); the same first page is set aside to be asked
   again for its filters.

Nothing else is set aside: a failed, empty, malformed, blocked or wrong-store page is handled as in 1.9.0rc4.

### 3.3 How it is asked again

- **Other listings first.** The listing's task is put aside with its checkpoint (`TaskDeferred`; it is not a failed
  attempt), the queue leases the run's other listing tasks, and the task comes back when its time has come. When
  only waiting tasks are left, the execution keeps the store lock and waits, as it already did for a retry.
- **The same request.** Address, page, listing, filter, store and fulfillment are those of the first ask, and a
  re-ask whose request differs from the one recorded is refused before it is counted. No identity is rotated and no
  address is changed.
- **At least five minutes.** `limits.reask_min_wait_seconds` is 300 and a configuration cannot set less. The wait
  runs from the previous answer or attempt.
- **At most twice more.** `max_reasks_per_request` cannot be set above 2. The count is in the database
  (`deferred_requests.reasks_dispatched`, migration 0006): it is raised and committed **before** a re-ask is sent,
  and the table's own constraints refuse a value above the ceiling. So the ceiling holds across listing lanes
  (each task holds its own request), across restarts, and for a worker killed while a re-ask is out: that re-ask
  stays counted, its evidence is marked unavailable, and the wait starts again from when it was sent.
- **Sent once.** The transport's own retries (three attempts on a provider failure) do not apply to a re-ask: a
  re-ask the provider fails is one submission and counts among the two.
- **Limits and reservation before each one.** The operator's stop, every run limit and the daily window are
  checked before a re-ask is counted; the submission is then reserved in the collector's ledger and at the
  account-wide gate, at its worst case, before anything is sent. A re-ask the ceiling refuses is not sent and not
  counted. A request cut after it was sent keeps its reservation as possibly charged, as before.

### 3.4 How an answer is judged

By its products' identities and its verified context, with the rules of 1.9.0rc4: the store and fulfillment on
the page, the page and listing it states, the filters it states, then its products against the listing's
completed pages. A new request ID, a matching page number, shifted ranks or another order establish nothing.

- A repeat counts **zero** products, at the first answer and at every re-ask.
- A re-ask that brings a genuine next page counts only the products new to the listing, each once (a page that
  overlaps earlier pages counts its new ones); the listing then goes on from the next page, and its end is still
  decided by the source's own count.
- When the re-asks are spent, the listing is incomplete **with the reason it had**, followed by what each re-ask
  brought. Spent re-asks are never the end of a listing: the reason says the remaining results were not read.
- A first page asked again for its filters counts **no** product of its own (its row's state is `reasked`). The
  subdivisions it names are planned as in 1.9; each brand or child reading must answer for its own filter
  (`wrong_filter`, `unbound` otherwise), and the listing is complete only when the distinct products of the
  listing and all its readings reach the total the source reports. A missing filter, another store, another
  filter or another page closes nothing.
- Records carried from earlier runs keep their own observation dates. A failed, rejected or incomplete run is not
  published and the last good export stays (unchanged rules; controls in §4).

### 3.5 What is recorded for every answer

One record per request set aside (`deferred_requests`; exported as `deferred_requests.json` by a run that has
any), holding every answer, the first one included and unchanged when a later one counts:

- **asked**: URL, page, offset, listing, reading, filter, store ID, fulfillment;
- **returned**, as the stored page states it: page, offset, loaded pages, listing, store, fulfillment, filters,
  search ID, total, window, product identities, sponsored placements, cards, and the subdivisions named;
- **capture**: the stored page's SHA-256, its fetch ID, its row in `listing_pages`; the provider's request ID; the
  time; whether the provider rendered the page;
- **counts**: distinct products before, new, overlap, distinct products after, whether the answer counted;
- the verdict and its detail, the store check, the original verdict and stop reason, and what followed.

What does not exist is said in words (`unavailable: no page was brought`, `unavailable: the worker stopped while
the request was out`), never left empty.

## 4. The offline proof

**Where and how.** Workstation (Windows 11, Python 3.12.10), a throwaway PostgreSQL per session, pages through
`httpx.MockTransport`, time from a fake clock that moves only when the run waits. 26 of the 28 tests drive
`Pipeline.execute` (the path a real run takes: preflight, listings, assembly, validation, export) at the client's
store and read back the persisted rows: listing pages, requests set aside, records, coverage, gates, ledger,
export files and the publication pointer. The other two are the replay controls: they read the saved pages
directly with the collector's parsers and page judge, to show what those answers contain. Test file:
[`source/tests/integration/test_reask_c1.py`](../source/tests/integration/test_reask_c1.py).

**Before and after, the same tests.** The file loads on 1.9.0rc4 too. It was run on an unchanged checkout of
1.9.0rc4 with only the candidate's test files added ([`RC4_OVERLAY.json`](../evidence/1.10.0/c1/RC4_OVERLAY.json)),
and on the candidate:

| | 1.9.0rc4 (`8abc2c1`) | 1.10.0rc3 (`a1040f7`) |
|---|---|---|
| 7 controls (`test_control_...`): what must hold with or without C1 | 7 passed | 7 passed |
| 21 C1 cases (`test_c1_...`): what C1 adds | 21 failed | 21 passed |

Test by test: [`c1/CASES_BEFORE_AFTER.csv`](../evidence/1.10.0/c1/CASES_BEFORE_AFTER.csv); what each test
observed on each revision, written before it was judged: [`c1/cases/`](../evidence/1.10.0/c1/cases/); the two
sessions: [`rc4_c1_cases`](../evidence/1.10.0/tests/rc4_c1_cases.json),
[`cand_c1_cases`](../evidence/1.10.0/tests/cand_c1_cases.json).

| Case | Required | Tests | What the candidate did |
|---|---|---|---|
| **1. A repeat, exact or reordered, through both re-asks** | zero new products; the original reason kept; G3 rejects; the last good dataset untouched | 2 controls (repeat, reorder), 2 C1 cases | page 2 asked 3 times, 300 s apart on the fake clock, never a fourth although one was there to be asked; 0 products from the three answers; three different request IDs recorded and no progress taken from them; the coverage reason begins with the 1.9 reason word for word; G3 FAIL, run rejected; publication refused and the published pointer, `latest.json`, manifest and products file unchanged (control, both revisions) |
| **2. A re-ask returns a genuine next page** | only new identities, once; later pages read; the usual end applies | 1 control, 3 C1 cases | next page on the first re-ask: 60 of 60, each product once, the first rejected answer still on record as `repeated`; with partial overlap: 12 new counted, 12 again not, page 3 read, 48 distinct of 60 so the listing stays incomplete by its own count; **replay** of Batteries (below): 96 of 96 |
| **3. Above the window, no filters; then filters, or a wrong or unbound brand** | only positively bound readings contribute; a missing filter, wrong store, filter or page closes nothing | 2 controls, 8 C1 cases | filters on the re-ask: two brand readings, each under its own filter, 60 distinct of 60, the re-asked page counting nothing; one brand answered unfiltered, for another brand, or without stating a filter: that reading counts nothing, none of its products is recorded, the listing incomplete with a gap of 30; filters never coming: 3 asks, then the pages to the window, 48 of 60, incomplete; the re-ask answered for another store: run stopped, nothing closed; answered with another page: not counted, the next re-ask may; **replay** of Frozen (below): 24 of 273, incomplete |
| **4. Two lanes, interruption and resume, budget, deadline** | no premature save, duplicate reservation, double count, refetch of a completed page, or attempt beyond the ceiling; the request keeps its identity and history | 8 C1 cases | two lanes: 2 requests in flight at most, each request set aside asked once more, every page row with its stored page, G13 PASS; other listings read before the re-ask; a re-ask the provider failed: one submission, counted among the two; a worker killed with re-ask 1 out: it stays counted, its reservation kept once as possibly charged, one re-ask left 300 s later, page 1 never asked again; the spending ceiling: the re-ask not sent and not counted, the run paused, asked once there was room; the daily window ending during the wait: nothing sent after it, the request and its first answer kept, asked the next day |
| **5. Ordinary pages and carried records** | credited paths still pass; carried records keep their dates; a replay is labelled a replay | 2 controls, and the whole integration suite (§6) | ordinary pages read once each, no wait, nothing set aside; 36 products carried from an earlier run keep that run's date while a page repeats |

**The two replays, and what they are.** Both serve pages the collector itself stored on 2026-11-09 (byte copies;
origins, request IDs and hashes in
[`SOURCES.json`](../source/tests/fixtures/oxylabs_2026-11-09/SOURCES.json)). A replay shows what the collector does
with those answers. It does not show that the site would give them again.

- **Batteries (26003).** Stage S4 was given page 1 and, at 14:36:19Z, a page 2 that repeated it; stage S5a, from
  14:42:52Z, was given a page 2, 3 and 4 with 24 other products each. Served in that order: on 1.9.0rc4 the listing
  ends at 24 of 96; on the candidate the repeat is set aside, the re-ask (five minutes later on the fake clock; 6
  min 33 s passed between the real answers) is given S5a's page 2, and the listing is read to 96 of 96, 96 records
  (90 valid, 6 price conflicts kept as such). This is the one case where the saved answers themselves show a
  later answer differing from an earlier one for the same address.
- **Frozen (18010).** Stage S3b was given a first page without filters and a page 2 that repeated page 1; no other
  answer for Frozen was saved that day. Each re-ask is therefore served the same saved answer again. The
  candidate asks each of the two requests twice more, counts nothing from them, and ends at 24 of 273, incomplete,
  with both reasons: this shows the cost when answers do not change (4 submissions) and that nothing is claimed.
  **Whether a re-ask of Frozen's first page would bring its filters is not shown by any saved answer**; the test
  of that path uses synthetic pages.

## 5. The publication result (kept apart from C1)

**Reproduced on 1.9.0rc4** (`operations.after_run`): a complete, validated run whose automatic publication
`publish_run` refuses left the execution reporting success. The refusal was logged at WARN
(`PUBLICATION_REFUSED`), `RUN_FINISHED` followed at INFO, and the exit code was 0; a later firing of the same
scheduled occurrence reported the occurrence done, again with 0. Two refusals were injected on a validated run:
an export changed on disk after validation (the manifest check fails) and a WARN finding with no recorded reason
(the shipped configuration records none). **The last published dataset was not replaced in either case**, on either
revision: that safeguard worked and is a control here.

**Corrected in `cf3b8eb`** (1.10.0rc2; `operations.py` +56 −4): the refusal is recorded on the run as an ERROR event
with its reason, the run's summary carries `publication: {published: false, refused: ...}`, and the execution
ends with **exit code 6** (rejected: nothing was published). A later firing of the occurrence ends with 6 again
while the run is validated and unpublished. An ordinary publication is unchanged: exit code 0, the pointer moved.

| [`test_publication_result.py`](../source/tests/integration/test_publication_result.py) | 1.9.0rc4 | 1.10.0rc3 |
|---|---|---|
| 3 controls: an ordinary publication ends OK; a refused one leaves the last good dataset published (two causes) | 3 passed | 3 passed |
| 3 cases of the new result: unsuccessful exit and ERROR line (two causes); a later firing says so again | 3 failed | 3 passed |

Evidence: [`publication_result/`](../evidence/1.10.0/publication_result/) (table, each test's observation on each
revision), diff [`PUBLICATION_RESULT_cf3b8eb.diff`](../evidence/1.10.0/diffs/PUBLICATION_RESULT_cf3b8eb.diff).
Synthetic pages; the refusal is injected. `publish.auto` was off in every live stage so far, so no live run met
this path.

## 6. Verification on the exact candidate

All on commit `a1040f79919b8e876e0b69cd909cecf9363780b4` with a clean tree, on the workstation; each session's record (revision, clean tree, times,
counts, log hash) and complete output are in [`evidence/1.10.0/tests/`](../evidence/1.10.0/tests/), summarized in
[`SESSIONS.csv`](../evidence/1.10.0/tests/SESSIONS.csv).

| Session | Result |
|---|---|
| Unit suite (`tests/unit`) | 494 passed |
| Integration suite (`tests/integration`, PostgreSQL) | 218 passed |
| of which the C1 cases and the publication cases, also run on their own | 28 passed; 6 passed |
| `ruff check .` | All checks passed |
| `ruff format --check .` | 181 files already formatted |
| `mypy` (strict) | no issues in 86 source files |

The integration suite ran for 2,182 s (about 36 min) and skipped no test. It started one throwaway PostgreSQL server (`pgserver`, in a temporary folder) for the whole suite and removed it at the end; no PostgreSQL process was left running afterwards. Its 218 tests are 1.9.0rc4's 183, the 28 C1 cases, the 6 publication cases and one migration test (migration 0006, its table of requests set aside and the ceiling in its constraints); [`INTEGRATION_BY_FILE.csv`](../evidence/1.10.0/tests/INTEGRATION_BY_FILE.csv) gives them per file.

**Again in a clean extraction.** The unit suite, the two case files and the three lint checks were run again in a
copy of the candidate's tree made with `git archive` (line ends unconverted) and installed from its lock with
`uv sync --frozen --offline`; the copy was checked file for file against the tree before and after the runs (the
`x_` sessions in `SESSIONS.csv`): unit 494 passed; C1 cases 28 passed; publication cases 6 passed; ruff 'All checks passed!', format '181 files already formatted', mypy 'Success: no issues found in 86 source files'. After the runs no file of the tree was missing or changed; the
runs had added only caches, among them the example database of the property tests (`.hypothesis/`). A first copy,
whose line ends the workstation's Git settings had converted, was found by that check and replaced before any
session ran in it.

**A failed first attempt, kept.** The unit suite on 1.10.0rc2 (`87086c1`) ended with 493 passed and 1 failed:
`test_the_parser_version_names_the_release_series`. The release had moved to 1.10.0 and the parser version, which
every run and export records, still said 1.9.0. 1.10.0rc3 corrects it; that run's record and output are in
[`tests/first_attempt_87086c1/`](../evidence/1.10.0/tests/first_attempt_87086c1/). 1.10.0rc1 and rc2 are not
delivered.

**Two before-runs superseded, kept.** The first runs of the two case files on 1.9.0rc4 used the test files of
`cf3b8eb`. In those, three staged C1 cases wrote their observation only after their first check, so on 1.9.0rc4,
where they fail at that check, they left none. `87086c1` moved those writes first, and both files were run again on
1.9.0rc4 with the same counts (21 failed and 7 passed; 3 failed and 3 passed). The first runs are in
[`tests/superseded_tests_of_cf3b8eb/`](../evidence/1.10.0/tests/superseded_tests_of_cf3b8eb/).

These are developer-run results on one workstation. The counts of 1.9.0rc4 (488 unit, 183 integration), its live
recovery and S4c's 700 products were developer-reported too, and stay what they were: results of 1.9.0rc4.

## 7. Requirements: what is closed here and what remains

The matrix ([`ACCEPTANCE_MATRIX.csv`](ACCEPTANCE_MATRIX.csv)) has two new columns, `status_1.10.0rc3` and
`evidence_1.10.0rc3`, beside the unchanged earlier ones; the 29-item audit
([`AUDIT_29_RECONCILIATION.csv`](AUDIT_29_RECONCILIATION.csv)) has the candidate's state for each group. Every
mandatory item still open is in
[`OUTSTANDING_REQUIREMENTS_1.10.0.csv`](OUTSTANDING_REQUIREMENTS_1.10.0.csv) with its owner, what blocks it, the
exact evidence it needs and the next action. In short:

**Closed by local work in this candidate**

- C1 implemented and tested offline (the change the 1.9 report proposed in §15);
- the publication result (a refused publication is reported as unsuccessful);
- the parser version of the release series; the O1 rendering count and the Temptations example corrected; the
  audit file's row G7 re-quoted; the 85 files of 1.9's evidence whose line ends were converted without a record now
  listed with their originals' hashes (§8).

**Coverage: unchanged, and not changed by an offline repair.** The queue of 2026-11-09
([`INCOMPLETE_QUEUE_190.csv`](../evidence/1.9.0/live/INCOMPLETE_QUEUE_190.csv)) stands: 303 entries, the Coupons
route and 302 product listings, of which **42 complete** in their latest run (40 done and 2 empty; 444 products),
**38 incomplete**, each stopped at a repeated page (2,659 products stated, 965 read), and **222 not collected** by
1.9 (72 measured on 2026-11-02 at 11,244 products, 11 of them above 250; 150 not measured). Rows 0 to 21 are
mostly in the last group. No production sampling cap exists in the collector: a listing is complete only by the
source's own count, every page and every partition.

- The 38 listings stopped at a repeated page are what C1's first kind addresses, if the site answers a re-ask.
- Above the window: 13 listings of the queue measured above 250 (5,464 products). Each needs a first page that
  names its subdivisions (C1's second kind asks again for one), every reading bound to its filter, and the
  distinct union equal to the total. None was completed live by 1.9.
- **Cat Food, 231 of 232**: unchanged. Q2 read 232 slots holding 231 products (0002310014492 shown twice); the
  three reads of 2026-11-09 stopped at page 2's repeat. A complete read on the candidate is live work.
- **The Coupons route** (row 0) lists offers, not products, and is read once per run as before; on 2026-11-09 it
  showed 24 cards in 5 reads and none in 5.

**The client's coupon examples**, checked again in the saved sources only
([`COUPON_EVIDENCE_CHECK.json`](../evidence/1.10.0/coupons/COUPON_EVIDENCE_CHECK.json)):

| UPC | State | Saved source |
|---|---|---|
| 0001780014939 | **complete** (kept): coupon 4257015 with its terms, expiry, clipping instruction and qualifying products; cash back 4257014 left out by the shipped setting | the rendered product page of stage O1 (request 7524540530412231682) |
| 0001780014941 | unread | two saved product pages, both brought without rendering: they say nothing about its coupons |
| 0002310014848 | unread, and **not shown on its rendered page** | its first saved product page was rendered (request 7524541411266425857, 22.6 s) and has no Savings section; its second was not rendered. The coupon its card showed on 2026-11-02 is not confirmed by the product's own page of 2026-11-06 |
| 0003980014995 | unread | two saved product pages, both brought without rendering |

No Coupons-page card of the ten reads of 2026-11-09 names Purina, Temptations or Energizer, and that page never
names the products a coupon applies to. For a coupon's terms to be exported as complete the collector requires
them product-bound: the coupon's ID, its terms (quantity, eligibility, redemption limits), its displayed expiry,
the clipping instruction and qualifying products that name the product, all from the product's own rendered page.
Until then the headline is kept as a headline and flagged (`DIGITAL_TERMS_UNREAD`, or `DIGITAL_COUPONS_UNOBSERVED`
on the tiles served since 2026-11-06), and a savings-only wording ("Save $10.00 on 2") leaves the payable price
empty. Nothing is guessed. Completing the three is live work (rendered product pages), not possible offline.

**Preserved unchanged, with their tests passing on the candidate:** the two price-per-measure traces
(0084024314377 at $19.99/oz and 0001280052496 at $7.99/oz: values the site displayed, exported as displayed and
flagged; report 1.9.0 §5), original product and image URLs and UPCs, the size and offer rules (report 1.9.0 §8),
and the export schema: 22 fields, in order, all strings, `gupc` and `unit_price` always empty
(`tests/unit/test_schema.py`).

**Tracked for later evidence, none met by this candidate:** at least 500 distinct fresh valid products in one
logical run *of this candidate*; proof of the designated pickup store on that run; natural missing-product
retention; a protected full-scope publication; measured concurrency, runtime and cost; the client's Azure
acceptance; authorized twice-weekly operation per store. What each one's dataset, source provenance, logs and run
report must contain is fixed in advance in
[`QUALIFICATION_EVIDENCE_REQUIREMENTS.md`](../evidence/1.10.0/QUALIFICATION_EVIDENCE_REQUIREMENTS.md). S4c's 700
products qualify a count on 1.9.0rc4, in a run G3 rejected; they are not evidence for 1.10.0rc3.

## 8. Corrections of earlier statements

- **Stage O1's rendered product pages: 3 of 14, not 1 of 14.** The saved raw answers of 2026-11-06 state `run_js`
  true for three product pages: 0001780014939 (request 7524540530412231682; Savings section with two coupons),
  0002310014848 (request 7524541411266425857; no Savings section) and 0087786900820 (request
  7524541856273716225; no Savings section). The 1.9.0 report (§6, §10), the cost report, the collector's README
  and two docstrings said 1 of 14, and a fixture note said all seven M6 answers stated false. The collector's
  texts are corrected in `8158b49`; the 1.9.0 report is left as published, with this note above it. The count of
  2026-11-09 (2 of 8) was taken from the collector's own fetch records and stands.
- **0002310014848** was described as "page brought unrendered: terms unread". Its first saved page was rendered
  and shows no Savings section; only its second sample was unrendered. Its state is "unread, and not shown on its
  rendered page" (§7). The practical outcome is the same (headline kept and flagged, no price exported), but the
  reason differs: for this product a rendered page did not show the coupon.
- **Consequence for the estimate of product-page reads:** rendered answers were 3 of 14 on 2026-11-06 and 2 of 8 on
  2026-11-09, so 5 of 22 over the two days, and 1 of those 5 showed a coupon. The read stays off by default.
- **The parser version** of 1.10.0rc1 and rc2 said 1.9.0 (§6); neither is delivered.
- **The audit file's row G7 of 1.9.0rc4** had 11 fields where its header has 8 (three unquoted commas). It is
  re-quoted, its text unchanged; no other published CSV has an uneven row.
- **85 files of 1.9's evidence changed their line ends without a record.** 1.9's builder wrote every text file with
  LF; where the private original had Windows line ends (CRLF), it neither listed the file in `REDACTIONS.csv` nor
  gave the original's hash in `FILE_MAP.csv`, which repeated the published one. Nothing else in those files
  differs. Among them are 50 exports of the live runs, whose run's own `exports/manifest.json` names the CRLF
  original, so a published export does not match its manifest byte for byte; writing each LF back as CRLF gives
  the manifest's hash. The 85 are now in `REDACTIONS.csv` with the original's hash, and `FILE_MAP.csv` gives it;
  the files are unchanged. 1.8's evidence, checked the same way, has no such case (596 of 596 archive files match).
  Details: [`DOC_CORRECTIONS.md`](../manifests/DOC_CORRECTIONS.md) and
  [`corrections/LINE_ENDS_190.json`](../evidence/1.10.0/corrections/LINE_ENDS_190.json).

## 9. Proposed live stages: not run, not approved

Live work for Mariano's is on hold. The two stages below are proposals for a later explicit decision by Hamza;
their full definition (command, configuration, prerequisites, stop conditions, what each records) is in
[`NEXT_STAGES.json`](../evidence/1.10.0/budget/NEXT_STAGES.json).

| Stage | Objective | Ceiling | Stops |
|---|---|---|---|
| **S6**, later-page recovery | whether C1 recovers later pages on the live site: rows 22 to 27 (17 listings, 1,190 products stated on 2026-11-09) in one run of the candidate; how many requests are set aside and recovered, after how long, at what cost; whether the run completes its scope with at least 500 fresh valid products | 130 requests, USD 0.195 | the ceiling; store or fulfillment not verified; abnormal result, site refusal or three pages in a row not read; a ledger refusal or more than 2 unknown outcomes; the deadline (150 min); by the operator once 10 re-asks were answered and none recovered |
| **S6b**, brand union above the window | Frozen (18010; 273 results, 250 reachable) read through the brands a first page names when one is obtained, each reading bound to its filter, the union reconciled with the total | 86 requests, USD 0.129 | the same; deadline 120 min |

Both together: 216 requests, USD 0.324 at the list rate, inside Mariano's part of the shared trial credit (USD
1.840500 spendable when read at 2026-11-11 23:45:39Z; a read: this task reserved and spent nothing). **S7**
(the rest of the queue) and a **full collection** are deferred until S6 has shown requests recovered, and for the
full scope until the client's account and authorization: it does not fit the trial credit. If S6 recovers nothing
while the site keeps repeating, C1 costs at most 2 requests for each request set aside and the open question is
the contingency C2 of the 1.9 report (§15 there): what supplies a form-B page with its filters and later pages.

## 10. The shared Classic probe: Walmart's 1.7.4

Mariano's still pins the shared probe **1.7.3** ([`classic-probe-1.7.3/`](../classic-probe-1.7.3/)); nothing in it
changed for this candidate, live Classic stays disabled, and no Classic page parameter for Mariano's is proved.

Since then the Walmart project published probe **1.7.4**, which corrects a Windows defect of the probe's
supervisor found in the client's review there. That work and its proof belong to the Walmart delivery; nothing
was run for it here and no Walmart file was changed for this candidate:

- corrected source:
  [`classic-probe-1.7.4/`](https://github.com/lonadonia/walmart-azure-scraper/tree/review-1.6.8-probe174-20261111/classic-probe-1.7.4)
  at Walmart's tag `review-1.6.8-probe174-20261111` (commit `00a18947668feb7d54bf5c019654d89bf0ad56a0`);
- the Windows regression (failing on 1.7.2, passing on 1.7.4) and how to reproduce it:
  [`evidence/offline-tests/1.7.4-classic-probe/`](https://github.com/lonadonia/walmart-azure-scraper/tree/review-1.6.8-probe174-20261111/evidence/offline-tests/1.7.4-classic-probe)
  (`REPRODUCE.md`, `REPRODUCTION_ON_1.7.2_WINDOWS.log`, `CANDIDATE_1.7.4_WINDOWS.log`).

The Mariano's adapter inside 1.7.4 (`src/classic_probe/marianos.py`) is the same blob as in 1.6.0 to 1.7.3
(`9de6510bddbb0cae7fd86e09dac5ed32fc3487a4`). Whether Mariano's moves its pin to 1.7.4 is an owner's decision;
details in [`SHARED_CLASSIC_PROBE.md`](SHARED_CLASSIC_PROBE.md).

## 11. What remains, and who decides

| Item | Owner | Blocked by | Next action |
|---|---|---|---|
| S6 and S6b on the live site | Hamza | the hold on live work; Hamza's decision on the ceilings | decide; then one run each, with the evidence of §9 |
| S7, then full coverage of rows 0 to 27 | Hamza, then the client | S6's result; the trial credit; the client's account and authorization | after S6 |
| The three coupon examples; Cat Food's 232nd slot | Hamza | live work (rendered product pages; a complete read) | with or after S6 |
| At least 500 fresh valid products, the store proof, concurrency, runtime and cost on this candidate | Hamza | live work | S6 can supply the first two; a one-lane and two-lane comparison is its own stage |
| Natural missing-product retention | time | two complete runs with a genuine disappearance between them | observed when it happens; never manufactured |
| Protected full-scope publication | Hamza, the client | a complete full-scope run | after full coverage |
| The client's VM checks | the client, then Hamza | the VM is deallocated; the window and the new key are the client's to give; when to ask is the owner's decision | none attempted |
| Twice-weekly schedule | the client | the client's authorization | schedules stay off |
| Classic | the client | the client's choice; a documented page contract | disabled |
| Support and IP terms | the client and Hamza | agreement | open |

## 12. Reproduce offline

[`evidence/1.10.0/REPRODUCE.md`](../evidence/1.10.0/REPRODUCE.md) has the exact commands: the candidate's suites,
the C1 cases and the publication cases on the candidate and on 1.9.0rc4, and the before/after tables. Nothing in
it sends a request anywhere.

## 13. Evidence for 1.10

[`evidence/1.10.0/`](../evidence/1.10.0/README.md): the before/after tables and each test's observation on both
revisions, the diffs, the test sessions, the coupon check, the proposed stages, the requirements for later
evidence, the line-end record of 1.9 (§8), and the tools. The evidence files of 1.9 and 1.8 are unchanged.
