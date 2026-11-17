# The spending ledger of this delivery

Every Oxylabs submission of 1.10.0rc6's live stages was reserved in one ledger before it was sent: a SQLite file on
Hamza's VM with an append-only, hash-chained event log, a lease that one process holds at a time, a spending envelope
and a ceiling per stage. A request whose outcome is unknown when its process stops (killed, or stopped with the
request in flight) stays charged at the worst case until it is reconciled.

This ledger is the new credential's own campaign, `oxylabs-marianos-20261116`: cap USD 5.00, USD 0.10 of headroom,
one envelope of USD 4.90 for Mariano's. Every stage in it belongs to this delivery. The earlier campaign's Mariano's
balance (USD 0.312) was not carried over, and Walmart has no envelope here. There was no top-up and no overage.

| File | What it is |
|---|---|
| [`STAGES.csv`](STAGES.csv) | each stage: opened, closed, ceiling, deadline, revision, command, outcome; its reservations by state, settled USD, unknown outcomes charged |
| [`RESERVATIONS.csv`](RESERVATIONS.csv) | every reservation: its stage, purpose, target, worst case, state, dispatch, the provider's job ID and status, settlement and the SHA-256 of the stored answer |
| [`ENVELOPES.csv`](ENVELOPES.csv) | the envelope, append-only |
| [`META.csv`](META.csv) | the campaign's own record: authority, cap, headroom, the rate and its source, the credential's relation to the earlier one (its fingerprint masked), what was not carried over |
| [`LEASES.csv`](LEASES.csv) | each lease: holder, acquired, expired or released and why (the lease token is left out: it authorizes the lease) |
| [`EVENTS.csv`](EVENTS.csv) | the whole event log with its hash chain |
| [`LEDGER_STATUS_END.json`](LEDGER_STATUS_END.json) | the ledger's own summary at the end: chain verified, no active lease, committed and spendable |
| [`PEAK_IN_FLIGHT.txt`](PEAK_IN_FLIGHT.txt) | requests in flight at once, per stage, from the reservations |
| `ledger_after_<stage>.json` | the ledger's status read after each live stage (P7, R6a, R7a, R7a2, P8, R7b, R7w, R7c): chain, lease, committed and spendable; the estimate's reprojections read them ([`../estimate/`](../estimate/README.md)) |
| [`CHAIN_CHECK.txt`](CHAIN_CHECK.txt) | the chain check below, as run on this folder's `EVENTS.csv` |

At the end (R7c): 349 reservations, USD 0.4665 settled and USD 0.0135 held for 9 unknown outcome(s), USD 0.4800 committed of the USD 4.90 envelope, USD 4.4200 left; chain verified (1,087 events); active lease: none

**Checking the chain.** Each event's hash is the SHA-256 of `prev_hash|at|kind|ref|detail`, and each `prev_hash` is the
hash of the event before it:

```
python3 -I evidence/tools/verify_ledger_chain.py evidence/ledger/EVENTS.csv
```

Its output on this folder's EVENTS.csv (2026-11-17T06:32:28Z, exit 0): events 1087: links checked 1086 of 1086; hashes recomputed and matching 1087; not recomputable (a private identifier masked in the published detail) 0; chain OK.

The rate is the reservation rate, USD 0.0015 a submission: the provider's price page's highest non-AI row, a list
price read on 2026-11-03, not an invoice. The provider documents no balance or usage API for this key, so the ledger,
not the provider, is the count. Every stage's own rows are also in its run folder (`../runs/<stage>/ledger_reservations.csv`,
with the chain checked at its close in `ledger_chain.txt`).
