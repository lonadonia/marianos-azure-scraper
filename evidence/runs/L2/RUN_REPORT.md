# Run report: run 01M7JFTHRTJ1ZKPZ9C7Y0Y301S

Stages: M-L2-rows22-27-two-lanes-110rc4-20261116. Store marianos-53100502-pickup (location 53100502, PICKUP). A pilot: never published.

## What was asked

- `M-L2-rows22-27-two-lanes-110rc4-20261116`: `run --store marianos-53100502-pickup --categories 22,23,24,25,26,27 --max-credits 130`; ceiling 130 submissions, USD 0.195000; deadline 2026-11-16T17:32:42Z; approved: Hamza's update of 16 November 2026 (recorded in the trial ledger as the event 'authorization_update'): live Mariano's collection with Hamza's Oxylabs Web API credit, tests on Hamza's Azure VM and scheduling on that VM are authorized, within the Mariano's envelope of the shared trial ledger; the client's VM, the client's billing and Oxylabs Classic stay outside it
- Objective (first stage): the two-lane half of Q5: the same scope as L1 (rows 22-27 (17 listings; the scope of S6 on 1.10.0rc3: 1,190 products stated on 2026-11-09)) read by the same candidate with limits.max_concurrent_listings 2, uninterrupted: submissions, active seconds, re-asks and waits, settled cost from the ledger, compared with L1

## Code and segments

Revisions recorded by the run's segments: 1.10.0rc4 (570ff7cce9d45a913963d495593f0f9d89c3c41e) (one revision for the whole run)

| segment | trigger | started (UTC) | ended (UTC) | active s | end state | stop code |
|---|---|---|---|---|---|---|
| 01M7JFTHV88S9PTD7WQ6H43J0Q | manual | 2026-11-16 15:32:46.567745+00 | 2026-11-16 15:52:10.902737+00 | 1164.3 | ended |  |

## Submissions and cost (the shared trial ledger)

72 submissions reserved before dispatch: settled 72; results charged 72; USD settled 0.108000 at the recorded rate.

- `run --store marianos-53100502-pickup --categories 22,23,24,25,26,27 --max-credits 130` (M-L2-rows22-27-two-lanes-110rc4-20261116): 2026-11-16T15:32:46+00:00 to 2026-11-16T15:52:12+00:00, exit 0 after 1166.5 s, revision 570ff7cce9d45a913963d495593f0f9d89c3c41e; gate counts {"reserved": 72, "dispatched": 72, "unsent": 0, "settled": 72, "settled_free": 0, "unknown": 0}

## Pages

68 answers asked as listing pages: by state completed 52, refused 2, stopped 14; by verdict malformed 2, new 52, repeated 14.
Store checks on every answer: PASS; locations 53100502; fulfillment PICKUP.

Requests set aside: 9 ({"exhausted": 2, "recovered": 7}); re-asks answered 12; new products brought by counted re-asks 135; shortest time between two answers of one request 304.4 s.

## Products

Distinct fresh valid products (this run's own observations, status valid): **1018** in 6 categories; retained dataset 1168 records (verified 1018, carried from earlier runs 120).
Identity sets: `{"record_rows": 1168, "fresh_valid": 1018, "fresh_not_valid": 30, "carried_forward": 120, "excluded": 0, "excluded_rows": 0, "exported_rows": 1168, "retained_unique": 1168, "duplicates": 0, "overlaps": {"fresh_valid & fresh_not_valid": 0, "fresh_valid & carried_forward": 0, "fresh_valid & excluded": 0, "fresh_not_valid & carried_forward": 0, "fresh_not_valid & excluded": 0, "carried_forward & excluded": 0}, "relations": {"no identity is in two classes": true, "retained = fresh valid + fresh not valid + carried forward": true, "no exported identity twice": true}, "holds": true}`

## Coverage and gates

Listings: {"DONE": 13, "EMPTY": 2, "INCOMPLETE": 2}; CSV rows: {"NOT_ATTEMPTED": 22, "INCOMPLETE": 1, "COMPLETE": 5}.

Gates: G1 PASS, G2 PASS, G3 FAIL, G4 PASS, G5 PASS, G6 PASS, G7 PASS, G8 PASS, G9 PASS, G10 PASS, G11 PASS, G12 PASS, G13 PASS, G14 PASS. Run status: rejected (rejected).

Listings not complete:

- row 22 Pet Supplies / Dog Treats (27018): 72 of 152, INCOMPLETE: accessible pages exhausted; coverage incomplete: page 4: page 4 repeats an earlier page exactly; asked again 2 time(s), each at least 300 s after the last answer or attempt: re-ask 1: repeated (page 4 repeats an earlier page exactly); re-ask 2: repeated (page 4 repeats an earlier page exactly); the re-asks are spent, which says nothing about where the listing ends: its remaining results were not read
- row 22 Pet Supplies / Cat Litter & Accessories (27023): 24 of 64, INCOMPLETE: accessible pages exhausted; coverage incomplete: page 2: page 2 repeats an earlier page exactly; asked again 2 time(s), each at least 300 s after the last answer or attempt: re-ask 1: repeated (page 2 repeats an earlier page exactly); re-ask 2: repeated (page 2 repeats an earlier page exactly); the re-asks are spent, which says nothing about where the listing ends: its remaining results were not read

