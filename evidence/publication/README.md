# Publication, refusal and rollback on an isolated target (P4 to P6)

The publication mechanism of the final candidate 1.10.0rc5, live, on an **isolated target**: its own PostgreSQL
database and data folder on Hamza's VM; the target of the full run in [`../runs/`](../runs/) was not touched. Its
configuration is the shipped one with the store's categories set to `[27]` (Hardware Home Improvement: one listing),
so a run of it has no command-line narrowing, is not a pilot, and is published when it completes and validates. It
proves the mechanism on the final candidate; **it is not the client's full scope, and its dataset is not a
catalogue.** No full-scope publication exists (the trial credit cannot complete the scope), so the schedule stays
off.

| Step | What was done | Expected | Observed |
|---|---|---|---|
| P4 | a complete run of row 27 on 1.10.0rc5 (`01M7JRXD9P93HPNBRY3J0BVMSX`), then `publish` | validated, published (exit 0) | validated; publish exit 0 |
| P5 | a run stopped at its 4-submission ceiling (`01M7JSXE192AD3KH2SV0178F4A`), finalized by the collector as partial; then `publish` | refused (exit 6); every published file unchanged | publish exit 6; published state after vs before: EQUAL: every file under published/; exports of the published run; latest.json; pointer; publications; latest.json dataset fields ['publication_id', 'run_id', 'manifest_key', 'manifest_sha256', 'mode'] (result as expected) |
| P6 | a complete run (`01M7JTAC3J8TYR7RV93F2W7PG3`), `publish`, then `rollback-publication` | published (exit 0), then rolled back to P4 (exit 0) with P4's files and dataset fields | publish exit 0; rollback exit 0; after the rollback vs P4 published: EQUAL: exports of the published run; latest.json dataset fields ['publication_id', 'run_id', 'manifest_key', 'manifest_sha256', 'mode']; different: every file under published/; latest.json; pointer; publications (result as expected); the differences are by design: the pointer's and latest.json's version and time (and so latest.json's hash), and P6's own row among the publications |

`pub_state_*.txt` is the published state read after each step (read only, no request): the database's publication
pointer and publications, `published/<store>/latest.json`, the SHA-256 of every file under `published/`, and of
every export of the run `latest.json` names. `COMPARE_*.txt` compares two of them section by section
(`pub_compare.py`). `latest.json` is a convenience copy rewritten after every publication and rollback (its
`version` and `written_at` change); the database pointer is authoritative.

The three stages' full evidence (pages, provenance, ledger rows, journals) is in [`../runs/`](../runs/) under P4, P5
and P6.

## The same three steps on 1.10.0rc4 (P1 to P3)

[`1.10.0rc4/`](1.10.0rc4/) keeps the same test as it ran earlier the same day on 1.10.0rc4 (another isolated
target): P1 published; P2 stopped at its 4-submission ceiling, was finalized by the collector as a partial dataset,
and its publication was refused (exit 6) with every published file unchanged; P3 published, then rolled back to P1
with P1's files and dataset fields restored. Its runs are under P1, P2 and P3 in [`../runs/`](../runs/).
