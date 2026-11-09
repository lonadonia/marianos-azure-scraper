# Mariano's collector 1.9.0rc4: corrections, the site's changes, the live stages of 2026-11-09, and what is still open (2026-11-09)

Target store: **Mariano's Vernon Hills, store 53100502, 1720 N Milwaukee Ave, Vernon Hills, IL 60061, PICKUP**.
Lakeshore East (53100503, In Store) appears only as earlier development evidence; its product counts are not used
as proof for this store. Every live request of this task was sent on 2026-11-06 and 2026-11-09 from Hamza's
workstation through Hamza's Oxylabs Web API trial account; nothing ran on the client's Azure VM. Times are UTC. On
these dates Chicago (the store's zone) is UTC−6, and Casablanca is UTC+0 (Morocco has kept GMT since 2026-09-20; §13).

This is a correction delivery for review: **corrections verified; named milestones still pending**. It is not a
final release, it has not been accepted, and nothing here is in production.

The 1.8.0rc5 report stays as it was published ([`TECHNICAL_REPORT.md`](TECHNICAL_REPORT.md), tag
`review-1.8.0rc5-20261102`): its runs, counts and versions are history and are not rewritten here.

## 1. Answer in brief

| | State on 2026-11-09 |
|---|---|
| Source | collector **1.9.0rc4** in [`source/`](../source/), development commit `8abc2c1297b8005d162721b6ddbf66bf8684d548` (git tree `7a4dfa05e526bddefdfeab9777b9616890e129ea`, the same tree id as `source/` here). The shared Classic probe **1.7.3** in [`classic-probe-1.7.3/`](../classic-probe-1.7.3/) |
| Offline verification of this exact tree | unit: 488 passed; integration (PostgreSQL): 183 passed (the full suite against PostgreSQL, 32 min 41 s); ruff and mypy: clean (ruff 0.17.1 check; ruff format --check: 174 files; mypy 2.4.0: no issues in 85 source files); probe 1.7.3: 222 passed, 5 skipped |
| Live in this task | 2026-11-06: O1, S1, O2 (28 submissions). 2026-11-09, within Hamza's approval of at most 295 submissions and USD 0.4425: five stages on 1.9.0rc3 (S1b, S4, S5a, S5b, S3: 101 submissions) and five on 1.9.0rc4 (S5b2, S4b, S4c, S3b, S4d: 147 submissions); 248 of the 295 used (§11, §14) |
| Fresh qualification of the final revision | **S4c** (run `01M70GKE2KJF0D6CKSY04VD8YK`, 1.9.0rc4): **700 distinct fresh valid products** from one logical run, each verified against its page; G13 (integrity) and G14 (at least 500 valid) pass. The run is **rejected by G3** (coverage): 25 of its 31 listings stopped at a repeated page 2, and its rows were narrowed to small listings. It qualifies the count, not production coverage |
| A defect found live and corrected | with two listing lanes, 1.9.0rc3 could write a page to the database before its answer arrived (S5b: G13 FAIL). **1.9.0rc4** writes a page only once its answer is processed. Its regression fails on 1.9.0rc3 and passes on 1.9.0rc4; live, S5b2 passed G13 through a signal, a refused second start, a hard kill and two resumes (§10) |
| The open finding: two forms of the site's answer | on 2026-11-09 a listing answer came in one of two forms (§3.2). **Form A** carries the listing's filters (brands, child listings) in its page state, and its later pages are distinct: Q2's form on 2026-11-02. **Form B** carries no filters, and its page N lists exactly page 1's products: every repeated page of the day (54 of 54) was form B, every distinct one (33 of 33) form A. Form A came in 50 of the day's 203 answers listing products, mostly before 15:00Z. 1.9 counts no repeated page and ends the listing incomplete; without filters it cannot split a listing above the 250-result window. What decides the form is not established; a bounded re-ask of form-B answers later in the run is a proposed change with its own review (§15) |
| Above the 250 window | **no union qualified.** S3: Milk states 246 now, so no brand reading. S3b: 18010 Frozen (273 products, 250 reachable) came in form B: no brand list, no reading planned, page 2 repeated (§4) |
| Last full live run | still **Q2** (1.8.0rc4, 2026-11-02, run `01M6E5V6CASQ8F00VC8PE9TFYW`): 1,137 fresh valid, 1,160 retained (1,137 + 23 + 0 carried), historically **rejected**; unchanged and not relabelled |
| Full scope | **not completed.** The exact queue after the last stage is [`INCOMPLETE_QUEUE_190.csv`](../evidence/1.9.0/live/INCOMPLETE_QUEUE_190.csv): 303 entries, namely the Coupons route, 42 listings complete in their latest 1.9 run (444 products), 38 incomplete at a repeated page (2,659 products stated, 965 read) and 222 not yet collected by 1.9 (72 of them measured on 2026-11-02 at 11,244 products; 150 not measured). It does not fit the trial credit, and while the site answers in form B this revision cannot complete a listing beyond its first page |
| Client decisions and access | the client's VM (deallocated; no SSH attempt was made, at the client's request); the schedule (off); Classic (disabled, not approved); support and IP terms |

## 2. What changed since 1.8.0rc5, and where it is tested

The published diff is the change of `source/` between the tags `review-1.8.0rc5-probe171-20261105` and `review-1.9.0rc4-20261109`.
Each correction, with its reproduction, cause, regression and remaining limitation, is in
[`CORRECTION_MAP_1.9.0.csv`](CORRECTION_MAP_1.9.0.csv) (N01 to N17).

| Candidate | Development commit | What it added |
|---|---|---|
| 1.9.0 (work) | `ea296c7` | M1 brand readings by full identity (migration 0005); M2 filter binding; M8 listing lanes; T07 pause events |
| 1.9.0 (work) | `51db61d` | the account-wide spending gate |
| 1.9.0 (work) | `ac114d7` | M4 complete coupon terms from the product's own page; M3 price-per-measure anomaly flags; M6 regressions |
| 1.9.0rc1 | `b0f9191` | T06 segment ends; M8 schedule capacity. **Ran live once (S1, 2026-11-06)** |
| 1.9.0rc2 | `dfbac1a`, `fc06efd` | the tile served since 2026-11-06; listing pages without rendering; "N/A" and "Count" are not sizes; the synthetic site of the tests follows the rendering setting |
| 1.9.0rc3 | `9090537` | a tile's coupon is unknown, not absent (DIGITAL_COUPONS_UNOBSERVED); neutral paths in the fixture notes; the collector's own README, CLI and OPERATIONS for 1.9. **Ran live in S1b, S4, S5a, S5b, S3 (2026-11-09)** |
| **1.9.0rc4** | `8abc2c1` | with two listing lanes, a page is written to the database only once its answer is processed (N17, found live in S5b). Against 1.9.0rc3 it changes `acquisition/oxylabs_session.py`, `collection/live.py`, the version, one integration test and two notes in README and OPERATIONS; the shipped configuration is byte for byte the same. **Ran live in S5b2, S4b, S4c, S3b, S4d** |

The development history is local; the published `source/` is the exact tree of `8abc2c1` (check:
`git rev-parse review-1.9.0rc4-20261109:source` prints `7a4dfa05e526bddefdfeab9777b9616890e129ea`). 1.9.0rc3 is development commit `90905377f4919d33854c23d8068fd7e36553ab31` (tree
`ee335e8fadfad01e3b419e539d5a4459cc7ac7e6`); its stages are kept with their revision named on each.

## 3. The site and the provider since 2026-11-06

### 3.1 The new tile (S1 and O2, 2026-11-06)

**S1** (19:33-19:40Z, 1.9.0rc1 `b0f9191`, Cat Food 27021, ceiling 25 submissions / USD 0.0375) read Cat Food page 1
three times and stopped the run as `ABNORMAL_RESULT` (exit 6, no record accepted, 5 results, USD 0.0075): the page
state listed 24 of 232 products, and rc1's grid parser found no card. All three were asked for rendered (rc1's
default). The provider rendered the first (its own metadata: `run_js` true, 38.5 s), which carried no product grid
at all; it brought the next two unrendered (`run_js` false, 7.3 and 6.3 s), and they carried 24 tiles in a markup
rc1 did not know. The store and PICKUP were verified on every page; the Coupons page, rendered (54.9 s), showed 0
coupon cards (Q2's showed 24).

**O2** (19:45-19:51Z, 7 of 8 planned requests, USD 0.0105) looked at the new markup on listing and search pages:

- listing pages show `horizontal-product-card-N` tiles, search pages `default-product-card-N`, with the same inner
  test ids; **no tile shows a size** (the size is only in the page's own product data, `item.customerFacingSize`);
  the price per measure has its own element;
- **a rendered listing answer carries no tiles** while its state lists 24 products; every unrendered answer carried
  all of them;
- **no tile showed a coupon**: the Purina ONE tiles have no savings zone while their product pages show coupons
  4257015 and 4257014 (O1). Across the six saved pages, 133 tiles, five show a "Buy 1 Save $N" deal and none a coupon;
- "Prices May Vary" without a price for a temporarily out-of-stock product; Nutrl "Sale: $16.99 discounted from
  $18.98" while the product data's regular price is USD 18.99 (a one-cent conflict, kept as such).

**1.9.0rc2** reads the tile with its own selectors (the cards of earlier saved pages read as before); takes the
weight from the product's own data in the same page (`SIZE_FROM_PRODUCT_DATA`, with its source; in Q2 the displayed
size equalled it for 1,157 of 1,157 comparable records), through the same size rules; reads a price only in the
three forms seen on the tile and otherwise exports none (`PRICE_DISPLAY_UNRECOGNIZED`, record not valid); asks for
listing pages without rendering (`listing_run_js: false`), and asks again for a rendered answer without tiles
(three in a row stop the run resumably, `PROVIDER_ERROR`). **1.9.0rc3** stops treating a tile's missing coupon as an
absence (§6). The regressions use the real answers S1 and O2 saved
([`source/tests/fixtures/oxylabs_2026-11-06/`](../source/tests/fixtures/oxylabs_2026-11-06/), origins and hashes in
`SOURCES_TILES.json`).

**Live on 2026-11-09:** the tile reading held on every department the stages reached (rows 1, 2, 4, 5, 6, 8, 10,
14, 15, 18, 19, 20, 21 and 22 to 27); every canary passed (§11). The paging census
([`PAGING_CENSUS_190.csv`](../evidence/1.9.0/live/PAGING_CENSUS_190.csv), every listing answer of the ten
collector runs of 2026-11-09, read from the stored pages) counts 208 answers. 202 were asked without rendering, and
the provider rendered 13 of them anyway (its own metadata): 10 without tiles and 3 with. Of the 189 it brought
unrendered, 183 carried their tiles, 4 were listings showing 0 results and 2 came without tiles (asked again). 6
answers have no provider metadata in the log: their sessions were ended by the hard kills of S5b and S5b2 before the
session's summary was written. Each answer without tiles was asked again, as designed, and read on the next answer,
except the 3 rendered answers whose state repeated page 1 (§3.3), which ended their listing like any repeated page.

### 3.2 Two forms of the listing answer (2026-11-02, 2026-11-06, 2026-11-09)

The page state of a listing answer (`productsInfo`) comes in two forms:

- **Form A** holds the listing's filters, `availability`, `brands` (each brand with its count at this store and
  fulfillment) and `departments` (the child listings), then the counts and the search id. Every Q2 answer listing
  products on 2026-11-02 was form A (58 of 58).
- **Form B** holds only `waysToShop`, `totalCount`, `availableCount`, `searchId` and `promotions`. The six pages O2
  saved on 2026-11-06 were form B.

Both forms state `areLazyFacetsEnabled: true` among the site's settings, so that setting does not tell them apart.
On 2026-11-09 the census column `brand_facet_in_state` gives each answer's form: form A in **50 of the 203 answers
listing products** (41 of them from 14:31Z to 14:57Z, 9 later), form B in the others. The form changed from one answer
to the next: in the 61 listings with both a page 1 and a page 2 in one run, page 2 had page 1's form in 56 (47 B then
B, 9 A then A) and not in 5.

**What form B does to a run:**

- a page N in form B lists page 1's products (§3.3): all 54 repeated answers were form B, and all 33 distinct page-N
  answers were form A;
- a page 1 in form B gives 1.9 no brand list and no child listing, so a listing above the 250-result window cannot be
  split (M1, M2): it is read page by page, its reachable 250 at most, and it ends incomplete with its reason. Nothing
  is guessed in their place: brands gathered from the products read would miss the brands of the products the window
  hides.

What decides the form (the site, the provider's route to it, the time) is not established.

### 3.3 Page N answered with page 1's products (2026-11-09)

Some answers for a listing's page N (N ≥ 2) listed exactly the products of its page 1. 1.9 judges such a page
`repeated`, counts nothing from it and ends the listing incomplete ("accessible pages exhausted; coverage incomplete:
page N repeats an earlier page exactly"); it asks nothing more for that listing in that run. The census gives each
answer's time, the page asked, the provider's request id and rendering, the products' ranks, the search id and the
form. The page-N answers by stage:

| Stage, revision | Asked (UTC) | Distinct | Repeated page 1 | Other |
|---|---|---|---|---|
| S1b, 1.9.0rc3 | 12:38 | 0 | 1 | |
| S4, 1.9.0rc3 | 14:31-14:37 | 14 | 8 | 1 asked again after an answer without tiles |
| S5a, 1.9.0rc3 | 14:42-14:45 | 11 | 1 | 1 without page number or products, asked again |
| S5b, 1.9.0rc3 | 14:47-14:52 | 5 | 2 | |
| S3, 1.9.0rc3 | 14:57 | 2 | 1 | |
| S5b2, 1.9.0rc4 | 15:16-15:18 | 1 | 4 | |
| S4b, 1.9.0rc4 | 15:54-15:58 | 0 | 10 | |
| S4c, 1.9.0rc4 | 16:01-16:09 | 0 | 25 | |
| S3b, 1.9.0rc4 | 16:13 | 0 | 1 | |
| S4d, 1.9.0rc4 | 16:25 | 0 | 1 | |
| **All** | | **33** | **54** | 2 |

What the answers show:

- **clustered in time, not tied to a listing:** S4 (1.9.0rc3) read Dog Treats and Dog Food pages 2-7 at
  14:31:50-14:33:28Z, then from 14:33:35Z to 14:36:47Z eight page-N answers in a row repeated page 1; six minutes
  later (S5a, 14:42-14:45Z) pages 2 and 3 of four of those listings were distinct. From 15:16Z, 41 of the 42 page-N
  answers repeated (S5b2, S4b, S4c, S3b, S4d);
- **a repeated answer is a new search, not a stored copy of page 1:** each has its own search id (54 of 54 differ
  from page 1's), its state says it loaded the page asked (`loadedPages` [N], 54 of 54) and it ranks its products
  from 24 × (N−1) + 1 (54 of 54: page 2 ranks 25 to 48), yet the products are page 1's;
- **it is not caused by the revision:** 1.9.0rc3 read later pages at 14:31-14:33Z and met the repeat from 14:33:35Z;
  1.9.0rc4 changes nothing in the request or the reading of a page;
- it met unrendered answers (50 of the 54) and answers the provider rendered (3) alike.

No identity was rotated and no page was asked with a changed address to get around it. The proposed change (§15): a
form-B answer where form A is needed is set aside and asked again later in the same run, a bounded number of times,
each submission reserved as usual; the listing stays incomplete if form A does not come.

## 4. M1 and M2: brand readings and filter binding

- **M1.** 1.8.0rc5 named a brand reading `<listing>~<brand>` cut at 64 characters, so two brands of one listing
  sharing their first 58 characters got one ID and the second reading was dropped by the idempotent insert. 1.9's
  ID is a digest of the reading's full identity (retailer, store, fulfillment, listing, filter, exact value); the
  descriptor travels with the node, the task and the page rows (migration 0005); a reading planned before 1.9.0 is
  refused on resume. Tests: `test_partition_identity` (11, on the real pages L11 and L20) and
  `tests/integration/test_partitions_190.py` (13 with the 1.9.0rc4 regression).
- **M2.** A page counts for a brand reading only when the page itself states that filter
  (`requestVars.brandName`), no other facet, is its latest search (`latestResponseSearchId` equal to
  `productsInfo.searchId`) and finished loading; otherwise its verdict is `wrong_filter` or `unbound`.
  [`BINDING_SCAN.csv`](../evidence/1.9.0/m2_binding/BINDING_SCAN.csv) records what 99 saved pages of 2026-11-02 state
  (93 loaded and bound, 1 still loading, 5 without a search state).
- **Live: not exercised.** S3 (1.9.0rc3) chose 02001 Milk, 251 products in Q2's count: it now states 246, inside the
  window, so no brand reading was planned (77 of 246 read; page 4 repeated). S3b (1.9.0rc4, 16:12Z) chose 18010
  Natural & Organic > Frozen: 273 products, 250 reachable, above the window; its page 1 came in form B (§3.2), with
  no brand and no child listing, so no reading could be planned, and its page 2 repeated page 1 (24 of 273). M1 and
  M2 remain verified offline only, on real pages of 2026-11-02. **Brief item "an above-window category with a
  complete partition union on the final revision": not met**; it needs a page 1 in form A for an above-window
  listing on the final revision (change C1 of §15 sets a form-B page 1 aside and asks it again), then a live union.
- **The S3b outcome closed in the ledger is corrected here.** Written when the stage closed (16:14Z), it says the
  brand list "is no longer in the page the collector reads", that the filters load "in a later request made by the
  page's scripts", and that a second run "would meet the same page state". The census made afterwards found the
  brand list in 50 answers of the same day (form A, §3.2), and what supplies the filters to a form-B page is not
  established. The outcome describes S3b's own answer, not the site: a later run may receive form A. A closed ledger
  outcome is part of the hash chain and is not amended.

## 5. M3: the two price-per-measure examples

Both are traced to Q2's saved pages, nodes and hashes in
[`PPM_RECONCILIATION.csv`](../evidence/1.9.0/m3_ppm/PPM_RECONCILIATION.csv) and
[`PPM_TRACE.json`](../evidence/1.9.0/m3_ppm/PPM_TRACE.json), with minimal excerpts of each card and state:

| UPC | Exported | What the source shows | Conclusion |
|---|---|---|---|
| 0084024314377 (12 ct / 2.6 oz) | `$19.99/oz` | the card's sizing slot shows `$19.99/oz`; the product data states `equivalizedUnitPrice` 19.99 PER OUNCE | source-value anomaly: the site states it |
| 0001280052496 (Headlight, 1 Count) | `$7.99/oz` | the card shows `$7.99/oz`; the product data states 10.49 PER OUNCE | source-value anomaly: the card states it, and the data disagrees |

The extraction took the card's slot text as displayed, with no arithmetic. Nothing is computed or corrected: the
value is exported as displayed, and 1.9 flags such records (`PPM_EQUALS_ITEM_PRICE`: the amount equals the item price
on a multi-unit pack; `PPM_UNIT_FAMILY_MISMATCH`: a measure unit for a pack stated as a count, or the reverse).
[`PPM_ANOMALY_CENSUS_Q2.csv`](../evidence/1.9.0/m3_ppm/PPM_ANOMALY_CENSUS_Q2.csv) lists the 54 Q2 records the two
rules flag. `unit_price` stays empty.

## 6. M4: complete coupon terms

**Where the terms are.** Stage O1 (2026-11-06 18:35-19:17Z, 16 requests, 14 results, USD 0.021) tried the routes.
The coupons API through the provider failed twice (HTTP 500 from the provider, not charged). The product's own page
holds the complete terms in its Savings section, and its coupons load only when the page's scripts run: the
provider's own answer stated `run_js` true for **1 of 14** product pages requested with rendering. The documented
contract has no option to wait for them.

**What 1.9 does.** With `coverage.read_product_terms` on, a product's page is read (rendered, once per product and
run, never retried, within `--max-term-reads`) for each coupon's ID, headline, complete terms, displayed expiry,
clipping instruction and qualifying products. A coupon attaches only to the product whose page shows it. Savings
wording ("Save $10.00 on 2") leaves `digital_deals_price` empty; nothing is subtracted or divided. A coupon whose
terms were not read keeps its headline, flagged `DIGITAL_TERMS_UNREAD`; a rendered page that disagrees with the card
is flagged `DIGITAL_TERMS_CONFLICT`. Since 2026-11-06 no tile shows a coupon, so unless the product's page was read
rendered, a tile's digital fields say the coupon is unknown (missing kind `not_attempted`, flag
`DIGITAL_COUPONS_UNOBSERVED`); with the read on, every tile's product is a candidate, within the read limit.

**The four examples:**

| UPC | Q2 headline | 1.9 evidence |
|---|---|---|
| 0001780014939 | Coupon: Save $10.00 on 2 Purina ONE | **complete**: coupon 4257015, "Save $10.00 on any TWO (2) Purina ONE Dry Dog Food bags (8 lb or larger) or Wet Dog Food 12-count packages (13 oz cans). Mix or match.", the legal text ("Limit of one coupon per household." among its restrictions), "Exp. Nov. 10", "Sign In To Clip"; the cash-back offer 4257014 left out by the shipped setting `include_cashback_in_digital: false`, with its reason. From the rendered page saved by O1 |
| 0001780014941 | the other Purina ONE example | page brought unrendered: terms unread, flagged |
| 0002310014848 | Coupon: $6.99 Temptations Cat Treats | page brought unrendered: terms unread; the $6.99 is not exported without its terms |
| 0003980014995 | Coupon: Save $1.00 on Energizer | page brought unrendered: terms unread |

**Live on 2026-11-09 (S1b, 1.9.0rc3):** with `--max-term-reads 8`, eight Cat Food product pages were asked rendered.
The provider rendered two (25.4 s and 16.7 s), and neither showed a coupon; it brought six unrendered (3.6 to 5.0 s),
whose products keep `DIGITAL_COUPONS_UNOBSERVED`. So 2 of 8 rendered, against 1 of 14 on 2026-11-06.

**The Coupons page** (row 0, read once by every run, always rendered by the provider: 13.3 to 88.7 s) showed 24
coupon cards in 5 of the 10 reads of 2026-11-09 (S5a, S4b, S4c, S3b, S4d) and none in the others (S1b, S4, S5b, S3,
S5b2), with the store verified each time; which answer the page gives is not predictable from the request.

**The 42 Energizer records** ([`m4_energizer42/`](../evidence/1.9.0/m4_energizer42/)): in Q1c (2026-11-02
12:41-12:45Z) 42 cards showed "Coupon: Save $1.00 on Energizer"; in Q2 (13:34-13:37Z) the same 42 cards showed no
savings zone. Whether the retailer or the provider changed is not established, and no cause is assumed.

**M4 stays partial:** complete terms are established for one of the four examples, and on the current site digital
deals are visible only on product pages the provider renders. The read stays off by default.

## 7. M5: CSV rows, Cat Food and the 250-result window

- **What 1.9 read live** (each row narrowed as stated; none of these is coverage of a whole row unless it says so):
  rows 22-27 in full in S4 (1.9.0rc3) and S4b (1.9.0rc4); rows 23-26 in S5a, S5b and S5b2; Milk (row 8) in S3;
  Frozen (row 10) in S3b; 31 listings of rows 1-21 measured at 18 to 48 products in S4c; the 30 single-page listings
  of rows 1-21 in S4d (29 complete, among them all six listings of row 6, Floral). Listings completed by at least one
  1.9 run: 46 (column `completed_by_1_9_stages` of the queue).
- **The queue.** [`INCOMPLETE_QUEUE_190.csv`](../evidence/1.9.0/live/INCOMPLETE_QUEUE_190.csv) lists every listing of
  the shipped CSV (rows 1-22 through the taxonomy seed's menu, rows 23-27 through their roots, row 0 the Coupons
  route), its size in the census of 2026-11-02, the latest state a 1.9 run recorded and what is still needed. Of
  its 303 entries: the Coupons route; 42 listings complete in their latest 1.9 run (40 done and 2 empty; 444
  products); 38 incomplete, each stopped at a repeated page (2,659 products stated, 965 read); 222 not yet collected
  by 1.9 (72 measured on 2026-11-02 at 11,244 products, 11 of them above 250 with 4,934; 150 not measured). A later
  run's state replaces an earlier one: a listing read completely in one run and incompletely in a later one is
  listed as incomplete, because each run is judged on its own. Hard Cider's menu link lacks the slash before its id
  (`/pl/hard-cider08194`); 1.9 asks a menu link as the site gives it, so the listing was left out of S4d rather than
  spend a submission on an address the site may not serve.
- **Cat Food, 231 of 232** ([`m5_catfood/`](../evidence/1.9.0/m5_catfood/)): Q2 read its 10 pages, 232 organic slots,
  reported total 232. The site showed 0002310014492 twice, at page 7 slot 24 and page 8 slot 1, so 232 slots held 231
  products and the 232nd was never shown on any page. The live re-read could not settle it: in S1b (12:38Z), S4
  (14:34Z) and S4b (15:55Z) Cat Food's page 2 repeated page 1, so each read stopped at 24 of 232.
- **Above the window:** the census estimate of 1.8.0rc5 counts 20 categories above 250 (11,034 products) among those
  the measured rows name ([`FULL_SCOPE_ESTIMATE.json`](../evidence/census/FULL_SCOPE_ESTIMATE.json)); among the
  listings 1.9 reads (the queue), 13 measured on 2026-11-02 are above 250 (5,464 products): 11 not yet collected by
  1.9, Milk (246 now, inside the window) and Frozen (273, 24 read in S3b). 1.9 splits them only by the filters a
  form-A page 1 carries (§3.2); with a form-B page 1, a listing stays incomplete beyond its reachable 250.
- Row 0 (Coupons) lists offers, not products: the collector reads it as its Coupons route (§6), not as a product
  listing.

## 8. M6: offers, sizes and prices

- **Offers re-observed by O1:** Nutrl's "Buy 1 Save $2" is a current MUST_BUY promotion (2026-09-16 to 2027-01-05), not
  a volume deal; Cutwater and The Finnish Long Drink state no offer now. Since 1.8.0 "Buy 1 Save $N" is not a volume
  deal (C02, C03), and these product pages are now regressions.
- **Sizes:** the dip shows "2 tbsp" (a serving) while its data states 8 OUNCES; the serving is never the pack size.
  Q2's three unresolved size cases are unchanged on the product pages and stay reported, not guessed. "N/A" and
  "Count" are not pack sizes (1.9.0rc2; Q2 exported them).
- **Prices:** the ten one-cent conflicts keep both values (`ONE_CENT_TRUNCATION_PATTERN` describes a pattern, not a
  cause); the three prices without a stated store stay `exported_not_valid`; "Prices May Vary" is not out of stock.
  The stages of 2026-11-09 kept their price conflicts out of the valid count (S4: 14, S4c: 5; each run's
  `products.csv` in [`live/`](../evidence/1.9.0/live/)).
- **Approximate weights:** S4c's five whole turkeys priced by weight ("10-14 lbs") are `excluded` (`APPROX_WEIGHT`),
  as the data contract requires.

## 9. M7: T05, T06, T07 and the three mutants

| | Reproduced on the earlier code | Fixed in | Result on 1.9 |
|---|---|---|---|
| **T05**, probe replay with an unusable `replay.json` | 1.7.2: three of the four unusable inputs ended in a traceback with exit 1 and the malformed one with exit 2, and in all four the output folder and an offline ledger were already created ([`t05_repro_172.txt`](../evidence/1.9.0/repro/t05_repro_172.txt)) | probe 1.7.3 `95f96a0` | each refused in one line with exit 2; no output folder, no ledger ([`t05_repro_173.txt`](../evidence/1.9.0/repro/t05_repro_173.txt)); 23 tests, 22 of them fail on 1.7.2 |
| **T06**, the final segment's end in the export | `ac114d7`: the test fails, 4 of 4 cases: the export gives the finished segment no end time where the segment has one (`assert (None == '2026-11-09T12:21:20.891770Z')`) and has no `end_state` ([`t06_repro_ac114d7.log`](../evidence/1.9.0/repro/t06_repro_ac114d7.log)) | 1.9.0rc1 `b0f9191` | `test_segment_end_t06.py` passes (normal end, graceful stop, resume, failed export, and a kill that keeps only its bounds); live, every segment of 2026-11-09 has its end, and S5b2's killed segment kept its bounds (§10) |
| **T07**, a provider-error pause named a limit | 1.8.0rc5 `ee5ec99`: the test fails: the pause after twelve provider failures is recorded as `RUN_LIMIT_REACHED`, and `RUN_PAUSED_ON_FAILURE` is absent ([`t07_repro_ee5ec99.log`](../evidence/1.9.0/repro/t07_repro_ee5ec99.log)) | `ea296c7` | `RUN_PAUSED_ON_FAILURE`; `RUN_LIMIT_REACHED` only for limits; `RUN_PAUSE_REQUESTED` for an operator |

**The mutation commitment of 1.8.0rc5** (8 of 11 mutants run then): the remaining three, run by the same method
([`mutants_190.json`](../evidence/1.9.0/tests/mutants_190.json)): all three are caught by the listing-page regressions (`tests/integration/test_listing_pages.py`, 29 tests), run on 1.9.0rc4 (`8abc2c1`, no tracked file changed): a page without its cards counting fails 1 test, a capped page counting as completed fails 1, recovery waiting for room fails 2; the control, the same 29 tests on the unchanged copy, passes 29 of 29

## 10. M8: concurrency, runtime and a proposed production configuration

**Implemented and tested offline:** `limits.max_concurrent_listings` (1 to 4, default 1), each lane with at most one
request in flight, sharing the run's ceiling, limits and checkpoints, a lane that stops the run halting the others;
durable task leases and reclaim (from 1.8); the account-wide gate (reserve before dispatch, settle with the
provider's request id, hold as unknown when unanswered); `collection.schedule.capacity`, whose tests state the
shipped schedule's capacity: with Monday/Thursday 07:00, the 07:00-19:00 window and `max_run_minutes` 2880, a Monday
run has 36 collection hours (72 elapsed) and a Thursday run 48 (96 elapsed); an unfinished run is superseded at the
next occurrence.

**The two-lane defect (N17), found live.** In S5b (1.9.0rc3, two lanes) six of the run's 13 listing-page rows had no
stored page linked, no HTTP status and no duration, though every page file was stored: the session's pages were
written to the database by whichever lane saved first, including a page whose answer had not arrived, and such a row
was never completed. G13 (integrity) rejected the run, as designed. One lane was never affected (S4: 43 rows, S5a:
19 rows, none without its page). **1.9.0rc4** keeps a fetch out of the database until its answer is processed. The
regression `test_two_lanes_never_save_a_page_whose_answer_has_not_arrived` (two lanes, one answer held back while the
other lane saves) fails on 1.9.0rc3 with G13 FAIL and passes on 1.9.0rc4
([`rc4_lanes_on_9090537.log`](../evidence/1.9.0/repro/rc4_lanes_on_9090537.log),
[`rc4_lanes_on_8abc2c1.log`](../evidence/1.9.0/repro/rc4_lanes_on_8abc2c1.log)).

**Interruption, overlap and resume on the final revision (S5b2, 1.9.0rc4, two lanes, rows 23-26),** from
[`s5b2_steps.json`](../evidence/1.9.0/live/s5b2_steps.json) and the step logs in
[`live/S5b2/`](../evidence/1.9.0/live/S5b2/):

| Step (UTC) | What was done | What the collector did |
|---|---|---|
| 15:15:17 | run | store verified; canary passed (Candles page 1: 13 valid, source check 13 of 13) |
| 15:15:57 | Ctrl+Break (graceful stop) | exit 75, run interrupted and resumable; segment ended with its end; the two requests in flight held as unknown |
| 15:16:00 | resume | the two unanswered pages asked again (their first requests stay held) |
| 15:16:15 | a second start while the resume runs | refused in 1.1 s, exit 9 (the store has an unfinished run); no reservation |
| 15:16:16 | hard kill of the resume (`taskkill /F /T`) | two requests in flight became unknown through the ledger's lease recovery |
| 15:18:34 | resume after the lease expired | run recovered; the killed segment closed as abandoned with its bounds (15:16:13.600Z to 15:18:34.087Z); 2 task leases reclaimed from their checkpoints; to the end, exit 0 |

Every page row of the run has its stored page, status and duration (G13 PASS). **No completed page was asked
again**; each of the four pages asked twice had no answer the first time, and those four first requests stay held at
their worst case (USD 0.0060). The run was rejected by G3 and G14: all four listings met the repeat of §3.3.

**Timing measured on 2026-11-09** (one lane unless stated; from the census and the stage logs; samples of one day,
not a full run):

| Request (2026-11-09) | Answers with a time | Median | Range |
|---|---|---|---|
| listing page, asked unrendered and brought unrendered | 187 | 5.1 s (90th percentile 8.9 s) | 2.9 to 52.1 s |
| listing page, asked unrendered and rendered by the provider anyway | 12 | 33.7 s | 27.5 to 45.7 s |
| the Coupons page (rendered every time) | 10 | 29.1 s | 13.3 to 88.7 s |
| product page asked rendered (S1b), rendered | 2 | | 16.7 and 25.4 s |
| product page asked rendered (S1b), brought unrendered | 6 | | 3.6 to 5.0 s |

Listing answers from the paging census ([`PAGING_CENSUS_190.csv`](../evidence/1.9.0/live/PAGING_CENSUS_190.csv)): 13 of the 202 asked unrendered were rendered by the provider, 12 of them with a time; 6 answers have no provider metadata (sessions ended by the hard kills of S5b and S5b2). The Coupons page from each run's `page_fetches` table, the product pages from S1b's log.

One lane read 188 submissions (one of them a provider failure, settled free) in 1,931.7 s of active collection over the five one-lane runs S4, S5a, S4b, S4c and S4d (each run's `collection_segments` table): 10.3 s per submission, 8.7 to 12.7 by run. The two-lane runs were interrupted on purpose and met different repeats, so they do
not measure the gain of a second lane; that comparison is still to be made on 1.9.0rc4 without interruptions.

**Extrapolation, not a measurement:** at about 10.3 s per submission with one lane, the full scope with brand
partitions (3,928 to 6,277 submissions per run in the 1.8 estimate) would take about 11 to 18 hours, inside the shipped
schedule's 36 hours; but only if the listings are answered in form A (by the site itself, or recovered by C1 of
§15), so that later pages are distinct and the filters present (§3.2, §3.3), and only a full run establishes it.

**Proposed production configuration** (not enabled; the schedule stays off until the client authorizes one):

| Setting | Proposal | Why |
|---|---|---|
| lanes (`max_concurrent_listings`) | **1**; 2 only after an uninterrupted comparison on 1.9.0rc4 | the correction of N17 held live (S5b2), but the gain of a second lane is not measured |
| in flight | 1 per lane | a lane's pages stay ordered; filter and store context never cross lanes |
| retries | as shipped: 3 attempts on 408/429/5xx with backoff; product-terms reads once | every attempt reserved at its worst case |
| segment | `max_segment_minutes` 300 | unchanged |
| logical run | `max_run_minutes` 2880, window 07:00-19:00 America/Chicago, continuation on | unchanged until measured |
| occurrences | Monday and Thursday 07:00 America/Chicago | DST-aware (tested for 2026-11-01 and 2027-03-14) |
| an unfinished occurrence | continue its run (not supersede) until it completes or reaches 2880 minutes; the next occurrence waits as backlog | supersession throws away paid pages; proposal, to be tested on the cadence |
| pause and stop | `stop` ends collection and the run is finalized with what it collected; an incomplete run is never published | as shipped; seen live in S5b2 |
| product-terms reads | off; when on, a per-run limit | 1 of 14 rendered on 2026-11-06, 2 of 8 on 2026-11-09 |

**Readiness, kept apart:** implementation and offline tests: done for lanes, gate and capacity; the two-lane save
corrected and verified live. Measured full-run feasibility: **not established** (blocked by the form-B answers of
§3.2 and §3.3, then a full run). Observed twice-weekly operation: **not started** (needs the client's authorization of a schedule, then two
weeks of observations).

**Cost** ([`COST_AND_RUNTIME_REPORT.md`](COST_AND_RUNTIME_REPORT.md) §0): the submissions are as in the 1.8 estimate
(scenario B, all rows: 3,928 to 6,277 per run, USD 5.89 to 9.41 per run at USD 0.0015 per result, about USD 51 to 82
a month twice weekly). That rate is Oxylabs' published list price for "Custom domain, JS" (USD 1.50 per 1,000,
read 2026-11-03), used as a worst case; it is **not a confirmed account rate**, and unrendered requests may be billed
lower. The re-ask of C1 (§15) would add at most 2 submissions per form-B answer it sets aside.

## 11. M9: live stages, retention, recovery and publication

**Every stage of this task** (in [`live/`](../evidence/1.9.0/live/), each stage's folder holds its ledger stage
record `stage.json` with command, configuration hashes, revision, objective, ceilings, deadline, retry policy and stop
conditions, its commands `run.jsonl` and its logs; the outcomes as closed in the ledger are in
[`LEDGER_STATUS.json`](../evidence/1.9.0/budget/LEDGER_STATUS.json)):

| Stage (2026-11-09 unless stated) | Revision | Run | Submissions | Result |
|---|---|---|---|---|
| O1, S1, O2 (2026-11-06) | 1.9.0rc1 for S1 | S1: `01M6S5MYBC05W3S308EC7XWTGV` | 28 rows, 26 results | the site's change found (§3.1); S1 stopped as designed |
| S1b, 12:36-12:39 | 1.9.0rc3 | `01M704YFEYRM4ZD5WNW3S7WVH8` | 13 | canary passed on the new tile; Cat Food page 2 repeated (24 of 232); 8 product-terms reads (§6); 23 fresh valid; G3, G14 FAIL |
| S4, 14:30-14:38 | 1.9.0rc3 | `01M70BG79WGW9EC5ZTW2M4V4XS` | 43 | rows 22-27: 7 listings done, 2 empty, 8 stopped at a repeated page; **552 fresh valid**; G3 FAIL only |
| S5a, 14:41-14:45 | 1.9.0rc3, one lane | `01M70C404FTCMYSY621EKJ015X` | 19 | rows 23-26: Batteries 96 of 96, Light Bulbs 100 of 100, Candles 56 of 57, School Office 74 of 113; 306 fresh valid; G3, G14 FAIL |
| S5b, 14:46-14:52 | 1.9.0rc3, two lanes | `01M70CD8PJQS3QDMWR5AXPS39P` | 20 (3 unknown) | signal, refused start, kill, resume; **G13 FAIL: the two-lane defect** (§10); 182 fresh valid |
| S3, 14:56-14:57 | 1.9.0rc3 | `01M70CYWNRZNS4NCZVDX2X13XK` | 6 | Milk states 246: no brand reading; 77 of 246 (page 4 repeated) |
| S5b2, 15:15-15:19 | 1.9.0rc4, two lanes | `01M70E1GNA85H05HDM45F5XQRS` | 17 (4 unknown) | signal, refused start, kill, resume; **G13 PASS**; no completed page asked again; 115 fresh valid |
| S4b, 15:52-15:58 | 1.9.0rc4 | `01M70G5ZEPFG1GVT2H5QWPVQKJ` | 32 (1 free) | rows 22-27: every page 2 repeated (10 of 10); 243 fresh valid; G3, G14 FAIL |
| S4c, 16:00-16:10 | 1.9.0rc4 | `01M70GKE2KJF0D6CKSY04VD8YK` | 59 | 31 listings of rows 1-21: 6 done, 25 stopped at a repeated page 2 (25 of 25); **700 fresh valid, all verified; G3 FAIL only** |
| S3b, 16:12-16:14 | 1.9.0rc4 | `01M70H9RB4Q736926MP3W5117A` | 4 | Frozen 273 (above the window): no filter in the page, no brand reading; 24 of 273; 23 fresh valid |
| S4d, 16:20-16:25 | 1.9.0rc4 | `01M70HRZQX1KXHZQVNMS1KDCPK` | 35 | the 30 single-page listings of rows 1-21 in the queue: 29 done (285 products), Dinnerware 24 of 34 (page 2 repeated); 294 fresh valid; G3, G14 FAIL |

The store and PICKUP were verified on every check of every run (preflight, each task start, periodic, final:
53100502, PICKUP). Each run's records, coverage, pages, validation report and manifest are in
[`live/`](../evidence/1.9.0/live/), with the stored pages identified by SHA-256 (the raw answers are kept privately).

- **The final revision's qualification:** S4c, above. The S4 run of 1.9.0rc3 (552) is kept as what it is, a run of
  the previous candidate.
- **Fresh and carried:** every count of "fresh valid" above is of records observed in that run; the records carried
  from earlier runs (historical, flagged `CARRIED_FORWARD`, 591 to 2,001 per run) are never counted as fresh. No
  natural disappearance or stock transition was observed; none is manufactured. Q2 re-observed all 362 Q1c identities
  and carried none, so it does not prove natural carry-forward either.
- **Publication protections, seen live:** no run of this task was published (`publish.auto: false` in every stage
  configuration, and every run rejected): G3 rejected every run with an incomplete listing, G13 rejected S5b for its
  pages without their stored capture, G14 rejected the runs with fewer than 500 valid records. Q2 stays rejected for
  its original completeness failures; Q1c's local publication of rows 23-26 stays a scoped demonstration, not a
  production publication.

## 12. M10 and the client's VM

**The adapter's identity:** the Mariano's Classic adapter is `classic-probe/src/classic_probe/marianos.py`, blob
`9de6510bddbb0cae7fd86e09dac5ed32fc3487a4`, in the shared probe 1.6.0 (`classic-probe/`, Git tree
`33c2d786fa793e2e588746f219eb9118cc789c38`, publication revision `1f568b8d367ee90e0f4a87879a44873ae649e906`), separate
from Walmart's frozen 1.5.2 probe. The same blob is in 1.7.1, 1.7.2 and 1.7.3: the corrections C1 to C5 (1.7.0,
1.7.1) and T05 (1.7.3) are all in the shared layer. Probe 1.7.3 is published here, in
[`classic-probe-1.7.3/`](../classic-probe-1.7.3/) (tree `912801d038092bc84906f6e0c5507388980fb9d8`, development commit
`95f96a02329bd3a92c9c8b07dd53e53ae89fe553`); [`SHARED_CLASSIC_PROBE.md`](SHARED_CLASSIC_PROBE.md) pins it. Its
vendored copies of Mariano's `initial_state.py` and `sanitize.py` match 1.9.0rc4's files (the second with its
import line rewritten, as the probe's `VENDORED.json` records). The adapter replays real Web API page bodies inside
**synthetic** Classic envelopes; it plans search page 1, product and category-URL steps and **no page 2**: no
documented Classic page parameter for Mariano's was found, so full Classic pagination is not proved, and live mode
stays disabled. The useful collector work uses the Web API route that works.

**The client's VM** `hamza-test-vm` is deallocated. At the client's request no SSH attempt was made, no rule or key
was changed and the VM was not started. The checks wait for the client to confirm the restart window and install
`scraper_client_test_v2.pub` with the old key revoked ([`ACCEPTANCE_RUNBOOK.md`](ACCEPTANCE_RUNBOOK.md) §2).

## 13. M11: the 29 earlier audit items, and corrections

[`AUDIT_29_RECONCILIATION.csv`](AUDIT_29_RECONCILIATION.csv) gives each group of the 29 items its 1.9 state;
[`ACCEPTANCE_MATRIX.csv`](ACCEPTANCE_MATRIX.csv) now has the columns `status_1.9.0rc4` and `evidence_1.9.0rc4` beside
the 1.8.0rc5 ones, which are unchanged. Corrections of earlier statements:

- the old M43 first-page parallel proof does not close full-pipeline partition concurrency; the old M42 Azure
  evidence does not cover the new revision or the client's VM; M26's "live In Store example" wording does not
  override the Vernon Hills PICKUP target; B29's verified source links do not prove product-page access;
- page 2 is implemented; four digital descriptions exist in Q2 but their terms were incomplete; the six Q2 category
  labels are rows 22-27, not all 28 CSV rows;
- the brand readings of 1.8.0rc5 and 1.9 rely on filters that only a form-A answer carries (§3.2): every answer
  listing products on 2026-11-02 was form A, 50 of 203 on 2026-11-09; what the 1.8.0rc5 report says about reading
  above-window listings by brand holds for form-A answers only; the S3b outcome closed in the ledger is corrected
  in §4;
- **the Casablanca offset of 2026-11-02 was checked and is UTC+0**, as the 1.8.0rc5 report says: Morocco returned to
  GMT on 2026-09-20; the IANA time-zone database 2026e and Windows' own "Morocco Standard Time" give
  +00:00 for that date. The request to change it to UTC+1 was therefore not applied; the statement now cites its
  source ([`manifests/DOC_CORRECTIONS.md`](../manifests/DOC_CORRECTIONS.md)).

The Walmart clarification that blanks four deal fields applies to Walmart only; Mariano's volume and digital
fields are unchanged.

## 14. The shared trial budget (one ledger for Walmart and Mariano's)

Campaign `oxylabs-trial-20261103`: cap USD 5.00 in total for both projects, USD 0.50 uncertainty headroom inside it,
envelopes USD 2.25 per retailer; every submission reserved at its worst case before dispatch under an exclusive lease;
settled at the list rate (rule estimate, USD 0.0015 per result) or as documented free (a provider 5xx); unanswered
submissions held as unknown at their worst case and never assumed free. The hash chain verifies (chain_ok true over 5,560 events).

| Ledger, USD at the reservation rate | Envelope | Settled | Unknown, held at worst case | Committed | Spendable |
|---|---|---|---|---|---|
| Campaign, both projects | cap 5.00; headroom 0.50; allocatable 4.50 | 2.6220 (1,748 results) | 0.0345 (23 submissions) | 2.6565 | **1.8435** |
| Walmart (its own tasks; not used by this one) | 2.25 | 2.2230 (1,482 results) | 0.0240 (16) | 2.2470 | 0.0030 |
| **Mariano's** (276 submissions) | 2.25 | 0.3990 (266 results; 3 submissions settled free) | 0.0105 (7) | 0.4095 | **1.8405** |
| of which 2026-11-06: O1, S1, O2 (28) | | 0.0390 (26 results; 2 free) | 0 | 0.0390 | |
| of which 2026-11-09: ten stages (248) | | 0.3600 (240 results; 1 free) | 0.0105 (7) | 0.3705 | |

No top-up, overage or other provider was used; the client's account was not used. Read at 2026-11-09 17:34:54Z
([`LEDGER_STATUS.json`](../evidence/1.9.0/budget/LEDGER_STATUS.json); every Mariano's row in
[`LEDGER_ROWS_MARIANOS.csv`](../evidence/1.9.0/budget/LEDGER_ROWS_MARIANOS.csv)).

## 15. Open items, the smallest next live proposal, and milestones

**What stops full coverage now** (observed on the live site; not a defect of 1.9.0rc4's corrections): the form-B
answers of §3.2. A form-B page N repeats page 1, so its listing ends there; a form-B page 1 of a listing above the
window carries no filters, so the listing cannot be split.

1. **Proposed change C1, for its own review: ask a form-B answer again where form A is needed.** A page N that
   repeats page 1, and the page 1 of an above-window listing that carries no filters, are set aside; after the
   run's other listings, and at least 5 minutes after the answer, the same address is asked again, at most 2 more
   times, each submission reserved at its worst case; an answer still in form B leaves its listing incomplete as
   now. Optionally, a listing above 24 products whose page 1 came in form B has its page 2 set aside in the same
   way before it is asked (in the census, 47 of 49 such page 2s repeated), so no submission is spent on a likely
   repeat. Bound: 2 extra submissions per answer set aside. Evidence that a later answer can come in form A: S4
   then S5a (§3.3: pages that repeated at 14:33-14:36Z were distinct six minutes later). Evidence against: from
   15:16Z to 16:25Z, 41 of 42 page-N answers repeated, so C1 may recover little while form B persists; S6
   measures it.
2. **Contingency C2, only if form A does not return:** find what supplies the filters and the later pages to a
   form-B page (a request its scripts make), and whether that answer can be obtained within the provider's
   documented contract; then read the brand and child partitions from it, with M2's binding re-verified on the
   new source. Not dated: it depends on what the site exposes.

**The smallest next live proposal** (needs Hamza's approval of its ceiling; within the trial credit, after C1 is
implemented and verified offline as a new candidate):

| Stage | Command (collector) | Objective | Ceiling |
|---|---|---|---|
| S6 | `run --store marianos-53100502-pickup --categories 22,23,24,25,26,27 --max-credits 130` | whether C1 recovers form-A answers: rows 22-27 (17 listings, 1,190 products stated in S4) in one logical run, one lane | 130 submissions, USD 0.195 |
| S6b | `run --store marianos-53100502-pickup --categories 10 --subcategory 10:18010 --max-credits 86` | the above-window union on the C1 candidate: Frozen (273 products) by brand, if C1 obtains a form-A page 1 | 86 submissions, USD 0.129 |
| S7 | rows 1-21, the below-window listings of the queue, in runs of at most 200 submissions | progressive coverage of rows 0-21 from [`INCOMPLETE_QUEUE_190.csv`](../evidence/1.9.0/live/INCOMPLETE_QUEUE_190.csv) | per run 200 submissions, USD 0.30; in all at most what Hamza approves of the USD 1.84 left in Mariano's envelope |

The full scope with brand partitions (about USD 5.89 to 9.41 a run at the list rate) does not fit the trial credit
and waits for form-A answers (C1, or C2 if needed) and the client's account. Each stage's configuration, deadline, retry
policy and stop conditions are in [`NEXT_STAGES.json`](../evidence/1.9.0/budget/NEXT_STAGES.json).

**Milestones** (dates in UTC; none is promised before its condition):

| Milestone | Condition | Earliest |
|---|---|---|
| 1.9.0rc4 published for review, with the stages of 2026-11-09 | done | 2026-11-09 |
| C1 implemented and verified offline (new candidate) | Hamza's go-ahead for the change | 1 working day after the go-ahead |
| S6 and S6b on that candidate | C1 verified; Hamza's approval of the ceilings | the same day |
| S7, progressively | S6 shows form-A answers recovered; Hamza's approval | from the day after S6 |
| C2 investigation | only if S6 and S6b obtain no form-A answer; Hamza's go-ahead; a rendered capture of a listing page | 2 working days after the go-ahead, for the finding (not the change) |
| client VM checks (install, migrations, suites, Docker, offline replay) | the client's restart window and key installation | the agreed window |
| full scope with brand partitions | form-A answers (C1, or C2 if needed); the client's account and authorization | after the client's decision |
| schedule on, twice weekly | the client's authorization | then two weeks of observed occurrences |
| Classic | the client's choice and approval; a documented page contract | open |

## 16. Evidence for 1.9

[`evidence/1.9.0/`](../evidence/1.9.0/README.md): the live stages (stage records, commands, logs, each run's
exports, the paging census and the queue; the raw answers are kept privately and identified by SHA-256), the M2 to
M5 analyses, the reproductions, the test sessions and the budget extract. Redactions are listed with both hashes in
[`manifests/REDACTIONS.csv`](../manifests/REDACTIONS.csv).
