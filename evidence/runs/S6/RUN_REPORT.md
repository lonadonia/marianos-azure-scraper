# Run report: run 01M7H79NGE1BT9KH49QR8EV4QJ

Stages: M-S6-later-page-recovery-110rc3-20261116. Store marianos-53100502-pickup (location 53100502, PICKUP). A pilot: never published.

## What was asked

- `M-S6-later-page-recovery-110rc3-20261116`: `run --store marianos-53100502-pickup --categories 22,23,24,25,26,27 --max-credits 130`; ceiling 130 submissions, USD 0.195000; deadline 2026-11-16T06:14:27Z; approved: not in this stage record (prepared before the field was added); the authorization is Hamza's update of 16 November 2026, entered in the trial ledger as the event note:authorization_update before the stage was opened
- Objective (first stage): whether C1 recovers later pages on the live site: rows 22-27 (17 listings; 1,190 products stated on 2026-11-09) in one logical run, one lane. Measured: how many requests are set aside, how many a re-ask recovers and after how long, the submissions spent on re-asks, and whether the run completes its scope (G3) with at least 500 distinct fresh valid products (G14)

## Code and segments

Revisions recorded by the run's segments: 1.10.0rc3 (a1040f79919b8e876e0b69cd909cecf9363780b4) (one revision for the whole run)

The segments table was not exported for this stage (its evidence was collected before that export was added); the revision above comes from the run's SEGMENT_STARTED events.

## Submissions and cost (the shared trial ledger)

67 submissions reserved before dispatch: settled 67; results charged 67; USD settled 0.100500 at the recorded rate.

- `run --store marianos-53100502-pickup --categories 22,23,24,25,26,27 --max-credits 130` (M-S6-later-page-recovery-110rc3-20261116): 2026-11-16T03:44:29+00:00 to 2026-11-16T04:01:19+00:00, exit 0 after 1009.7 s, revision a1040f79919b8e876e0b69cd909cecf9363780b4; gate counts {"reserved": 67, "dispatched": 67, "unsent": 0, "settled": 67, "settled_free": 0, "unknown": 0}

## Pages

63 answers asked as listing pages: by state completed 58, refused 1, stopped 4; by verdict malformed 1, new 57, partial_overlap 1, repeated 4.
Store checks on every answer: PASS; locations 53100502; fulfillment PICKUP.

Requests set aside: 3 ({"recovered": 3}); re-asks answered 4; new products brought by counted re-asks 72; shortest time between two answers of one request 304.5 s.

## Products

Distinct fresh valid products (this run's own observations, status valid): **1141** in 6 categories; retained dataset 1168 records (verified 1141, carried from earlier runs 0).
Identity sets: `{"record_rows": 1168, "fresh_valid": 1141, "fresh_not_valid": 27, "carried_forward": 0, "excluded": 0, "excluded_rows": 0, "exported_rows": 1168, "retained_unique": 1168, "duplicates": 0, "overlaps": {"fresh_valid & fresh_not_valid": 0, "fresh_valid & carried_forward": 0, "fresh_valid & excluded": 0, "fresh_not_valid & carried_forward": 0, "fresh_not_valid & excluded": 0, "carried_forward & excluded": 0}, "relations": {"no identity is in two classes": true, "retained = fresh valid + fresh not valid + carried forward": true, "no exported identity twice": true}, "holds": true}`

## Coverage and gates

Listings: {"DONE": 14, "EMPTY": 2, "INCOMPLETE": 1}; CSV rows: {"NOT_ATTEMPTED": 22, "COMPLETE": 5, "INCOMPLETE": 1}.

Gates: G1 PASS, G2 PASS, G3 FAIL, G4 PASS, G5 PASS, G6 PASS, G7 PASS, G8 PASS, G9 PASS, G10 PASS, G11 PASS, G12 PASS, G13 PASS, G14 PASS. Run status: rejected (rejected).

Listings not complete:

- row 23 Candles Home Fragrances / - (32001): 57 of 58, INCOMPLETE: accessible pages exhausted; coverage incomplete: 3 page(s) read, 57 distinct products of 58 reported

