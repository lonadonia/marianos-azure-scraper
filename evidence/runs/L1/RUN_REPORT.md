# Run report: run 01M7JEFZW4PY88RKT5FBMJMZWT

Stages: M-L1-rows22-27-one-lane-110rc4-20261116. Store marianos-53100502-pickup (location 53100502, PICKUP). A pilot: never published.

## What was asked

- `M-L1-rows22-27-one-lane-110rc4-20261116`: `run --store marianos-53100502-pickup --categories 22,23,24,25,26,27 --max-credits 130`; ceiling 130 submissions, USD 0.195000; deadline 2026-11-16T17:09:29Z; approved: Hamza's update of 16 November 2026 (recorded in the trial ledger as the event 'authorization_update'): live Mariano's collection with Hamza's Oxylabs Web API credit, tests on Hamza's Azure VM and scheduling on that VM are authorized, within the Mariano's envelope of the shared trial ledger; the client's VM, the client's billing and Oxylabs Classic stay outside it
- Objective (first stage): the final candidate 1.10.0rc4 on the live site, one lane: rows 22-27 (17 listings; the scope of S6 on 1.10.0rc3: 1,190 products stated on 2026-11-09) in one uninterrupted run. Measured: Q1 (at least 500 distinct fresh valid products, G13 and G14), Q2 (store 53100502 PICKUP on every page), and the one-lane half of Q5 (submissions, active seconds, re-asks and waits, settled cost from the ledger)

## Code and segments

Revisions recorded by the run's segments: 1.10.0rc4 (570ff7cce9d45a913963d495593f0f9d89c3c41e) (one revision for the whole run)

| segment | trigger | started (UTC) | ended (UTC) | active s | end state | stop code |
|---|---|---|---|---|---|---|
| 01M7JEFZZ4PFH3HA9TC0T755RJ | manual | 2026-11-16 15:09:32.003242+00 | 2026-11-16 15:28:29.898611+00 | 1137.9 | ended |  |

## Submissions and cost (the shared trial ledger)

73 submissions reserved before dispatch: settled 73; results charged 73; USD settled 0.109500 at the recorded rate.

- `run --store marianos-53100502-pickup --categories 22,23,24,25,26,27 --max-credits 130` (M-L1-rows22-27-one-lane-110rc4-20261116): 2026-11-16T15:09:31+00:00 to 2026-11-16T15:28:31+00:00, exit 0 after 1140.0 s, revision 570ff7cce9d45a913963d495593f0f9d89c3c41e; gate counts {"reserved": 73, "dispatched": 73, "unsent": 0, "settled": 73, "settled_free": 0, "unknown": 0}

## Pages

69 answers asked as listing pages: by state completed 58, stopped 11; by verdict new 58, repeated 11.
Store checks on every answer: PASS; locations 53100502; fulfillment PICKUP.

Requests set aside: 8 ({"recovered": 8}); re-asks answered 11; new products brought by counted re-asks 192; shortest time between two answers of one request 305.3 s.

## Products

Distinct fresh valid products (this run's own observations, status valid): **1138** in 6 categories; retained dataset 1168 records (verified 1138, carried from earlier runs 0).
Identity sets: `{"record_rows": 1168, "fresh_valid": 1138, "fresh_not_valid": 30, "carried_forward": 0, "excluded": 0, "excluded_rows": 0, "exported_rows": 1168, "retained_unique": 1168, "duplicates": 0, "overlaps": {"fresh_valid & fresh_not_valid": 0, "fresh_valid & carried_forward": 0, "fresh_valid & excluded": 0, "fresh_not_valid & carried_forward": 0, "fresh_not_valid & excluded": 0, "carried_forward & excluded": 0}, "relations": {"no identity is in two classes": true, "retained = fresh valid + fresh not valid + carried forward": true, "no exported identity twice": true}, "holds": true}`

## Coverage and gates

Listings: {"DONE": 15, "EMPTY": 2}; CSV rows: {"NOT_ATTEMPTED": 22, "COMPLETE": 6}.

Gates: G1 PASS, G2 PASS, G3 PASS, G4 PASS, G5 PASS, G6 PASS, G7 PASS, G8 PASS, G9 PASS, G10 PASS, G11 PASS, G12 PASS, G13 PASS, G14 PASS. Run status: validated (validated).

