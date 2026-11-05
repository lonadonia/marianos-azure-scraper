# The shared Classic probe: release 1.7.1 (pinned reference)

Added on 2026-11-04, after the 1.8.0rc5 publication (tag `review-1.8.0rc5-20261102`), for the shared probe 1.7.0
(tag `review-1.8.0rc5-probe170-20261104`). Changed on 2026-11-05 for the shared probe 1.7.1 (tag `review-1.8.0rc5-probe171-20261105`). Each time, this file, one
sentence of [`README.md`](../README.md) and their rows in the two manifests were the only changes; `source/` and
`classic-probe/` stay the frozen trees of 1.8.0rc5.

**A correction of this file.** On 2026-11-04 this file said that the shared probe 1.7.0 corrects the five defects
C1 to C5. That was true of C1, C3 and C5. C2 and C4 were corrected only in part. Release 1.7.1 completes them, and
each gap was first reproduced by a test that fails on 1.7.0. The earlier text stays at the tag
[`review-1.8.0rc5-probe170-20261104`](https://github.com/lonadonia/marianos-azure-scraper/blob/review-1.8.0rc5-probe170-20261104/review/SHARED_CLASSIC_PROBE.md).

The client's second Walmart review found five defects (C1 to C5) in the Walmart Classic offline probe 1.5.2. The
probe in [`classic-probe/`](../classic-probe/) here is the shared probe **1.6.0**, and it has the same five defects in
its shared layer. The shared probe **1.7.1**, published with the Walmart delivery 1.6.6, corrects all five:

| | |
|---|---|
| Published at | [https://github.com/lonadonia/walmart-azure-scraper](https://github.com/lonadonia/walmart-azure-scraper/tree/4bae4fb383dc47ac44c3175896edaf19ae1064cc/classic-probe-1.7.1), commit `4bae4fb383dc47ac44c3175896edaf19ae1064cc` (tag `review-1.6.6-20261105`), folder `classic-probe-1.7.1/` |
| Source revision | Git tree `7adfea8fbd8e562fd72444891e62e3029d544a5f` of the probe, the same at `68ff3d8518b38a3792792ed6ffb8e73c2756245f`, where its code last changed, and at `cbea802891d4e66b74a0abc33e0af0af74c89708` (Walmart collector 1.6.6), where its archive was built: `OXYLABS_CLASSIC_OFFLINE_PROBE_1.7.1.zip`, SHA-256 `89558e533d3d5b9c2fc2981a6caf168c481ba637a02eb5cb46eec3bce467c4f9` |
| What 1.7.0 corrected | C1 a redirect is never followed; C3 the clock is read under the ledger's lock and checked again before sending; C5 a retry really waits. C2 and C4 only in part |
| What 1.7.1 completes | C2: the deadline now holds through recovery, export and cleanup. The ledger writes after an answer end within the session's write window; the supervisor's kill, reap and recovery all end by the hard end, and the recovery runs in its own process. C4: each answer is kept durably, as received, before anything else is done with it, and a crash loses no paid answer: the recovery keeps it without a paid refetch. A body cut short is kept and recorded, never as an answer, and every evidence file is synced before it is renamed into place. Details and tests: [`review/CLASSIC_PROBE_CORRECTIONS.md`](https://github.com/lonadonia/walmart-azure-scraper/blob/4bae4fb383dc47ac44c3175896edaf19ae1064cc/review/CLASSIC_PROBE_CORRECTIONS.md) |
| Offline proof | from the probe's archive: 173 tests, 171 passed and 2 skipped (the vendored-file check, which needs the collectors' sources beside it); 7 reproduction tests fail on 1.7.0's code and pass on 1.7.1 ([`offline_results/`](https://github.com/lonadonia/walmart-azure-scraper/tree/4bae4fb383dc47ac44c3175896edaf19ae1064cc/classic-probe-1.7.1/offline_results)) |
| The Mariano's adapter | `src/classic_probe/marianos.py`, blob `9de6510bddbb0cae7fd86e09dac5ed32fc3487a4` in 1.7.1: byte for byte the one in `classic-probe/` here (blob `9de6510bddbb0cae7fd86e09dac5ed32fc3487a4`, tree `33c2d786fa793e2e588746f219eb9118cc789c38`). Every correction is in the shared layer |
| Live mode | disabled in both. Neither probe has ever sent a request to Oxylabs, and a live Classic test is not approved |

A Classic run for Mariano's, if the client chooses Classic and approves it, would use 1.7.1 or a later corrected
revision, never the 1.6.0 copy in `classic-probe/` or 1.7.0.
