# Run report: run 01M7JRXD9P93HPNBRY3J0BVMSX

Stages: M-P4-pubtarget-first-publication-110rc5-20261116. Store marianos-53100502-pickup (location 53100502, PICKUP). Not a pilot (no command-line narrowing or limit).

## What was asked

- `M-P4-pubtarget-first-publication-110rc5-20261116`: `run --store marianos-53100502-pickup`; ceiling 12 submissions, USD 0.018000; deadline 2026-11-16T18:51:32Z; approved: Hamza's update of 16 November 2026 (recorded in the trial ledger as the event 'authorization_update'): live Mariano's collection with Hamza's Oxylabs Web API credit, tests on Hamza's Azure VM and scheduling on that VM are authorized, within the Mariano's envelope of the shared trial ledger; the client's VM, the client's billing and Oxylabs Classic stay outside it
- Objective (first stage): ISOLATED PUBLICATION TARGET (its own database marianos_pubtest5 and data folder; the production target is not touched). Its configuration is the shipped one with the store's categories set to [27] (Hardware Home Improvement: one listing, 65 products on 2026-11-16), so a run of it is not a pilot and can be published when it completes and validates. It proves the publication mechanism on the final candidate; it is not the client's full scope and its dataset is not a catalogue. P4: the first complete run of that scope, validated, then published explicitly (publish).

## Code and segments

Revisions recorded by the run's segments: 1.10.0rc5 (bc19afe60c1016cf5d08d055abd96bc69c9d3dd1) (one revision for the whole run)

| segment | trigger | started (UTC) | ended (UTC) | active s | end state | stop code |
|---|---|---|---|---|---|---|
| 01M7JRXDBR0B0MCH1KTRFDWF4E | manual | 2026-11-16 18:11:37.463263+00 | 2026-11-16 18:27:36.344666+00 | 958.9 | ended |  |

## Submissions and cost (the shared trial ledger)

8 submissions reserved before dispatch: settled 8; results charged 8; USD settled 0.012000 at the recorded rate.

- `run --store marianos-53100502-pickup` (M-P4-pubtarget-first-publication-110rc5-20261116): 2026-11-16T18:11:37+00:00 to 2026-11-16T18:27:36+00:00, exit 0 after 959.5 s, revision bc19afe60c1016cf5d08d055abd96bc69c9d3dd1; gate counts {"reserved": 8, "dispatched": 8, "unsent": 0, "settled": 8, "settled_free": 0, "unknown": 0}

## Pages

6 answers asked as listing pages: by state completed 3, stopped 3; by verdict new 3, repeated 3.
Store checks on every answer: PASS; locations 53100502; fulfillment PICKUP.

Requests set aside: 2 ({"recovered": 2}); re-asks answered 3; new products brought by counted re-asks 41; shortest time between two answers of one request 305.8 s.

## Products

Distinct fresh valid products (this run's own observations, status valid): **62** in 1 categories; retained dataset 65 records (verified 62, carried from earlier runs 0).
Identity sets: `{"record_rows": 65, "fresh_valid": 62, "fresh_not_valid": 3, "carried_forward": 0, "excluded": 0, "excluded_rows": 0, "exported_rows": 65, "retained_unique": 65, "duplicates": 0, "overlaps": {"fresh_valid & fresh_not_valid": 0, "fresh_valid & carried_forward": 0, "fresh_valid & excluded": 0, "fresh_not_valid & carried_forward": 0, "fresh_not_valid & excluded": 0, "carried_forward & excluded": 0}, "relations": {"no identity is in two classes": true, "retained = fresh valid + fresh not valid + carried forward": true, "no exported identity twice": true}, "holds": true}`

## Coverage and gates

Listings: {"DONE": 1}; CSV rows: {"NOT_ATTEMPTED": 27, "COMPLETE": 1}.

Gates: G1 PASS, G2 PASS, G3 PASS, G4 PASS, G5 PASS, G6 PASS, G7 PASS, G8 PASS, G9 PASS, G10 PASS, G11 PASS, G12 PASS, G13 PASS, G14 FAIL. Run status: validated (validated).

