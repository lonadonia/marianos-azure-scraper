"""Gated live stages of Mariano's release 1.9.0 (M9): the frozen candidate's own command line, run in this process
behind the account-wide gate over the shared trial ledger.

- Collector: the frozen candidate C:/m8/qwt (its revision is checked: clean and equal to the stage's
  ``source_revision``), its own environment, the copied database marianos_q190 (a copy of Q2's database made
  2026-11-06 from the stopped cluster; Q2's own database is never written) and data folder C:/m8/q190/data.
- Configuration: the stage's own folder (``config_dir`` of the stage), whose files' SHA-256 are checked against the
  stage record before anything is sent.
- Budget: the shared ledger (<projects>/.shared-oxylabs-trial-20261103, campaign oxylabs-trial-20261103, project
  marianos). The process holds the campaign's exclusive lease (120 s TTL, renewed every 30 s) and sets
  ``OxylabsClient.account_gate_factory``: every submission is reserved at its worst case in the shared ledger
  before it is sent, marked dispatched, then settled with the provider's request id or held as unknown. The
  stage's ledger ceilings (requests, USD, deadline) and the collector's own ceiling (``set-ceiling``) both apply.
- The key: the designated file, read by the collector's own loader (parsed as data); only its fingerprint is shown,
  and a key whose fingerprint differs from EXPECTED_FP is refused.

usage:
  python -I live190_run.py open-stage STAGE_ID
  python -I live190_run.py run STAGE_ID -- <marianos-collector arguments>
  python -I live190_run.py cli CONFIG_DIR -- <marianos-collector arguments>  (no provider request: status, export, ...)
  python -I live190_run.py refused-start STAGE_ID -- run ...   (S5b's overlap check: every submission refused)
  python -I live190_run.py close-stage STAGE_ID OUTCOME
Stages: C:/m8/evidence/live190/stages.json; each run appends to C:/m8/evidence/live190/runs.jsonl.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from observe190 import CAMPAIGN, EXPECTED_FP, KEY_FILE, LEASE_RENEW_S, LEASE_TTL_S, PROJECT, PROXY_VARS, TRIAL_DIR, TrialGate, trial  # noqa: E402,E501

QWT = Path("C:/m8/qwt")
COLLECTOR = QWT / "headless" / "marianos-azure-headless"
EV = Path("C:/m8/evidence/live190")
STAGES = EV / "stages.json"
RUNS = EV / "runs.jsonl"
PGDATA = Path("C:/m8/pg/data")
DB = "marianos_q190"
DATA = r"C:\m8\q190\data"


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def git(*a: str) -> str:
    return subprocess.run(["git", "-C", str(QWT), *a], capture_output=True, text=True, check=False).stdout.strip()


def stage_spec(stage_id: str) -> dict[str, Any]:
    return json.loads(STAGES.read_text(encoding="utf-8"))[stage_id]


def env_for(config_dir: str) -> None:
    for v in PROXY_VARS:
        os.environ.pop(v, None)
    for v in ("OXYLABS_WEB_API_KEY", "SCRAPFLY_API_KEY", "SCRAPFLY_API_KEY_FILE", "MARIANOS_COLLECTOR_SOURCE_COMMIT"):
        os.environ.pop(v, None)
    port = (PGDATA / "postmaster.pid").read_text(encoding="utf-8").splitlines()[3].strip()
    os.environ["PSYCOPG_IMPL"] = "python"
    os.environ["PATH"] = str(COLLECTOR / ".venv/Lib/site-packages/pgserver/pginstall/bin") + os.pathsep + os.environ["PATH"]
    os.environ["MARIANOS_COLLECTOR_DATABASE_URL"] = f"postgresql+psycopg://postgres:@127.0.0.1:{port}/{DB}"
    os.environ["MARIANOS_COLLECTOR_CONFIG"] = str(Path(config_dir) / "collector.yaml")
    os.environ["MARIANOS_COLLECTOR_DATA_DIR"] = DATA
    os.environ["MARIANOS_COLLECTOR_ACTOR"] = "hamza-qualification-190"
    os.environ["OXYLABS_WEB_API_KEY_FILE"] = KEY_FILE


def check_tree(spec: dict[str, Any]) -> dict[str, Any]:
    import marianos_headless

    pkg = Path(marianos_headless.__file__).resolve()
    if COLLECTOR.resolve() not in pkg.parents:
        raise SystemExit(f"the collector imported from {pkg}, not the frozen candidate {COLLECTOR}")
    head = git("rev-parse", "HEAD")
    modified = git("status", "--porcelain", "--untracked-files=no").splitlines()
    if head != spec["source_revision"] or modified:
        raise SystemExit(f"candidate tree {head} (modified: {modified}) is not the stage's {spec['source_revision']}")
    files = {p.name: sha256(p) for p in sorted(Path(spec["config"]["config_dir"]).iterdir()) if p.is_file()}
    if files != spec["config"]["config_sha256"]:
        raise SystemExit("the stage's configuration files differ from the recorded hashes")
    return {"revision": head, "version": marianos_headless.__version__, "package": str(pkg),
            "uv_lock_sha256": sha256(COLLECTOR / "uv.lock"), "config_sha256": files}


def cli(args: list[str]) -> int:
    from marianos_headless.cli import main

    try:
        return int(main(args) or 0)
    except SystemExit as exc:  # argparse and the CLI's own exits
        return int(exc.code or 0) if isinstance(exc.code, int) else 1


def cmd_open(stage_id: str) -> int:
    otl = trial()
    spec = stage_spec(stage_id)
    led = otl.open_ledger(TRIAL_DIR, CAMPAIGN)
    keys = ("stage_id", "project", "objective", "command", "config", "source_revision", "max_requests", "max_results",
            "max_usd", "deadline_utc", "retry_policy", "stop_conditions")
    led.open_stage(**{k: spec[k] for k in keys})
    s = led.summary()
    print(json.dumps({"opened": stage_id, "committed_usd": s["committed_usd"], "marianos": s["projects"]["marianos"]}))
    return 0


def cmd_close(stage_id: str, outcome: str) -> int:
    otl = trial()
    led = otl.open_ledger(TRIAL_DIR, CAMPAIGN)
    led.close_stage(stage_id, outcome)
    s = led.summary()
    print(json.dumps({"closed": stage_id, "committed_usd": s["committed_usd"], "marianos": s["projects"]["marianos"],
                      "chain": led.verify_chain()}))
    return 0


def cmd_run(stage_id: str, args: list[str]) -> int:
    spec = stage_spec(stage_id)
    env_for(spec["config"]["config_dir"])
    tree = check_tree(spec)
    from marianos_headless.acquisition import oxylabs

    key = oxylabs.load_key()
    if key is None:
        raise SystemExit("no key in the designated file")
    fp = oxylabs.fingerprint(key)
    if fp != EXPECTED_FP:
        raise SystemExit(f"key fingerprint {fp} is not the noted {EXPECTED_FP}")
    del key
    otl = trial()
    ledger = otl.open_ledger(TRIAL_DIR, CAMPAIGN)
    lease = ledger.acquire_lease(PROJECT, f"live190:{stage_id}:{os.getpid()}", LEASE_TTL_S)
    stop = threading.Event()
    lost: list[str] = []

    def renew() -> None:
        while not stop.wait(LEASE_RENEW_S):
            try:
                ledger.renew_lease(lease, LEASE_TTL_S)
            except Exception as exc:  # the gate refuses every later reservation once the lease is gone
                lost.append(f"{now()} {type(exc).__name__}: {exc}"[:300])
                print(json.dumps({"event": "TRIAL_LEASE_RENEW_FAILED", "message": lost[-1]}), flush=True)
                return

    threading.Thread(target=renew, daemon=True).start()
    lanes = int(spec["config"].get("lanes", 1))
    gates: list[TrialGate] = []

    def factory() -> TrialGate:
        g = TrialGate(otl, ledger, lease, stage_id, inflight_cap=lanes)
        gates.append(g)
        return g

    oxylabs.OxylabsClient.account_gate_factory = factory
    started, t0 = now(), time.monotonic()
    code = 1
    try:
        code = cli(args)
    finally:
        oxylabs.OxylabsClient.account_gate_factory = None
        stop.set()
        try:
            ledger.release_lease(lease, f"live190 {stage_id} ended (exit {code})")
        except Exception as exc:
            lost.append(f"release: {type(exc).__name__}: {exc}"[:300])
        events = [e for g in gates for e in g.events]
        s = ledger.summary()
        rec = {
            "stage": stage_id,
            "utc_start": started,
            "utc_end": now(),
            "seconds": round(time.monotonic() - t0, 1),
            "args": args,
            "exit_code": code,
            "key_fingerprint": fp,
            "tree": tree,
            "lease_id": lease.id,
            "lease_problems": lost,
            "gate_counts": {k: sum(1 for e in events if e["event"] == k)
                            for k in ("reserved", "dispatched", "unsent", "settled", "settled_free", "unknown")},
            "ledger_marianos": s["projects"]["marianos"],
            "campaign_committed_usd": s["committed_usd"],
            "campaign_spendable_usd": s["spendable_campaign_usd"],
        }
        with RUNS.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, default=str) + "\n")
        print(json.dumps({"event": "LIVE190_STAGE_RUN_ENDED", **{k: rec[k] for k in (
            "stage", "exit_code", "seconds", "gate_counts", "ledger_marianos", "lease_problems")}}, default=str), flush=True)
    return code


class DenyGate:
    """S5b's overlap check (a second start while a run holds the store): a gate that refuses every submission,
    so this process can never send a request, whatever the collector decides. It takes no ledger lease."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def reserve(self, *, purpose: str, endpoint: str, target_url: str, attempt: int, usd: float, key: str) -> str:
        from marianos_headless.acquisition.oxylabs import GateRefused

        self.events.append({"at": now(), "event": "refused", "purpose": purpose, "attempt": attempt})
        raise GateRefused("overlap check: this process may not send any submission")

    def dispatched(self, ref: str) -> None:
        raise AssertionError("nothing can be dispatched through the overlap check's gate")

    def unsent(self, ref: str, reason: str) -> None:
        raise AssertionError("nothing can be reserved through the overlap check's gate")

    def settled(self, ref: str, **kw: Any) -> None:
        raise AssertionError("nothing can be settled through the overlap check's gate")

    def unknown(self, ref: str, reason: str) -> None:
        raise AssertionError("nothing can be held through the overlap check's gate")


def cmd_refused_start(stage_id: str, args: list[str]) -> int:
    spec = stage_spec(stage_id)
    env_for(spec["config"]["config_dir"])
    tree = check_tree(spec)
    from marianos_headless.acquisition import oxylabs

    gates: list[DenyGate] = []

    def factory() -> DenyGate:
        g = DenyGate()
        gates.append(g)
        return g

    oxylabs.OxylabsClient.account_gate_factory = factory
    started, t0 = now(), time.monotonic()
    code = 1
    try:
        code = cli(args)
    finally:
        oxylabs.OxylabsClient.account_gate_factory = None
        rec = {
            "stage": stage_id,
            "kind": "refused-start: a second start while a run holds the store, through a gate refusing every "
            "submission (no ledger lease, nothing can be sent)",
            "utc_start": started,
            "utc_end": now(),
            "seconds": round(time.monotonic() - t0, 1),
            "args": args,
            "exit_code": code,
            "tree": tree,
            "gate_refusals": [e for g in gates for e in g.events],
        }
        with RUNS.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, default=str) + "\n")
        print(json.dumps({"event": "LIVE190_REFUSED_START_ENDED", **{k: rec[k] for k in (
            "stage", "exit_code", "seconds", "gate_refusals")}}, default=str), flush=True)
    return code


def cmd_cli(args: list[str], config_dir: str) -> int:
    env_for(config_dir)
    from marianos_headless.acquisition import oxylabs

    oxylabs.OxylabsClient.account_gate_factory = None
    if args and args[0] in ("run", "resume"):
        raise SystemExit("run and resume send requests: use `run STAGE_ID -- ...`")
    return cli(args)


def main(argv: list[str]) -> int:
    if not argv:
        raise SystemExit(__doc__)
    if argv[0] == "open-stage":
        return cmd_open(argv[1])
    if argv[0] == "close-stage":
        return cmd_close(argv[1], argv[2])
    if argv[0] == "run":
        stage_id, rest = argv[1], argv[2:]
        if rest[:1] == ["--"]:
            rest = rest[1:]
        return cmd_run(stage_id, rest)
    if argv[0] == "refused-start":
        stage_id, rest = argv[1], argv[2:]
        if rest[:1] == ["--"]:
            rest = rest[1:]
        return cmd_refused_start(stage_id, rest)
    if argv[0] == "cli":
        config_dir, rest = argv[1], argv[2:]
        if rest[:1] == ["--"]:
            rest = rest[1:]
        return cmd_cli(rest, config_dir)
    raise SystemExit(__doc__)


if __name__ == "__main__":
    with contextlib.suppress(BrokenPipeError):
        sys.exit(main(sys.argv[1:]))
