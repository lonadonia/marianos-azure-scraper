"""PRIVATE (workstation): the steps file of the recorded walkthrough on the owner VM (for record_cast.py, run there as
root). Every command is real and runs while it is recorded; paid commands go through the gated harness (mstage)
only. The slice's stage must already be prepared (prep_stage.py) and opened in the ledger, and its ceiling set.

    python -I make_walk_steps.py OUT.json STAGE_ID RUN_ID UNIT PAGES_BEFORE_STOP EXPORT_DIR UPC [UPC ...]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

out, sid, run, unit, pages_before_stop, export_dir, *upcs = sys.argv[1:]
OPS = "/var/lib/marianos-collector/ops111"
VERSION, COMMIT = "1.10.0rc5", "bc19afe"
DATA = "/var/lib/marianos-collector/rc5/data"
PY = "/opt/marianos-collector/current/venv/bin/python"
STORE = "marianos-53100502-pickup"
show = f"python3 -I {OPS}/tools/show.py"
steps: list[dict] = [
    {"say": [f"Mariano's collector {VERSION} (commit {COMMIT}), recorded on Hamza's own Azure test VM (Ubuntu 24.04),",
             "not on the client's VM. Store: Mariano's Vernon Hills 53100502, PICKUP. Provider: Oxylabs Web API,",
             "Hamza's trial credit, every submission reserved in the shared trial ledger before it is sent.",
             "Every command below runs for real while it is recorded; nothing is edited afterwards. The published",
             "copy masks private identifiers (host name, paths) and nothing else.",
             f"The run shown is the logical full run {run}, read in slices; this is its last slice ({sid})."]},
    {"cmd": "marianos --version", "argv": ["marianos", "--version"], "save": "version"},
    {"say": ["The run as the collector records it: interrupted by the operator's SIGTERM that ended the previous slice,",
             "resumable."]},
    {"cmd": f"marianos status --run {run} | {show} status -",
     "argv": ["bash", "-c", f"marianos status --run {run} | {show} status -"], "save": "status_before"},
    {"say": ["The shared trial ledger: hash chain, active lease, what Mariano's can still spend."]},
    {"cmd": "mstage ledger-status", "argv": ["bash", "-c",
     "mstage ledger-status | python3 -I -c 'import json,sys; d=json.load(sys.stdin); m=d[\"projects\"][\"marianos\"]; "
     "print(\"chain\", d[\"chain\"], \"| lease\", d[\"active_lease\"], \"| Mariano\\x27s committed\", m[\"committed_usd\"], "
     "\"| spendable\", m[\"spendable_in_envelope_usd\"], \"| held unknown\", m[\"unknown_rows\"], \"rows\")'"],
     "save": "ledger_before"},
    {"say": ["Resume the run as a service (it survives a lost SSH session), two lanes, and follow its log. After "
             f"{pages_before_stop} pages",
             "it is stopped with SIGTERM (systemctl stop): the collector records a resumable stop (exit 75)."]},
    {"cmd": f"run_and_follow.sh {unit} {sid} resume --store {STORE}",
     "argv": [f"{OPS}/run_and_follow.sh", unit, sid, "resume", "--store", STORE], "save": "resume_then_sigterm",
     "view": "events", "kill_after": {"event": "PAGE_COLLECTED", "count": int(pages_before_stop),
                                       "cmd": f"systemctl stop {unit}   # SIGTERM",
                                       "argv": ["systemctl", "stop", unit], "save": "sigterm"}},
    {"cmd": f"marianos status --run {run} | {show} status -",
     "argv": ["bash", "-c", f"marianos status --run {run} | {show} status -"], "save": "status_after_sigterm"},
    {"say": ["A second start for the store while it has an unfinished run is refused before any request: the harness",
             "gives it a gate that refuses every submission, and none is even attempted (exit 9)."]},
    {"cmd": f"mstage refused-start {sid} -- run --store {STORE}",
     "argv": ["mstage", "refused-start", sid, "--", "run", "--store", STORE], "save": "refused_start",
     "view": "events"},
    {"say": ["Resume again: the run goes on until this slice's ceiling, the last of the trial credit, before the whole",
             "scope. At the ceiling the collector stops (exit 4) and finalizes the run itself: its records are",
             "exported as a partial dataset, which is never published."]},
    {"cmd": f"run_and_follow.sh {unit}-2 {sid} resume --store {STORE}",
     "argv": [f"{OPS}/run_and_follow.sh", f"{unit}-2", sid, "resume", "--store", STORE], "save": "resume_to_ceiling",
     "view": "events"},
    {"cmd": f"marianos status --run {run} | {show} status -",
     "argv": ["bash", "-c", f"marianos status --run {run} | {show} status -"], "save": "status_final"},
    {"say": ["An attempt to publish it:"]},
    {"cmd": f"marianos publish --run {run} | {show} result -",
     "argv": ["bash", "-c", f"marianos publish --run {run} | {show} result -; exit ${{PIPESTATUS[0]}}"],
     "save": "publish_refused"},
    {"say": ["Publication refused (exit 6): only a complete run is published; nothing was published or replaced.",
             "The coverage of the CSV rows as the run left them:"]},
    {"cmd": f"{show} coverage {export_dir}", "argv": ["python3", "-I", f"{OPS}/tools/show.py", "coverage", export_dir],
     "save": "coverage"},
    {"say": ["Records traced to the stored page they were read from (its SHA-256 checked), and the tile read again",
             "independently of the collector:"]},
    {"cmd": f"trace_record.py {export_dir} <data folder> {' '.join(upcs)}",
     "argv": ["sudo", "-u", "marianos", PY, "-I", f"{OPS}/tools/trace_record.py", export_dir,
              DATA, *upcs], "save": "trace"},
    {"cmd": "mstage ledger-status", "argv": ["bash", "-c",
     "mstage ledger-status | python3 -I -c 'import json,sys; d=json.load(sys.stdin); m=d[\"projects\"][\"marianos\"]; "
     "print(\"chain\", d[\"chain\"], \"| lease\", d[\"active_lease\"], \"| Mariano\\x27s committed\", m[\"committed_usd\"], "
     "\"| spendable\", m[\"spendable_in_envelope_usd\"], \"| held unknown\", m[\"unknown_rows\"], \"rows\")'"],
     "save": "ledger_after"},
    {"cmd": "systemctl list-units --no-legend 'marianos-*'",
     "argv": ["bash", "-c", "systemctl list-units --no-legend 'marianos-*'; echo \"(units listed above; none means "
              "no collector process is left running)\""], "save": "units_left"},
    {"say": ["End of the walkthrough. Not shown here, and still open: the full scope (beyond the trial credit), the",
             "client's VM (a separately authorized window), the twice-weekly schedule (blocked until a protected",
             "full publication) and the client's own review."]},
]
Path(out).write_bytes((json.dumps({"title": f"Mariano's collector {VERSION} walkthrough, {sid}", "steps": steps},
                                  indent=1, ensure_ascii=False) + "\n").encode("utf-8"))
print(f"{len(steps)} steps written to {out}")
