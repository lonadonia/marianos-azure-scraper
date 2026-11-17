# Publication on 1.10.0rc6

The collector publishes a run only when the run has ended complete and its blocking gates pass, and it publishes
atomically: the run's export files are written once, then one database transaction moves the store's publication
pointer to the new publication. A refused publication changes nothing that is published. The schedule
(`publish.auto`) stays off in every stage of this delivery: each publication below was asked for by hand.

**What 1.10.0rc6 changed here.** The publication code is that of 1.10.0rc5: `publishing/publish.py` and the
`publish` and `rollback` commands are unchanged (`git diff bc19afe d77f306`). What changed is what feeds the gates:
a run's manifest now names the rows of the client's list that the run read as routes (the Coupons page, row 0), and
G3 fails a run whose plan names a route that was not read (OR-04, [`../tests/`](../tests/README.md)).

## On the run target of this delivery

| When (UTC) | What | Result | Published state |
|---|---|---|---|
| 2026-11-17T05:15:58Z | in the walkthrough R7w, `publish --run 01M7KQ5GZVF5VK1S9FGTG6YFC9`, the run interrupted | exit 6: "a partial dataset: only complete runs are published" ([`../walkthrough/raw/16_publish_attempt.txt`](../walkthrough/raw/16_publish_attempt.txt)) | not read in the walkthrough (read at 05:59Z, below) |
| 05:48:35Z | the same, on R7's copy finalized offline (rejected: G3 and G4 FAIL) | exit 6, the same refusal ([`R7/R7_copy_publish.log`](R7/R7_copy_publish.log)) | the copy, dropped after its checks |
| 05:59:29Z | the same, on R7's own run target (R7 interrupted and resumable) | exit 6, the same refusal ([`R7/R7_publish.log`](R7/R7_publish.log)) | equal before and after: no pointer, no publication, no `published/` folder ([`before`](R7/pub_state_0_before_R7_publish.txt), [`after`](R7/pub_state_1_after_R7_publish.txt), [`compared`](R7/COMPARE_before_vs_after_R7_refusal.txt)) |

`pub_state_*.txt` is the published state read before and after each step (read only, no request): the database's
publication pointer and publications, `published/<store>/latest.json`, the SHA-256 of every file under `published/`,
and of every export of the run that `latest.json` names. Two equal readings show the published dataset unchanged
([`../tools/pub_state.sh`](../tools/pub_state.sh)). On R7's target nothing has ever been published, so its two readings are empty and equal: the refusal created nothing. The refusal beside a published dataset is shown on the copy of the isolated target (below). The whole step on R7's target: [`R7/PUBLISH_R7.log`](R7/PUBLISH_R7.log).

## The mechanism on an isolated target (1.10.0rc5, carried)

The publication, a refused publication and a rollback were shown live on 1.10.0rc5, on an isolated target of
Hamza's VM (its own database and data folder, the store's categories set to Hardware alone): P4, a complete run,
was published (exit 0); P5, a run finalized by the collector at its ceiling as a partial dataset, was refused
(exit 6), and the published state read after the refusal equals the one read before it (every file under
`published/`, the published run's exports, `latest.json`, the pointer, the publications); P6, a complete run, was
published and then rolled back to P4 (exit 0 each), after which the published run's exports and `latest.json`'s
dataset fields equal P4's again. The code they ran is the code above; their evidence is complete at the tag
[`review-1.10.0rc5-20261116`](https://github.com/lonadonia/marianos-azure-scraper/tree/review-1.10.0rc5-20261116/evidence/publication)
(`evidence/publication/`). It is carried evidence of the mechanism, not a run of 1.10.0rc6.

## 1.10.0rc6 beside a published dataset, on a copy of that isolated target

On 2026-11-17 at 02:54Z, 1.10.0rc6 ran on a copy of that isolated target: its database restored from a fresh dump
into a database of its own, its data folder copied, and no provider credential
([`../tools/protect_check6.sh`](../tools/protect_check6.sh), [`../tools/vm_copy_target6.sh`](../tools/vm_copy_target6.sh)).
`db-upgrade` found the schema already at 1.10.0rc6's (0006 before and after, exit 0). `publish --run
01M7JSXE192AD3KH2SV0178F4A` (P5, the partial dataset) was refused with exit 6 ("is a partial dataset: only complete
runs are published"), and the published state read after the refusal equals the one read before it in every
section, with P4 (`01M7JRXD9P93HPNBRY3J0BVMSX`) still published at version 3
([`protection_rc6/`](protection_rc6/)). No request was sent, and the copy was dropped afterwards. This is
1.10.0rc6's own refusal beside a published dataset; P4 and P5 themselves are 1.10.0rc5's runs.
