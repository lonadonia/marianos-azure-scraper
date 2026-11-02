"""Persisted budget of the 1.8.0 task, reservation before dispatch (C:/m6/plan/TEST_PLAN_180.md).

    python -I budget180.py status
    python -I budget180.py reserve <mode> <stage> <usd> [--credits N] [--requests N] [--note TEXT]
    python -I budget180.py settle <id> <usd> [--credits N] [--requests N] [--outcome TEXT]

Append-only JSONL. The earlier ledgers are read, never written: a new brief or release resets nothing. An open
reservation counts at its estimate. Units are never added across providers.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import secrets
import sys
from pathlib import Path

LEDGER = Path("C:/m6/ledger/budget180.jsonl")
EARLIER = [Path("C:/m5/ev160/ledger/budget160.jsonl"), Path("C:/m5/ev170/ledger/budget170.jsonl")]
OX_EARLIER_MODES = {"B", "C", "D", "OXM", "OXR", "LEAD", "FINAL", "MARGIN"}

STAGES: dict[tuple[str, str], dict[str, float]] = {
    ("OXP", "L"): {"usd": 0.036, "requests": 24},  # TEST_PLAN_180 sections 2 and 6
    ("OXQ", "Q"): {"usd": 0.30, "requests": 200},  # section 3: the frozen candidate at Vernon Hills
    ("OXP", "D"): {"usd": 0.036, "requests": 24},  # Amendment 8: department census (full-scope estimate)
    ("SF", "S"): {"credits": 120, "requests": 1},  # section 3: one browser session, with a stated reason
    ("KR", "K"): {"requests": 6},  # certification host: a lead, never production data
}
OXYLABS_MODES = {"OXP", "OXQ"}
SHARED_OXYLABS_USD = 1.00
SCRAPFLY_CUMULATIVE = 300


def now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def entries(path: Path = LEDGER) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def positions(path: Path = LEDGER) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for e in entries(path):
        if e["kind"] == "reserve":
            out[e["id"]] = {**e, "settled": None}
        elif e["kind"] == "settle" and e["id"] in out:
            out[e["id"]]["settled"] = e
    return out


def amount(p: dict, unit: str) -> float:
    s = p["settled"]
    return float((s if s is not None else p).get(unit, 0) or 0)


def earlier() -> dict[str, float]:
    ox = sf = 0.0
    for path in EARLIER:
        for p in positions(path).values():
            if p["mode"] in OX_EARLIER_MODES:
                ox += amount(p, "usd")
            if p["mode"] == "A":
                sf += amount(p, "credits")
    return {"oxylabs_usd": ox, "scrapfly_credits": sf}


def used(pred) -> dict[str, float]:
    ps = [p for p in positions().values() if pred(p)]
    return {u: sum(amount(p, u) for p in ps) for u in ("usd", "credits", "requests")}


def append(rec: dict) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def reserve(mode: str, stage: str, usd: float = 0.0, *, credits: float = 0, requests: int = 1, note: str = "") -> str:
    key = (mode, stage)
    ceil = STAGES.get(key)
    if ceil is None:
        raise SystemExit(f"REFUSED: no ceiling for {key}")
    want = {"usd": usd, "credits": credits, "requests": requests}
    u = used(lambda p: p["mode"] == mode and p["stage"] == stage)
    for unit, limit in ceil.items():
        if u[unit] + want[unit] > limit + 1e-12:
            raise SystemExit(f"REFUSED: {key} {unit} {u[unit]} + {want[unit]} > {limit}")
    prior = earlier()
    if mode in OXYLABS_MODES:
        t = used(lambda p: p["mode"] in OXYLABS_MODES)["usd"] + prior["oxylabs_usd"]
        if t + usd > SHARED_OXYLABS_USD + 1e-12:
            raise SystemExit(f"REFUSED: cumulative Oxylabs USD {t:.4f} + {usd} > {SHARED_OXYLABS_USD}")
    if mode == "SF":
        t = used(lambda p: p["mode"] == "SF")["credits"] + prior["scrapfly_credits"]
        if t + credits > SCRAPFLY_CUMULATIVE + 1e-12:
            raise SystemExit(f"REFUSED: cumulative Scrapfly credits {t:g} + {credits:g} > {SCRAPFLY_CUMULATIVE}")
    rid = f"{mode}-{stage}-{secrets.token_hex(3)}"
    append({"kind": "reserve", "id": rid, "ts": now(), "mode": mode, "stage": stage, **want, "note": note})
    return rid


def settle(rid: str, usd: float, *, credits: float = 0, requests: int = 1, outcome: str = "") -> None:
    if rid not in positions():
        raise SystemExit(f"unknown reservation {rid}")
    append({"kind": "settle", "id": rid, "ts": now(), "usd": usd, "credits": credits, "requests": requests,
            "outcome": outcome})


def status() -> None:
    for key, ceil in STAGES.items():
        t = used(lambda p, k=key: p["mode"] == k[0] and p["stage"] == k[1])
        print(f"{key[0]:4} {key[1]:2} usd={t['usd']:.4f} credits={t['credits']:g} requests={int(t['requests'])} | {ceil}")
    prior = earlier()
    ox = used(lambda p: p["mode"] in OXYLABS_MODES)["usd"]
    sf = used(lambda p: p["mode"] == "SF")["credits"]
    print(f"Oxylabs cumulative: earlier {prior['oxylabs_usd']:.4f} + 1.8.0 {ox:.4f} of {SHARED_OXYLABS_USD}; "
          f"left {SHARED_OXYLABS_USD - prior['oxylabs_usd'] - ox:.4f}")
    print(f"Scrapfly cumulative: earlier {prior['scrapfly_credits']:g} + 1.8.0 {sf:g} of {SCRAPFLY_CUMULATIVE}; "
          f"left {SCRAPFLY_CUMULATIVE - prior['scrapfly_credits'] - sf:g}")
    print("open reservations:", [p["id"] for p in positions().values() if p["settled"] is None] or "none")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    r = sub.add_parser("reserve")
    r.add_argument("mode"), r.add_argument("stage"), r.add_argument("usd", type=float)
    r.add_argument("--credits", type=float, default=0), r.add_argument("--requests", type=int, default=1)
    r.add_argument("--note", default="")
    s = sub.add_parser("settle")
    s.add_argument("id"), s.add_argument("usd", type=float)
    s.add_argument("--credits", type=float, default=0), s.add_argument("--requests", type=int, default=1)
    s.add_argument("--outcome", default="")
    a = ap.parse_args()
    if a.cmd == "status":
        status()
    elif a.cmd == "reserve":
        print(reserve(a.mode, a.stage, a.usd, credits=a.credits, requests=a.requests, note=a.note))
    else:
        settle(a.id, a.usd, credits=a.credits, requests=a.requests, outcome=a.outcome)
    sys.exit(0)
