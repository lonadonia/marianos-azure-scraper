"""PRIVATE (workstation): the steps file of the recorded walkthrough of 1.10.0rc6 on the owner VM (for record_cast.py,
run there as root). Every command is real and runs while it is recorded; paid commands go through the gated harness
(mstage6) only. The slice's stage must already be prepared (prep_stage.py) and opened in the ledger, and its ceiling
set (launch with NO_START=1).

    python -I make_walk_steps6.py OUT.json STAGE_ID RUN_ID UNIT PAGES_BEFORE_STOP SLICE_TARGET UPC [UPC ...]

The slice: the run is resumed as a service and stopped with SIGTERM after PAGES_BEFORE_STOP pages (exit 75); a second
start is refused (exit 9); the run is resumed again with the slice stopper at SLICE_TARGET reservations (exit 75,
resumable) unless the run completes first. What follows depends on how the run stands, and the commands say so: a
finished run's export gives the coverage by CSV row and the traces of the named UPCs; a publication is attempted
either way (an unfinished or incomplete run is refused, exit 6).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

out, sid, run, unit, pages_before_stop, slice_target, *upcs = sys.argv[1:]
OPS = "/var/lib/marianos-collector/ops-rc6"
TOOLS = f"{OPS}/walk/tools"
VERSION, COMMIT = "1.10.0rc6", "d77f306"
DATA = "/var/lib/marianos-collector/rc5/data"
PY = "/opt/marianos-collector/current/venv/bin/python"
STORE = "marianos-53100502-pickup"
EXPORT = f"{DATA}/runs/{STORE}/{run}/exports"
show = f"python3 -I {TOOLS}/show.py"
ledger = ("mstage6 ledger-status | python3 -I -c 'import json,sys; d=json.load(sys.stdin); m=d[\"projects\"][\"marianos\"]; "
          "print(\"chain\", d[\"chain\"], \"| lease\", d[\"active_lease\"], \"| Mariano\\x27s committed\", m[\"committed_usd\"], "
          "\"| spendable\", m[\"spendable_in_envelope_usd\"], \"| held unknown\", m[\"unknown_rows\"], \"rows\")'")
steps: list[dict] = [
    {"say": [f"Mariano's collector {VERSION} (commit {COMMIT}), recorded on Hamza's own Azure test VM (Ubuntu 24.04),",
             "not on the client's VM. Store: Mariano's Vernon Hills 53100502, PICKUP. Provider: Oxylabs Web API,",
             "the credit Hamza supplied, every submission reserved in its own spending ledger before it is sent.",
             "Every command below runs for real while it is recorded; nothing is edited afterwards. The published",
             "copy masks private identifiers (host name, paths) and nothing else.",
             f"The run shown is the logical full-scope run {run}, read in slices; this is the slice {sid}."]},
    {"cmd": "marianos --version", "argv": ["marianos", "--version"], "save": "version"},
    {"say": ["The run as the collector records it: interrupted by the operator's SIGTERM that ended the previous slice,",
             "resumable."]},
    {"cmd": f"marianos status --run {run} | {show} status -",
     "argv": ["bash", "-c", f"marianos status --run {run} | {show} status -"], "save": "status_before"},
    {"say": ["The spending ledger of this credit: hash chain, active lease, what Mariano's can still spend."]},
    {"cmd": "mstage6 ledger-status", "argv": ["bash", "-c", ledger], "save": "ledger_before"},
    {"say": ["Resume the run as a service (it survives a lost SSH session), two lanes, and follow its log. After "
             f"{pages_before_stop} pages",
             "it is stopped with SIGTERM (systemctl stop): the collector records a resumable stop (exit 75)."]},
    {"cmd": f"run_and_follow6.sh {unit} {sid} resume --store {STORE}",
     "argv": [f"{OPS}/walk/run_and_follow6.sh", unit, sid, "resume", "--store", STORE], "save": "resume_then_sigterm",
     "view": "events", "kill_after": {"event": "PAGE_COLLECTED", "count": int(pages_before_stop),
                                       "cmd": f"systemctl stop {unit}   # SIGTERM",
                                       "argv": ["systemctl", "stop", unit], "save": "sigterm"}},
    {"cmd": f"marianos status --run {run} | {show} status -",
     "argv": ["bash", "-c", f"marianos status --run {run} | {show} status -"], "save": "status_after_sigterm"},
    {"say": ["A second start for the store while it has an unfinished run is refused before any request: the harness",
             "gives it a gate that refuses every submission, and none is even attempted (exit 9)."]},
    {"cmd": f"mstage6 refused-start {sid} -- run --store {STORE}",
     "argv": ["mstage6", "refused-start", sid, "--", "run", "--store", STORE], "save": "refused_start",
     "view": "events"},
    {"say": ["Resume again, with the slice stopper beside it: the run goes on until this slice's stage holds "
             f"{slice_target} reservations",
             "in the ledger (then SIGTERM: exit 75, resumable), or until the run itself ends, whichever comes first.",
             "Pages completed before the stop are not asked again."]},
    {"cmd": f"SLICE_TARGET={slice_target} run_and_follow6.sh {unit}-2 {sid} resume --store {STORE}",
     "argv": ["env", f"SLICE_TARGET={slice_target}", f"{OPS}/walk/run_and_follow6.sh", f"{unit}-2", sid, "resume",
              "--store", STORE], "save": "resume_to_target", "view": "events"},
    {"cmd": f"marianos status --run {run} | {show} status -",
     "argv": ["bash", "-c", f"marianos status --run {run} | {show} status -"], "save": "status_final"},
    {"say": ["An attempt to publish the run as it now stands (only a complete run whose gates pass is published;",
             "anything else is refused with exit 6 and the published dataset is left as it was):"]},
    {"cmd": f"marianos publish --run {run} | {show} result -",
     "argv": ["bash", "-c", f"marianos publish --run {run} | {show} result -; exit ${{PIPESTATUS[0]}}"],
     "save": "publish_attempt"},
    {"say": ["The coverage of the CSV rows, when the run has ended and exported its records:"]},
    {"cmd": f"{show} coverage <the run's export folder>",
     "argv": ["bash", "-c", f"if [ -f {EXPORT}/manifest.json ]; then python3 -I {TOOLS}/show.py coverage {EXPORT}; "
              "else echo 'no export yet: the run is interrupted and resumable, and exports its records when it ends'; fi"],
     "save": "coverage"},
    {"say": ["Records traced to the stored page they were read from (its SHA-256 checked), and the tile read again",
             "independently of the collector, when the run has exported them:"]},
    {"cmd": f"trace_record.py <the run's export folder> <data folder> {' '.join(upcs)}",
     "argv": ["bash", "-c", f"if [ -f {EXPORT}/manifest.json ]; then sudo -u marianos {PY} -I {TOOLS}/trace_record.py "
              f"{EXPORT} {DATA} {' '.join(upcs)}; else echo 'no export yet: nothing to trace'; fi"], "save": "trace"},
    {"cmd": "mstage6 ledger-status", "argv": ["bash", "-c", ledger], "save": "ledger_after"},
    {"cmd": "systemctl list-units --no-legend 'marianos-*'",
     "argv": ["bash", "-c", "systemctl list-units --no-legend 'marianos-*'; echo \"(units listed above; none means "
              "no collector process is left running)\""], "save": "units_left"},
    {"say": ["End of the walkthrough. Not shown here, and still open: the client's VM (a separately authorized",
             "window), the twice-weekly schedule (enabled only after a protected full-scope publication) and the",
             "client's own review."]},
]
Path(out).write_bytes((json.dumps({"title": f"Mariano's collector {VERSION} walkthrough, {sid}", "steps": steps},
                                  indent=1, ensure_ascii=False) + "\n").encode("utf-8"))
print(f"{len(steps)} steps written to {out}")
