# Classic test plan (proposed; not approved, not run)

This is how a small Classic campaign could be run for Walmart and for Mariano's, once the account's owner has approved it.

This build (1.6.0) implements Stage W (Walmart, unchanged from 1.5.2) and Stage M (Mariano's, added in 1.6.0), on one shared ledger with the limits of the Walmart probe 1.5.2.

None of it has been run. This build's live mode is disabled, and no request has been made to Oxylabs Classic. The limits below are the proposal sent to the client: they are a proposal, not an approval.

## What has to exist first (the account owner)

| # | What | Why | How the probe checks it |
| --- | --- | --- | --- |
| 1 | The Classic account's API user, set in `OXYLABS_CLASSIC_USERNAME` and `OXYLABS_CLASSIC_PASSWORD` on the machine that runs the campaign, never in a file | the probe reads credentials only from the environment, only on the live path, after every other gate | `gates.evaluate` (presence only; the values are never shown or kept) |
| 2 | A statement of the account's entitlement: `walmart_search` and `walmart_product` (Stage W), `marianos_search` and `marianos_product` (Stage M), with the Realtime method | the documentation cannot say what this account may use | `entitlement.json`: verified by the owner, per retailer |
| 3 | The account's maximum rate per result for each class (the Mariano's ones included), read from the account, with where it was read | no rate ships with the probe, and an unknown rate prevents dispatch | `rates.json` with `"synthetic": false`. Only USD per result gives a bound |
| 4 | One ledger for the whole campaign: `campaign-init` without `--offline`, once, on a local disk of the one machine that runs both retailers' parts | a second ledger or a copy on another machine would spend a second allowance | the ledger's genesis id. The approval must name it |
| 5 | An approval naming the campaign, that ledger's genesis id and the retailers | approval in one context does not extend to another | `approval.json` |
| 6 | A separately approved build with live mode enabled | this build cannot send anything | `gates.LIVE_ENABLED` |

`classic-probe live --manifest M --approval A --entitlement E --rates R` lists everything still missing, and sends nothing.

## The limits (shared by both retailers, in one ledger)

- 10 dispatched requests per retailer.
- 20 for both retailers. This includes any setup, authentication or qualification call, every retry and every restart.
- 30 minutes for the combined campaign from its first reservation, with the last 3 minutes kept for evidence export and cleanup.
- USD 5.00 of combined provider charges, less USD 0.50 of headroom for delayed or uncertain charges. Each retailer has USD 2.25, which is not borrowed.
- A request is reserved before it is sent, and its reservation stays until the owner records the charge read from the account (`confirm-charge`).

## Stage W: Walmart (one invocation, at most 8 dispatches)

The steps and their checks are in [docs/PAYLOAD_MATRIX.md](docs/PAYLOAD_MATRIX.md):

1. search page 1;
2. page 2, only if page 1 shows one;
3. one product page;
4. a category page by URL.

The first failed check stops everything, and nothing more is sent.

| Outcome | What it would show |
| --- | --- |
| Step 1 passes | Classic served this account a Walmart search for store 3891 Pickup, as Walmart's own page data states it |
| Step 1 stops: another store, or no store | Classic's `store_id` did not set the store for this request. Nothing in the collector may use Classic for this store until that is solved |
| Step 2 passes | `start_page` advanced for this query and store (one case, not a general property) |
| Step 2 stops: a repeated or empty page | pagination is not shown to work. No more pages are asked for |
| Step 3 passes | a product page for the requested item, for the store, with its UPC as the collector reads it |
| Step 4 passes or stops | whether a category page by URL comes for the store. The documentation does not say |
| A challenge or a retailer refusal | Walmart refused the request. It is a stop, not a retry |
| HTTP 401 or 403 | the credentials or the entitlement. The owner resolves it, then a new approval is needed |

After the invocation, the owner reads the account's usage and records each dispatch's charge with `confirm-charge`. The evidence is then exported (`export`) and reviewed:

- `campaign_evidence.json`;
- the sanitized `response_NNN.json.gz` files;
- `ledger_export.json`.

What it will not show, whatever the outcome:

- coverage of the client's categories;
- the rate a full run would sustain;
- the cost of a full run;
- anything about Mariano's.

## Stage M: Mariano's (one invocation, at most 6 dispatches; added in 1.6.0)

Store 53100502 (Marianos Vernon Hills, 1720 N Milwaukee Ave, Vernon Hills, IL 60061), Pickup. 53100503 is refused: it is the Lakeshore East store of earlier tests. The steps and their checks are in [docs/PAYLOAD_MATRIX.md](docs/PAYLOAD_MATRIX.md):

1. search page 1 (`marianos_search`, `cereal`, the store, `pickup`);
2. one product page (`marianos_product`, page 1's first ranked product);
3. a category page by URL (`/pl/cereal-granola/03001`).

There is no page-2 step: the documentation gives `marianos_search` no page parameter. The first failed check stops everything, and nothing more is sent. Stage M uses the same ledger as Stage W, with Mariano's own share (10 requests, USD 2.25), and the campaign's 30 minutes are shared: if Stage W used most of them, the ledger refuses what no longer fits (`STOP_DEADLINE`).

| Outcome | What it would show |
| --- | --- |
| Step 1 passes | Classic served this account a Mariano's search for 53100502 Pickup, as the page's own state states it: selected store, the search's own store and modality, every stated price's store |
| Step 1 stops: another store or fulfillment, or no page state | `store_id` and `fulfillment_type` did not set the context for this request. Nothing in the collector may use Classic for this store until that is solved |
| Step 2 passes | a product page for the requested product, with its prices for the store |
| Step 2 stops: the product's prices state no store | the product page alone does not prove the store's price (the Mariano's collector met this on 2026-11-02 through the Web API: a product temporarily out of stock at the store, its price stated for ZIP 60061) |
| Step 3 passes or stops | whether a category page by URL comes for the store and Pickup. The documentation does not say |
| A refusal page or a retailer status that is not 2xx | Mariano's refused the request. It is a stop, not a retry |
| HTTP 401 or 403 | the credentials or the entitlement. The owner resolves it, then a new approval is needed |

What Stage M will not show, whatever the outcome: any page after the first, coverage of the client's categories, the rate or cost of a full run. **Listing pagination through Classic stays an open gap.**

## Ending the campaign

- **Nothing left running:** no process of the probe stays running. A request still open at its deadline is recorded as unknown, keeps its reservation, and is never retried.
- **History kept:** the ledger is kept and never deleted, because it is the campaign's spend history.
- **No limit reset:** nothing resets a limit. A new campaign is a new approval with a new ledger.
