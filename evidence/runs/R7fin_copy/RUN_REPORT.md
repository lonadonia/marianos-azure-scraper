# Run report: run 01M7KQ5GZVF5VK1S9FGTG6YFC9

Stages: M-R7a-full-run-110rc6-20261117, M-R7a2-full-run-110rc6-20261117, M-R7b-full-run-110rc6-20261117, M-R7w-walkthrough-110rc6-20261117, M-R7c-full-run-110rc6-20261117. Store marianos-53100502-pickup (location 53100502, PICKUP). Not a pilot (no command-line narrowing or limit).

## What was asked

- `M-R7a-full-run-110rc6-20261117`: `run --store marianos-53100502-pickup --rows-first 22,27,23,24,25,26,15 --term-upc 0001780014939 --term-upc 0001780014941 --term-upc 0002310014848 --term-upc 0003980014995`; ceiling 160 submissions, USD 0.240000; deadline 2026-11-17T04:15:17Z; approved: Hamza's brief of 16 November 2026 (closeout after 1.10.0rc5): USD 5 of free credit authorized for Mariano's on the Oxylabs Web API credential he supplied, on his own Azure VM, accounted in the campaign oxylabs-marianos-20261116 (cap 5.00, headroom 0.10, Mariano's envelope 4.90); the client's VM, the client's billing, Oxylabs Classic and other providers stay outside it; no top-up or paid overage
- `M-R7a2-full-run-110rc6-20261117`: `resume --store marianos-53100502-pickup`; ceiling 160 submissions, USD 0.240000; deadline 2026-11-17T05:15:21Z; approved: Hamza's brief of 16 November 2026 (closeout after 1.10.0rc5): USD 5 of free credit authorized for Mariano's on the Oxylabs Web API credential he supplied, on his own Azure VM, accounted in the campaign oxylabs-marianos-20261116 (cap 5.00, headroom 0.10, Mariano's envelope 4.90); the client's VM, the client's billing, Oxylabs Classic and other providers stay outside it; no top-up or paid overage
- `M-R7b-full-run-110rc6-20261117`: `resume --store marianos-53100502-pickup`; ceiling 610 submissions, USD 0.915000; deadline 2026-11-17T07:05:18Z; approved: Hamza's brief of 16 November 2026 (closeout after 1.10.0rc5): USD 5 of free credit authorized for Mariano's on the Oxylabs Web API credential he supplied, on his own Azure VM, accounted in the campaign oxylabs-marianos-20261116 (cap 5.00, headroom 0.10, Mariano's envelope 4.90); the client's VM, the client's billing, Oxylabs Classic and other providers stay outside it; no top-up or paid overage
- `M-R7w-walkthrough-110rc6-20261117`: `resume --store marianos-53100502-pickup`; ceiling 110 submissions, USD 0.165000; deadline 2026-11-17T06:20:23Z; approved: Hamza's brief of 16 November 2026 (closeout after 1.10.0rc5): USD 5 of free credit authorized for Mariano's on the Oxylabs Web API credential he supplied, on his own Azure VM, accounted in the campaign oxylabs-marianos-20261116 (cap 5.00, headroom 0.10, Mariano's envelope 4.90); the client's VM, the client's billing, Oxylabs Classic and other providers stay outside it; no top-up or paid overage
- `M-R7c-full-run-110rc6-20261117`: `resume --store marianos-53100502-pickup`; ceiling 150 submissions, USD 0.225000; deadline 2026-11-17T07:22:25Z; approved: Hamza's brief of 16 November 2026 (closeout after 1.10.0rc5): USD 5 of free credit authorized for Mariano's on the Oxylabs Web API credential he supplied, on his own Azure VM, accounted in the campaign oxylabs-marianos-20261116 (cap 5.00, headroom 0.10, Mariano's envelope 4.90); the client's VM, the client's billing, Oxylabs Classic and other providers stay outside it; no top-up or paid overage
- Objective (first stage): one logical full-scope run R7 of the candidate 1.10.0rc6 (every CSV row 0-27 as configured; not a pilot: --rows-first only orders the plan, reading rows 22, 27, 23 to 26 and 15 first, and --term-upc names the four product pages of the review; neither narrows the scope), two lanes, read in slices, each one ledger stage of the new credential's campaign oxylabs-marianos-20261116 whose ceiling is also set in the collector (set-ceiling). Every slice is ended by the operator with SIGTERM once the stage has its target of reservations (a resumable stop, exit 75); the ceiling, 10 above the target, is the backstop. Why R7: run R6 started at 23:40Z on 2026-11-16, when the site served page 1 again for 25 of 29 answers to a page 2 or later and for all 12 re-asks (measured by hour over all runs of the day: 10% at 03Z, 20-27% at 15Z, 28-34% at 16-17Z, 55-60% at 18Z, 80-86% at 23Z); a page has at most 2 re-asks in a run, so R6 was finalized offline after its first slice (rejected, never published) and R7 starts afresh in the night hours, with every page's re-asks intact. The envelope then held USD 4.7935 (3,195 submissions); a full run needs 3,145 to 3,750 submissions at F2's measured 1.43 per counted page, fewer at the night rate: if the envelope ends first, the run is left resumable after its last slice and the shortfall is reported with R7's measured rates. This slice starts the run and measures the hour's repeat rate before the larger slices.

## Code and segments

Revisions recorded by the run's segments: 1.10.0rc6 (d77f3065c757b8b962524dbf8d9961dec212e72b) (one revision for the whole run)

| segment | trigger | started (UTC) | ended (UTC) | active s | end state | stop code |
|---|---|---|---|---|---|---|
| 01M7KQ5H6KDYDQEWNQJY7NTH23 | manual | 2026-11-17 03:00:20.817949+00 | 2026-11-17 03:04:55.879433+00 | 275.1 | ended | TERMINATED |
| 01M7KTKFXRM3FAR0N3KTQ2CJC7 | resume | 2026-11-17 04:00:23.991121+00 | 2026-11-17 04:14:04.224341+00 | 820.2 | ended | TERMINATED |
| 01M7KWKG7QG6KQTA4Z2Y949ER9 | resume | 2026-11-17 04:35:21.462399+00 |  | 206.6 | abandoned | TERMINATED |
| 01M7KWWTEYTS7W34DV9NN6Q2V1 | resume | 2026-11-17 04:40:26.844925+00 | 2026-11-17 04:45:53.124867+00 | 326.3 | ended | PROVIDER_ERROR |
| 01M7KX8KV64FM7NTBRD20H6TNE | auto | 2026-11-17 04:46:53.286422+00 | 2026-11-17 04:52:23.572944+00 | 330.3 | ended | PROVIDER_ERROR |
| 01M7KXPBNSGNREX68WF7RZDBFB | auto | 2026-11-17 04:54:23.672975+00 | 2026-11-17 04:55:09.426361+00 | 45.7 | ended | TERMINATED |
| 01M7KYAZM3XXDPQVZXSWFD0KXQ | resume | 2026-11-17 05:05:39.458397+00 | 2026-11-17 05:11:02.999509+00 | 323.5 | ended | PROVIDER_ERROR |
| 01M7KYN2ENBHJ1EQVQC2Y579F6 | resume | 2026-11-17 05:11:10.035454+00 | 2026-11-17 05:15:54.266072+00 | 284.2 | ended | PROVIDER_ERROR |
| 01M7KZ9RTAXYZHG904TH1A1YB2 | resume | 2026-11-17 05:22:28.296564+00 | 2026-11-17 05:27:09.586438+00 | 281.3 | ended | PROVIDER_ERROR |
| 01M7KZQQR4FR7WMD999GNN420Q | resume | 2026-11-17 05:30:05.95512+00 | 2026-11-17 05:35:38.697795+00 | 332.7 | ended | PROVIDER_ERROR |

## Submissions and cost (the shared trial ledger)

256 submissions reserved before dispatch: settled 249, unknown 7; results charged 223; USD settled 0.334500 at the recorded rate.

- `run --store marianos-53100502-pickup --rows-first 22,27,23,24,25,26,15 --term-upc 0001780014939 --term-upc 0001780014941 --term-upc 0002310014848 --term-upc 0003980014995` (M-R7a-full-run-110rc6-20261117): 2026-11-17T03:00:20+00:00 to 2026-11-17T03:04:55+00:00, exit 75 after 275.6 s, revision d77f3065c757b8b962524dbf8d9961dec212e72b; gate counts {"reserved": 46, "dispatched": 46, "unsent": 0, "settled": 44, "settled_free": 0, "unknown": 2}
- `resume --store marianos-53100502-pickup` (M-R7a2-full-run-110rc6-20261117): 2026-11-17T04:00:23+00:00 to 2026-11-17T04:14:04+00:00, exit 75 after 820.6 s, revision d77f3065c757b8b962524dbf8d9961dec212e72b; gate counts {"reserved": 76, "dispatched": 76, "unsent": 0, "settled": 68, "settled_free": 6, "unknown": 2}
- `resume --store marianos-53100502-pickup` (M-R7b-full-run-110rc6-20261117): 2026-11-17T04:40:26+00:00 to 2026-11-17T04:55:09+00:00, exit 75 after 883.0 s, revision d77f3065c757b8b962524dbf8d9961dec212e72b; gate counts {"reserved": 37, "dispatched": 37, "unsent": 0, "settled": 29, "settled_free": 6, "unknown": 2}
- `resume --store marianos-53100502-pickup` (M-R7w-walkthrough-110rc6-20261117): 2026-11-17T05:05:39+00:00 to 2026-11-17T05:11:03+00:00, exit 75 after 324.2 s, revision d77f3065c757b8b962524dbf8d9961dec212e72b; gate counts {"reserved": 21, "dispatched": 21, "unsent": 0, "settled": 18, "settled_free": 3, "unknown": 0}
- `run --store marianos-53100502-pickup` (M-R7w-walkthrough-110rc6-20261117): 2026-11-17T05:11:07+00:00 to 2026-11-17T05:11:07+00:00, exit 9 after 0.2 s, revision d77f3065c757b8b962524dbf8d9961dec212e72b; gate counts null
- `resume --store marianos-53100502-pickup` (M-R7w-walkthrough-110rc6-20261117): 2026-11-17T05:11:09+00:00 to 2026-11-17T05:15:54+00:00, exit 75 after 284.6 s, revision d77f3065c757b8b962524dbf8d9961dec212e72b; gate counts {"reserved": 14, "dispatched": 14, "unsent": 0, "settled": 11, "settled_free": 3, "unknown": 0}
- `resume --store marianos-53100502-pickup` (M-R7c-full-run-110rc6-20261117): 2026-11-17T05:22:28+00:00 to 2026-11-17T05:27:09+00:00, exit 75 after 281.6 s, revision d77f3065c757b8b962524dbf8d9961dec212e72b; gate counts {"reserved": 17, "dispatched": 17, "unsent": 0, "settled": 14, "settled_free": 3, "unknown": 0}
- `resume --store marianos-53100502-pickup` (M-R7c-full-run-110rc6-20261117): 2026-11-17T05:30:05+00:00 to 2026-11-17T05:35:38+00:00, exit 75 after 333.1 s, revision d77f3065c757b8b962524dbf8d9961dec212e72b; gate counts {"reserved": 22, "dispatched": 22, "unsent": 0, "settled": 19, "settled_free": 3, "unknown": 0}

## Pages

216 answers asked as listing pages: by state completed 132, failed 10, refused 22, stopped 52; by verdict failed 10, malformed 22, new 131, partial_overlap 1, repeated 52.
Store checks on every answer: N/A, PASS; locations 53100502; fulfillment PICKUP.

Requests set aside: 35 ({"exhausted": 6, "recovered": 23, "waiting": 6}); re-asks answered 43; new products brought by counted re-asks 508; shortest time between two answers of one request 309.7 s.

## Products

Distinct fresh valid products (this run's own observations, status valid): **2518** in 8 categories; retained dataset 10536 records (verified 2518, carried from earlier runs 7869).
Identity sets: `{"record_rows": 10536, "fresh_valid": 2518, "fresh_not_valid": 149, "carried_forward": 7869, "excluded": 0, "excluded_rows": 0, "exported_rows": 10536, "retained_unique": 10536, "duplicates": 0, "overlaps": {"fresh_valid & fresh_not_valid": 0, "fresh_valid & carried_forward": 0, "fresh_valid & excluded": 0, "fresh_not_valid & carried_forward": 0, "fresh_not_valid & excluded": 0, "carried_forward & excluded": 0}, "relations": {"no identity is in two classes": true, "retained = fresh valid + fresh not valid + carried forward": true, "no exported identity twice": true}, "holds": true}`

## Coverage and gates

Listings: {"DONE": 29, "EMPTY": 2, "INCOMPLETE": 9, "NOT_COLLECTED": 270}; CSV rows: {"COMPLETE": 5, "INCOMPLETE": 23}.

Gates: G1 PASS, G2 PASS, G3 FAIL, G4 FAIL, G5 PASS, G6 PASS, G7 PASS, G8 PASS, G9 PASS, G10 PASS, G11 PASS, G12 PASS, G13 PASS, G14 PASS. Run status: rejected (rejected).

Listings not complete:

- row 22 Pet Supplies / Dog Treats (27018): 52 of 152, INCOMPLETE: accessible pages exhausted; coverage incomplete: page 3: page 3 repeats an earlier page exactly; asked again 2 time(s), each at least 300 s after the last answer or attempt: re-ask 1: repeated (page 3 repeats an earlier page exactly); re-ask 2: repeated (page 3 repeats an earlier page exactly); the re-asks are spent, which says nothing about where the listing ends: its remaining results were not read
- row 25 Light Bulbs / - (26002): 72 of 99, INCOMPLETE: accessible pages exhausted; coverage incomplete: page 4: page 4 repeats an earlier page exactly; asked again 2 time(s), each at least 300 s after the last answer or attempt: re-ask 1: repeated (page 4 repeats an earlier page exactly); re-ask 2: repeated (page 4 repeats an earlier page exactly); the re-asks are spent, which says nothing about where the listing ends: its remaining results were not read
- row 15 Beer Wine Liquor / Hard Cider (08194): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 15 Beer Wine Liquor / Red Wine (08120): 499 of 557, INCOMPLETE: the site's search lets the page reach 250 of the 557 results; the listing is read through 5 subdivisions the page itself names (Red Blend Wine, Cabernet Sauvignon Wine, Pinot Noir Wine, Merlot Wine, Malbec Wine) and is complete only when they cover its results
- row 15 Beer Wine Liquor / Cabernet Sauvignon Wine (0812000571): 120 of 180, INCOMPLETE: accessible pages exhausted; coverage incomplete: page 6: page 6 repeats an earlier page exactly; asked again 2 time(s), each at least 300 s after the last answer or attempt: re-ask 1: repeated (page 6 repeats an earlier page exactly); re-ask 2: repeated (page 6 repeats an earlier page exactly); the re-asks are spent, which says nothing about where the listing ends: its remaining results were not read
- row 15 Beer Wine Liquor / White Wine (08122): 404 of 441, INCOMPLETE: the site's search lets the page reach 250 of the 441 results; the listing is read through 6 subdivisions the page itself names (Chardonnay Wine, Sauvignon Blanc Wine, Pinot Grigio/Pinot Gris Wine, White Blend Wine, Riesling Wine, Moscato Wine) and is complete only when they cover its results
- row 15 Beer Wine Liquor / White Blend Wine (0812200583): 24 of 63, INCOMPLETE: accessible pages exhausted; coverage incomplete: page 2: page 2 repeats an earlier page exactly; asked again 2 time(s), each at least 300 s after the last answer or attempt: re-ask 1: repeated (page 2 repeats an earlier page exactly); re-ask 2: repeated (page 2 repeats an earlier page exactly); the re-asks are spent, which says nothing about where the listing ends: its remaining results were not read
- row 15 Beer Wine Liquor / Sauvignon Blanc Wine (0812200586): 125 of 126, INCOMPLETE: accessible pages exhausted; coverage incomplete: 6 page(s) read, 125 distinct products of 126 reported
- row 15 Beer Wine Liquor / Rose & Blush Wine (08181): 48 of 63, NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 15 Beer Wine Liquor / Champagne & Sparkling Wine (08180): 24 of 117, INCOMPLETE: accessible pages exhausted; coverage incomplete: page 2: page 2 repeats an earlier page exactly; asked again 2 time(s), each at least 300 s after the last answer or attempt: re-ask 1: repeated (page 2 repeats an earlier page exactly); re-ask 2: repeated (page 2 repeats an earlier page exactly); the re-asks are spent, which says nothing about where the listing ends: its remaining results were not read
- row 15 Beer Wine Liquor / Hard Seltzers (08183): 24 of 87, INCOMPLETE: accessible pages exhausted; coverage incomplete: page 2: page 2 repeats an earlier page exactly; asked again 2 time(s), each at least 300 s after the last answer or attempt: re-ask 1: malformed (the page state lists 24 products and the grid shows 0 cards; the provider ran the page's scripts (its answer states run_js true), and a rendered listing page carries no product tile: asked for again); re-ask 2: repeated (page 2 repeats an earlier page exactly); the re-asks are spent, which says nothing about where the listing ends: its remaining results were not read
- row 15 Beer Wine Liquor / Flavored Malt Beverages (08192): 24 of 56, NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 15 Beer Wine Liquor / Shop Liquor (08121): 24 of 473, NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 15 Beer Wine Liquor / Shop All (08184): 48 of 110, NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 1 Produce / Fresh Fruit (06111): 0 of 198, NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 1 Produce / Fresh Vegetables (06112): 24 of 369, NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 1 Produce / Organic Produce (18003): 51 of 127, NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
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
- row 4 Deli / Chicken & Hot Meals (13007): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 4 Deli / Olives, Dips, Spreads & Snacks (13011): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 4 Deli / Packaged Deli Meats (13003): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 4 Deli / Packaged Deli Cheeses (13004): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 4 Deli / Ready-to-heat Meals & Soups (13006): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 4 Deli / Cold Side Dishes (13009): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 4 Deli / Grab & Go Meals (13008): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 4 Deli / Party Platters (13010): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 5 Bakery / Cakes & Cupcakes (14160): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 5 Bakery / Donuts, Danishes & Muffins (14166): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 5 Bakery / Cookies (14187): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 5 Bakery / Brownies (14165): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- row 5 Bakery / Pies (14169): 0 of , NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run
- ... 219 more in export/coverage_reconciliation.csv

