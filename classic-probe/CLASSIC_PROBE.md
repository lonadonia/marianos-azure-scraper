# The Mariano's Classic probe: frozen for review, offline results

**What it is.** `oxylabs-classic-probe` **1.6.0** is an offline probe and request plan for the Oxylabs **Classic**
Web Scraper API (Realtime method). It is frozen in this folder, `classic-probe/`, file for file the `classic_probe/`
of `MARIANOS_SOURCE_1.8.0rc5.zip`, with its lock file, tests and documents (this note is the only added file).

- **Its live mode is disabled.** No command sends a request or reads a credential.
- **It does not use the collectors' accounts.** Nothing here comes from or says anything about the Oxylabs Web API
  accounts the collectors use.
- **Why it is not run live:** Classic execution is not approved by the client, and there are no Classic credentials.

## Documents in the frozen probe

| Document | What it holds |
|---|---|
| [`classic-probe/README.md`](README.md) | what the build does and will not do; the campaign limits; the Walmart and Mariano's steps |
| [`classic-probe/CLASSIC_TEST_PLAN.md`](CLASSIC_TEST_PLAN.md) | the test plan for a future approved campaign: sequence, stops, evidence |
| [`classic-probe/docs/DOCUMENTED_CONTRACT.md`](docs/DOCUMENTED_CONTRACT.md) | the request contract from Oxylabs' documentation (Mariano's pages read on 2026-11-02) |
| [`classic-probe/docs/PAYLOAD_MATRIX.md`](docs/PAYLOAD_MATRIX.md) | every planned payload in full |
| [`evidence/classic-probe/oxylabs-docs-20261102/`](../evidence/classic-probe/oxylabs-docs-20261102/) | the saved Oxylabs documentation pages. Nine general pages are byte-identical to 2026-10-31. `targets/marianos.md` answers "Page Not Found" |

## The Mariano's steps (planned, never sent)

1. `marianos-search-p1`: `marianos_search` for `cereal`, store 53100502, `fulfillment_type` pickup.
2. `marianos-product`: `marianos_product` for page 1's first ranked product (never a sponsored placement).
3. `marianos-category-url`: `/pl/cereal-granola/03001` by URL alone. It is last, because the documentation states no
   store parameter for this form and a page of another store stops the campaign.

**No second page is planned.** `marianos_search` documents no page parameter. The Web API's `/pl/?page=N`, which works
([`review/PROVIDER_COMPARISON.md`](../review/PROVIDER_COMPARISON.md)), says nothing about Classic.

## Aggregate limits (shared with the Walmart probe)

The limits are those of the separately versioned Walmart probe 1.5.2, unchanged:

| Limit | Value |
|---|---|
| Requests | 10 per retailer, 20 in all |
| Campaign time | 30 minutes |
| Charges | USD 5.00 combined, less USD 0.50 of headroom |

- **One ledger for both retailers.** It is append-only, and each request reserves its worst-case charge before it
  leaves.
- **The Walmart package is not modified.**
- **Proof, offline** (synthetic tests, [`classic-probe/tests/`](tests/)):
  - concurrent processes, crashes and both retailers on one ledger;
  - the 11th request never reserved;
  - no second ledger granting a fresh budget.

## Commands and offline results

These ran from the clean extraction of `MARIANOS_SOURCE_1.8.0rc5.zip` ([`evidence/classic-probe/from-1.8.0rc5-archive/probe_x19.log`](../evidence/classic-probe/from-1.8.0rc5-archive/probe_x19.log), 2026-11-02
15:21-15:22Z), and earlier from 1.8.0rc4's ([`evidence/classic-probe/from-1.8.0rc4-archive/`](../evidence/classic-probe/from-1.8.0rc4-archive/)):

| Command | Result |
|---|---|
| `uv sync --frozen --offline` | exit 0 |
| `uv run pytest -q` | 93 passed, 2 skipped, exit 0 (the log keeps pytest's progress marks, 93 `.` and 2 `s`, without its summary line) |
| `uv run ruff check src tests`, `ruff format --check`, `mypy` | clean |
| `classic-probe plan --targets config/targets.json` | exit 0: the request-by-request plan, with `not_planned` naming the missing second page |
| `classic-probe validate --targets config/targets.json` | exit 0 |
| `classic-probe replay … --rates config/rates.example.json` | **refused, exit 2, by design**: the example rates are not confirmed |
| `classic-probe campaign-init … --offline`, then `classic-probe live --manifest …` | **refused, exit 3**: lists what is missing (the approval naming the ledger, credentials, entitlement, confirmed rates) |
| `classic-probe replay … --fixtures <folder> --rates SYNTHETIC_rates_offline_replay.json` | exit 0: the three Mariano's steps run against saved responses, each reserved first |

**About that last replay:**

- **The folder** is built by [`evidence/tools/probe_fixtures180.py`](../evidence/tools/probe_fixtures180.py) from the probe's own test material. The pages inside are
  real Vernon Hills Pickup pages saved by the collector through the **Web API**. The Classic envelopes around them are
  **synthetic**, because no Classic response exists. So is the rate card.
- **What it shows:** the plan, the checks and the ledger work offline. It does not show what Classic returns.

**Open defect (T05).** `replay` on a folder without `replay.json` ends in a Python traceback (exit 1), not a clean
refusal. Nothing is sent either way. It is not fixed in this delivery.

## Before any live Classic request

All of these are needed:

- the client's approval for Classic;
- the account owner's credentials, installed by the owner;
- the entitlement for the Mariano's sources;
- confirmed rates;
- a new build with live mode enabled (a code change and a new version);
- an approval that names the campaign's ledger.

The client VM is not to be used for it unless the client approves.
