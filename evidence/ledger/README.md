# The shared trial ledger

Every Oxylabs submission of Mariano's (and of the Walmart project, which shares the trial account) is reserved in one
ledger before it is sent: a SQLite file with an append-only, hash-chained event log, a lease that one process holds
at a time, a spending envelope per project and a ceiling per stage. A request whose outcome is unknown when its
process stops (killed, or stopped with the request in flight) stays charged at the worst case until it is
reconciled. For the live campaign of 16 November 2026 the ledger was moved to Hamza's VM (where the stages ran) and
then brought back to the workstation, each move verified by hash and chain; there was never a second usable copy.

| File | What it is |
|---|---|
| [`STAGES_OF_THIS_DELIVERY.csv`](STAGES_OF_THIS_DELIVERY.csv) | each stage of this delivery: opened, closed, ceiling, revision, outcome, its reservations by state, settled USD, unknown outcomes held |
| [`LEDGER_STATUS_END.json`](LEDGER_STATUS_END.json) | the ledger's own summary at the end: chain verified, no active lease, committed and spendable per project |
| [`ENVELOPES.csv`](ENVELOPES.csv) | the projects' envelopes, append-only |
| [`EVENTS_OF_THE_DAY_SUMMARY.csv`](EVENTS_OF_THE_DAY_SUMMARY.csv) | the events of 2026-11-16 counted by kind |
| [`NOTES_20261116.txt`](NOTES_20261116.txt) | the ledger's notes of that day, verbatim (among them Hamza's update of 16 November 2026, recorded without changing what earlier entries said) |
| [`PEAK_IN_FLIGHT.txt`](PEAK_IN_FLIGHT.txt) | requests in flight at once, per stage, from the stages' rows |

At the end (2026-11-16T19:12:22.617945Z): chain verified (8692 events); Mariano's committed USD 1.9380 of its USD 2.25 envelope (settled 1.9140, unknown held 0.0240 for 16 submissions), spendable USD 0.3120; Walmart's envelope untouched (spendable USD 0.0030). The stages of this delivery reserved 1,022 submissions (USD 1.5285 with the unknown ones charged).

The rate is the reservation rate, USD 0.0015 a submission: the provider's price page's highest non-AI row, a list
price read on 2026-11-03, not an invoice. The provider documents no balance or usage API for this key, so the ledger,
not the provider, is the count. Walmart's envelope is reserved for Walmart and none of it was used; there was no
top-up and no overage. Every stage's own rows are in its run folder (`../runs/<stage>/ledger_reservations.csv`, with
the chain checked at its close in `ledger_chain.txt`).
