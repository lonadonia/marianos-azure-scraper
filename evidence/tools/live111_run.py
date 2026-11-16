"""Gated live stages of Mariano's on the owner's own VM: the installed release's command line, run in this process
behind the account-wide gate over the shared trial ledger. Adapted from evidence/1.9.0/tools/live190_run.py and
observe190.py (the gate class is unchanged); what differs is where things are: an installed release instead of a
worktree, the VM's PostgreSQL, and paths taken from the environment.

- Collector: the release under RELEASES (a virtual environment installed from the wheel and the hashed lockfile
  export). Checked before anything is sent: the imported package is inside that release, its version and the
  release's recorded source commit equal the stage's, and the release's SOURCES.sha256 equals the stage's.
- Configuration: the stage's own folder, whose files' SHA-256 are checked against the stage record.
- Budget: the shared ledger (LEDGER_DIR, campaign oxylabs-trial-20261103, project marianos). The process holds the
  campaign's exclusive lease (120 s TTL, renewed every 30 s) and sets ``OxylabsClient.account_gate_factory``: every
  submission is reserved at its worst case in the shared ledger before it is sent, marked dispatched, then settled
  with the provider's request id or held as unknown. The stage's ledger ceilings (requests, USD, deadline) and the
  collector's own ceiling (``set-ceiling``) both apply.
- The key: the designated file, read by the collector's own loader; only its fingerprint is shown, and a key whose
  fingerprint differs from the one noted in the ledger's handoff (EXPECTED_FP, from the environment) is refused.

Environment (set by the wrapper, none secret): M111_OPS (stages.json, runs.jsonl), M111_LEDGER_DIR,
M111_EXPECTED_FP, M111_RELEASES, plus the collector's own (database URL, data folder, key file).

usage:
  live111_run.py open-stage STAGE_ID
  live111_run.py run STAGE_ID -- <marianos-collector arguments>
  live111_run.py cli STAGE_ID -- <marianos-collector arguments>   (no provider request: status, export, ...)
  live111_run.py refused-start STAGE_ID -- run ...   (a second start through a gate refusing every submission)
  live111_run.py close-stage STAGE_ID OUTCOME
  live111_run.py ledger-status
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import json
import os
import sys
import threading
import time
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

OPS = Path(os.environ.get("M111_OPS", "/var/lib/marianos-collector/ops111"))
LEDGER_DIR = Path(os.environ.get("M111_LEDGER_DIR", "/var/lib/oxylabs-trial-20261103"))
RELEASES = Path(os.environ.get("M111_RELEASES", "/opt/marianos-collector/releases"))
EXPECTED_FP = os.environ.get("M111_EXPECTED_FP", "")
CAMPAIGN = "oxylabs-trial-20261103"
PROJECT = "marianos"
LEASE_TTL_S = 120.0
LEASE_RENEW_S = 30.0
PROXY_VARS = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy")
STAGES = OPS / "stages.json"
RUNS = OPS / "runs.jsonl"


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def trial() -> Any:
    spec = importlib.util.spec_from_file_location("oxytrial_ledger", LEDGER_DIR / "oxytrial_ledger.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["oxytrial_ledger"] = mod
    spec.loader.exec_module(mod)
    return mod


class TrialGate:
    """The collector's AccountGate over the shared trial ledger (one lease for the process). ``inflight_cap``:
    a reservation that would put more than that many submissions of this lease in flight is refused (the
    ledger-backed worker cap; nothing is sent). Unchanged from evidence/1.9.0/tools/observe190.py."""

    def __init__(self, otl: Any, ledger: Any, lease: Any, stage_id: str, *, inflight_cap: int = 1) -> None:
        self.otl, self.ledger, self.lease, self.stage_id = otl, ledger, lease, stage_id
        self.inflight_cap = inflight_cap
        self.events: list[dict[str, Any]] = []

    def _inflight(self) -> int:
        return sum(1 for r in self.ledger.rows(lease_id=self.lease.id) if r["state"] in ("reserved", "dispatched"))

    def reserve(self, *, purpose: str, endpoint: str, target_url: str, attempt: int, usd: float, key: str) -> str:
        from marianos_headless.acquisition.oxylabs import GateRefused

        inflight = self._inflight()
        if inflight >= self.inflight_cap:
            raise GateRefused(f"in-flight cap {self.inflight_cap} of this lease reached ({inflight} in flight)")
        worst = max(Decimal(str(usd)), Decimal("0.0015"))
        try:
            rid = str(
                self.ledger.reserve(
                    self.lease,
                    stage_id=self.stage_id,
                    purpose=f"{purpose} (attempt {attempt})",
                    endpoint=endpoint,
                    target=target_url,
                    worst_results=1,
                    worst_usd=str(worst),
                    dispatch_key=f"{self.stage_id}:{key}",
                )
            )
        except self.otl.LedgerError as exc:
            raise GateRefused(str(exc)) from None
        self.events.append({"at": now(), "event": "reserved", "rid": rid, "worst_usd": str(worst)})
        return rid

    def dispatched(self, ref: str) -> None:
        self.ledger.mark_dispatched(self.lease, ref)
        self.events.append({"at": now(), "event": "dispatched", "rid": ref})

    def unsent(self, ref: str, reason: str) -> None:
        self.ledger.release_unsent(self.lease, ref, reason=reason)
        self.events.append({"at": now(), "event": "unsent", "rid": ref, "reason": reason})

    def settled(
        self, ref: str, *, status: int, kind: str | None, charged: bool | None, usd: float, request_id: str
    ) -> None:
        job = request_id or None
        if charged is True:
            self.ledger.settle(
                ref,
                results=1,
                usd_amount=str(max(Decimal(str(usd)), Decimal("0.0015"))),
                kind="rule_estimate",
                basis="an answer with a page: one result at the reservation rate USD 0.0015 (the price page's "
                "highest non-AI row, a list price read 2026-11-03; not an invoice)",
                provider_job_id=job,
                http_status=status,
            )
            state = "settled"
        elif charged is False:
            self.ledger.settle(
                ref,
                results=0,
                usd_amount="0",
                kind="documented_free",
                basis=f"{kind}: documented by Oxylabs as not charged (Web API Troubleshooting)",
                provider_job_id=job,
                http_status=status,
            )
            state = "settled_free"
        else:
            self.ledger.mark_unknown(
                ref, reason=f"HTTP {status} {kind}: the charge is not known", provider_job_id=job, http_status=status
            )
            state = "unknown"
        self.events.append({"at": now(), "event": state, "rid": ref, "status": status, "kind": kind,
                            "provider_job_id": job})

    def unknown(self, ref: str, reason: str) -> None:
        self.ledger.mark_unknown(ref, reason=reason)
        self.events.append({"at": now(), "event": "unknown", "rid": ref, "reason": reason})


class DenyGate:
    """A gate that refuses every submission, so this process can never send a request, whatever the collector
    decides (the refused-second-start check). It takes no ledger lease."""

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


def stage_spec(stage_id: str) -> dict[str, Any]:
    return dict(json.loads(STAGES.read_text(encoding="utf-8"))[stage_id])


def env_for(spec: dict[str, Any]) -> None:
    for v in (*PROXY_VARS, "OXYLABS_WEB_API_KEY", "SCRAPFLY_API_KEY", "SCRAPFLY_API_KEY_FILE"):
        os.environ.pop(v, None)
    cfg = Path(spec["config"]["config_dir"])
    os.environ["MARIANOS_COLLECTOR_CONFIG"] = str(cfg / "collector.yaml")
    os.environ["MARIANOS_COLLECTOR_CONFIG_DIR"] = str(cfg)
    os.environ.setdefault("MARIANOS_COLLECTOR_ACTOR", "hamza-owner-vm-qualification")
    target = spec.get("target") or {}
    if target:  # an isolated target named by the stage record (its own database and data folder)
        os.environ["MARIANOS_COLLECTOR_DATABASE_URL"] = target["database_url"]
        os.environ["MARIANOS_COLLECTOR_DATA_DIR"] = target["data_dir"]
    for name in ("MARIANOS_COLLECTOR_DATABASE_URL", "MARIANOS_COLLECTOR_DATA_DIR", "OXYLABS_WEB_API_KEY_FILE",
                 "MARIANOS_COLLECTOR_SOURCE_COMMIT"):
        if not os.environ.get(name):
            raise SystemExit(f"{name} is not set (the wrapper passes the target's env file and release.env)")


def check_release(spec: dict[str, Any]) -> dict[str, Any]:
    import marianos_headless

    pkg = Path(marianos_headless.__file__).resolve()
    release = RELEASES / spec["release"]
    if release.resolve() not in pkg.parents:
        raise SystemExit(f"the collector imported from {pkg}, not the stage's release {release}")
    commit = os.environ["MARIANOS_COLLECTOR_SOURCE_COMMIT"]
    recorded = (release / "release.env").read_text(encoding="utf-8").strip().split("=", 1)[1]
    if not (commit == recorded == spec["source_revision"]):
        raise SystemExit(f"release commit {recorded} / environment {commit} is not the stage's {spec['source_revision']}")
    if marianos_headless.__version__ != spec["version"]:
        raise SystemExit(f"version {marianos_headless.__version__} is not the stage's {spec['version']}")
    sources = sha256(release / "SOURCES.sha256")
    if sources != spec["release_sources_sha256"]:
        raise SystemExit("the release's SOURCES.sha256 differs from the stage record")
    files = {p.name: sha256(p) for p in sorted(Path(spec["config"]["config_dir"]).iterdir()) if p.is_file()}
    if files != spec["config"]["config_sha256"]:
        raise SystemExit("the stage's configuration files differ from the recorded hashes")
    return {"revision": recorded, "version": marianos_headless.__version__, "package": str(pkg),
            "release_sources_sha256": sources, "config_sha256": files}


def cli(args: list[str]) -> int:
    from marianos_headless.cli import main

    try:
        return int(main(args) or 0)
    except SystemExit as exc:  # argparse and the CLI's own exits
        return int(exc.code or 0) if isinstance(exc.code, int) else 1


def record(rec: dict[str, Any]) -> None:
    with RUNS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, default=str) + "\n")


def cmd_open(stage_id: str) -> int:
    otl = trial()
    spec = stage_spec(stage_id)
    led = otl.open_ledger(LEDGER_DIR, CAMPAIGN)
    keys = ("stage_id", "project", "objective", "command", "config", "source_revision", "max_requests", "max_results",
            "max_usd", "deadline_utc", "retry_policy", "stop_conditions")
    led.open_stage(**{k: spec[k] for k in keys})
    s = led.summary()
    print(json.dumps({"opened": stage_id, "at": now(), "committed_usd": s["committed_usd"],
                      "marianos": s["projects"]["marianos"]}, default=str))
    return 0


def cmd_close(stage_id: str, outcome: str) -> int:
    otl = trial()
    led = otl.open_ledger(LEDGER_DIR, CAMPAIGN)
    led.close_stage(stage_id, outcome)
    s = led.summary()
    print(json.dumps({"closed": stage_id, "at": now(), "committed_usd": s["committed_usd"],
                      "marianos": s["projects"]["marianos"], "chain": led.verify_chain()}, default=str))
    return 0


def cmd_ledger_status() -> int:
    otl = trial()
    led = otl.open_ledger(LEDGER_DIR, CAMPAIGN)
    s = led.summary()
    print(json.dumps({"read_at": now(), "chain": led.verify_chain(), "cap_usd": s["cap_usd"],
                      "committed_usd": s["committed_usd"], "spendable_campaign_usd": s["spendable_campaign_usd"],
                      "active_lease": s["active_lease"], "projects": s["projects"],
                      "reservations_by_state": s["reservations_by_state"]}, default=str, indent=1))
    return 0


def cmd_run(stage_id: str, args: list[str]) -> int:
    spec = stage_spec(stage_id)
    env_for(spec)
    tree = check_release(spec)
    from marianos_headless.acquisition import oxylabs

    key = oxylabs.load_key()
    if key is None:
        raise SystemExit("no key in the designated file")
    fp = oxylabs.fingerprint(key)
    if not EXPECTED_FP or fp != EXPECTED_FP:
        raise SystemExit("the key's fingerprint is not the one noted for the trial account")
    del key
    otl = trial()
    ledger = otl.open_ledger(LEDGER_DIR, CAMPAIGN)
    lease = ledger.acquire_lease(PROJECT, f"live111:{stage_id}:{os.getpid()}", LEASE_TTL_S)
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
            ledger.release_lease(lease, f"live111 {stage_id} ended (exit {code})")
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
            "key_fingerprint_matches_the_noted_one": True,
            "tree": tree,
            "lease_id": lease.id,
            "lease_problems": lost,
            "gate_counts": {k: sum(1 for e in events if e["event"] == k)
                            for k in ("reserved", "dispatched", "unsent", "settled", "settled_free", "unknown")},
            "ledger_marianos": s["projects"]["marianos"],
            "campaign_committed_usd": s["committed_usd"],
            "campaign_spendable_usd": s["spendable_campaign_usd"],
        }
        record(rec)
        print(json.dumps({"event": "LIVE111_STAGE_RUN_ENDED", **{k: rec[k] for k in (
            "stage", "exit_code", "seconds", "gate_counts", "ledger_marianos", "lease_problems")}}, default=str),
            flush=True)
    return code


def cmd_refused_start(stage_id: str, args: list[str]) -> int:
    spec = stage_spec(stage_id)
    env_for(spec)
    tree = check_release(spec)
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
        record(rec)
        print(json.dumps({"event": "LIVE111_REFUSED_START_ENDED", **{k: rec[k] for k in (
            "stage", "exit_code", "seconds", "gate_refusals")}}, default=str), flush=True)
    return code


def cmd_cli(stage_id: str, args: list[str]) -> int:
    spec = stage_spec(stage_id)
    env_for(spec)
    from marianos_headless.acquisition import oxylabs

    oxylabs.OxylabsClient.account_gate_factory = None
    if args and args[0] in ("run", "resume"):
        raise SystemExit("run and resume send requests: use `run STAGE_ID -- ...`")
    return cli(args)


def main(argv: list[str]) -> int:
    if not argv:
        raise SystemExit(__doc__)
    cmd = argv[0]
    rest = argv[2:]
    if rest[:1] == ["--"]:
        rest = rest[1:]
    if cmd == "open-stage":
        return cmd_open(argv[1])
    if cmd == "close-stage":
        return cmd_close(argv[1], argv[2])
    if cmd == "ledger-status":
        return cmd_ledger_status()
    if cmd == "run":
        return cmd_run(argv[1], rest)
    if cmd == "refused-start":
        return cmd_refused_start(argv[1], rest)
    if cmd == "cli":
        return cmd_cli(argv[1], rest)
    raise SystemExit(__doc__)


if __name__ == "__main__":
    with contextlib.suppress(BrokenPipeError):
        sys.exit(main(sys.argv[1:]))
