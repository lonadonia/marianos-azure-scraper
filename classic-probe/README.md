# oxylabs-classic-probe 1.6.0

An **offline** probe and request plan for the Oxylabs **Classic** Web Scraper API (Realtime method). It holds three things:

- the documented request contract;
- the checks a Classic response must pass before anything more is sent;
- one durable ledger that enforces the proposed campaign limits for both retailers together.

**Its live mode is disabled.** No command of this build sends a request to Oxylabs or to a retailer, and no command reads a credential.

Version 1.6.0 adds the **Mariano's** steps (Mariano's Vernon Hills, store 53100502, 1720 N Milwaukee Ave, Vernon Hills, IL 60061, Pickup) to the Walmart steps of 1.5.2. The Walmart steps, the response checks of the Walmart steps and the campaign limits are unchanged: both retailers run on the one shared ledger, with the same limits as the separately versioned Walmart probe 1.5.2 that ships in the Walmart package. That Walmart package is not modified by this release.

This package is separate from both collectors. It does not use their Oxylabs Web API, Scrape.do or Scrapfly accounts, and nothing here is evidence of what Classic returns.

| What | Status in this build |
| --- | --- |
| Request contract (payload forms, parameter names) | Built from the official documentation: Walmart read on 2026-10-31, Mariano's read on 2026-11-02 ([docs/DOCUMENTED_CONTRACT.md](docs/DOCUMENTED_CONTRACT.md)) |
| Response checks: Walmart (store, fulfillment, identity, pagination, challenge, parser status) | **SYNTHETIC TEST**: tested against invented responses shaped like the documented envelope |
| Response checks: Mariano's (selected store and modality, the search's own store and modality, each price's store, identity, refusal) | **OFFLINE REPLAY**: tested on two real Mariano's pages (Vernon Hills, Pickup) that the Mariano's collector saved through the Oxylabs **Web API** on 2026-11-02, each wrapped in an invented Classic envelope. The pages are real; the Classic envelope is not |
| Shared ledger (10 per retailer, 20 total, 30 minutes, USD 5, headroom, deadline) | **SYNTHETIC TEST**: tested offline, including concurrent processes, crashes and both retailers on one ledger |
| A Classic request | **NOT TESTED**: none was made. That needs the account owner's credentials, entitlement, rates and approval |
| Listing pagination for Mariano's | **NOT AVAILABLE**: the documentation gives `marianos_search` no page parameter, so no second page is planned (see below) |

## What this build will not do

- Send a request. `HttpTransport` refuses to be built while `gates.LIVE_ENABLED` is `False`. Changing that takes a code change, a new version and the owner's approval.
- Read a credential. `live` lists what a campaign still lacks, and it refuses before any credential is looked at.
- Probe an account. There are no automatic balance, usage, entitlement, authentication or qualification calls. The documented usage endpoint is never called.
- Use another service's results to qualify Classic. Results of the collectors' providers (the Oxylabs Web API included) say nothing about Classic.
- Assume pagination, store targeting or broader access works. Every one of them is checked in the response itself.
- Present a first page as category coverage. Page 1 of a Mariano's search is a sample of a store's assortment, nothing more.

## Install and check (offline)

```
uv sync --frozen
uv run pytest
uv run ruff check src tests
uv run mypy
```

The tests close the network: any attempt to open a socket or resolve a name fails the test that made it. They also remove the two credential variables from their environment.

## Commands

All commands are offline. `classic-probe --help` and `python -m classic_probe --help` show the same list.

| Command | Reads | Writes | Sends |
| --- | --- | --- | --- |
| `plan --targets config/targets.json [--rates FILE]` | the targets, an optional rate card | nothing | nothing |
| `validate --targets config/targets.json [--rates FILE]` | the same | nothing | nothing |
| `campaign-init --manifest M --ledger L --campaign-id ID [--offline]` | nothing | a new ledger and its manifest (refuses to replace either) | nothing |
| `status --manifest M` | the ledger | nothing | nothing |
| `confirm-charge --manifest M --seq N --value V --unit U --basis TEXT` | the ledger | one confirmed charge, with where it was read | nothing |
| `export --manifest M --out DIR` | the ledger | `ledger_export.json` | nothing |
| `replay --targets T --fixtures DIR --rates FILE --out DIR [--retailer walmart\|marianos]` | saved responses | a new offline ledger and the evidence | nothing (OFFLINE REPLAY) |
| `live --manifest M [--approval F] [--entitlement F] [--rates F]` | those files | nothing | nothing: always refused in this build |

`plan` and `validate` cover both retailers. Exit codes: `0` ok, `2` refused input, `3` live refused, `4` the campaign stopped, `5` evidence export failed.

## The campaign limits (proposed; ceilings, never raised)

These are the limits of the Walmart probe 1.5.2, unchanged.

| Limit | Value | Enforced by |
| --- | --- | --- |
| Requests per retailer | 10, including setup, authentication or qualification calls, every retry and every restart | `Ledger.reserve`: the 11th is never reserved |
| Requests for both retailers | 20 | the same check, across both retailers |
| Campaign time | 30 minutes for the combined campaign, from its first reservation | each reservation must end before the end less 3 minutes kept for evidence export and cleanup |
| Provider charges | USD 5.00 combined, less USD 0.50 of headroom for delayed or uncertain charges | each request reserves its worst-case charge. Each retailer's share is USD 2.25 and is not borrowed |

A request exists in the ledger before it is sent:

1. `BEGIN IMMEDIATE` serializes concurrent invocations.
2. Each request reserves its worst-case charge before it leaves.
3. The reservation stays until the owner records a confirmed charge with its basis.

So a crash after a reservation, a request with no answer and a response the documentation says is not billed all keep their reservation. A row is never deleted and a reservation never changes; database triggers refuse both. The first stop stays the campaign's reason.

What keeps a second execution from granting itself a fresh budget:

- `open` never creates a ledger.
- Every ledger has a random genesis id, and the owner's approval must name it.
- A ledger is bound to its host.
- A path on a network share is refused.
- The Mariano's steps use the same ledger as the Walmart steps (`MarianosCampaign` is a `Campaign` with another adapter, not a second ledger).

## The Walmart steps

[docs/PAYLOAD_MATRIX.md](docs/PAYLOAD_MATRIX.md) has each payload in full.

1. `walmart-search-p1`: `walmart_search` for the store's Pickup results, with `?type=raw,parsed`.
2. `walmart-search-p2`: the same with `start_page: 2`, sent only when page 1's `last_visible_page` shows a page 2.
3. `walmart-product`: `walmart_product` for page 1's first non-sponsored Walmart.com product with a Pickup line.
4. `walmart-category-url`: a required category page by its URL alone. The documentation states no store or fulfillment parameter for this form. It is last because a page for any other store stops the campaign.

Store, fulfillment and identity are read from Walmart's own page data in the raw result. The readers are the Walmart collector's validated readers, vendored unchanged in `src/classic_probe/vendor/` (`VENDORED.json` has their origin and SHA-256). The parsed result has to agree with them.

## The Mariano's steps (added in 1.6.0)

1. `marianos-search-p1`: `marianos_search` for `cereal` with `store_id` `53100502` and `fulfillment_type` `pickup`. Mariano's documentation names no `parse` for its sources and returns the page HTML in `content`, so one result is reserved.
2. `marianos-product`: `marianos_product` for page 1's first ranked product (a sponsored placement is never chosen), the same store and Pickup. The documented `product_id` is the 13-digit product ID.
3. `marianos-category-url`: `https://www.marianos.com/pl/cereal-granola/03001` by its URL alone. The documentation states no store or fulfillment parameter for this form; a page for another store or fulfillment stops the campaign, so it is last.

**Not planned: any second page.** `marianos_search` documents no `start_page` or `pages`, and a listing URL with `page=2` could only be sent by URL alone, without the store. Listing pagination through Classic is an open gap, stated in the plan output (`not_planned`) and in [docs/DOCUMENTED_CONTRACT.md](docs/DOCUMENTED_CONTRACT.md).

What a Mariano's page shows is read from its own page state (`window.__INITIAL_STATE__`) with the Mariano's collector's reader, vendored unchanged (`vendor/marianos_initial_state.py`; its sanitizer `vendor/marianos_sanitize.py` with one import line rewritten, recorded in `VENDORED.json`):

- the shopper's selected store and modality (`getModalityPreferences`): must be 53100502 and `PICKUP`;
- the search's own request (`search.searchAll.requestVars`): `locationId` 53100502, `activeModalityType` `PICKUP`, page 1;
- each product's `price.storePrices.sourceLocationId`: any other store stops the campaign;
- for the product page, the requested product must be in the page's own product data, its prices for 53100502.

A refusal page (the collector's challenge markers), a retailer status that is not 2xx, a page without page state, an empty first page or a page for another product stops the campaign, and nothing more is sent.

## Files

| Path | What |
| --- | --- |
| `config/targets.json` | the two retailers. Walmart #3891 Waukegan, Pickup, store verified from Walmart's own data. Mariano's Vernon Hills 53100502, Pickup: a lead from Kroger's certification Locations API, verified from the page state of the Mariano's collector's Web API requests of 2026-11-02 (not from Classic) |
| `config/*.example.json`, `.env.example` | placeholders only. No rate, approval, entitlement or credential ships with the probe; the Mariano's rates in `rates.example.json` are `null` |
| `docs/DOCUMENTED_CONTRACT.md` | what the documentation says, page by page, with the SHA-256 of each saved page |
| `docs/PAYLOAD_MATRIX.md` | every request the plan can send, with its reserved upper bound and its stop conditions |
| `CLASSIC_TEST_PLAN.md` | the staged plan for a future approved campaign |
| `tests/` | the offline tests. Their Classic envelopes are SYNTHETIC; `tests/captures_marianos/` holds the two real Mariano's pages they wrap |
