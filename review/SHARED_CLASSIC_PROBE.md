# The shared Classic probe: release 1.7.3 (pinned, published here)

Added on 2026-11-04 for the shared probe 1.7.0 (tag `review-1.8.0rc5-probe170-20261104`), changed on 2026-11-05 for
1.7.1 (tag `review-1.8.0rc5-probe171-20261105`), and on 2026-11-09 for **1.7.3**, with the collector 1.9.0rc4 (tag
`review-1.9.0rc4-20261109`). On 2026-11-12, with the collector 1.10.0rc3 (tag `review-1.10.0rc3-20261112`), the pin stays at
1.7.3 and Walmart's probe 1.7.4 is linked below. The earlier texts stay at their tags. [`classic-probe/`](../classic-probe/) stays the frozen probe 1.6.0
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

**Walmart's probe 1.7.4 (published by the Walmart project; its proof is Walmart's).** On 2026-11-11 the Walmart
repository published the shared probe **1.7.4** at its tag [`review-1.6.8-probe174-20261111`](https://github.com/lonadonia/walmart-azure-scraper/tree/review-1.6.8-probe174-20261111) (commit
`00a18947668feb7d54bf5c019654d89bf0ad56a0`). It is 1.7.3 with the session's process supervision on Windows
corrected (C2, the client's review of 1.7.2 there): a session runs only once a verified job object holds it, a
failure refuses it with no fallback, and a cleanup that cannot be verified stays unknown. Nothing was run for it
here and no Walmart file was changed for this publication:

| | |
|---|---|
| Corrected source | [`classic-probe-1.7.4/`](https://github.com/lonadonia/walmart-azure-scraper/tree/review-1.6.8-probe174-20261111/classic-probe-1.7.4): the probe's tree `07477cc61b2c1aa0871fb17965b132c131314fc6` (`oxylabs-classic-probe/`), development commit `a1def53747dfabcb2ad9ca97efc421c1e70f0ac6`, on 1.7.3 (`95f96a0`), so it keeps T05 |
| Windows regression | [`evidence/offline-tests/1.7.4-classic-probe/`](https://github.com/lonadonia/walmart-azure-scraper/tree/review-1.6.8-probe174-20261111/evidence/offline-tests/1.7.4-classic-probe): [`REPRODUCE.md`](https://github.com/lonadonia/walmart-azure-scraper/blob/review-1.6.8-probe174-20261111/evidence/offline-tests/1.7.4-classic-probe/REPRODUCE.md), [`REPRODUCTION_ON_1.7.2_WINDOWS.log`](https://github.com/lonadonia/walmart-azure-scraper/blob/review-1.6.8-probe174-20261111/evidence/offline-tests/1.7.4-classic-probe/REPRODUCTION_ON_1.7.2_WINDOWS.log) (the review tests failing on 1.7.2 by their output), [`CANDIDATE_1.7.4_WINDOWS.log`](https://github.com/lonadonia/walmart-azure-scraper/blob/review-1.6.8-probe174-20261111/evidence/offline-tests/1.7.4-classic-probe/CANDIDATE_1.7.4_WINDOWS.log) (passing on 1.7.4) |
| What changed and why | [`review/CLASSIC_PROBE_CORRECTIONS.md`](https://github.com/lonadonia/walmart-azure-scraper/blob/review-1.6.8-probe174-20261111/review/CLASSIC_PROBE_CORRECTIONS.md) in the Walmart repository |
| The Mariano's adapter | `src/classic_probe/marianos.py`, blob `9de6510bddbb0cae7fd86e09dac5ed32fc3487a4`: unchanged, the same as here |

**Mariano's keeps the pin at 1.7.3** in this publication: 1.7.4's correction is the process supervision of a
probe session on Windows, live Classic stays disabled for Mariano's, and moving the pin is the owner's decision (a
separate publication, with the probe's offline suite run on the pinned tree).

A Classic run for Mariano's, if the client chooses Classic and approves it, would use 1.7.4 or a later corrected
revision (1.7.3's Windows supervision is the one 1.7.4 corrects), never the 1.6.0 copy in `classic-probe/`.
