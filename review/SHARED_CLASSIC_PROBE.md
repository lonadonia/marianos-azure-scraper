# The shared Classic probe: release 1.7.3 (pinned, published here)

Added on 2026-11-04 for the shared probe 1.7.0 (tag `review-1.8.0rc5-probe170-20261104`), changed on 2026-11-05 for
1.7.1 (tag `review-1.8.0rc5-probe171-20261105`), and on 2026-11-09 for **1.7.3**, with the collector 1.9.0rc4 (tag
`review-1.9.0rc4-20261109`). The earlier texts stay at their tags. [`classic-probe/`](../classic-probe/) stays the frozen probe 1.6.0
of 1.8.0rc5.

**Where it is.** Release 1.7.3 is published in this repository, in [`classic-probe-1.7.3/`](../classic-probe-1.7.3/):

| | |
|---|---|
| Source revision | Git tree `912801d038092bc84906f6e0c5507388980fb9d8` (development commit `95f96a02329bd3a92c9c8b07dd53e53ae89fe553`, folder `headless/oxylabs-classic-probe`); `git rev-parse review-1.9.0rc4-20261109:classic-probe-1.7.3` prints the same tree id |
| Lineage | 1.6.0 (here, frozen) -> 1.7.0 and 1.7.1 (C1 to C5; 1.7.1 published with the Walmart delivery 1.6.6) -> 1.7.2 (published with the Walmart delivery 1.6.8) -> **1.7.3** |
| What 1.7.3 changes | **T05:** `replay` checks its saved responses before it creates anything. A missing, malformed or invalid `replay.json`, or a step whose body file is missing, ends with one line and exit 2: no traceback, no output folder, no ledger, no network and no credential read. Valid replays behave as before. Only `src/classic_probe/cli.py` and the version changed in `src/` |
| Unchanged since 1.7.1 | `transport.py`, `ledger.py` and `campaign.py`, which carry the C1 to C5 corrections ([CLASSIC_PROBE_CORRECTIONS.md](https://github.com/lonadonia/walmart-azure-scraper/blob/4bae4fb383dc47ac44c3175896edaf19ae1064cc/review/CLASSIC_PROBE_CORRECTIONS.md)) |
| Offline proof | the probe's suite on this tree: 222 passed, 5 skipped. The 23 T05 tests (`tests/test_t05_replay_input.py`) fail 22 times on 1.7.2 and pass on 1.7.3; the reproduction on both is in [`evidence/1.9.0/repro/`](../evidence/1.9.0/repro/) |
| The Mariano's adapter | `src/classic_probe/marianos.py`, blob `9de6510bddbb0cae7fd86e09dac5ed32fc3487a4`: byte for byte the one in `classic-probe/` (tree `33c2d786fa793e2e588746f219eb9118cc789c38`, publication revision `1f568b8d367ee90e0f4a87879a44873ae649e906`) |
| Vendored collector files | Mariano's `initial_state.py` is copied byte for byte (blob `44ee75d54f31a92d4ff8900f36eb0819583005bb`) and `sanitize.py` with its import line alone rewritten (origin blob `6530c7afd59b2cdfc54294b4cf1810f35e30aa8f`), as `vendor/VENDORED.json` records and `tests/test_vendored.py` checks. Collector 1.9.0rc4 holds the same two blobs: neither file has changed since it was copied |
| Live mode | disabled. The probe has never sent a request to Oxylabs, and a live Classic test is not approved |

**What it does not prove.** The adapter replays real Web API page bodies inside synthetic Classic envelopes, which
are not real Classic responses. It plans search page 1, product and category-URL steps and no Mariano's page 2:
no documented Classic page parameter for Mariano's was found, so full Classic pagination is not proved.

**The Walmart repository** still pins 1.7.2 (its delivery 1.6.8). The T05 change is in the shared CLI only; giving
that repository the same pinned reference to 1.7.3 is a separate publication there, not made with this one.

A Classic run for Mariano's, if the client chooses Classic and approves it, would use 1.7.3 or a later corrected
revision, never the 1.6.0 copy in `classic-probe/`.
