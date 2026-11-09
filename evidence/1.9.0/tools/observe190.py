"""Gated single-request source observations for Mariano's release 1.9 (stage O1 and later observation stages):
complete coupon terms (M4), offer and size reobservations (M6). Nothing here collects or exports products.

Each request goes through the collector's own Oxylabs client (marianos_headless.acquisition.oxylabs.OxylabsClient
of the interpreter's installed tree, recorded with its revision), with ONE attempt (no automatic retry: a retry is a
new, separately reserved step), and through the account-wide gate over the shared trial ledger
(<projects>/.shared-oxylabs-trial-20261103, campaign oxylabs-trial-20261103, project marianos): the process holds the
campaign's exclusive lease (120 s TTL, renewed every 30 s); the submission is reserved at its worst case and marked
dispatched before it is sent, then settled with the provider's request id, or held as unknown.

The key: the designated file, read by the collector's load_key() (parsed as data); only its fingerprint is shown,
and a key whose fingerprint differs from EXPECTED_FP is refused (a new ledger note is needed first).

Steps: <OUT>/steps.json  {label: {"stage": id, "endpoint": path, "body": {...}, "purpose": str, "target": url}}
Stages: <OUT>/stages.json {stage_id: {...open_stage keywords...}}
Outputs per step: <OUT>/captures/<nn>_<label>.raw.gz (the provider's answer as received, gzip, mtime 0) and
<nn>_<label>.json (request body sent, never the key; status, kind, request id, hashes, ledger ids, timings);
<OUT>/commands.csv (one row per step). A step's record is never overwritten.

usage:
  python -I observe190.py OUT_DIR open-stage STAGE_ID
  python -I observe190.py OUT_DIR probe LABEL [LABEL...]
  python -I observe190.py OUT_DIR close-stage STAGE_ID OUTCOME
"""

from __future__ import annotations

import asyncio
import csv
import gzip
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

KEY_FILE = r"<projects>\marianos-scraper\data\local\oxylabs.env"
TRIAL_DIR = r"<projects>\.shared-oxylabs-trial-20261103"
CAMPAIGN = "oxylabs-trial-20261103"
PROJECT = "marianos"
EXPECTED_FP = "<key fingerprint>"  # noted in the shared ledger 2026-11-06 (event 4630, note:credential_changed)
LEASE_TTL_S = 120.0
LEASE_RENEW_S = 30.0
PROXY_VARS = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy")


def trial(trial_dir: str = TRIAL_DIR) -> Any:
    sys.path.insert(0, trial_dir)
    import oxytrial_ledger as otl  # the shared ledger: stdlib only

    return otl


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class TrialGate:
    """The collector's AccountGate over the shared trial ledger (one lease for the process). ``inflight_cap``:
    a reservation that would put more than that many submissions of this lease in flight is refused (the
    ledger-backed worker cap; nothing is sent)."""

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


class StubLedger:
    """The collector client's own ledger, in memory for a standalone observation (the shared ledger is the
    authority here): same reserve/settle/release semantics as marianos_headless.acquisition.oxylabs.Ledger."""

    def __init__(self, rate: float) -> None:
        self.rate = rate
        self.rows: dict[str, dict[str, Any]] = {}

    def reserve(self, *, run_id: Any, segment_id: Any, purpose: str, endpoint: str, target: str, attempt: int) -> str:
        rid = uuid.uuid4().hex
        self.rows[rid] = {"purpose": purpose, "endpoint": endpoint, "attempt": attempt, "state": "reserved"}
        return rid

    def settle(self, row_id: str, *, status: int, kind: str | None, request_id: str | None) -> float:
        from marianos_headless.acquisition.oxylabs import CHARGED

        charged = CHARGED.get(kind)
        cost = self.rate if charged is not False else 0.0
        self.rows[row_id].update(state="settled", status=status, kind=kind, request_id=request_id,
                                 cost_usd=cost, cost_source="unknown" if charged is None else "rule")
        return cost

    def release(self, row_id: str, *, sent: bool, outcome: str) -> None:
        self.rows[row_id].update(state="settled" if sent else "released", outcome=outcome,
                                 cost_source="unknown" if sent else "rule")


def tree_revision() -> dict[str, Any]:
    import marianos_headless

    src = Path(marianos_headless.__file__).resolve().parents[1]
    def git(*a: str) -> str:
        return subprocess.run(["git", "-C", str(src), *a], capture_output=True, text=True).stdout.strip()
    return {"package_file": str(Path(marianos_headless.__file__)), "version": getattr(marianos_headless, "__version__", ""),
            "revision": git("rev-parse", "HEAD"), "modified": git("status", "--porcelain", "--untracked-files=no").splitlines()}


def load_json(p: Path) -> dict[str, Any]:
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}


def open_stage(out: Path, stage_id: str) -> int:
    otl = trial()
    spec = load_json(out / "stages.json")[stage_id]
    led = otl.open_ledger(TRIAL_DIR, CAMPAIGN)
    led.open_stage(**spec)
    print(json.dumps({"opened": stage_id, "committed_usd": led.summary()["committed_usd"]}))
    return 0


def close_stage(out: Path, stage_id: str, outcome: str) -> int:
    otl = trial()
    led = otl.open_ledger(TRIAL_DIR, CAMPAIGN)
    led.close_stage(stage_id, outcome)
    s = led.summary()
    print(json.dumps({"closed": stage_id, "committed_usd": s["committed_usd"], "marianos": s["projects"]["marianos"]}))
    return 0


def probe(
    out: Path,
    label: str,
    *,
    trial_dir: str = TRIAL_DIR,
    campaign: str = CAMPAIGN,
    key_file: str = KEY_FILE,
    expected_fp: str = EXPECTED_FP,
    transport: Any = None,
) -> int:
    from marianos_headless.acquisition import oxylabs
    from marianos_headless.core.settings import OxylabsSettings

    for v in PROXY_VARS:
        os.environ.pop(v, None)
    spec = load_json(out / "steps.json")[label]
    caps = out / "captures"
    caps.mkdir(parents=True, exist_ok=True)
    if list(caps.glob(f"*_{label}.json")):
        raise SystemExit(f"step {label} already has a record: a step is never repeated under the same label")
    n = len(list(caps.glob("*.json"))) + 1
    os.environ.pop(oxylabs.ENV_KEY, None)
    os.environ[oxylabs.ENV_KEY_FILE] = key_file
    key = oxylabs.load_key()
    if key is None:
        raise SystemExit("no key in the designated file")
    fp = oxylabs.fingerprint(key)
    if fp != expected_fp:
        raise SystemExit(f"key fingerprint {fp} is not the noted {expected_fp}: note the change in the ledger first")
    otl = trial(trial_dir)
    ledger = otl.open_ledger(trial_dir, campaign)
    lease = ledger.acquire_lease(PROJECT, f"observe190:{label}:{os.getpid()}", LEASE_TTL_S)
    stop = threading.Event()

    def renew() -> None:
        while not stop.wait(LEASE_RENEW_S):
            try:
                ledger.renew_lease(lease, LEASE_TTL_S)
            except Exception as exc:  # the gate refuses once the lease is gone
                print(json.dumps({"event": "TRIAL_LEASE_RENEW_FAILED", "message": str(exc)}), flush=True)
                return

    threading.Thread(target=renew, daemon=True).start()
    gate = TrialGate(otl, ledger, lease, spec["stage"], inflight_cap=1)
    settings = OxylabsSettings(max_attempts=1)
    stub = StubLedger(settings.usd_per_result)
    raw: list[bytes] = []

    async def go() -> Any:
        client = oxylabs.OxylabsClient(settings, key, stub, account_gate=gate, transport=transport)

        async def keep(response: Any) -> None:
            await response.aread()
            raw.append(response.content)

        client.http.event_hooks["response"] = [keep]
        try:
            return await client.fetch(spec["endpoint"], dict(spec["body"]), purpose=spec["purpose"],
                                      target=spec["target"])
        finally:
            await client.aclose()

    started = now()
    t0 = time.monotonic()
    error = ""
    answer = None
    try:
        answer = asyncio.run(go())
    except Exception as exc:  # recorded (a ceiling or gate refusal: nothing was sent)
        error = oxylabs.redact(f"{type(exc).__name__}: {exc}", key)[:500]
    finally:
        stop.set()
        try:
            ledger.release_lease(lease, f"observe190 step {label} ended")
        except Exception as exc:
            print(json.dumps({"event": "TRIAL_LEASE_RELEASE_FAILED", "message": str(exc)}), flush=True)
    secret = key.get_secret_value().encode()
    body = raw[0] if raw else b""
    if secret and secret in body:
        body = body.replace(secret, b"[REDACTED]")  # never kept; recorded below
    rawgz = caps / f"{n:02d}_{label}.raw.gz"
    if raw:
        rawgz.write_bytes(gzip.compress(body, mtime=0))
    rec = {
        "step": n,
        "label": label,
        "utc_start": started,
        "utc_end": now(),
        "seconds": round(time.monotonic() - t0, 2),
        "key_fingerprint": fp,
        "tree": tree_revision(),
        "stage": spec["stage"],
        "endpoint": spec["endpoint"],
        "body_sent": spec["body"],
        "purpose": spec["purpose"],
        "target": spec["target"],
        "error": error,
        "status": answer.status if answer else None,
        "kind": answer.kind if answer else None,
        "request_id": (answer.meta.get("request_id") if answer else None),
        "attempts": answer.attempts if answer else [],
        "html_chars": len(answer.html or "") if answer else 0,
        "raw_bytes": len(body),
        "raw_sha256": hashlib.sha256(body).hexdigest() if raw else None,
        "raw_file": rawgz.name if raw else None,
        "key_found_in_raw": bool(secret and raw and secret in raw[0]),
        "gate_events": gate.events,
        "gate_errors": [],
        "lease_id": lease.id,
    }
    (caps / f"{n:02d}_{label}.json").write_text(json.dumps(rec, indent=1, default=str) + "\n", encoding="utf-8")
    table = out / "commands.csv"
    new = not table.is_file()
    with table.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        if new:
            w.writerow(["step", "label", "utc_start", "utc_end", "seconds", "stage", "endpoint", "target", "status",
                        "kind", "request_id", "raw_sha256", "error"])
        w.writerow([n, label, rec["utc_start"], rec["utc_end"], rec["seconds"], rec["stage"], rec["endpoint"],
                    rec["target"], rec["status"], rec["kind"], rec["request_id"], rec["raw_sha256"], error])
    print(json.dumps({k: rec[k] for k in ("step", "label", "seconds", "status", "kind", "request_id", "html_chars",
                                          "raw_sha256", "error")}))
    return 0 if answer is not None else 2


if __name__ == "__main__":
    out_dir = Path(sys.argv[1])
    cmd = sys.argv[2]
    if cmd == "open-stage":
        sys.exit(open_stage(out_dir, sys.argv[3]))
    if cmd == "close-stage":
        sys.exit(close_stage(out_dir, sys.argv[3], sys.argv[4]))
    if cmd == "probe":
        # The stage's stop conditions: a refusal or quota answer stops at once; two unknown charges in a row stop.
        rc, unknown_run = 0, 0
        for lab in sys.argv[3:]:
            rc = probe(out_dir, lab)
            if rc:
                break
            rec = json.loads(next((out_dir / "captures").glob(f"*_{lab}.json")).read_text(encoding="utf-8"))
            if rec["kind"] in ("auth", "entitlement", "quota", "rate_limit"):
                print(json.dumps({"stop": f"{lab}: {rec['kind']} answer: the stage stops"}))
                rc = 3
                break
            unknown_run = unknown_run + 1 if rec["kind"] not in (None, "provider_failed_free") else 0
            if unknown_run >= 2:
                print(json.dumps({"stop": "two unknown charges in a row: the stage stops"}))
                rc = 4
                break
        sys.exit(rc)
    raise SystemExit(__doc__)
