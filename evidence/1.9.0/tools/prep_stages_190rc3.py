"""Configurations and ledger stage records for the live stages of collector 1.9.0rc3 (S1b, S3, S4, S5a, S5b).

Each configuration folder is built from the shipped configuration of the development commit (``git show``,
byte for byte) with only the stated changes, each asserted to apply exactly once:

- every stage: ``publish.auto: false`` (a stage run is never published automatically);
- S1b: ``coverage.read_product_terms: true`` (the product-page coupon-terms path, at most 8 reads);
- S5a / S5b: ``limits.max_concurrent_listings`` 1 / 2 in the Vernon Hills PICKUP collection.

usage:
  python -I prep_stages_190rc3.py configs            build the folders (refuses to overwrite a different file)
  python -I prep_stages_190rc3.py add STAGE_KEY      write the stage record (deadline = now + its minutes)
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

WT = Path("C:/m8/wt")
REV = "90905377f4919d33854c23d8068fd7e36553ab31"
CFG_PREFIX = "headless/marianos-azure-headless/config/"
FILES = ("collector.yaml", "Marianos_Category_URLs.csv", "private_label_brands.yaml", "settings.yaml",
         "stores.yaml", "taxonomy_seed.snapshot_2026-10-17.json")
Q = Path("C:/m8/q190")
STAGES = Path("C:/m8/evidence/live190/stages.json")
RUNNER = "C:/m8/qwt/headless/marianos-azure-headless/.venv/Scripts/python.exe -I C:/m8/live/live190_run.py"
STORE = "marianos-53100502-pickup"

AUTO_OLD = b"  auto: true\n"
AUTO_NEW = b"  auto: false                      # live stages of 1.9.0: a stage run is never published automatically\n"
TERMS_OLD = b"    partition_large_listings: true }\n"
TERMS_NEW = b"    partition_large_listings: true, read_product_terms: true }\n"
LANES_AFTER = b"      min_credit_reserve: 0\n"


def lanes_line(n: int) -> bytes:
    return f"      max_concurrent_listings: {n}   # live stage S5 of 1.9.0: listing lanes\n".encode()


def shipped(name: str) -> bytes:
    return subprocess.run(["git", "-C", str(WT), "show", f"{REV}:{CFG_PREFIX}{name}"], capture_output=True,
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


def build(folder: str, *, terms: bool = False, lanes: int | None = None) -> dict[str, str]:
    out = Q / folder
    out.mkdir(parents=True, exist_ok=True)
    digests = {}
    for name in FILES:
        data = shipped(name)
        if name == "collector.yaml":
            data = once(data, AUTO_OLD, AUTO_NEW, f"{folder}/{name} publish.auto")
            if lanes is not None:
                data = once(data, LANES_AFTER, lanes_line(lanes), f"{folder}/{name} lanes")
        if name == "settings.yaml" and terms:
            data = once(data, TERMS_OLD, TERMS_NEW, f"{folder}/{name} read_product_terms")
        p = out / name
        if p.exists() and p.read_bytes() != data:
            raise SystemExit(f"{p} exists with different content: not overwritten")
        p.write_bytes(data)
        digests[name] = hashlib.sha256(data).hexdigest()
    return digests


CONFIGS = {
    "cfg_s1b": {"terms": True},
    "cfg_ship190": {},
    "cfg_s5_l1": {"lanes": 1},
    "cfg_s5_l2": {"lanes": 2},
}

RETRY = ("the collector's own, as shipped: a listing page up to 3 attempts on 408/429/5xx with backoff (failed "
         "requests are documented as not charged; every attempt is still reserved at its worst case); a rendered "
         "listing answer without tiles is asked again, three in a row stop the run resumably (PROVIDER_ERROR); a "
         "product-page terms read is sent once and never retried; the stage is not repeated before its outcome is read")
STOPS = ("the store or PICKUP not verified on a page; the canary failing; a refusal page; 401/402/403 or a quota "
         "answer; ABNORMAL_RESULT; the stage's or the collector's ceiling; more than 2 outcomes unknown; lease loss; "
         "the key fingerprint differing from the noted one; the deadline")

# The note recorded with S4 (2026-11-09 14:30Z) said the repeat was on every listing above 24 products; S4 itself
# contradicted it (its outcome says so). The stages recorded after S4 carry this note instead.
NOTE = ("Known before this stage (O2 2026-11-06; S1b and S4 2026-11-09): an unrendered listing answer for ?page=N can "
        "carry page 1's products under ranks shifted by 24(N-1); the collector then ends that listing as incomplete "
        "(repeated page). S4 showed it is intermittent and clustered in time, not tied to a listing: 12 page-N answers "
        "were distinct from 14:31:50Z to 14:33:28Z (Dog Treats 150 of 150 over 7 pages; Dog Food pages 2-7), 8 "
        "repeated page 1 from 14:33:35Z to 14:36:51Z (Dog Food page 8, then page 2 of Cat Food, Cat Treats, Cat "
        "Litter, Candles, Batteries, Light Bulbs and School Office), and Hardware's pages 2-3 were distinct again at "
        "14:37:57Z. ")

SPECS = {
    "S1b": {
        "stage_id": "M-S1b-canary-catfood-190rc3-20261109",
        "objective": "M9 S1b on 1.9.0rc3 (9090537): the Vernon Hills PICKUP canary on the product tile served since "
        "2026-11-06 (store, fulfillment and page checks on every page); Cat Food (CSV row 22, listing 27021) read "
        "again in full for the 231/232 reconciliation (Q2: 232 slots, 231 distinct products); the product-page "
        "coupon-terms path live, at most 8 reads, each sent once",
        "args": ["run", "--store", STORE, "--categories", "22", "--subcategory", "22:27021", "--max-term-reads", "8",
                 "--max-credits", "25"],
        "folder": "cfg_s1b", "lanes": 1, "submissions": 25, "usd": "0.0375", "minutes": 45,
    },
    "S3": {
        "stage_id": "M-S3-milk-brand-union-190rc3-20261109",
        "objective": "M9 S3 on 1.9.0rc3: an above-window listing read through its brand readings with the M1 "
        "identities and the M2 binding: 02001 Milk (CSV row 8; 251 products in Q2's menu count, the smallest listing "
        "above the 250-result window). " + NOTE + "Measured: whether each brand page states its filter (M2), how much "
        "of the listing's stated total the brand readings reach, and how often a brand reading's page repeats page 1 "
        "(the union is complete only if no needed page repeats)",
        "args": ["run", "--store", STORE, "--categories", "8", "--subcategory", "8:02001", "--max-credits", "80"],
        "folder": "cfg_ship190", "lanes": 1, "submissions": 80, "usd": "0.1200", "minutes": 120,
    },
    "S4": {
        "stage_id": "M-S4-rows22-27-190rc3-20261109",
        "objective": "M9 S4 on 1.9.0rc3, CSV rows 22-27 in one logical run. " + NOTE + "Q2's 17 listings of these rows "
        "hold 1,181 products, 275 of them on first pages, so the planned at least 500 fresh valid is not expected. "
        "Measured: the new tile read live across 17 listings, the repeat on every listing above 24, the fresh valid "
        "count, retention against Q2 as observed, latencies",
        "args": ["run", "--store", STORE, "--categories", "22,23,24,25,26,27", "--max-credits", "130"],
        "folder": "cfg_ship190", "lanes": 1, "submissions": 130, "usd": "0.1950", "minutes": 150,
    },
    "S5a": {
        "stage_id": "M-S5a-rows23-26-one-lane-190rc3-20261109",
        "objective": "M8/M9 S5a on 1.9.0rc3: CSV rows 23-26 with one listing lane (limits.max_concurrent_listings "
        "1), uninterrupted: the time and submissions of one lane, for the comparison with S5b; and whether the four "
        "listings of these rows (Candles, Batteries, Light Bulbs, School Office), each repeated at page 2 in S4, "
        "repeat again. " + NOTE.strip(),
        "args": ["run", "--store", STORE, "--categories", "23,24,25,26", "--max-credits", "30"],
        "folder": "cfg_s5_l1", "lanes": 1, "submissions": 30, "usd": "0.0450", "minutes": 60,
    },
    "S5b": {
        "stage_id": "M-S5b-rows23-26-two-lanes-190rc3-20261109",
        "objective": "M8/M9 S5b on 1.9.0rc3: the same rows with two listing lanes (limits.max_concurrent_listings 2): "
        "the time and submissions of two lanes; in this run a termination signal (interrupted, resumable), resume, "
        "a second start while it runs (expected refused, sent through a gate that refuses every submission), a hard "
        "kill, resume to the end; then status and export; and whether these rows' listings repeat at page 2 again. "
        + NOTE.strip(),
        "args": ["run", "--store", STORE, "--categories", "23,24,25,26", "--max-credits", "30"],
        "folder": "cfg_s5_l2", "lanes": 2, "submissions": 30, "usd": "0.0450", "minutes": 90,
    },
}


def sha256_dir(folder: str) -> dict[str, str]:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((Q / folder).iterdir()) if p.is_file()}


def add(key: str) -> None:
    s = SPECS[key]
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
            "read_product_terms": folder == "cfg_s1b",
            "listing_route": "listing (/pl/ pages), listing_run_js false (shipped)",
            "publish_auto": False,
            "changes_from_shipped": ["publish.auto false"]
            + (["coverage.read_product_terms true"] if folder == "cfg_s1b" else [])
            + ([f"limits.max_concurrent_listings {s['lanes']}"] if folder.startswith("cfg_s5") else []),
        },
        "source_revision": REV,
        "max_requests": s["submissions"],
        "max_results": s["submissions"],
        "max_usd": s["usd"],
        "deadline_utc": deadline,
        "retry_policy": RETRY,
        "stop_conditions": STOPS,
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
