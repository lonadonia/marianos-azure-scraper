# Run report: run 01M7KBQ3XXMP3W3FK2EXE525EA

Stages: M-R6a-full-run-110rc6-20261116. Store marianos-53100502-pickup (location 53100502, PICKUP). Not a pilot (no command-line narrowing or limit).

## What was asked

- `M-R6a-full-run-110rc6-20261116`: `run --store marianos-53100502-pickup --rows-first 22,27,23,24,25,26,15 --term-upc 0001780014939 --term-upc 0001780014941 --term-upc 0002310014848 --term-upc 0003980014995`; ceiling 160 submissions, USD 0.240000; deadline 2026-11-17T00:55:11Z; approved: Hamza's brief of 16 November 2026 (closeout after 1.10.0rc5): USD 5 of free credit authorized for Mariano's on the Oxylabs Web API credential he supplied, on his own Azure VM, accounted in the campaign oxylabs-marianos-20261116 (cap 5.00, headroom 0.10, Mariano's envelope 4.90); the client's VM, the client's billing, Oxylabs Classic and other providers stay outside it; no top-up or paid overage
- Objective (first stage): one logical full-scope run R6 of the candidate 1.10.0rc6 (every CSV row 0-27 as configured; not a pilot: --rows-first only orders the plan, reading rows 22, 27, 23 to 26 and 15 first, and --term-upc names the four product pages of the review; neither narrows the scope), two lanes, read in slices, each one ledger stage of the new credential's campaign oxylabs-marianos-20261116 whose ceiling is also set in the collector (set-ceiling). In 1.10.0rc6, as in rc5, a stop at a spending ceiling finalizes the run, so every slice is ended by the operator with SIGTERM (systemctl stop, by slice_stop.sh) once the stage has its target of reservations in the ledger: a resumable stop (exit 75); the requests then in flight are held as unknown outcomes, charged against the ceiling; the ceiling, 10 above the target, is the backstop. The estimate from F2's traces (brand readings of the 7 child listings above the window included) puts a full run at 3,190 to 3,796 submissions (USD 4.79 to 5.69 at the reservation rate) against the USD 4.90 envelope (3,266 submissions): at the low end the run completes; at the high end the envelope ends first, the run is then left resumable after its last slice and the shortfall is reported with the measured rates. This slice starts the run. Its first requests verify the corrections: the Coupons page's list read as loaded or not and asked again while not loaded (OR-04), the store check of re-asks as they occur (OR-19), then rows 22, 27 and 15 (Cat Food 27021, the PPM traces, the four product pages, the named offers). Operator check during it: a second start for the store is refused (exit 9) before any request (a gate refusing every submission, no lease).

## Code and segments

Revisions recorded by the run's segments: 1.10.0rc6 (d77f3065c757b8b962524dbf8d9961dec212e72b) (one revision for the whole run)

| segment | trigger | started (UTC) | ended (UTC) | active s | end state | stop code |
|---|---|---|---|---|---|---|
| 01M7KBQ44S7MHY7TWNA1ZPQHQV | manual | 2026-11-16 23:40:14.359386+00 | 2026-11-16 23:47:30.184035+00 | 435.8 | ended | PROVIDER_ERROR |
| 01M7KC68EKTZGF13GJMYTT6E7E | auto | 2026-11-16 23:48:30.290945+00 | 2026-11-16 23:49:51.310672+00 | 81.0 | ended | TERMINATED |

## Submissions and cost (the shared trial ledger)

65 submissions reserved before dispatch: settled 63, unknown 2; results charged 60; USD settled 0.090000 at the recorded rate.

- `run --store marianos-53100502-pickup` (M-R6a-full-run-110rc6-20261116): 2026-11-16T23:41:06+00:00 to 2026-11-16T23:41:07+00:00, exit 9 after 0.5 s, revision d77f3065c757b8b962524dbf8d9961dec212e72b; gate counts null
- `run --store marianos-53100502-pickup --rows-first 22,27,23,24,25,26,15 --term-upc 0001780014939 --term-upc 0001780014941 --term-upc 0002310014848 --term-upc 0003980014995` (M-R6a-full-run-110rc6-20261116): 2026-11-16T23:40:13+00:00 to 2026-11-16T23:49:51+00:00, exit 75 after 577.5 s, revision d77f3065c757b8b962524dbf8d9961dec212e72b; gate counts {"reserved": 65, "dispatched": 65, "unsent": 0, "settled": 60, "settled_free": 3, "unknown": 2}

## Pages

57 answers asked as listing pages: by state completed 24, failed 2, refused 6, stopped 25; by verdict failed 2, malformed 6, new 24, repeated 25.
Store checks on every answer: N/A, PASS; locations 53100502; fulfillment PICKUP.

Requests set aside: 15 ({"waiting": 15}); re-asks answered 12; new products brought by counted re-asks 0; shortest time between two answers of one request 310.2 s.

## Products

Distinct fresh valid products (this run's own observations, status valid): **448** in 7 categories; retained dataset 8513 records (verified 448, carried from earlier runs 8032).
Identity sets: `{"record_rows": 8513, "fresh_valid": 448, "fresh_not_valid": 33, "carried_forward": 8032, "excluded": 0, "excluded_rows": 0, "exported_rows": 8513, "retained_unique": 8513, "duplicates": 0, "overlaps": {"fresh_valid & fresh_not_valid": 0, "fresh_valid & carried_forward": 0, "fresh_valid & excluded": 0, "fresh_not_valid & carried_forward": 0, "fresh_not_valid & excluded": 0, "carried_forward & excluded": 0}, "relations": {"no identity is in two classes": true, "retained = fresh valid + fresh not valid + carried forward": true, "no exported identity twice": true}, "holds": true}`

## Coverage and gates

Listings: {"DONE": 5, "EMPTY": 2, "NOT_COLLECTED": 292}; CSV rows: {"COMPLETE": 1, "INCOMPLETE": 27}.

Gates: G1 PASS, G2 PASS, G3 FAIL, G4 FAIL, G5 PASS, G6 PASS, G7 PASS, G8 PASS, G9 PASS, G10 PASS, G11 PASS, G12 PASS, G13 PASS, G14 FAIL. Run status: rejected (rejected).

Listings not complete:

- row 22 Pet Supplies / Dog Food (27017): 24 of 224, NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 22 Pet Supplies / Dog Treats (27018): 24 of 152, NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 22 Pet Supplies / Cat Food (27021): 24 of 234, NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 22 Pet Supplies / Cat Treats (27022): 24 of 52, NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 22 Pet Supplies / Cat Litter & Accessories (27023): 48 of 64, NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 27 Hardware Home Improvement / - (33): 24 of 65, NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 23 Candles Home Fragrances / - (32001): 24 of 55, NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 24 Batteries / - (26003): 24 of 96, NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 25 Light Bulbs / - (26002): 48 of 99, NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 26 School Office / - (35): 24 of 103, NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 15 Beer Wine Liquor / Craft Beer (08145): 24 of 145, NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 15 Beer Wine Liquor / American Lager (08119): 48 of 90, NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 15 Beer Wine Liquor / Import Beer (08190): 48 of 84, NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 15 Beer Wine Liquor / Hard Cider (08194): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 15 Beer Wine Liquor / Red Wine (08120): 0 of 557, NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 15 Beer Wine Liquor / White Wine (08122): 24 of 441, NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 15 Beer Wine Liquor / Rose & Blush Wine (08181): 24 of 63, NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 15 Beer Wine Liquor / Champagne & Sparkling Wine (08180): 0 of 117, NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 15 Beer Wine Liquor / Box Wine (08182): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 15 Beer Wine Liquor / Dessert & Vermouth Wine (08185): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 15 Beer Wine Liquor / Hard Seltzers (08183): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 15 Beer Wine Liquor / Ready to Drink Cocktails (08193): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 15 Beer Wine Liquor / Hard Teas & Lemonades (08191): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 15 Beer Wine Liquor / Flavored Malt Beverages (08192): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 15 Beer Wine Liquor / Shop Liquor (08121): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 15 Beer Wine Liquor / Shop All (08184): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 1 Produce / Fresh Fruit (06111): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 1 Produce / Fresh Vegetables (06112): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 1 Produce / Fresh Herbs (06122): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 1 Produce / Organic Produce (18003): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 1 Produce / Salads (06114): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 1 Produce / Dressings & Dips (06110): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 1 Produce / Fresh-cut Fruit & Vegetables (06121): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 1 Produce / Packaged Produce (06123): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 1 Produce / Party Trays (06119): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 1 Produce / Fresh Juice & Smoothies (06113): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 2 Meat / Beef (05001): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 2 Meat / Chicken (05002): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 2 Meat / Pork & Ham (05006): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 2 Meat / Turkey (05012): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 2 Meat / Lamb, Veal & Bison (05014): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 2 Meat / Specialty Meat (05011): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 2 Meat / Bacon & Breakfast Sausage (05017): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 2 Meat / Packaged & Sliced Deli Meat (05013): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 2 Meat / Dinner Sausage (05003): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 2 Meat / Heat & Serve Meals & Sides (05016): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 2 Meat / Hot Dogs & Franks (05005): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 2 Meat / Pepperoni, Salami & Summer Sausage (05015): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 2 Meat / Lunch & Snack Kits (05018): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 2 Meat / Canned Meat (0100600006): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 2 Meat / Enhancements (05008): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 2 Meat / Frozen Meatless Choices (1900800005): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 3 Seafood / Shrimp (0501000009): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 3 Seafood / Breaded Fish (1900800003): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 3 Seafood / Seafood Salads & Dips (0500400020): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 3 Seafood / Canned Seafood (0100600007): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 3 Seafood / Sauce & Breading (05009): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 3 Seafood / Sushi (13013): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 4 Deli / Fresh Deli Meats (13001): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 4 Deli / Fresh Deli Cheeses (13002): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- ... 232 more in export/coverage_reconciliation.csv

