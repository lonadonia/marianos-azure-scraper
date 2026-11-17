"""PRIVATE OPS on the owner VM (root): writes one stage's record and its own configuration folder.

    python3.12 -I prep_stage.py DEFS_JSON STAGE_KEY

The stage's configuration is the installed release's shipped configuration with ``publish.auto`` false (a trial
stage is never published) and, when the definition asks for it, the listing lanes; nothing else differs. Its files'
SHA-256 go into the stage record, which the harness checks before anything is sent. A stage id is never reused.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

OPS = Path("/var/lib/marianos-collector/ops-rc6")
CURRENT = Path("/opt/marianos-collector/current")
ETC = Path("/etc/marianos-collector")
RATE = "0.0015"


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    defs = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    d = defs["stages"][sys.argv[2]]
    common = defs["common"]
    release = CURRENT.resolve()
    version = release.name
    commit = (release / "release.env").read_text(encoding="utf-8").strip().split("=", 1)[1]
    stage_id = d["stage_id"]
    stages_file = OPS / "stages.json"
    stages = json.loads(stages_file.read_text(encoding="utf-8")) if stages_file.exists() else {}
    if stage_id in stages:
        print(f"REFUSED: stage {stage_id} exists")
        return 2
    cfg = OPS / "stages" / stage_id / "config"
    cfg.mkdir(parents=True)
    src = ETC / f"config.{version}"
    for p in sorted(src.iterdir()):
        if p.is_file():
            shutil.copy2(p, cfg / p.name)
    y = (cfg / "collector.yaml").read_bytes()
    old = b"publish:\n  auto: true"
    if y.count(old) != 1:
        print("REFUSED: publish.auto true not found exactly once in collector.yaml")
        return 3
    y = y.replace(old, b"publish:\n  auto: false")
    lanes = int(d.get("lanes", 1))
    if lanes != 1:
        anchor = b"      reask_min_wait_seconds: 300" + bytes([10])
        if y.count(anchor) != 1 or b"max_concurrent_listings" in y:
            print("REFUSED: the contest store's limits block was not found exactly once in collector.yaml")
            return 4
        y = y.replace(anchor, anchor + f"      max_concurrent_listings: {lanes}".encode() + bytes([10]))
    cats = d.get("categories")
    if cats is not None:
        anchor = b"  marianos-53100502-pickup:\n    categories: []"  # the contest store's block only
        if y.count(anchor) != 1:
            print("REFUSED: the contest store's categories line was not found exactly once in collector.yaml")
            return 5
        y = y.replace(anchor, b"  marianos-53100502-pickup:\n    categories: " + json.dumps(cats).encode())
    (cfg / "collector.yaml").write_bytes(y)
    for p in cfg.iterdir():
        shutil.chown(p, "root", "marianos")
        os.chmod(p, 0o640)
    for p in (cfg, cfg.parent):
        shutil.chown(p, "root", "marianos")
        os.chmod(p, 0o750)
    deadline = datetime.now(UTC) + timedelta(minutes=int(d["deadline_minutes"]))
    n = int(d["max_submissions"])
    rec = {
        "stage_id": stage_id,
        "project": "marianos",
        "objective": d["objective"],
        "command": d["command"],
        "config": {
            "config_dir": str(cfg),
            "config_sha256": {p.name: sha256(p) for p in sorted(cfg.iterdir()) if p.is_file()},
            "shipped_config_sha256": {p.name: sha256(p) for p in sorted(src.iterdir()) if p.is_file()},
            "differs_from_shipped_in": ["collector.yaml: publish.auto false"] + (
                [f"collector.yaml: limits.max_concurrent_listings {lanes}"] if lanes != 1 else []) + (
                [f"collector.yaml: categories {json.dumps(cats)} (the isolated publication target's "
                 "configured scope)"] if cats is not None else []),
            "lanes": lanes,
            "environment": "the owner's own Azure VM (Ubuntu 24.04), PostgreSQL 16, release installed from the wheel",
        },
        "source_revision": commit,
        "version": version,
        "release": version,
        "release_sources_sha256": sha256(release / "SOURCES.sha256"),
        "max_requests": n,
        "max_results": n,
        "max_usd": f"{n * float(RATE):.6f}",
        "deadline_utc": deadline.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "deadline_minutes": int(d["deadline_minutes"]),
        "retry_policy": common["retry_policy"],
        "stop_conditions": "; ".join(common["stop_conditions"]),
        "passes_when": d.get("passes_when", ""),
        "approval": common.get("approval", ""),
        "target": d.get("target") or {},
        "prepared_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    stages[stage_id] = rec
    tmp = stages_file.with_suffix(".tmp")
    tmp.write_text(json.dumps(stages, indent=1), encoding="utf-8")
    os.replace(tmp, stages_file)
    shutil.chown(stages_file, "root", "marianos")
    os.chmod(stages_file, 0o640)
    print(json.dumps({k: rec[k] for k in ("stage_id", "command", "max_requests", "max_usd", "deadline_utc",
                                           "source_revision", "version")}, indent=1))
    print("config:", json.dumps(rec["config"]["config_sha256"], indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
