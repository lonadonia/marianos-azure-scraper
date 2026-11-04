# The shared Classic probe: corrected as release 1.7.0 (pinned reference)

Added on 2026-11-04, after the 1.8.0rc5 publication (tag `review-1.8.0rc5-20261102`). This file, one sentence of
[`README.md`](../README.md) and their rows in the two manifests are the only changes; `source/` and `classic-probe/`
stay the frozen trees of 1.8.0rc5.

The client's second Walmart review found five defects (C1 to C5) in the Walmart Classic offline probe 1.5.2. The
probe in [`classic-probe/`](../classic-probe/) here is the shared probe **1.6.0**, and it has the same five defects in
its shared layer. They are corrected in the shared probe **1.7.0**, published with the Walmart delivery:

| | |
|---|---|
| Published at | [https://github.com/lonadonia/walmart-azure-scraper](https://github.com/lonadonia/walmart-azure-scraper/tree/bcb53e81ff412e629ebf4a58b400be62e2fa8327/classic-probe-1.7.0), commit `bcb53e81ff412e629ebf4a58b400be62e2fa8327` (tag `review-1.6.5-20261104`), folder `classic-probe-1.7.0/` |
| Source revision | Git tree `8305ffe25665b404347954dad38d501cbba70640` of the probe, the same at `1780349e522d771a3642fe88bfb7b542044ec844`, where its archive was built, and at `67d216eb8ee2ec839a437b0b5bf2d594324b6982` (Walmart collector 1.6.5) |
| What was corrected | C1 a redirect is never followed; C2 a request runs in its own process, killed at its time limit, and every size is bounded; C3 the clock is read under the ledger's lock and checked again before sending; C4 each answer is written to disk and indexed before the next paid step; C5 a retry really waits. Details and tests: [`review/CLASSIC_PROBE_CORRECTIONS.md`](https://github.com/lonadonia/walmart-azure-scraper/blob/bcb53e81ff412e629ebf4a58b400be62e2fa8327/review/CLASSIC_PROBE_CORRECTIONS.md) |
| The Mariano's adapter | `src/classic_probe/marianos.py`, blob `9de6510bddbb0cae7fd86e09dac5ed32fc3487a4` in 1.7.0: byte for byte the one in `classic-probe/` here (blob `9de6510bddbb0cae7fd86e09dac5ed32fc3487a4`, tree `33c2d786fa793e2e588746f219eb9118cc789c38`). Every correction is in the shared layer: transport, ledger, campaign, deadline and captures |
| Live mode | disabled in both. Neither probe has ever sent a request to Oxylabs, and a live Classic test is not approved |

A Classic run for Mariano's, if the client chooses Classic and approves it, would use 1.7.0 or a later corrected
revision, never the 1.6.0 copy in `classic-probe/`.
