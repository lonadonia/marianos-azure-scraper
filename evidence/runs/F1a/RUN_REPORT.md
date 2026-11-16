# Run report: run 01M7JHWNC5EGHRMNMCJQ14P8DR

Stages: M-F1a-full-run-110rc4-20261116. Store marianos-53100502-pickup (location 53100502, PICKUP). Not a pilot (no command-line narrowing or limit).

## What was asked

- `M-F1a-full-run-110rc4-20261116`: `run --store marianos-53100502-pickup`; ceiling 200 submissions, USD 0.300000; deadline 2026-11-16T18:08:50Z; approved: Hamza's update of 16 November 2026 (recorded in the trial ledger as the event 'authorization_update'): live Mariano's collection with Hamza's Oxylabs Web API credit, tests on Hamza's Azure VM and scheduling on that VM are authorized, within the Mariano's envelope of the shared trial ledger; the client's VM, the client's billing and Oxylabs Classic stay outside it
- Objective (first stage): one logical full-scope run of the final candidate 1.10.0rc4 (no command-line narrowing or limit: every CSV row 0-27 as configured, so the run is not a pilot), two lanes, read in slices of at most 200 submissions (USD 0.30), each one ledger stage whose ceiling is also set in the collector (set-ceiling). In 1.10.0rc4 a stop at a spending ceiling finalizes the run (observed in P2 on 2026-11-16), so every slice but the last is ended by the operator with SIGTERM (systemctl stop, by slice_stop.sh) once the stage has 190 reservations in the ledger: a resumable stop (exit 75); the requests in flight at that moment are held as unknown outcomes, charged against the ceiling; the ceiling, 10 above, is the backstop. The last slice runs to its ceiling, where the collector finalizes the run as a partial dataset, which is never published. The trial credit cannot complete the scope: the result is the run's coverage (listings DONE, EMPTY, INCOMPLETE, not reached), its measured submissions and cost per listing, and the census of listings not measured before. This slice starts the run. Operator check during it: a second start for the store is refused (exit 9) before any request (the harness gives it a gate that refuses every submission and takes no lease).

## Code and segments

Revisions recorded by the run's segments: 1.10.0rc4 (570ff7cce9d45a913963d495593f0f9d89c3c41e) (one revision for the whole run)

| segment | trigger | started (UTC) | ended (UTC) | active s | end state | stop code |
|---|---|---|---|---|---|---|
| 01M7JHWNKFCW8EVXTD9Y88Q06R | manual | 2026-11-16 16:08:53.101262+00 | 2026-11-16 16:20:02.804604+00 | 669.7 | ended | STORE_NOT_VERIFIED |

## Submissions and cost (the shared trial ledger)

158 submissions reserved before dispatch: settled 158; results charged 158; USD settled 0.237000 at the recorded rate.

- `run --store marianos-53100502-pickup` (M-F1a-full-run-110rc4-20261116): 2026-11-16T16:09:52+00:00 to 2026-11-16T16:09:52+00:00, exit 9 after 0.3 s, revision 570ff7cce9d45a913963d495593f0f9d89c3c41e; gate counts null
- `run --store marianos-53100502-pickup` (M-F1a-full-run-110rc4-20261116): 2026-11-16T16:08:52+00:00 to 2026-11-16T16:20:06+00:00, exit 7 after 673.5 s, revision 570ff7cce9d45a913963d495593f0f9d89c3c41e; gate counts {"reserved": 158, "dispatched": 158, "unsent": 0, "settled": 158, "settled_free": 0, "unknown": 0}

## Pages

156 answers asked as listing pages: by state completed 122, refused 2, stopped 32; by verdict malformed 1, new 122, repeated 32, wrong_context 1.
Store checks on every answer: FAIL, PASS; locations 53100502; fulfillment PICKUP.

Requests set aside: 28 ({"recovered": 13, "waiting": 15}); re-asks answered 17; new products brought by counted re-asks 259; shortest time between two answers of one request 305.0 s.

## Products

Distinct fresh valid products (this run's own observations, status valid): **2087** in 6 categories; retained dataset 2353 records (verified None, carried from earlier runs 0).
Identity sets: `{"record_rows": 2365, "fresh_valid": 2087, "fresh_not_valid": 266, "carried_forward": 0, "excluded": 12, "excluded_rows": 12, "exported_rows": 2353, "retained_unique": 2353, "duplicates": 0, "overlaps": {"fresh_valid & fresh_not_valid": 0, "fresh_valid & carried_forward": 0, "fresh_valid & excluded": 0, "fresh_not_valid & carried_forward": 0, "fresh_not_valid & excluded": 0, "carried_forward & excluded": 0}, "relations": {"no identity is in two classes": true, "retained = fresh valid + fresh not valid + carried forward": true, "no exported identity twice": true}, "holds": true}`

## Coverage and gates

Listings: null; CSV rows: {"NOT_ATTEMPTED": 1, "INCOMPLETE": 27}.

Gates: . Run status: rejected (None).

Listings not complete:

- row 1 Produce / Fresh Fruit (06111): 168 of 198, NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 1 Produce / Fresh Vegetables (06112): 33 of 370, INCOMPLETE: the site's search lets the page reach 250 of the 370 results; the listing is read through 19 subdivisions the page itself names (Lettuce & Leafy Greens, Potatoes, Onions & Garlic, Peppers, Mushrooms, Tomatoes, Root Vegetables, Carrots, Squash, Broccoli & Cauliflower, Cucumbers, Beans & Peas, Cabbage, Corn, Artichokes, Brussels Sprouts, Celery, Asparagus, Eggplant) and is complete only when they cover its results
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
- row 1 Produce / Fresh Herbs (06122): 29 of 47, NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 1 Produce / Organic Produce (18003): 52 of 128, NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 1 Produce / Salads (06114): 73 of 133, NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 2 Meat / Pork & Ham (05006): 54 of 84, NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 2 Meat / Packaged & Sliced Deli Meat (05013): 96 of 115, NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 2 Meat / Lunch & Snack Kits (05018): 24 of 59, NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 2 Meat / Frozen Meatless Choices (1900800005): 48 of 60, NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 3 Seafood / Canned Seafood (0100600007): 24 of 157, NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 3 Seafood / Sauce & Breading (05009): 73 of 221, NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 3 Seafood / Sushi (13013): 48 of 54, NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 4 Deli / Olives, Dips, Spreads & Snacks (13011): 27 of 167, NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 4 Deli / Ready-to-heat Meals & Soups (13006): 48 of 128, NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 4 Deli / Grab & Go Meals (13008): 24 of 30, NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 5 Bakery / Cakes & Cupcakes (14160): 29 of 60, NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 5 Bakery / Donuts, Danishes & Muffins (14166): 24 of 42, NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 6 Floral / Bouquets (09126): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 6 Floral / Floral Arrangements (09128): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 6 Floral / Orchids (09132): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 6 Floral / Plants (09133): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 6 Floral / Balloons (09125): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 7 Grocery / Crackers (01026): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 7 Grocery / Packaged Breads (01016): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 7 Grocery / Canned Foods (01006): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 7 Grocery / Baking & Cooking (01012): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 7 Grocery / Condiments & Salad Dressings (01008): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 7 Grocery / Pasta & Pasta Sauces (01010): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 7 Grocery / Grains, Beans & Rice (01007): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 7 Grocery / Easy Meals, Sides, Mac & Cheese (01011): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 7 Grocery / Spreads, Jelly & Honey (01014): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 7 Grocery / Spices & Seasonings (01015): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 7 Grocery / Nuts, Trail Mix & Seeds (01022): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 7 Grocery / Indian (0101300170): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 7 Grocery / European (0101300166): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 7 Grocery / Kosher (0101300004): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 8 Dairy / Milk & Plant-based Milk (02001): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 8 Dairy / Cream & Creamer (02005): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 8 Dairy / Eggs (02003): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 8 Dairy / Cheese (02002): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 8 Dairy / Yogurt (02009): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- ... 217 more in export/coverage_reconciliation.csv

