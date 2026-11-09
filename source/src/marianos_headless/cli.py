"""``marianos-collector``: the headless collector's command line.

Every command writes structured logs (one JSON object per line) on standard output and ends with a
``RESULT`` line (``--pretty`` prints the result indented instead). The exit code says how it ended
(:class:`marianos_headless.operations.Exit`): 0 done, 2 configuration, 3 credentials, 4 credits, 5 site
refusal, 6 rejected, 7 store or source checks, 8 held, 9 busy, 75 interrupted (resumable), 1 unexpected.

A termination signal (SIGTERM from Azure at the job's timeout or a stop, or Ctrl+C) stops a collection at
once: the provider session is closed, the run's checkpoints are kept, the run is left ``interrupted`` with
the reason ``TERMINATED``, the store lock is released and the command exits with 75.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shlex
import signal
import sys
from collections.abc import Coroutine
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from marianos_headless import __version__, operations
from marianos_headless.acquisition.scrapfly import redact
from marianos_headless.collection.scrapfly_account import load_key
from marianos_headless.core import logs
from marianos_headless.core.paths import DERIVED_FROM
from marianos_headless.core.version import source_version
from marianos_headless.db import migrate
from marianos_headless.operations import CommandError, Context, Exit

ENV_CONFIG = "MARIANOS_COLLECTOR_CONFIG"
ENV_LOG_LEVEL = "MARIANOS_COLLECTOR_LOG_LEVEL"
ENV_ACTOR = "MARIANOS_COLLECTOR_ACTOR"
ENV_COMMAND = "MARIANOS_COLLECTOR_COMMAND"
LIMIT_FLAGS = {
    "max_products": "max_products_per_run",
    "max_pages_per_listing": "max_pages_per_listing",
    "max_credits": "max_credits_per_run",
    "max_minutes": "max_run_minutes",
    "max_term_reads": "max_product_term_reads",
}


# SIGTERM (Azure, systemd, docker stop), SIGINT (Ctrl+C) and, on Windows, SIGBREAK (Ctrl+Break: the signal
# another process can send to a console process group there).
STOP_SIGNALS = (signal.SIGTERM, signal.SIGINT, *([signal.SIGBREAK] if hasattr(signal, "SIGBREAK") else []))


class Terminated(Exception):
    pass


def run_async(coro: Coroutine[Any, Any, Exit]) -> Exit:
    """Run a collection; a termination signal cancels it (the pipeline then leaves the run resumable)."""
    loop = asyncio.new_event_loop()
    task = loop.create_task(coro)
    received: list[str] = []

    def on_signal(signum: int, _frame: Any) -> None:
        name = signal.Signals(signum).name
        received.append(name)
        logs.log("WARN", "SIGNAL_RECEIVED", signal=name)
        loop.call_soon_threadsafe(task.cancel)

    previous = {sig: signal.signal(sig, on_signal) for sig in STOP_SIGNALS}
    try:
        return loop.run_until_complete(task)
    except asyncio.CancelledError:
        raise Terminated(received[0] if received else "cancelled") from None
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()


def _categories(value: str) -> list[int]:
    try:
        return sorted({int(x) for x in value.split(",") if x.strip()})
    except ValueError:
        raise argparse.ArgumentTypeError("categories are CSV row numbers, e.g. 3,7") from None


def _safe(text: object) -> str:
    """An error message with any configured key value removed (never printed or logged)."""
    return redact(str(text), load_key())[:2000]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="marianos-collector", description=__doc__.split("\n\n")[0])
    p.add_argument("--version", action="version", version=f"marianos-azure-headless {__version__}")
    p.add_argument(
        "--config",
        type=Path,
        default=Path(os.environ.get(ENV_CONFIG, "config/collector.yaml")),
        help=f"collector configuration file (default: ${ENV_CONFIG} or config/collector.yaml)",
    )
    p.add_argument("--pretty", action="store_true", help="print the result indented")
    sub = p.add_subparsers(dest="command", required=True)

    v = sub.add_parser("validate-config", help="check the configuration files and the environment")
    v.add_argument(
        "--require-credentials", action="store_true", help="fail (3) without the configured provider's key"
    )
    v.add_argument("--check-db", action="store_true", help="also connect and check the schema revision")

    sub.add_parser("db-upgrade", help="create or upgrade the database schema")
    sub.add_parser("sync-config", help="load the stores and the category CSV into the database")

    r = sub.add_parser("run", help="collect a store (a new run)")
    r.add_argument("--store", required=True)
    r.add_argument(
        "--scheduled",
        action="store_true",
        help="a scheduled execution: act only when it is the store's due local occurrence",
    )
    r.add_argument("--categories", type=_categories, help="CSV row numbers (default: the configuration)")
    r.add_argument(
        "--subcategory",
        action="append",
        metavar="ROW:TAXONOMY_ID",
        help="narrow a category row to one listing of the site menu (repeatable), e.g. 1:06111",
    )
    for flag in LIMIT_FLAGS:
        r.add_argument("--" + flag.replace("_", "-"), dest=flag, type=int)

    for name, text in (
        ("resume", "continue an interrupted run from its checkpoints"),
        ("finalize", "check and export what an unfinished run collected (no provider request)"),
    ):
        c = sub.add_parser(name, help=text)
        c.add_argument("--run")
        c.add_argument("--store")

    s = sub.add_parser("stop", help="stop collecting; the run is finalized with what it collected")
    s.add_argument("--run")
    s.add_argument("--store")
    s.add_argument("--reason", default="stopped by an operator")

    pb = sub.add_parser("publish", help="publish a complete validated run")
    pb.add_argument("--run", required=True)
    pb.add_argument("--accept-warnings", metavar="REASON")

    rb = sub.add_parser(
        "rollback-publication", help="point the published dataset back at the publication it replaced"
    )
    rb.add_argument("--store", required=True)
    rb.add_argument("--reason", required=True)

    st = sub.add_parser("status", help="runs, holds, the published dataset and the provider ledger")
    st.add_argument("--store")
    st.add_argument("--run")
    st.add_argument("--limit", type=int, default=5)

    e = sub.add_parser("export", help="copy a run's verified export files to a folder")
    e.add_argument("--run")
    e.add_argument("--store", help="the store's published dataset (when --run is not given)")
    e.add_argument("--out", type=Path, required=True)

    ve = sub.add_parser("validate-export", help="the 22-field contract (and, for a run, the source check)")
    ve.add_argument("--file", type=Path)
    ve.add_argument("--run")

    sub.add_parser(
        "provider-balance",
        help="the configured provider's account: Scrapfly's balance (free read), or the Oxylabs ledger",
    )

    sc = sub.add_parser(
        "set-ceiling",
        help="the spending ceiling of a provider without a balance API (Oxylabs Web API), counted from now",
    )
    sc.add_argument("--provider", required=True, choices=["oxylabs"])
    sc.add_argument("--submissions", type=int, required=True)
    sc.add_argument("--usd", type=float, required=True)
    sc.add_argument("--reason", required=True)

    rh = sub.add_parser("release-hold", help="let a held store collect again")
    rh.add_argument("--store", required=True)
    rh.add_argument("--reason", required=True)

    rp = sub.add_parser(
        "reprocess",
        help="rebuild products an earlier run recorded, from what it stored, with the current rules "
        "(audited; nothing is requested from the site; the records keep their original date)",
    )
    rp.add_argument("--store", required=True)
    rp.add_argument("--source-run", required=True)
    rp.add_argument("--upcs-file", required=True, type=Path, help="one UPC per line")
    rp.add_argument("--reason", required=True)
    rp.add_argument("--dry-run", action="store_true", help="report what would change; write nothing")

    si = sub.add_parser("schedule-info", help="the store's schedule and the Azure cron expression (UTC)")
    si.add_argument("--store", required=True)

    sub.add_parser(
        "ops",
        help=f"run the command written in ${ENV_COMMAND} (the Azure operations job; default: status)",
    )
    return p


def _result(args: argparse.Namespace, data: Any, code: Exit) -> int:
    if args.pretty:
        print(json.dumps(data, indent=2, ensure_ascii=False, default=str))
    else:
        logs.log("INFO", "RESULT", command=args.command, exit_code=int(code), result=data)
    return int(code)


def _ctx(args: argparse.Namespace) -> Context:
    return Context(args.config)


def dispatch(args: argparse.Namespace) -> int:
    actor = os.environ.get(ENV_ACTOR) or "operator"
    cmd = args.command
    if cmd == "ops":
        command = shlex.split(os.environ.get(ENV_COMMAND) or "status")
        if not command or command[0] == "ops":
            raise CommandError(Exit.CONFIG, f"{ENV_COMMAND} must name another command")
        logs.log("INFO", "OPS_COMMAND", command=command)
        return main(["--config", str(args.config), *(["--pretty"] if args.pretty else []), *command])
    if cmd == "validate-config":
        ctx = _ctx(args)
        try:
            data = operations.describe_config(ctx)
            code = Exit.OK
            env = data["environment"]
            key = env["oxylabs_key"] if env["provider"] == "oxylabs" else env["scrapfly_key"]
            if args.require_credentials and not key["configured"]:
                code = Exit.CREDENTIALS
            if args.check_db:
                current, head = migrate.state(ctx.engine)
                data["database"] = {"revision": current, "head": head, "current": current == head}
                if current != head:
                    code = Exit.CONFIG
            data["code"] = {"version": __version__, "derived_from": DERIVED_FROM, **source_version()}
            return _result(args, data, code)
        finally:
            ctx.close()
    if cmd == "schedule-info":
        ctx = _ctx(args)
        data = next(s for s in operations.describe_config(ctx)["stores"] if s["key"] == args.store)
        return _result(args, {"store": args.store, "schedule": data["schedule"]}, Exit.OK)
    if cmd == "validate-export" and args.run is None:
        code, data = operations.validate_export(None, args.file, None)
        return _result(args, data, code)

    ctx = _ctx(args)
    try:
        if cmd == "db-upgrade":
            before, after = migrate.upgrade(ctx.engine)
            return _result(args, {"before": before, "after": after}, Exit.OK)
        ctx.require_schema()
        if cmd == "sync-config":
            return _result(args, operations.sync_config(ctx, actor), Exit.OK)
        if cmd == "run":
            overrides: dict[str, Any] = {
                # "is not None": 0 is a value (``--max-term-reads 0``: no product page read for terms).
                LIMIT_FLAGS[k]: getattr(args, k)
                for k in LIMIT_FLAGS
                if getattr(args, k) is not None
            }
            if args.categories:
                overrides["categories"] = args.categories
            if args.subcategory:
                chosen: dict[str, list[str]] = {}
                for item in args.subcategory:
                    row, sep, tax = item.partition(":")
                    if not sep or not row.strip().isdigit() or not tax.strip():
                        raise CommandError(Exit.CONFIG, f"--subcategory takes ROW:TAXONOMY_ID, not {item!r}")
                    chosen.setdefault(row.strip(), []).append(tax.strip())
                overrides["subcategories"] = chosen
            if args.scheduled:
                if overrides:
                    raise CommandError(
                        Exit.CONFIG, "a scheduled run takes its settings from the configuration"
                    )
                code = run_async(operations.scheduled_run(ctx, args.store))
            else:
                code = run_async(operations.start_run(ctx, args.store, overrides, actor))
            return _result(args, {"store": args.store}, code)
        if cmd == "resume":
            return _result(args, {}, run_async(operations.resume_run(ctx, args.run, args.store)))
        if cmd == "finalize":
            return _result(args, {}, run_async(operations.finalize_run(ctx, args.run, args.store)))
        if cmd == "stop":
            return _result(args, operations.stop_run(ctx, args.run, args.store, args.reason, actor), Exit.OK)
        if cmd == "publish":
            return _result(args, operations.publish(ctx, args.run, args.accept_warnings, actor), Exit.OK)
        if cmd == "rollback-publication":
            return _result(args, operations.rollback(ctx, args.store, args.reason, actor), Exit.OK)
        if cmd == "status":
            return _result(args, operations.status(ctx, args.store, args.run, args.limit), Exit.OK)
        if cmd == "export":
            return _result(args, operations.export(ctx, args.run, args.store, args.out), Exit.OK)
        if cmd == "validate-export":
            code, data = operations.validate_export(ctx, args.file, args.run)
            return _result(args, data, code)
        if cmd == "provider-balance":
            code, data = operations.provider_balance(ctx, actor)
            return _result(args, data, code)
        if cmd == "set-ceiling":
            data = operations.set_ceiling(ctx, args.provider, args.submissions, args.usd, args.reason, actor)
            return _result(args, data, Exit.OK)
        if cmd == "release-hold":
            return _result(args, operations.release_hold(ctx, args.store, args.reason, actor), Exit.OK)
        if cmd == "reprocess":
            data = operations.reprocess_products(
                ctx, args.store, args.source_run, args.upcs_file, args.reason, actor, dry_run=args.dry_run
            )
            return _result(args, data, Exit.OK)
        raise CommandError(Exit.CONFIG, f"unknown command {cmd}")
    finally:
        ctx.close()


def main(argv: list[str] | None = None) -> int:
    logs.configure(level=os.environ.get(ENV_LOG_LEVEL, "INFO"))
    args = build_parser().parse_args(argv)
    try:
        return dispatch(args)
    except CommandError as exc:
        logs.log(
            "ERROR",
            "COMMAND_REFUSED",
            command=args.command,
            exit_code=int(exc.code),
            message=_safe(exc),
            **exc.data,
        )
        return int(exc.code)
    except Terminated as exc:
        logs.log("WARN", "TERMINATED", command=args.command, signal=str(exc), exit_code=int(Exit.INTERRUPTED))
        return int(Exit.INTERRUPTED)
    except (ValidationError, FileNotFoundError, KeyError, ValueError) as exc:
        logs.log(
            "ERROR", "CONFIG_INVALID", command=args.command, exit_code=int(Exit.CONFIG), message=_safe(exc)
        )
        return int(Exit.CONFIG)
    except RuntimeError as exc:
        if "DATABASE_URL" in str(exc):
            logs.log(
                "ERROR",
                "CONFIG_INVALID",
                command=args.command,
                exit_code=int(Exit.CONFIG),
                message=_safe(exc),
            )
            return int(Exit.CONFIG)
        logs.log("ERROR", "UNEXPECTED", command=args.command, error=type(exc).__name__, message=_safe(exc))
        return int(Exit.UNEXPECTED)
    except Exception as exc:
        logs.log("ERROR", "UNEXPECTED", command=args.command, error=type(exc).__name__, message=_safe(exc))
        return int(Exit.UNEXPECTED)


def entrypoint() -> None:
    sys.exit(main())


if __name__ == "__main__":
    entrypoint()
