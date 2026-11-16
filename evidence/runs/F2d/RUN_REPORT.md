# Run report: run 01M7JNB2HDFCNR3GHQVX8FYXX6

Stages: M-F2a-full-run-110rc5-20261116, M-F2b-full-run-110rc5-20261116, M-F2c-full-run-110rc5-20261116, M-F2d-full-run-110rc5-20261116. Store marianos-53100502-pickup (location 53100502, PICKUP). Not a pilot (no command-line narrowing or limit).

## What was asked

- `M-F2a-full-run-110rc5-20261116`: `run --store marianos-53100502-pickup`; ceiling 200 submissions, USD 0.300000; deadline 2026-11-16T19:09:07Z; approved: Hamza's update of 16 November 2026 (recorded in the trial ledger as the event 'authorization_update'): live Mariano's collection with Hamza's Oxylabs Web API credit, tests on Hamza's Azure VM and scheduling on that VM are authorized, within the Mariano's envelope of the shared trial ledger; the client's VM, the client's billing and Oxylabs Classic stay outside it
- `M-F2b-full-run-110rc5-20261116`: `resume --store marianos-53100502-pickup`; ceiling 200 submissions, USD 0.300000; deadline 2026-11-16T19:36:35Z; approved: Hamza's update of 16 November 2026 (recorded in the trial ledger as the event 'authorization_update'): live Mariano's collection with Hamza's Oxylabs Web API credit, tests on Hamza's Azure VM and scheduling on that VM are authorized, within the Mariano's envelope of the shared trial ledger; the client's VM, the client's billing and Oxylabs Classic stay outside it
- `M-F2c-full-run-110rc5-20261116`: `resume --store marianos-53100502-pickup`; ceiling 200 submissions, USD 0.300000; deadline 2026-11-16T19:51:19Z; approved: Hamza's update of 16 November 2026 (recorded in the trial ledger as the event 'authorization_update'): live Mariano's collection with Hamza's Oxylabs Web API credit, tests on Hamza's Azure VM and scheduling on that VM are authorized, within the Mariano's envelope of the shared trial ledger; the client's VM, the client's billing and Oxylabs Classic stay outside it
- `M-F2d-full-run-110rc5-20261116`: `resume --store marianos-53100502-pickup`; ceiling 200 submissions, USD 0.300000; deadline 2026-11-16T20:54:11Z; approved: Hamza's update of 16 November 2026 (recorded in the trial ledger as the event 'authorization_update'): live Mariano's collection with Hamza's Oxylabs Web API credit, tests on Hamza's Azure VM and scheduling on that VM are authorized, within the Mariano's envelope of the shared trial ledger; the client's VM, the client's billing and Oxylabs Classic stay outside it
- Objective (first stage): one logical full-scope run of the final candidate 1.10.0rc5 (no command-line narrowing or limit: every CSV row 0-27 as configured, so the run is not a pilot), two lanes, read in slices of at most 200 submissions (USD 0.30), each one ledger stage whose ceiling is also set in the collector (set-ceiling). In 1.10.0rc5 a stop at a spending ceiling finalizes the run (observed in P2 on 2026-11-16), so every slice but the last is ended by the operator with SIGTERM (systemctl stop, by slice_stop.sh) once the stage has 190 reservations in the ledger: a resumable stop (exit 75); the requests in flight at that moment are held as unknown outcomes, charged against the ceiling; the ceiling, 10 above, is the backstop. The last slice runs to its ceiling, where the collector finalizes the run as a partial dataset, which is never published. The trial credit cannot complete the scope: the result is the run's coverage (listings DONE, EMPTY, INCOMPLETE, not reached), its measured submissions and cost per listing, and the census of listings not measured before. This slice starts the run. Operator check during it: a second start for the store is refused (exit 9) before any request (the harness gives it a gate that refuses every submission and takes no lease). This run is on 1.10.0rc5: 1.10.0rc4's full run F1 was stopped by the collector after 158 submissions (STORE_NOT_VERIFIED on a page brought before its search was made); rc5 asks such a page again.

## Code and segments

Revisions recorded by the run's segments: 1.10.0rc5 (bc19afe60c1016cf5d08d055abd96bc69c9d3dd1) (one revision for the whole run)

| segment | trigger | started (UTC) | ended (UTC) | active s | end state | stop code |
|---|---|---|---|---|---|---|
| 01M7JNB2R3TJEAQND0WK1E7TAY | manual | 2026-11-16 17:09:11.042249+00 | 2026-11-16 17:22:58.01823+00 | 827.0 | ended | TERMINATED |
| 01M7JPXCW0K5JNHJMH5G1Z55BG | resume | 2026-11-16 17:36:39.805907+00 | 2026-11-16 17:38:56.323088+00 | 136.2 | ended | PROVIDER_ERROR |
| 01M7JQ3CX9FQXVGWXSTXWJV9XT | auto | 2026-11-16 17:39:56.457345+00 | 2026-11-16 17:49:48.190093+00 | 591.7 | ended | TERMINATED |
| 01M7JQRAS20VSE08T4DV842NAE | resume | 2026-11-16 17:51:22.401334+00 |  | 159.9 | abandoned | TERMINATED |
| 01M7JR0RJS3K79H9EM732NZHJ0 | resume | 2026-11-16 17:55:58.680286+00 | 2026-11-16 18:09:04.299964+00 | 785.6 | ended | TERMINATED |
| 01M7JVC0T14G569KJVYSNKHWY7 | resume | 2026-11-16 18:54:33.28066+00 | 2026-11-16 18:55:17.604416+00 | 44.3 | ended | TERMINATED |
| 01M7JVDHZ62KK70J8R653656JA | resume | 2026-11-16 18:55:23.621664+00 | 2026-11-16 18:56:08.113059+00 | 44.4 | ended | STORE_NOT_VERIFIED |

## Submissions and cost (the shared trial ledger)

595 submissions reserved before dispatch: settled 586, unknown 9; results charged 583; USD settled 0.874500 at the recorded rate.

- `run --store marianos-53100502-pickup` (M-F2a-full-run-110rc5-20261116): 2026-11-16T17:10:18+00:00 to 2026-11-16T17:10:18+00:00, exit 9 after 0.2 s, revision bc19afe60c1016cf5d08d055abd96bc69c9d3dd1; gate counts null
- `run --store marianos-53100502-pickup` (M-F2a-full-run-110rc5-20261116): 2026-11-16T17:09:10+00:00 to 2026-11-16T17:22:58+00:00, exit 75 after 827.6 s, revision bc19afe60c1016cf5d08d055abd96bc69c9d3dd1; gate counts {"reserved": 190, "dispatched": 190, "unsent": 0, "settled": 188, "settled_free": 0, "unknown": 2}
- `resume --store marianos-53100502-pickup` (M-F2b-full-run-110rc5-20261116): 2026-11-16T17:36:39+00:00 to 2026-11-16T17:49:48+00:00, exit 75 after 788.9 s, revision bc19afe60c1016cf5d08d055abd96bc69c9d3dd1; gate counts {"reserved": 191, "dispatched": 191, "unsent": 0, "settled": 189, "settled_free": 0, "unknown": 1}
- `resume --store marianos-53100502-pickup` (M-F2c-full-run-110rc5-20261116): 2026-11-16T17:55:58+00:00 to 2026-11-16T18:09:04+00:00, exit 75 after 786.2 s, revision bc19afe60c1016cf5d08d055abd96bc69c9d3dd1; gate counts {"reserved": 144, "dispatched": 144, "unsent": 0, "settled": 139, "settled_free": 3, "unknown": 2}
- `resume --store marianos-53100502-pickup` (M-F2d-full-run-110rc5-20261116): 2026-11-16T18:54:32+00:00 to 2026-11-16T18:55:17+00:00, exit 75 after 44.8 s, revision bc19afe60c1016cf5d08d055abd96bc69c9d3dd1; gate counts {"reserved": 16, "dispatched": 16, "unsent": 0, "settled": 14, "settled_free": 0, "unknown": 2}
- `run --store marianos-53100502-pickup` (M-F2d-full-run-110rc5-20261116): 2026-11-16T18:55:21+00:00 to 2026-11-16T18:55:21+00:00, exit 9 after 0.2 s, revision bc19afe60c1016cf5d08d055abd96bc69c9d3dd1; gate counts null
- `resume --store marianos-53100502-pickup` (M-F2d-full-run-110rc5-20261116): 2026-11-16T18:55:23+00:00 to 2026-11-16T18:56:20+00:00, exit 7 after 56.7 s, revision bc19afe60c1016cf5d08d055abd96bc69c9d3dd1; gate counts {"reserved": 8, "dispatched": 8, "unsent": 0, "settled": 8, "settled_free": 0, "unknown": 0}

## Pages

576 answers asked as listing pages: by state completed 416, failed 3, reasked 12, refused 18, stopped 127; by verdict failed 3, malformed 17, new 425, partial_overlap 3, repeated 127, wrong_context 1.
Store checks on every answer: FAIL, N/A, PASS; locations 53100502; fulfillment PICKUP.

Requests set aside: 98 ({"exhausted": 13, "recovered": 66, "waiting": 19}); re-asks answered 111; new products brought by counted re-asks 1204; shortest time between two answers of one request 303.8 s.

## Products

Distinct fresh valid products (this run's own observations, status valid): **7678** in 15 categories; retained dataset 8104 records (verified None, carried from earlier runs 0).
Identity sets: `{"record_rows": 8118, "fresh_valid": 7678, "fresh_not_valid": 426, "carried_forward": 0, "excluded": 14, "excluded_rows": 14, "exported_rows": 8104, "retained_unique": 8104, "duplicates": 0, "overlaps": {"fresh_valid & fresh_not_valid": 0, "fresh_valid & carried_forward": 0, "fresh_valid & excluded": 0, "fresh_not_valid & carried_forward": 0, "fresh_not_valid & excluded": 0, "carried_forward & excluded": 0}, "relations": {"no identity is in two classes": true, "retained = fresh valid + fresh not valid + carried forward": true, "no exported identity twice": true}, "holds": true}`

## Coverage and gates

Listings: null; CSV rows: {"NOT_ATTEMPTED": 1, "INCOMPLETE": 26, "COMPLETE": 1}.

Gates: . Run status: rejected (None).

Listings not complete:

- row 1 Produce / Fresh Fruit (06111): 97 of 198, INCOMPLETE: accessible pages exhausted; coverage incomplete: page 5: page 5 repeats an earlier page exactly; asked again 2 time(s), each at least 300 s after the last answer or attempt: re-ask 1: repeated (page 5 repeats an earlier page exactly); re-ask 2: repeated (page 5 repeats an earlier page exactly); the re-asks are spent, which says nothing about where the listing ends: its remaining results were not read
- row 1 Produce / Fresh Vegetables (06112): 32 of 370, INCOMPLETE: the site's search lets the page reach 250 of the 370 results; the listing is read through 19 subdivisions the page itself names (Lettuce & Leafy Greens, Potatoes, Onions & Garlic, Peppers, Mushrooms, Tomatoes, Root Vegetables, Carrots, Squash, Broccoli & Cauliflower, Cucumbers, Beans & Peas, Cabbage, Corn, Artichokes, Brussels Sprouts, Celery, Asparagus, Eggplant) and is complete only when they cover its results
- row 1 Produce / Artichokes (0611200001): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 1 Produce / Beans & Peas (0611200002): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 1 Produce / Brussels Sprouts (0611200003): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 1 Produce / Cabbage (0611200004): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 1 Produce / Eggplant (0611200005): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 1 Produce / Root Vegetables (0611200006): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 1 Produce / Asparagus (0611200681): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 1 Produce / Carrots (0611200682): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 1 Produce / Corn (0611200683): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 1 Produce / Celery (0611200684): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 1 Produce / Broccoli & Cauliflower (0611200685): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 1 Produce / Mushrooms (0611200686): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 1 Produce / Cucumbers (0611200688): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 1 Produce / Peppers (0611200689): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 1 Produce / Tomatoes (0611200690): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 1 Produce / Potatoes (0611200691): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 1 Produce / Onions & Garlic (0611200692): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 1 Produce / Lettuce & Leafy Greens (0611200694): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 1 Produce / Squash (0611200695): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 1 Produce / Organic Produce (18003): 127 of 128, INCOMPLETE: accessible pages exhausted; coverage incomplete: 6 page(s) read, 127 distinct products of 128 reported
- row 2 Meat / Pork & Ham (05006): 84 of 85, INCOMPLETE: accessible pages exhausted; coverage incomplete: 4 page(s) read, 84 distinct products of 85 reported (the source's total changed during the read: [84, 85])
- row 2 Meat / Bacon & Breakfast Sausage (05017): 100 of 100, INCOMPLETE: accessible pages exhausted; coverage incomplete: page 4: page 4 repeats an earlier page exactly; asked again 2 time(s), each at least 300 s after the last answer or attempt: re-ask 1: repeated (page 4 repeats an earlier page exactly); re-ask 2: repeated (page 4 repeats an earlier page exactly); the re-asks are spent, which says nothing about where the listing ends: its remaining results were not read
- row 3 Seafood / Canned Seafood (0100600007): 51 of 157, INCOMPLETE: accessible pages exhausted; coverage incomplete: page 3: page 3 repeats an earlier page exactly; asked again 2 time(s), each at least 300 s after the last answer or attempt: re-ask 1: repeated (page 3 repeats an earlier page exactly); re-ask 2: repeated (page 3 repeats an earlier page exactly); the re-asks are spent, which says nothing about where the listing ends: its remaining results were not read
- row 3 Seafood / Sauce & Breading (05009): 219 of 221, INCOMPLETE: accessible pages exhausted; coverage incomplete: 10 page(s) read, 219 distinct products of 221 reported
- row 4 Deli / Fresh Deli Meats (13001): 24 of 43, INCOMPLETE: accessible pages exhausted; coverage incomplete: page 2: page 2 repeats an earlier page exactly; asked again 2 time(s), each at least 300 s after the last answer or attempt: re-ask 1: failed (no page from Oxylabs for https://www.marianos.com/pl/fresh-deli-meats/13001?page=2: transport (HTTP 0)); re-ask 2: repeated (page 2 repeats an earlier page exactly); the re-asks are spent, which says nothing about where the listing ends: its remaining results were not read
- row 4 Deli / Ready-to-heat Meals & Soups (13006): 72 of 128, INCOMPLETE: accessible pages exhausted; coverage incomplete: page 4: page 4 repeats an earlier page exactly; asked again 2 time(s), each at least 300 s after the last answer or attempt: re-ask 1: repeated (page 4 repeats an earlier page exactly); re-ask 2: repeated (page 4 repeats an earlier page exactly); the re-asks are spent, which says nothing about where the listing ends: its remaining results were not read
- row 5 Bakery / Pies (14169): 24 of 31, INCOMPLETE: accessible pages exhausted; coverage incomplete: page 2: page 2 repeats an earlier page exactly; asked again 2 time(s), each at least 300 s after the last answer or attempt: re-ask 1: repeated (page 2 repeats an earlier page exactly); re-ask 2: repeated (page 2 repeats an earlier page exactly); the re-asks are spent, which says nothing about where the listing ends: its remaining results were not read
- row 7 Grocery / Crackers (01026): 27 of 305, INCOMPLETE: the site's search lets the page reach 250 of the 266 results; the listing is read through 17 subdivisions the page itself names (Cheese Crackers, Artisan & Charcuterie Crackers, Wheat Crackers, Crisps Crackers, Butter Crackers, Multipack & Variety Pack Crackers, Vegetable Crackers, Grain Free & Gluten Free Crackers, Oyster, Soda & Saltine Crackers, Rice Crackers, Sandwich Crackers, Multigrain & Whole Grain Crackers, Protein, Keto & Low Carb Crackers, Flatbread & Pita Crackers, Low Sodium & Unsalted Crackers, Vegan Crackers,) and is complete only when they cover its results
- row 7 Grocery / Cheese Crackers (0102600001): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 7 Grocery / Butter Crackers (0102600002): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 7 Grocery / Artisan & Charcuterie Crackers (0102600003): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 7 Grocery / Crisps Crackers (0102600004): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 7 Grocery / Grain Free & Gluten Free Crackers (0102600005): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 7 Grocery / Flatbread & Pita Crackers (0102600006): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 7 Grocery / Rice Crackers (0102600007): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 7 Grocery / Oyster, Soda & Saltine Crackers (0102600008): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 7 Grocery / Sandwich Crackers (0102600009): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 7 Grocery / Wheat Crackers (0102600010): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 7 Grocery / Multigrain & Whole Grain Crackers (0102600011): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 7 Grocery / Multipack & Variety Pack Crackers (0102600012): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 7 Grocery / Low Sodium & Unsalted Crackers (0102600013): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 7 Grocery / Protein, Keto & Low Carb Crackers (0102600014): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 7 Grocery / Vegetable Crackers (0102600015): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 7 Grocery / Vegan Crackers (0102600016): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 7 Grocery / Water Crackers (0102600017): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 7 Grocery / Packaged Breads (01016): 26 of 273, INCOMPLETE: the site's search lets the page reach 250 of the 273 results; the listing is read through 15 subdivisions the page itself names (Tortillas & Taco Shells, Sandwich White Bread, Sandwich Wheat Bread, Sandwich Whole Grain Bread, Sandwich Multigrain Bread, Sandwich Rye Bread, Sourdough Bread, Pizza Crust, Brioche Bread, Pita Bread, Italian Bread, Oat Bread, Flatbread, Potato Bread, Garlic Bread) and is complete only when they cover its results
- row 7 Grocery / Italian Bread (0101600001): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 7 Grocery / Sandwich White Bread (0101600003): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 7 Grocery / Sandwich Wheat Bread (0101600004): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 7 Grocery / Sandwich Rye Bread (0101600005): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 7 Grocery / Pita Bread (0101600006): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 7 Grocery / Pizza Crust (0101600007): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 7 Grocery / Tortillas & Taco Shells (0101600008): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 7 Grocery / Garlic Bread (0101600009): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 7 Grocery / Sandwich Whole Grain Bread (0101600010): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 7 Grocery / Sandwich Multigrain Bread (0101600011): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 7 Grocery / Sourdough Bread (0101600012): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 7 Grocery / Potato Bread (0101600013): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- ... 405 more in export/coverage_reconciliation.csv

