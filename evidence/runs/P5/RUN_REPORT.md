# Run report: run 01M7JSXE192AD3KH2SV0178F4A

Stages: M-P5-pubtarget-partial-refused-110rc5-20261116. Store marianos-53100502-pickup (location 53100502, PICKUP). Not a pilot (no command-line narrowing or limit).

## What was asked

- `M-P5-pubtarget-partial-refused-110rc5-20261116`: `run --store marianos-53100502-pickup`; ceiling 4 submissions, USD 0.006000; deadline 2026-11-16T18:59:04Z; approved: Hamza's update of 16 November 2026 (recorded in the trial ledger as the event 'authorization_update'): live Mariano's collection with Hamza's Oxylabs Web API credit, tests on Hamza's Azure VM and scheduling on that VM are authorized, within the Mariano's envelope of the shared trial ledger; the client's VM, the client's billing and Oxylabs Classic stay outside it
- Objective (first stage): ISOLATED PUBLICATION TARGET (its own database marianos_pubtest5 and data folder; the production target is not touched). Its configuration is the shipped one with the store's categories set to [27] (Hardware Home Improvement: one listing, 65 products on 2026-11-16), so a run of it is not a pilot and can be published when it completes and validates. It proves the publication mechanism on the final candidate; it is not the client's full scope and its dataset is not a catalogue. P5: a run stopped by a 4-submission ceiling (robots, store, Coupons route and at most one listing page: incomplete, with products), finalized, then offered for publication: the publication must be refused (exit 6) and P4's published files stay byte-identical.

## Code and segments

Revisions recorded by the run's segments: 1.10.0rc5 (bc19afe60c1016cf5d08d055abd96bc69c9d3dd1) (one revision for the whole run)

| segment | trigger | started (UTC) | ended (UTC) | active s | end state | stop code |
|---|---|---|---|---|---|---|
| 01M7JSXE3ARMJ6TV5Y8M0HFDD1 | manual | 2026-11-16 18:29:06.793815+00 | 2026-11-16 18:34:33.607481+00 | 326.8 | ended | SPENDING_CEILING |

## Submissions and cost (the shared trial ledger)

4 submissions reserved before dispatch: settled 4; results charged 4; USD settled 0.006000 at the recorded rate.

- `run --store marianos-53100502-pickup` (M-P5-pubtarget-partial-refused-110rc5-20261116): 2026-11-16T18:29:06+00:00 to 2026-11-16T18:34:33+00:00, exit 4 after 327.4 s, revision bc19afe60c1016cf5d08d055abd96bc69c9d3dd1; gate counts {"reserved": 4, "dispatched": 4, "unsent": 0, "settled": 4, "settled_free": 0, "unknown": 0}

## Pages

2 answers asked as listing pages: by state completed 1, stopped 1; by verdict new 1, repeated 1.
Store checks on every answer: PASS; locations 53100502; fulfillment PICKUP.

Requests set aside: 1 ({"waiting": 1}); re-asks answered 0; new products brought by counted re-asks 0; shortest time between two answers of one request None s.

## Products

Distinct fresh valid products (this run's own observations, status valid): **22** in 1 categories; retained dataset 65 records (verified 22, carried from earlier runs 41).
Identity sets: `{"record_rows": 65, "fresh_valid": 22, "fresh_not_valid": 2, "carried_forward": 41, "excluded": 0, "excluded_rows": 0, "exported_rows": 65, "retained_unique": 65, "duplicates": 0, "overlaps": {"fresh_valid & fresh_not_valid": 0, "fresh_valid & carried_forward": 0, "fresh_valid & excluded": 0, "fresh_not_valid & carried_forward": 0, "fresh_not_valid & excluded": 0, "carried_forward & excluded": 0}, "relations": {"no identity is in two classes": true, "retained = fresh valid + fresh not valid + carried forward": true, "no exported identity twice": true}, "holds": true}`

## Coverage and gates

Listings: {"NOT_COLLECTED": 1}; CSV rows: {"NOT_ATTEMPTED": 27, "INCOMPLETE": 1}.

Gates: G1 PASS, G2 PASS, G3 FAIL, G4 FAIL, G5 PASS, G6 PASS, G7 PASS, G8 PASS, G9 PASS, G10 PASS, G11 PASS, G12 PASS, G13 PASS, G14 FAIL. Run status: rejected (rejected).

Listings not complete:

- row 27 Hardware Home Improvement / - (33): 24 of 65, NOT_COLLECTED: accessible pages exhausted; coverage incomplete: the listing was not read to an end by this run

