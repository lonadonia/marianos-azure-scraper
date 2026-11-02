"""``classic-probe``: the offline probe's command line (README.md has the commands and what each touches).

No command here makes a provider request. ``live`` lists what a future approved campaign still lacks and
refuses: this build's live mode is disabled, and it reads no credential.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from classic_probe import __version__, campaign, contract, gates, ledger, marianos, money, targets
from classic_probe.transport import ProviderResponse, ReplayTransport

EXIT_OK, EXIT_USAGE, EXIT_LIVE_REFUSED, EXIT_STOPPED, EXIT_EXPORT = 0, 2, 3, 4, 5


def _print(data: Any) -> None:
    print(json.dumps(data, indent=1, sort_keys=True, default=str))


def _read_json(path: Path | None) -> Any:
    if path is None or not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def cmd_plan(args: argparse.Namespace) -> int:
    campaign_id, tgts = targets.load(args.targets)
    rates = _read_json(args.rates)
    card = None
    rate_problem = "no rate card given: a live campaign would be refused"
    if rates is not None:
        try:
            card = money.RateCard.load(rates)
            rate_problem = ""
        except money.UnknownRate as exc:
            rate_problem = str(exc)
    rows = []
    for retailer, plan in _steps(tgts):
        row: dict[str, Any] = {
            "retailer": retailer,
            "step": plan.step,
            "purpose": plan.purpose,
            "endpoint": contract.ENDPOINT + (f"?{plan.query_string}" if plan.query_string else ""),
            "payload": dict(plan.payload),
            "max_billable_results": plan.max_results,
        }
        if card is not None:
            try:
                row["reserved_upper_bound_usd"] = str(card.worst_case(plan.request_class, plan.max_results))
            except money.UnknownRate as exc:
                row["reserved_upper_bound_usd"] = f"unknown: {exc}"
        rows.append(row)
    limits = ledger.Limits()
    _print(
        {
            "campaign_id": campaign_id,
            "mode": "plan (nothing is sent, nothing is written)",
            "limits": json.loads(limits.as_json()),
            "retailer_share_usd": str(limits.retailer_share_usd()),
            "rates": rate_problem or "confirmed rate card given",
            "steps": rows,
            "not_planned": marianos.NOT_PLANNED,
            "targets": {n: t.live_problems() or ["ready to plan"] for n, t in tgts.items()},
        }
    )
    return EXIT_OK


def _steps(tgts: dict[str, targets.Target]) -> list[tuple[str, campaign.StepPlan]]:
    """Each retailer's planned steps, for the adapters this build has."""
    out = [("walmart", p) for p in campaign.planned_steps(tgts["walmart"])]
    if tgts["marianos"].adapter == "marianos":
        out += [("marianos", p) for p in marianos.planned_steps(tgts["marianos"])]
    return out


def cmd_validate(args: argparse.Namespace) -> int:
    campaign_id, tgts = targets.load(args.targets)
    for _, plan in _steps(tgts):
        contract.assert_documented(plan.payload)
    out: dict[str, Any] = {"targets": "ok", "campaign_id": campaign_id, "documented_payloads": "ok"}
    if args.rates:
        try:
            money.RateCard.load(_read_json(args.rates) or {})
            out["rates"] = "ok"
        except money.UnknownRate as exc:
            out["rates"] = f"refused: {exc}"
    out["targets_detail"] = {n: t.live_problems() or ["ready to plan"] for n, t in tgts.items()}
    _print(out)
    return EXIT_OK


def cmd_campaign_init(args: argparse.Namespace) -> int:
    led = ledger.Ledger.create(args.ledger, args.campaign_id, ledger.Limits(), offline=args.offline)
    try:
        ledger.write_manifest(args.manifest, led)
        _print(
            {
                "campaign_id": led.campaign_id,
                "ledger_genesis_id": led.genesis_id,
                "manifest": str(args.manifest),
                "offline": led.offline,
            }
        )
    finally:
        led.close()
    return EXIT_OK


def cmd_status(args: argparse.Namespace) -> int:
    led = ledger.open_from_manifest(args.manifest)
    try:
        _print(
            {
                "campaign_id": led.campaign_id,
                "stopped": led.stopped(),
                "totals": led.totals().as_dict(),
                "dispatches": led.rows(),
            }
        )
    finally:
        led.close()
    return EXIT_OK


def cmd_confirm_charge(args: argparse.Namespace) -> int:
    led = ledger.open_from_manifest(args.manifest)
    try:
        led.confirm_charge(args.seq, args.value, args.unit, args.basis)
        _print(led.totals().as_dict())
    finally:
        led.close()
    return EXIT_OK


def cmd_export(args: argparse.Namespace) -> int:
    led = ledger.open_from_manifest(args.manifest)
    try:
        args.out.mkdir(parents=True, exist_ok=True)
        campaign.write_json(
            args.out / "ledger_export.json",
            {
                "campaign_id": led.campaign_id,
                "ledger_genesis_id": led.genesis_id,
                "offline": led.offline,
                "totals": led.totals().as_dict(),
                "dispatches": led.rows(),
                "events": led.events(),
                "stopped": led.stopped(),
            },
        )
    finally:
        led.close()
    _print({"exported": str(args.out / "ledger_export.json")})
    return EXIT_OK


def load_replay(fixtures: Path) -> ReplayTransport:
    """``replay.json`` maps each step to its saved responses: ``{"step": [{"http_status": 200, "body_file":
    "x.json"}]}``."""
    spec = json.loads((fixtures / "replay.json").read_text(encoding="utf-8"))
    responses = {
        step: [
            ProviderResponse(
                int(r["http_status"]),
                (fixtures / r["body_file"]).read_bytes()
                if r.get("body_file")
                else str(r.get("body", "")).encode("utf-8"),
            )
            for r in rows
        ]
        for step, rows in spec["steps"].items()
    }
    return ReplayTransport(responses)


def cmd_replay(args: argparse.Namespace) -> int:
    """The campaign against saved responses, with a new isolated offline ledger in ``--out``."""
    _, tgts = targets.load(args.targets)
    card = money.RateCard.load(_read_json(args.rates) or {})
    args.out.mkdir(parents=True, exist_ok=True)
    led = ledger.Ledger.create(args.out / "ledger.sqlite3", "offline-replay", ledger.Limits(), offline=True)
    transport = load_replay(args.fixtures)
    kind = marianos.MarianosCampaign if args.retailer == "marianos" else campaign.Campaign
    run = kind(led, transport, tgts[args.retailer], card, out_dir=args.out)
    result = run.run()
    run.close()
    _print({"OFFLINE REPLAY": True, "dispatched": len(transport.dispatched), **result.as_dict()})
    if result.export_errors:
        return EXIT_EXPORT
    return EXIT_STOPPED if result.stop else EXIT_OK


def cmd_live(args: argparse.Namespace) -> int:
    """What a future approved campaign still lacks. Refused in this build, before any credential is read."""
    led = ledger.open_from_manifest(args.manifest)
    try:
        missing = gates.evaluate(
            led,
            approval=_read_json(args.approval),
            entitlement=_read_json(args.entitlement),
            rates=_read_json(args.rates),
            credentials=False,
            retailer=args.retailer,
        )
    finally:
        led.close()
    missing = [
        "live mode is disabled in this build (a later, separately approved version may enable it)",
        "credentials: not checked while live mode is disabled",
        *missing,
    ]
    _print({"live": "refused", "nothing was sent": True, "missing": missing})
    return EXIT_LIVE_REFUSED


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="classic-probe",
        description="Offline probe of the Oxylabs Classic Web Scraper API (Realtime). No command sends a "
        "request.",
    )
    p.add_argument("--version", action="version", version=f"classic-probe {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("plan", help="the request plan and payload matrix (writes nothing)")
    c.add_argument("--targets", type=Path, required=True)
    c.add_argument("--rates", type=Path)
    c.set_defaults(func=cmd_plan)
    c = sub.add_parser("validate", help="check the targets, the payloads and a rate card")
    c.add_argument("--targets", type=Path, required=True)
    c.add_argument("--rates", type=Path)
    c.set_defaults(func=cmd_validate)
    c = sub.add_parser("campaign-init", help="create the campaign's one ledger and its manifest")
    c.add_argument("--manifest", type=Path, required=True)
    c.add_argument("--ledger", type=Path, required=True)
    c.add_argument("--campaign-id", required=True)
    c.add_argument(
        "--offline", action="store_true", help="a test ledger: it never authorizes a provider request"
    )
    c.set_defaults(func=cmd_campaign_init)
    c = sub.add_parser("status", help="the ledger's counters, reservations and stops")
    c.add_argument("--manifest", type=Path, required=True)
    c.set_defaults(func=cmd_status)
    c = sub.add_parser("confirm-charge", help="record a charge read from the account, with its basis")
    c.add_argument("--manifest", type=Path, required=True)
    c.add_argument("--seq", type=int, required=True)
    c.add_argument("--value", required=True)
    c.add_argument("--unit", required=True)
    c.add_argument("--basis", required=True)
    c.set_defaults(func=cmd_confirm_charge)
    c = sub.add_parser("export", help="write the ledger's history")
    c.add_argument("--manifest", type=Path, required=True)
    c.add_argument("--out", type=Path, required=True)
    c.set_defaults(func=cmd_export)
    c = sub.add_parser("replay", help="one retailer's steps against saved responses (OFFLINE)")
    c.add_argument("--retailer", choices=("walmart", "marianos"), default="walmart")
    c.add_argument("--targets", type=Path, required=True)
    c.add_argument("--fixtures", type=Path, required=True)
    c.add_argument("--rates", type=Path, required=True)
    c.add_argument("--out", type=Path, required=True)
    c.set_defaults(func=cmd_replay)
    c = sub.add_parser("live", help="list what a live campaign lacks; refused in this build")
    c.add_argument("--manifest", type=Path, required=True)
    c.add_argument("--approval", type=Path)
    c.add_argument("--entitlement", type=Path)
    c.add_argument("--rates", type=Path)
    c.add_argument("--retailer", default="walmart")
    c.set_defaults(func=cmd_live)
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        code: int = args.func(args)
    except (
        targets.TargetRefused,
        contract.RequestRefused,
        ledger.LedgerRefused,
        money.UnknownRate,
        ValueError,
    ) as exc:
        print(json.dumps({"refused": f"{type(exc).__name__}: {exc}"}), file=sys.stderr)
        return EXIT_USAGE
    return code


def entrypoint() -> None:
    sys.exit(main())
