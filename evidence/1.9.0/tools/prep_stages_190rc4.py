"""Configurations and ledger stage records for the live stages of collector 1.9.0rc4 (S5b2, S4b, S4c, S3b, S4d).

1.9.0rc4 (8abc2c1) changes one thing against 1.9.0rc3 (9090537): with two listing lanes, a page is written to the
database only once its answer is processed. Its shipped configuration is byte for byte that of 1.9.0rc3 (checked
by ``configs``). Each configuration folder is built from the shipped configuration of the commit (``git show``,
byte for byte) with only the stated changes, each asserted to apply exactly once:

- every stage: ``publish.auto: false`` (a stage run is never published automatically);
- S5b2: ``limits.max_concurrent_listings`` 2 in the Vernon Hills PICKUP collection.

Every ceiling stays within what is left of the approval of 2026-11-09 (295 submissions, USD 0.4425): ``add`` counts
the ledger rows of the approved stages (1.9.0rc3: S1b 13, S4 43, S5a 19, S5b 20, S3 6; then those of 1.9.0rc4) and
refuses a stage whose ceiling exceeds the rest. S4c was added after S4b (2026-11-09 ~15:56Z), when every page 2 of
S4b repeated page 1: it reads listings of rows 1-21 small enough for one or two pages each. S4d was added after S3b
(2026-11-09 ~16:30Z): the single-page listings of rows 1-21 that the queue still lists as never collected.

usage:
  python -I prep_stages_190rc4.py configs            build the folders (refuses to overwrite a different file)
  python -I prep_stages_190rc4.py add STAGE_KEY      write the stage record (deadline = now + its minutes)
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

WT = Path("C:/m8/wt")
REV = "8abc2c1297b8005d162721b6ddbf66bf8684d548"
RC3 = "90905377f4919d33854c23d8068fd7e36553ab31"
CFG_PREFIX = "headless/marianos-azure-headless/config/"
FILES = ("collector.yaml", "Marianos_Category_URLs.csv", "private_label_brands.yaml", "settings.yaml",
         "stores.yaml", "taxonomy_seed.snapshot_2026-10-17.json")
Q = Path("C:/m8/q190")
STAGES = Path("C:/m8/evidence/live190/stages.json")
RUNNER = "C:/m8/qwt/headless/marianos-azure-headless/.venv/Scripts/python.exe -I C:/m8/live/live190_run.py"
STORE = "marianos-53100502-pickup"
APPROVAL = {"submissions": 295, "usd": "0.4425"}
APPROVED_STAGES = (
    "M-S1b-canary-catfood-190rc3-20261109", "M-S4-rows22-27-190rc3-20261109", "M-S5a-rows23-26-one-lane-190rc3-20261109",
    "M-S5b-rows23-26-two-lanes-190rc3-20261109", "M-S3-milk-brand-union-190rc3-20261109",
    "M-S5b2-rows23-26-two-lanes-190rc4-20261109", "M-S4b-rows22-27-190rc4-20261109",
    "M-S4c-rows1-21-small-listings-190rc4-20261109", "M-S3b-natural-frozen-brand-union-190rc4-20261109",
    "M-S4d-rows1-21-single-page-listings-190rc4-20261109",
)
LEDGER = Path("<projects>/.shared-oxylabs-trial-20261103/oxytrial_ledger.py")
SIGNED_PY = "C:/w6/py312/pkg/tools/python.exe"
S4D_LISTINGS = ['1:06119', '2:05008', '2:05011', '2:05014', '4:13002', '4:13007', '4:13010', '5:14161', '5:14164', '5:14180', '5:14182', '5:14183', '5:14184', '5:14185', '5:14186', '6:09125', '6:09126', '6:09128', '6:09130', '6:09132', '6:09133', '10:18008', '18:20003', '20:26011', '21:28015', '21:28016', '21:40001', '21:40002', '21:40005', '21:40006']
S4C_LISTINGS = ['1:06113', '1:06121', '1:06122', '2:05012', '2:05015', '4:13001', '4:13004', '4:13008', '4:13009', '5:14162', '5:14165', '5:14166', '5:14169', '5:14181', '5:14187', '8:02008', '10:18011', '14:23004', '14:23005', '15:08182', '15:08185', '15:08191', '19:10098', '19:10099', '20:26019', '21:28003', '21:28004', '21:28005', '21:28006', '21:40003', '21:40008']

AUTO_OLD = b"  auto: true\n"
AUTO_NEW = b"  auto: false                      # live stages of 1.9.0: a stage run is never published automatically\n"
LANES_AFTER = b"      min_credit_reserve: 0\n"


def lanes_line(n: int) -> bytes:
    return f"      max_concurrent_listings: {n}   # live stage S5 of 1.9.0: listing lanes\n".encode()


def shipped(name: str, rev: str = REV) -> bytes:
    return subprocess.run(["git", "-C", str(WT), "show", f"{rev}:{CFG_PREFIX}{name}"], capture_output=True,
                          check=True).stdout


def once(data: bytes, old: bytes, new: bytes, what: str) -> bytes:
    if data.count(old) < 1:
        raise SystemExit(f"{what}: the text to change is not in the shipped file")
    if old is LANES_AFTER:
        # the first collection of collector.yaml is the Vernon Hills PICKUP one: change only its limits block
        pick = data.index(b"  marianos-53100502-pickup:\n")
        nxt = data.index(b"  marianos-53100503-instore:\n")
        at = data.index(old, pick)
        if not pick < at < nxt:
            raise SystemExit(f"{what}: the limits line is not inside the PICKUP collection")
        return data[: at + len(old)] + new + data[at + len(old):]
    if data.count(old) != 1:
        raise SystemExit(f"{what}: the text to change occurs {data.count(old)} times")
    return data.replace(old, new)


def build(folder: str, *, lanes: int | None = None) -> dict[str, str]:
    out = Q / folder
    out.mkdir(parents=True, exist_ok=True)
    digests = {}
    for name in FILES:
        data = shipped(name)
        if data != shipped(name, RC3):
            raise SystemExit(f"{name}: the shipped file of 1.9.0rc4 differs from 1.9.0rc3's")
        if name == "collector.yaml":
            data = once(data, AUTO_OLD, AUTO_NEW, f"{folder}/{name} publish.auto")
            if lanes is not None:
                data = once(data, LANES_AFTER, lanes_line(lanes), f"{folder}/{name} lanes")
        p = out / name
        if p.exists() and p.read_bytes() != data:
            raise SystemExit(f"{p} exists with different content: not overwritten")
        p.write_bytes(data)
        digests[name] = hashlib.sha256(data).hexdigest()
    return digests


CONFIGS = {
    "cfg_rc4_ship": {},
    "cfg_rc4_l2": {"lanes": 2},
}

RETRY = ("the collector's own, as shipped: a listing page up to 3 attempts on 408/429/5xx with backoff (failed "
         "requests are documented as not charged; every attempt is still reserved at its worst case); a rendered "
         "listing answer without tiles is asked again, three in a row stop the run resumably (PROVIDER_ERROR); the "
         "stage is not repeated before its outcome is read")
STOPS = ("the store or PICKUP not verified on a page; the canary failing; a refusal page; 401/402/403 or a quota "
         "answer; ABNORMAL_RESULT; the stage's or the collector's ceiling; more than 2 outcomes unknown; lease loss; "
         "the key fingerprint differing from the noted one; the deadline")
# S5b (1.9.0rc3) planned two interruptions and its stop condition said "more than 2 outcomes unknown": its signal
# and its kill left 3 unanswered (its outcome says so). S5b2 states the bound its plan implies.
STOPS_S5B2 = STOPS.replace("more than 2 outcomes unknown", "more than 4 outcomes unknown (the planned signal and "
                           "the planned kill can each leave at most one request per lane unanswered)")

NOTE = ("Known before this stage (O2 2026-11-06; S1b, S4, S5a, S5b and S3 on 1.9.0rc3, 2026-11-09): an unrendered "
        "listing answer for ?page=N can carry page 1's products under ranks shifted by 24(N-1), or repeat an earlier "
        "page exactly; the collector then ends that listing as incomplete (repeated page). It is intermittent and "
        "clustered in time, not tied to a listing: in S4, 8 page-N answers repeated page 1 from 14:33:35Z to "
        "14:36:51Z between distinct ones; in S5a (14:42-14:45Z) the four listings that had repeated in S4 paged, "
        "with one repeat (School Office page 4); in S5b (14:51Z) Light Bulbs and School Office repeated again; in S3 "
        "(14:57Z) Milk's page 4 repeated an earlier page. S5b's two-lane run on 1.9.0rc3 was rejected by G13: a lane "
        "wrote the other lane's page to the database before its answer arrived (6 of 13 listing-page rows); "
        "1.9.0rc4 corrects this. ")

SPECS = {
    "S5b2": {
        "stage_id": "M-S5b2-rows23-26-two-lanes-190rc4-20261109",
        "objective": "M8/M9 S5b2 on 1.9.0rc4 (8abc2c1), S5b again on the corrected revision: CSV rows 23-26 with "
        "two listing lanes (limits.max_concurrent_listings 2); a termination signal (interrupted, resumable), resume, "
        "a second start while it runs (expected refused, sent through a gate that refuses every submission), a hard "
        "kill, resume to the end; then status and export. Expected now: every page row named by the run's records "
        "has its stored page and G13 passes; the requests in flight at the signal and the kill are held as unknown; "
        "completed pages are not asked again; the time and submissions of two lanes against S5a's one lane. " + NOTE,
        "args": ["run", "--store", STORE, "--categories", "23,24,25,26", "--max-credits", "30"],
        "folder": "cfg_rc4_l2", "lanes": 2, "submissions": 30, "usd": "0.0450", "minutes": 90, "stops": STOPS_S5B2,
    },
    "S4b": {
        "stage_id": "M-S4b-rows22-27-190rc4-20261109",
        "objective": "M9 S4b on 1.9.0rc4 (8abc2c1): CSV rows 22-27 in one logical run with one listing lane, S4's "
        "scope and configuration again on the final revision (S4 on 1.9.0rc3: 552 fresh valid, rejected on G3 only): "
        "the final revision's fresh qualification (at least 500 distinct fresh valid products in one logical run), a "
        "repeat of S4's scope, the new tile across 17 listings, retention as observed, latencies. " + NOTE,
        "args": ["run", "--store", STORE, "--categories", "22,23,24,25,26,27", "--max-credits", "70"],
        "folder": "cfg_rc4_ship", "lanes": 1, "submissions": 70, "usd": "0.1050", "minutes": 120, "stops": STOPS,
    },
    "S4c": {
        "stage_id": "M-S4c-rows1-21-small-listings-190rc4-20261109",
        "objective": "M9 S4c on 1.9.0rc4 (8abc2c1): the final revision's fresh qualification and progressive coverage "
        "of rows 0-21 (never collected by 1.8 or 1.9): the 31 listings of rows 1-21 that the census of 2026-11-02 "
        "measured at 18 to 48 products (1,021 products; at most 2 pages each, 55 pages), in one logical run with one "
        "lane. Measured: whether at least 500 distinct fresh valid products come from one logical run of the final "
        "revision (about 700 products are on these listings' first pages, so it holds even if every page 2 repeats "
        "page 1), the repeat on page 2, the new tile on other departments. Not a coverage claim for these rows: each "
        "row is narrowed to the listed listings. " + NOTE,
        "args": ["run", "--store", STORE, "--categories", "1,2,4,5,8,10,14,15,19,20,21"]
        + [a for x in S4C_LISTINGS for a in ("--subcategory", x)] + ["--max-credits", "64"],
        "folder": "cfg_rc4_ship", "lanes": 1, "submissions": 64, "usd": "0.0960", "minutes": 90, "stops": STOPS,
    },
    "S3b": {
        "stage_id": "M-S3b-natural-frozen-brand-union-190rc4-20261109",
        "objective": "M9 S3b on 1.9.0rc4 (8abc2c1): S3's objective on a listing above the 250-result window, since "
        "Milk now states 246: 18010 Natural & Organic > Frozen (CSV row 10; 279 products in the census of "
        "2026-11-02, the smallest listing above 250 apart from Milk 251 and Specialty Cheeses 255, which may have "
        "fallen below as Milk did) read through its brand readings with the M1 identities and the M2 binding. "
        "Measured: whether the listing still states more than 250; whether each brand page states its filter (M2); "
        "how much of the listing's stated total the brand readings reach; how often a brand reading's page repeats "
        "(the union is complete only if no needed page repeats); the brand readings' cost. " + NOTE,
        "args": ["run", "--store", STORE, "--categories", "10", "--subcategory", "10:18010", "--max-credits", "86"],
        "folder": "cfg_rc4_ship", "lanes": 1, "submissions": 86, "usd": "0.1290", "minutes": 120, "stops": STOPS,
    },
    "S4d": {
        "stage_id": "M-S4d-rows1-21-single-page-listings-190rc4-20261109",
        "objective": "M9 S4d on 1.9.0rc4 (8abc2c1): progressive coverage of rows 0-21 within what is left of the "
        "approval: the 30 listings of rows 1-21 that the census of 2026-11-02 measured at 24 products or fewer "
        "(one page each, 286 products) and that no 1.8 or 1.9 run has collected (INCOMPLETE_QUEUE after S3b). "
        "Hard Cider 08194 (6 products) is left out: its seed URL has no slash before its ID. One page each, so the "
        "repeat of later pages cannot stop them unless a listing has grown past 24. Measured: how many listings "
        "complete; the tile on more departments. Not a coverage claim for these rows: each row is narrowed to the "
        "listed listings. " + NOTE,
        "args": ["run", "--store", STORE, "--categories", "1,2,4,5,6,10,18,20,21"]
        + [a for x in S4D_LISTINGS for a in ("--subcategory", x)] + ["--max-credits", "64"],
        "folder": "cfg_rc4_ship", "lanes": 1, "submissions": 64, "usd": "0.0960", "minutes": 60, "stops": STOPS,
    },
}
for _s in SPECS.values():
    assert f"{_s['submissions'] * 0.0015:.4f}" == _s["usd"], _s["stage_id"]
    assert _s["stage_id"] in APPROVED_STAGES, _s["stage_id"]


def approval_used() -> int:
    """Ledger rows (submissions) of the approved stages so far, each reserved at USD 0.0015."""
    out = subprocess.run([SIGNED_PY, "-I", str(LEDGER), "--campaign", "oxylabs-trial-20261103", "rows"],
                         capture_output=True, text=True, check=True).stdout
    return sum(1 for r in json.loads(out) if r.get("stage_id") in APPROVED_STAGES)


def sha256_dir(folder: str) -> dict[str, str]:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((Q / folder).iterdir()) if p.is_file()}


def add(key: str) -> None:
    s = SPECS[key]
    used = approval_used()
    if s["submissions"] > APPROVAL["submissions"] - used:
        raise SystemExit(f"{s['stage_id']}: ceiling {s['submissions']} exceeds what is left of the approval "
                         f"({APPROVAL['submissions']} - {used})")
    stages = json.loads(STAGES.read_text(encoding="utf-8"))
    if s["stage_id"] in stages:
        raise SystemExit(f"{s['stage_id']} is already recorded")
    deadline = (datetime.now(UTC) + timedelta(minutes=s["minutes"])).strftime("%Y-%m-%dT%H:%M:%SZ")
    folder = s["folder"]
    rec = {
        "stage_id": s["stage_id"],
        "project": "marianos",
        "objective": s["objective"],
        "command": f"{RUNNER} run {s['stage_id']} -- " + " ".join(s["args"]),
        "collector_args": s["args"],
        "config": {
            "config_dir": str(Q / folder).replace("/", "\\"),
            "config_sha256": sha256_dir(folder),
            "lanes": s["lanes"],
            "database": "marianos_q190 (copy of Q2's database, cluster C:/m8/pg/data port 55190)",
            "data_dir": "C:\\m8\\q190\\data",
            "collector_ceiling": {"submissions": s["submissions"], "usd": s["usd"]},
            "read_product_terms": False,
            "listing_route": "listing (/pl/ pages), listing_run_js false (shipped)",
            "publish_auto": False,
            "changes_from_shipped": ["publish.auto false"]
            + ([f"limits.max_concurrent_listings {s['lanes']}"] if folder == "cfg_rc4_l2" else []),
        },
        "source_revision": REV,
        "max_requests": s["submissions"],
        "max_results": s["submissions"],
        "max_usd": s["usd"],
        "deadline_utc": deadline,
        "retry_policy": RETRY,
        "stop_conditions": s["stops"],
    }
    stages[s["stage_id"]] = rec
    STAGES.write_text(json.dumps(stages, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"recorded": s["stage_id"], "deadline_utc": deadline, "config_dir": rec["config"]["config_dir"]}))


def main(argv: list[str]) -> int:
    if argv[:1] == ["configs"]:
        for folder, kw in CONFIGS.items():
            print(folder, json.dumps(build(folder, **kw)))
        return 0
    if argv[:1] == ["add"] and len(argv) == 2:
        add(argv[1])
        return 0
    raise SystemExit(__doc__)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
