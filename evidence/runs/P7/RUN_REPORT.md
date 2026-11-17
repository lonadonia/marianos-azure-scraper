# Run report: run 01M7KAJZTFXAWFA8AHXRQ343TT

Stages: M-P7-one-lane-pilot-110rc6-20261116. Store marianos-53100502-pickup (location 53100502, PICKUP). A pilot: never published.

## What was asked

- `M-P7-one-lane-pilot-110rc6-20261116`: `run --store marianos-53100502-pickup --categories 0,27`; ceiling 20 submissions, USD 0.030000; deadline 2026-11-16T23:50:27Z; approved: Hamza's brief of 16 November 2026 (closeout after 1.10.0rc5): USD 5 of free credit authorized for Mariano's on the Oxylabs Web API credential he supplied, on his own Azure VM, accounted in the campaign oxylabs-marianos-20261116 (cap 5.00, headroom 0.10, Mariano's envelope 4.90); the client's VM, the client's billing, Oxylabs Classic and other providers stay outside it; no top-up or paid overage
- Objective (first stage): a one-lane pilot of the candidate 1.10.0rc6 before its full run R6 (a bounded run: --categories 0,27 narrows the scope, so it is a pilot, never a complete catalogue, never published): row 0, the Coupons page (read as the run's Coupons route, asked again while its list has not loaded: at most 4 answers, 60 s apart), and row 27 (Hardware, one listing of about 3 pages). It shows on the exact release, live: one lane under the account-wide gate of the new campaign (shared accounting with the later two-lane run, one ledger), the Coupons page read with its list's state recorded (OR-04), and the depth-first order. It ends on its own when its scope is read (the run is then finalized as a pilot); the ceiling of 20 is the backstop. A resumed run keeps the lanes it started with, so the full run R6 starts with two.

## Code and segments

Revisions recorded by the run's segments: 1.10.0rc6 (d77f3065c757b8b962524dbf8d9961dec212e72b) (one revision for the whole run)

| segment | trigger | started (UTC) | ended (UTC) | active s | end state | stop code |
|---|---|---|---|---|---|---|
| 01M7KAJZWM2FFR3WDW0EDCD24S | manual | 2026-11-16 23:20:30.355654+00 | 2026-11-16 23:37:57.396752+00 | 1047.0 | ended |  |

## Submissions and cost (the shared trial ledger)

9 submissions reserved before dispatch: settled 9; results charged 9; USD settled 0.013500 at the recorded rate.

- `run --store marianos-53100502-pickup --categories 0,27` (M-P7-one-lane-pilot-110rc6-20261116): 2026-11-16T23:20:30+00:00 to 2026-11-16T23:38:02+00:00, exit 0 after 1052.5 s, revision d77f3065c757b8b962524dbf8d9961dec212e72b; gate counts {"reserved": 9, "dispatched": 9, "unsent": 0, "settled": 9, "settled_free": 0, "unknown": 0}

## Pages

7 answers asked as listing pages: by state completed 2, refused 1, stopped 4; by verdict malformed 1, new 2, repeated 4.
Store checks on every answer: PASS; locations 53100502; fulfillment PICKUP.

Requests set aside: 2 ({"exhausted": 1, "recovered": 1}); re-asks answered 3; new products brought by counted re-asks 24; shortest time between two answers of one request 304.9 s.

## Products

Distinct fresh valid products (this run's own observations, status valid): **46** in 1 categories; retained dataset 8152 records (verified 46, carried from earlier runs 8104).
Identity sets: `{"record_rows": 8152, "fresh_valid": 46, "fresh_not_valid": 2, "carried_forward": 8104, "excluded": 0, "excluded_rows": 0, "exported_rows": 8152, "retained_unique": 8152, "duplicates": 0, "overlaps": {"fresh_valid & fresh_not_valid": 0, "fresh_valid & carried_forward": 0, "fresh_valid & excluded": 0, "fresh_not_valid & carried_forward": 0, "fresh_not_valid & excluded": 0, "carried_forward & excluded": 0}, "relations": {"no identity is in two classes": true, "retained = fresh valid + fresh not valid + carried forward": true, "no exported identity twice": true}, "holds": true}`

## Coverage and gates

Listings: {"INCOMPLETE": 1}; CSV rows: {"COMPLETE": 1, "NOT_ATTEMPTED": 26, "INCOMPLETE": 1}.

Gates: G1 PASS, G2 PASS, G3 FAIL, G4 PASS, G5 PASS, G6 PASS, G7 PASS, G8 PASS, G9 PASS, G10 PASS, G11 PASS, G12 PASS, G13 PASS, G14 FAIL. Run status: rejected (rejected).

Listings not complete:

- row 27 Hardware Home Improvement / - (33): 48 of 65, INCOMPLETE: accessible pages exhausted; coverage incomplete: page 3: page 3 repeats an earlier page exactly; asked again 2 time(s), each at least 300 s after the last answer or attempt: re-ask 1: repeated (page 3 repeats an earlier page exactly); re-ask 2: repeated (page 3 repeats an earlier page exactly); the re-asks are spent, which says nothing about where the listing ends: its remaining results were not read

