"""PRIVATE (workstation): the one-page run report of one stage's evidence folder (from stage_evidence.sh, after
analyze_stage.py), as listed in QUALIFICATION_EVIDENCE_REQUIREMENTS.md section 2. No network.

    python -I run_report.py EVIDENCE_DIR [EVIDENCE_DIR ...]

Several folders are the slices of one logical run (same run ID, one stage per slice): the report covers them
together, the last folder's export standing for the run. Writes RUN_REPORT.md and RUN_FACTS.json into the last
folder. Every figure is read from a file of the folders; nothing is estimated.
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

csv.field_size_limit(1 << 30)
EVS = [Path(a) for a in sys.argv[1:]]
LAST = EVS[-1]


def rows(ev: Path, name: str) -> list[dict[str, str]]:
    p = ev / name
    return list(csv.DictReader(p.open(encoding="utf-8", newline=""))) if p.exists() else []


def jl(ev: Path, name: str) -> list[dict]:
    p = ev / name
    out = []
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("{"):
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return out


def js(v: str, default: object = None) -> object:
    try:
        return json.loads(v) if v else default
    except json.JSONDecodeError:
        return default


def ts(v: str) -> datetime:
    return datetime.fromisoformat(v.replace("Z", "+00:00").replace(" ", "T"))


facts: dict[str, object] = {}
stages = [json.loads((ev / "stage_record.json").read_text(encoding="utf-8")) for ev in EVS]
run_rows = [rows(ev, "db_runs.csv")[0] for ev in EVS]
run_id = run_rows[-1]["id"]
assert all(r["id"] == run_id for r in run_rows), "the folders are not slices of one run"
run = run_rows[-1]
snap = js(run["config_snapshot"], {}) or {}
counts = js(run["counts"], {}) or {}
facts["run_id"] = run_id
facts["stages"] = [s.get("stage_id") for s in stages]

# segments and their code revisions (each segment's SEGMENT_STARTED event)
segs = rows(LAST, "db_collection_segments.csv")
events = rows(LAST, "db_events.csv")
seg_code = {}
for e in events:
    if e["code"] == "SEGMENT_STARTED":
        d = js(e["data"], {}) or {}
        seg_code[d.get("segment")] = d.get("code") or {}
revisions = sorted({(c.get("version"), c.get("commit")) for c in seg_code.values()})
facts["revisions"] = [{"version": v, "commit": c} for v, c in revisions]
facts["segments"] = [{"id": s["id"], "started_at": s["started_at"], "ended_at": s["ended_at"], "active_s": s["active_s"],
                      "end_state": s["end_state"], "stop_code": s["stop_code"], "trigger": s["trigger"],
                      "code": seg_code.get(s["id"], {})} for s in segs]

# ledger rows of every slice
led = [r for ev in EVS for r in rows(ev, "ledger_reservations.csv")]
by_state = Counter(r["state"] for r in led)
settled_results = sum(int(r.get("settled_results") or 0) for r in led if r["state"] == "settled")
usd = sum(float(r.get("settled_usd") or 0) for r in led)
facts["ledger"] = {"rows": len(led), "by_state": dict(sorted(by_state.items())), "results_charged": settled_results,
                   "usd_settled": round(usd, 6)}
harness = [h for ev in EVS for h in jl(ev, "harness_runs.jsonl")]
facts["executions"] = [{"stage": h.get("stage"), "utc_start": h.get("utc_start"), "utc_end": h.get("utc_end"),
                        "args": h.get("args"), "exit_code": h.get("exit_code"), "seconds": h.get("seconds"),
                        "revision": (h.get("tree") or {}).get("revision"), "gate_counts": h.get("gate_counts")}
                       for h in harness if "exit_code" in h]

# pages and requests set aside
pages = rows(LAST, "db_listing_pages.csv")
facts["pages"] = {"answers": len(pages), "by_state": dict(Counter(p["state"] for p in pages)),
                  "by_verdict": dict(Counter(p["verdict"] for p in pages)),
                  "store_checks": sorted({p["store_check"] for p in pages}),
                  "locations": sorted({p["location_id"] for p in pages if p["location_id"]}),
                  "modalities": sorted({p["modality"] for p in pages if p["modality"]})}
an = json.loads((LAST / "analysis" / "ANALYSIS.json").read_text(encoding="utf-8")) if (LAST / "analysis" / "ANALYSIS.json").exists() else {}
facts["set_aside"] = {"requests": an.get("deferred_requests"), "by_state": an.get("deferred_by_state"),
                      "reasks_answered": an.get("reasks_answered"),
                      "new_products_from_reasks": an.get("distinct_new_products_from_counted_reasks"),
                      "min_seconds_between_answers": an.get("min_seconds_between_answers_of_a_request")}

# products and coverage from the run's own export
exp = LAST / "export"
vr = json.loads((exp / "validation_report.json").read_text(encoding="utf-8"))
recs = json.loads((exp / "products.json").read_text(encoding="utf-8"))
recs = recs if isinstance(recs, list) else recs.get("products", [])
fresh = json.loads((exp / "products_fresh.json").read_text(encoding="utf-8"))
fresh = fresh if isinstance(fresh, list) else fresh.get("products", [])
cov = json.loads((exp / "coverage_reconciliation.json").read_text(encoding="utf-8"))
facts["products"] = {"retained_records": len(recs), "fresh_records": len(fresh),
                     "distinct_fresh_upcs": len({r["upc"] for r in fresh}),
                     "fresh_categories": len({r["category"] for r in fresh}),
                     "verified": counts.get("verified"), "historical": counts.get("historical"),
                     "identities": cov.get("identities") if isinstance(cov, dict) else None}
facts["gates"] = counts.get("gates") or (vr.get("counts") or {}).get("gates")
facts["nodes"] = counts.get("nodes") or (vr.get("counts") or {}).get("nodes")
facts["status"] = run["status"]
facts["outcome"] = counts.get("outcome")
facts["pilot"] = snap.get("pilot")
facts["store"] = snap.get("store")
cov_rows = rows(exp, "coverage_by_csv_row.csv")
facts["csv_rows"] = dict(Counter(r.get("status", "") for r in cov_rows))
recon = rows(exp, "coverage_reconciliation.csv")
inc = [r for r in recon if r.get("status") not in ("DONE", "EMPTY")]
facts["listings_not_complete"] = [{k: r.get(k) for k in ("csv_row", "category", "sub_category", "listing_id",
                                                           "reported_total", "unique_identities", "status",
                                                           "completion_reason")} for r in inc]
(LAST / "RUN_FACTS.json").write_bytes((json.dumps(facts, indent=1, ensure_ascii=False, default=str) + "\n").encode("utf-8"))

# the page
s0, sl = stages[0], stages[-1]
L = []
L.append(f"# Run report: run {run_id}")
L.append("")
L.append(f"Stages: {', '.join(str(s.get('stage_id')) for s in stages)}. Store {facts['store'].get('key') if facts['store'] else '?'} "
         f"(location {facts['store'].get('location_id') if facts['store'] else '?'}, {facts['store'].get('modality') if facts['store'] else '?'}). "
         f"{'A pilot: never published.' if facts['pilot'] else 'Not a pilot (no command-line narrowing or limit).'}")
L.append("")
L.append("## What was asked")
L.append("")
NO_APPROVAL_FIELD = ("not in this stage record (prepared before the field was added); the authorization is Hamza's "
                     "update of 16 November 2026, entered in the trial ledger as the event note:authorization_update "
                     "before the stage was opened")
for s in stages:
    L.append(f"- `{s.get('stage_id')}`: `{s.get('command')}`; ceiling {s.get('max_requests')} submissions, USD "
             f"{s.get('max_usd')}; deadline {s.get('deadline_utc')}; approved: "
             f"{s.get('approval') or s.get('approved_by') or NO_APPROVAL_FIELD}")
L.append(f"- Objective (first stage): {s0.get('objective')}")
L.append("")
L.append("## Code and segments")
L.append("")
L.append("Revisions recorded by the run's segments: " + "; ".join(f"{r['version']} ({r['commit']})" for r in facts["revisions"]) +
         (" (one revision for the whole run)" if len(facts["revisions"]) == 1 else " (MORE THAN ONE REVISION)"))
L.append("")
if facts["segments"]:
    L.append("| segment | trigger | started (UTC) | ended (UTC) | active s | end state | stop code |")
    L.append("|---|---|---|---|---|---|---|")
    for g in facts["segments"]:
        act = f"{float(g['active_s']):.1f}" if g["active_s"] else ""
        L.append(f"| {g['id']} | {g['trigger']} | {g['started_at']} | {g['ended_at']} | {act} | {g['end_state']} | {g['stop_code']} |")
else:
    L.append("The segments table was not exported for this stage (its evidence was collected before that export was "
             "added); the revision above comes from the run's SEGMENT_STARTED events.")
L.append("")
L.append("## Submissions and cost (the shared trial ledger)")
L.append("")
L.append(f"{facts['ledger']['rows']} submissions reserved before dispatch: " + ", ".join(f"{k} {v}" for k, v in facts['ledger']['by_state'].items()) +
         f"; results charged {facts['ledger']['results_charged']}; USD settled {facts['ledger']['usd_settled']:.6f} at the recorded rate.")
L.append("")
for x in facts["executions"]:
    L.append(f"- `{' '.join(x['args'] or [])}` ({x['stage']}): {x['utc_start']} to {x['utc_end']}, exit {x['exit_code']} "
             f"after {x['seconds']} s, revision {x['revision']}; gate counts {json.dumps(x['gate_counts'])}")
L.append("")
L.append("## Pages")
L.append("")
pg = facts["pages"]
L.append(f"{pg['answers']} answers asked as listing pages: by state " + ", ".join(f"{k} {v}" for k, v in sorted(pg['by_state'].items())) +
         "; by verdict " + ", ".join(f"{k or '(none)'} {v}" for k, v in sorted(pg['by_verdict'].items())) + ".")
L.append(f"Store checks on every answer: {', '.join(pg['store_checks'])}; locations {', '.join(pg['locations'])}; fulfillment {', '.join(pg['modalities'])}.")
sa = facts["set_aside"]
L.append("")
L.append(f"Requests set aside: {sa['requests']} ({json.dumps(sa['by_state'])}); re-asks answered {sa['reasks_answered']}; "
         f"new products brought by counted re-asks {sa['new_products_from_reasks']}; shortest time between two answers of one request "
         f"{sa['min_seconds_between_answers']} s.")
L.append("")
L.append("## Products")
L.append("")
pr = facts["products"]
L.append(f"Distinct fresh valid products (this run's own observations, status valid): **{pr['distinct_fresh_upcs']}** in "
         f"{pr['fresh_categories']} categories; retained dataset {pr['retained_records']} records (verified {pr['verified']}, "
         f"carried from earlier runs {(pr.get('identities') or {}).get('carried_forward')}).")
if pr.get("identities"):
    L.append(f"Identity sets: `{json.dumps(pr['identities'])[:600]}`")
L.append("")
L.append("## Coverage and gates")
L.append("")
L.append(f"Listings: {json.dumps(facts['nodes'])}; CSV rows: {json.dumps(facts['csv_rows'])}.")
L.append("")
L.append("Gates: " + ", ".join(f"{k} {v}" for k, v in (facts["gates"] or {}).items()) + f". Run status: {facts['status']} ({facts['outcome']}).")
if facts["listings_not_complete"]:
    L.append("")
    L.append("Listings not complete:")
    L.append("")
    for r in facts["listings_not_complete"][:60]:
        L.append(f"- row {r['csv_row']} {r['category']} / {r['sub_category'] or '-'} ({r['listing_id']}): {r['unique_identities']} of {r['reported_total']}, {r['status']}: {r['completion_reason'] or ''}")
    if len(facts["listings_not_complete"]) > 60:
        L.append(f"- ... {len(facts['listings_not_complete']) - 60} more in export/coverage_reconciliation.csv")
L.append("")
(LAST / "RUN_REPORT.md").write_bytes(("\n".join(L) + "\n").encode("utf-8"))  # LF on every platform
print(f"run {run_id}: {len(facts['segments'])} segments, revisions {facts['revisions']}, ledger {facts['ledger']}, "
      f"fresh valid {pr['distinct_fresh_upcs']}, gates {facts['gates']}, nodes {facts['nodes']}")
