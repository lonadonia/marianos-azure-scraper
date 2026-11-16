# The operator's tools, as used for these stages

These scripts are Hamza's own operator tools for the live campaign of 16 November 2026 on Hamza's VM. They are
**not part of the collector** (that is [`../../source/`](../../source/), 1.10.0rc5) and are published so that each
evidence file can be traced to the code that wrote it. Private identifiers (the VM's host name and address, home
folders) are masked as everywhere else ([`../../manifests/REDACTIONS.csv`](../../manifests/REDACTIONS.csv)); no tool
holds a credential: the provider key is read by the collector from its own 0600 file on the VM.

| Tool | Where it ran | What it does | Its output in this delivery |
|---|---|---|---|
| [`mstage`](mstage), [`live111_run.py`](live111_run.py), [`prep_stage.py`](prep_stage.py), [`stage_launch.sh`](stage_launch.sh) | the VM, as root | the gated stage harness: opens a stage in the shared ledger with its ceiling, runs the collector under a lease that reserves every submission before it is sent, refuses a second start | each run folder's `stage_record.json`, `harness_runs.jsonl`, `ledger_reservations.csv` |
| [`watch_stage.sh`](watch_stage.sh), [`slice_stop.sh`](slice_stop.sh) | the VM | the operator's stops: progress every 30 s; more than 2 unknown outcomes or 10 re-asks without a recovery stop the stage; the slice stopper ends a slice with SIGTERM at 190 reservations | `../operations/WATCH_*.log`, `../operations/SLICE_STOP_*.log` |
| [`kill_recover.sh`](kill_recover.sh) | the VM | the hard kill (SIGKILL) after 40 pages under two lanes, the dead lease's expiry and the resume | `../operations/KILL_RECOVER_F2c.log` |
| [`reboot_check.sh`](reboot_check.sh) | the VM | the run's state before and after the VM reboot | `../operations/REBOOT_*` |
| [`stage_evidence.sh`](stage_evidence.sh), [`run_report.py`](run_report.py) | the VM; the workstation | a stage's evidence after it ended (status, export, validation, database rows, ledger rows, journal); the run report over a run's slices | `../runs/<stage>/` |
| [`no_refetch.py`](no_refetch.py), [`no_refetch_v1.py`](no_refetch_v1.py) | the workstation | no completed page asked again (the corrected rule, and the first rule kept to reproduce its output) | `../operations/NO_REFETCH_*.txt` |
| [`peak_in_flight.py`](peak_in_flight.py) | the workstation | requests in flight at once, per stage, from the ledger rows | `../operations/PEAK_IN_FLIGHT.txt` |
| [`q5_compare.py`](q5_compare.py) | the workstation | one lane against two (L1, L2) | `../operations/LANES_L1_L2.json` |
| [`pub_state.sh`](pub_state.sh), [`pub_step.sh`](pub_step.sh), [`pub_compare.py`](pub_compare.py) | the VM; the workstation | the published state of the isolated target, each publication step, and the comparison of two states | `../publication/` |
| [`cat_food_record.py`](cat_food_record.py), [`ppm_embedded.py`](ppm_embedded.py), [`tile_text.py`](tile_text.py), [`named_offers.py`](named_offers.py), [`coupons_route_check.py`](coupons_route_check.py) | the VM; the workstation | the named checks, from the runs' stored pages and exports | `../accuracy/` |
| [`excerpts.py`](excerpts.py) | the VM | each record's tile cut from its stored page, with the page's SHA-256 | `../samples/<run>/source_excerpts.jsonl.gz` |
| [`coverage_vs_queue.py`](coverage_vs_queue.py) | the workstation | F2's coverage against the 1.9 queue | `../coverage/` |
| [`estimate_folder.py`](estimate_folder.py) | the workstation | the full-cycle estimate from F2's measures | `../estimate/` |
| [`ledger_folder.py`](ledger_folder.py) | the workstation | the ledger's account of this delivery (read only) | `../ledger/` |
| [`make_walk_steps.py`](make_walk_steps.py), [`record_cast.py`](record_cast.py), [`run_and_follow.sh`](run_and_follow.sh), [`show.py`](show.py), [`trace_record.py`](trace_record.py), [`render_cast.py`](render_cast.py) | the workstation (the steps); the VM (the rest) | the walkthrough: its steps, the recording of real commands, a stage started as a service with its log followed, the condensed views, the trace from a stored page to a record, the video | `../walkthrough/` |
