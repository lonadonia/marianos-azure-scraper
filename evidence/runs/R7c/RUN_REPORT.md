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

No export yet: the run is interrupted, and the collector writes a run's export when the run is finalized (`export --run` before that is refused, exit 2). The pages read so far are in the listing tables above.

## Coverage and gates

Listings: null; CSV rows: {}.

Gates: . Run status: interrupted (None).

