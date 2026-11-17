# Run report: run 01M7KQ5GZVF5VK1S9FGTG6YFC9

Stages: M-R7a-full-run-110rc6-20261117. Store marianos-53100502-pickup (location 53100502, PICKUP). Not a pilot (no command-line narrowing or limit).

## What was asked

- `M-R7a-full-run-110rc6-20261117`: `run --store marianos-53100502-pickup --rows-first 22,27,23,24,25,26,15 --term-upc 0001780014939 --term-upc 0001780014941 --term-upc 0002310014848 --term-upc 0003980014995`; ceiling 160 submissions, USD 0.240000; deadline 2026-11-17T04:15:17Z; approved: Hamza's brief of 16 November 2026 (closeout after 1.10.0rc5): USD 5 of free credit authorized for Mariano's on the Oxylabs Web API credential he supplied, on his own Azure VM, accounted in the campaign oxylabs-marianos-20261116 (cap 5.00, headroom 0.10, Mariano's envelope 4.90); the client's VM, the client's billing, Oxylabs Classic and other providers stay outside it; no top-up or paid overage
- Objective (first stage): one logical full-scope run R7 of the candidate 1.10.0rc6 (every CSV row 0-27 as configured; not a pilot: --rows-first only orders the plan, reading rows 22, 27, 23 to 26 and 15 first, and --term-upc names the four product pages of the review; neither narrows the scope), two lanes, read in slices, each one ledger stage of the new credential's campaign oxylabs-marianos-20261116 whose ceiling is also set in the collector (set-ceiling). Every slice is ended by the operator with SIGTERM once the stage has its target of reservations (a resumable stop, exit 75); the ceiling, 10 above the target, is the backstop. Why R7: run R6 started at 23:40Z on 2026-11-16, when the site served page 1 again for 25 of 29 answers to a page 2 or later and for all 12 re-asks (measured by hour over all runs of the day: 10% at 03Z, 20-27% at 15Z, 28-34% at 16-17Z, 55-60% at 18Z, 80-86% at 23Z); a page has at most 2 re-asks in a run, so R6 was finalized offline after its first slice (rejected, never published) and R7 starts afresh in the night hours, with every page's re-asks intact. The envelope then held USD 4.7935 (3,195 submissions); a full run needs 3,145 to 3,750 submissions at F2's measured 1.43 per counted page, fewer at the night rate: if the envelope ends first, the run is left resumable after its last slice and the shortfall is reported with R7's measured rates. This slice starts the run and measures the hour's repeat rate before the larger slices.

## Code and segments

Revisions recorded by the run's segments: 1.10.0rc6 (d77f3065c757b8b962524dbf8d9961dec212e72b) (one revision for the whole run)

| segment | trigger | started (UTC) | ended (UTC) | active s | end state | stop code |
|---|---|---|---|---|---|---|
| 01M7KQ5H6KDYDQEWNQJY7NTH23 | manual | 2026-11-17 03:00:20.817949+00 | 2026-11-17 03:04:55.879433+00 | 275.1 | ended | TERMINATED |

## Submissions and cost (the shared trial ledger)

46 submissions reserved before dispatch: settled 44, unknown 2; results charged 44; USD settled 0.066000 at the recorded rate.

- `run --store marianos-53100502-pickup --rows-first 22,27,23,24,25,26,15 --term-upc 0001780014939 --term-upc 0001780014941 --term-upc 0002310014848 --term-upc 0003980014995` (M-R7a-full-run-110rc6-20261117): 2026-11-17T03:00:20+00:00 to 2026-11-17T03:04:55+00:00, exit 75 after 275.6 s, revision d77f3065c757b8b962524dbf8d9961dec212e72b; gate counts {"reserved": 46, "dispatched": 46, "unsent": 0, "settled": 44, "settled_free": 0, "unknown": 2}

## Pages

39 answers asked as listing pages: by state completed 27, refused 5, stopped 7; by verdict malformed 5, new 27, repeated 7.
Store checks on every answer: PASS; locations 53100502; fulfillment PICKUP.

Requests set aside: 7 ({"waiting": 7}); re-asks answered 0; new products brought by counted re-asks 0; shortest time between two answers of one request None s.

## Products

No export yet: the run is interrupted, and the collector writes a run's export when the run is finalized (`export --run` before that is refused, exit 2). The pages read so far are in the listing tables above.

## Coverage and gates

Listings: null; CSV rows: {}.

Gates: . Run status: interrupted (None).

