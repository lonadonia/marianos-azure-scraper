# What the later live evidence must contain (prepared with 1.10.0rc3; nothing here has been run)

1.10.0rc3 is an offline candidate. None of the items below is met by it: each needs a live run, the client's
environment or the client's decision. This page fixes, before any of that happens, what each one's evidence has to
contain, so a later run is judged against a list written in advance.

Every item is specific to the revision that runs it: evidence of 1.9.0rc4 or earlier (S4c's 700 products among it)
is kept as what it is and does not qualify 1.10.0rc3.

## 1. The items

| # | Item | Owner | What must be true | Status on 2026-11-12 |
|---|---|---|---|---|
| Q1 | At least 500 distinct fresh valid products in one logical run of the candidate | Hamza (the run, once Hamza has approved the stage) | one run ID; at least 500 distinct UPCs with status `valid`, each observed by that run (no carried record counted); G13 and G14 pass | not run on 1.10.0rc3 |
| Q2 | Proof of the designated pickup store | Hamza (run) | every page of the run verified for location 53100502 and fulfillment PICKUP (the request's parameters, the page's store details, its search request and each price's `sourceLocationId`); no attestation fails | not run on 1.10.0rc3 |
| Q3 | Natural missing-product retention | Hamza (two runs), time | a product a complete earlier run observed and a later run genuinely does not observe, carried forward with its own observation date; never produced by removing or editing a page | not observed on any revision; none is manufactured |
| Q4 | Protected full-scope publication | Hamza (run), client (account, authorization) | a run of every CSV row that completes its scope (G3 passes on the source's own counts and partition unions), is validated and published on its own target; a failed or incomplete run before or after it leaves the published dataset untouched | not run; full scope does not fit the trial credit |
| Q5 | Measured concurrency, runtime and cost | Hamza (runs) | the same scope read with one lane and with two, uninterrupted, on the candidate: submissions, active seconds, re-asks and waits, settled cost from the ledger | not measured on 1.10.0rc3 |
| Q6 | Client Azure acceptance | client (window, key), then Hamza | the checks of `review/ACCEPTANCE_RUNBOOK.md` on the client's VM, recorded by the client's own acceptance | not started; the VM is deallocated and nothing was attempted |
| Q7 | Authorized twice-weekly operation per store | client (authorization), then time | the schedule enabled for the store by the client's decision; two weeks of observed occurrences with their runs | schedules are off |

## 2. What each run's evidence folder must hold

For every run offered as evidence of Q1 to Q5, one folder named by its stage and run ID, with:

**Identification**

- the stage record written before the run: objective, command, configuration hashes, ceiling in submissions and in
  US dollars, deadline, retry policy, stop conditions, and who approved it and when;
- the collector's version, source revision and tree as each segment of the run recorded them (one revision for the
  whole run: a run resumed by another revision does not qualify it);
- the store key, location ID and fulfillment; the UTC start and end of every segment.

**Dataset**

- `products.json` and `products.csv` (the retained dataset: the 22 fields, in order, all strings) and
  `products_fresh.json` and `products_fresh.csv` (this run's own valid records only);
- `memberships.json`, `offers.json`, `provenance.json`, `validation_report.json`, `manifest.json` with the SHA-256
  of every other file;
- the counts as sets of identities: fresh valid, fresh not valid, carried forward, excluded, and that no identity is
  in two of them (`coverage_reconciliation.json`, `identities`).

**Source provenance**

- for every record: the page it was read from (fetch ID, URL, page number, request ID, SHA-256 of the stored page)
  and the time it was observed;
- `listing_pages.csv`: every answer asked for as a listing's page, counted or not, with its verdict;
- `deferred_requests.json` when a request was set aside: every answer of each, the first one included;
- `coverage_reconciliation.csv` and `coverage_by_csv_row.csv`: each listing's reported total, pages, distinct
  products and gap; each CSV row's state;
- the stored pages themselves kept privately, identified in the published files by their SHA-256.

**Logs**

- the run's complete structured log (JSON lines), unedited except for the documented masking of workstation paths
  and key fingerprints, with its SHA-256;
- the stage's command log (each command, its UTC time, its exit code);
- the ledger rows of the stage: every submission reserved, settled or held as unknown, with the provider's request
  ID, and the ledger's chain verification after the stage.

**Run report** (one page per run)

- what was asked and what was answered: submissions, results charged, free failures, unknown outcomes, cost at the
  recorded rate;
- pages asked, counted and not counted by verdict; requests set aside, recovered and not recovered, with the waits;
- products: distinct fresh valid, fresh not valid, carried, excluded; price conflicts kept apart;
- coverage: listings DONE, EMPTY, INCOMPLETE with each reason; CSV rows complete; partition unions against their
  totals;
- every gate's result; whether the run was published, and if not, why;
- what the run does not show.

## 3. What does not count

- a count assembled from more than one run, or from a run and its carried records;
- a replay, a fixture or a synthetic page (they stay labelled as such);
- a run whose pages were not all verified for store 53100502 and PICKUP;
- a listing called complete because its pages ran out, its re-asks were spent, or a share of its total was reached;
- a statement of acceptance not made by the client.

## 4. Optional items and owner decisions (not requirements of this candidate)

| Item | Whose decision | State |
|---|---|---|
| The Classic Web Scraper API route | the client's choice and approval; a documented page contract | disabled; the shared probe is offline only |
| Restoring the Scrapfly browser route, the Kroger production API, another provider, a second live store | the client | not chosen; none was used |
| The short Azure window on the client's VM | the owner's (Hamza's) decision on timing, then the client's restart and key installation | not requested by this task |
| Lifting the hold on live work; the ceilings of S6 and S6b | Hamza | on hold; proposals in `budget/NEXT_STAGES.json` |
| Support period and IP terms | the client and Hamza | to be agreed |
