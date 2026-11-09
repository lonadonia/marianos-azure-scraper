"""The outer bound of a whole session (1.7.0, finding C2; corrected in 1.7.1 and 1.7.2).

A request's worker is killed and reaped at the request's own deadline (transport.py). This module bounds the
rest: a campaign session runs in its own process, and the supervisor kills it, with every process it started,
reaps it, and then recovers in its own process. Rows the session left reserved or sent are kept as unknown
(``Ledger.recover``: their reservations stay held), capture files are indexed or removed
(``CaptureStore.recover``), and an evidence manifest marked incomplete is written from the durable index.

1.7.1 (the client's review of 1.7.0, finding C2): in 1.7.0 the recovery ran after the session's end with no
bound of its own: a ledger lock held elsewhere kept it waiting 30 s and then raised, and a killed session that
could not be reaped raised out of the supervisor with nothing recovered. Now the supervisor's whole run ends
by the session's hard end:

- the session's command runs until the hard end less a reserve kept for the recovery
  (:func:`classic_probe.deadline.recovery_reserve`: a third of a short session, 30 s at most);
- its kill and its reap are each bounded by the time left. A process that has not gone when its reap's time
  runs out is recorded (``reaped``: False), and the recovery still runs;
- the recovery runs in its own process, which the supervisor kills if it is still running at the hard end.
  Inside it, every wait for the ledger's lock is bounded by the same end (``Ledger.bind_time_left``), so a
  lock held elsewhere ends the recovery's ledger writes, not the recovery: it writes the manifest of what it
  found and says what it could not do (``completed``: False, and why). A row it could not mark stays as the
  session left it, its money held, for the next recovery to mark. Nothing is assumed.

1.7.2 (the client's review of 1.7.1, finding C2). On Linux the 1.7.1 supervisor waited 1.10 s for a FIFO put
at the evidence path, despite a hard end of 0.30 s: it opened the path as a file, and opening a FIFO waits for
a writer. It accepted the complete evidence manifest a previous run had left in the same folder when a new
command exited 0 without writing any (its only test was the file's age). A process the session left behind
kept running after a session that exited by itself, and the recovery's bound was passed on the wall clock.
Now:

- one monotonic deadline bounds everything the supervisor does: the command, the end of its process tree,
  the reading of its evidence and the recovery, which is given the same monotonic end (``--until-monotonic``;
  Python's monotonic clock is system-wide). :func:`run_session` returns within the hard end plus
  :data:`TOLERANCE_S`, whatever the session did;
- the session's process tree is ended whenever the session ends, by itself or by its kill (proctree.py: a
  process group on Linux and macOS, a job object on Windows), so no process it started can send anything
  once the supervisor has returned; the session's output goes to a temporary file, not a pipe that a
  left-behind process could hold open;
- the session's evidence is read only if it is a regular file (never a FIFO, a device, a directory or a
  link), no larger than :data:`MAX_EVIDENCE_BYTES`, opened without blocking and read within the time left;
  and it is accepted only if it names this campaign, this ledger and this execution: each run gets a new
  ``execution_id`` in the session's environment (:data:`classic_probe.campaign.EXECUTION_ENV`), which the
  campaign writes into its evidence. An earlier run's manifest, however recent, is not this run's: the run
  is recovered, and the earlier file is left as it was.

The supervisor is the bound for a future approved live session. This build's live mode stays disabled: the
tests run it against a stub on 127.0.0.1 only.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Any

from classic_probe import ledger as ledger_mod
from classic_probe.campaign import EXECUTION_ENV, write_json
from classic_probe.captures import CaptureStore
from classic_probe.deadline import recovery_reserve
from classic_probe.proctree import ProcessTree

REAP_TIMEOUT_S = 10.0  # the longest a kill or a reap is waited for, when the session has that much time left
MIN_STEP_S = 0.05  # the shortest wait given to a kill or a reap
RECOVERY_MARGIN_S = 0.5  # the recovery's own end comes this long before the supervisor's end
RECOVERY_KILL_S = 0.25  # within that margin: the time to kill and reap a recovery that did not end by itself
FINAL_WRITE_S = 0.25  # the part of the recovery's time its ledger writes leave for writing the manifest
# 1.7.2 (C2): run_session returns within its hard end plus this. Past the end only the last kill and reap of
# the session's tree (MIN_STEP_S each at most) can run.
TOLERANCE_S = 0.5
MAX_EVIDENCE_BYTES = 16 * 1024 * 1024  # an evidence manifest holds no bodies: a few hundred KB at most
MAX_MANIFEST_BYTES = 64 * 1024  # the campaign manifest: four short fields
READ_CHUNK = 1 << 20
MIN_PARSE_S = 0.05  # a manifest is parsed only while this much time, plus its reading time, is left
PARSE_BYTES_PER_S = 20_000_000  # a conservative rate for that reading time
TAIL_BYTES = 16_000
EVIDENCE = "campaign_evidence.json"
RECOVERED = "campaign_evidence.recovered.json"


@dataclass
class SupervisedSession:
    returncode: int | None
    killed: bool
    elapsed_s: float
    stdout_tail: str = ""
    recovery: dict[str, Any] = field(default_factory=dict)
    reaped: bool = True  # 1.7.1: False when the killed session had not gone when its reap's time ran out
    recovery_reserve_s: float = 0.0
    problems: list[str] = field(default_factory=list)
    execution_id: str = (
        ""  # 1.7.2: this run's own identity, given to the session and expected in its evidence
    )
    evidence: dict[str, Any] = field(default_factory=dict)  # 1.7.2: whether its evidence was taken, and why
    tree: dict[str, Any] = field(default_factory=dict)  # 1.7.2: how the session's process tree was ended


class EvidenceRefused(ValueError):
    """A file the supervisor will not take as a session's evidence, with why."""


def _step(left: float) -> float:
    """How long a kill or a reap may take: a quarter of what is left, between MIN_STEP_S and
    REAP_TIMEOUT_S."""
    return max(MIN_STEP_S, min(REAP_TIMEOUT_S, left / 4))


def _kind(mode: int) -> str:
    for test, name in (
        (stat.S_ISFIFO, "a FIFO"),
        (stat.S_ISDIR, "a directory"),
        (stat.S_ISLNK, "a link"),
        (stat.S_ISSOCK, "a socket"),
        (stat.S_ISCHR, "a character device"),
        (stat.S_ISBLK, "a block device"),
    ):
        if test(mode):
            return name
    return "not a regular file"


def read_bounded(path: Path, *, max_bytes: int, left: Callable[[], float]) -> bytes:
    """A regular file's bytes, read without blocking and while ``left()`` is above 0 (1.7.2, C2). Raises
    :class:`EvidenceRefused`, saying why, for anything else: a missing path, a FIFO, a device, a directory, a
    link, a file above ``max_bytes`` or one replaced while it was opened."""
    try:
        before = os.lstat(path)
    except FileNotFoundError:
        raise EvidenceRefused("it does not exist") from None
    except OSError as exc:
        raise EvidenceRefused(f"it cannot be examined ({type(exc).__name__})") from None
    if not stat.S_ISREG(before.st_mode):
        raise EvidenceRefused(f"it is {_kind(before.st_mode)}, not a regular file")
    if before.st_size > max_bytes:
        raise EvidenceRefused(f"it holds {before.st_size} bytes, more than the {max_bytes} allowed")
    flags = (
        os.O_RDONLY
        | getattr(os, "O_NONBLOCK", 0)  # opening a FIFO swapped in now cannot wait for a writer
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_BINARY", 0)
    )
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise EvidenceRefused(f"it cannot be opened ({type(exc).__name__})") from None
    try:
        opened = os.fstat(fd)
        same = (opened.st_dev, opened.st_ino) == (before.st_dev, before.st_ino) or not (
            opened.st_ino and before.st_ino
        )
        if not stat.S_ISREG(opened.st_mode) or not same:
            raise EvidenceRefused("it was replaced while it was opened")
        chunks: list[bytes] = []
        total = 0
        while True:
            if left() <= 0:
                raise EvidenceRefused("the session's time ran out while it was read")
            chunk = os.read(fd, min(READ_CHUNK, max_bytes + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > max_bytes:
                raise EvidenceRefused(f"it grew past the {max_bytes} bytes allowed while it was read")
        return b"".join(chunks)
    finally:
        os.close(fd)


def _json_bounded(path: Path, *, max_bytes: int, left: Callable[[], float]) -> dict[str, Any]:
    raw = read_bounded(path, max_bytes=max_bytes, left=left)
    if left() < MIN_PARSE_S + len(raw) / PARSE_BYTES_PER_S:
        raise EvidenceRefused(f"no time was left to read its {len(raw)} bytes")
    try:
        data = json.loads(raw)
    except ValueError:
        raise EvidenceRefused("it is not JSON") from None
    if not isinstance(data, dict):
        raise EvidenceRefused("it is not a JSON object")
    return data


def evidence_of_this_execution(
    out_dir: Path, manifest: Path, execution_id: str, left: Callable[[], float]
) -> tuple[bool, str]:
    """Whether the session left a complete evidence manifest of its own (1.7.2, C2), and why or why not: a
    regular file, of bounded size, read without blocking within the time left, naming this campaign, this
    ledger and this execution, and marked complete."""
    try:
        ids = _json_bounded(manifest, max_bytes=MAX_MANIFEST_BYTES, left=left)
    except EvidenceRefused as exc:
        return False, f"the campaign manifest {manifest.name} could not be read: {exc}"
    try:
        data = _json_bounded(out_dir / EVIDENCE, max_bytes=MAX_EVIDENCE_BYTES, left=left)
    except EvidenceRefused as exc:
        return False, f"{EVIDENCE}: {exc}"
    named = data.get("execution_id")
    if named != execution_id:
        shown = repr(named)[:80]
        return False, f"{EVIDENCE} was not written by this execution (it names execution {shown})"
    for key in ("campaign_id", "ledger_genesis_id"):
        if data.get(key) != ids.get(key):
            return False, f"{EVIDENCE} names another {key} than the campaign manifest"
    if data.get("complete") is not True:
        return False, f"{EVIDENCE} is not marked complete"
    return True, f"{EVIDENCE} is this execution's own and complete"


def _tail(log: IO[bytes]) -> str:
    log.seek(0, os.SEEK_END)
    size = log.tell()
    log.seek(max(0, size - TAIL_BYTES))
    return log.read().decode("utf-8", "replace")[-4000:]


def run_session(
    command: Sequence[str],
    *,
    hard_end_s: float,
    manifest: Path,
    out_dir: Path,
    retailer: str,
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
    recovery_reserve_s: float | None = None,
) -> SupervisedSession:
    """Run one session's command so that all of it, the end of its process tree, the reading of its
    evidence and its recovery included, ends ``hard_end_s`` seconds after it starts, within
    :data:`TOLERANCE_S` (1.7.1 and 1.7.2, C2). The command has the hard end less the recovery's reserve.

    A recovery runs when the session was killed, ended with an error, or left no complete evidence manifest of
    its own (this execution's)."""
    t0 = time.monotonic()
    end = t0 + max(0.0, hard_end_s)
    reserve = (
        recovery_reserve(hard_end_s)
        if recovery_reserve_s is None
        else max(0.0, min(recovery_reserve_s, hard_end_s))
    )
    command_end = t0 + max(0.0, hard_end_s - reserve)

    def left() -> float:
        return end - time.monotonic()

    execution_id = uuid.uuid4().hex
    session_env = dict(os.environ if env is None else env)
    session_env[EXECUTION_ENV] = execution_id
    problems: list[str] = []
    with tempfile.TemporaryFile() as log:
        tree = ProcessTree.start(command, cwd=cwd, env=session_env, stdout=log)
        try:
            returncode = tree.wait(command_end - time.monotonic())
            killed = returncode is None
            ended = tree.end(_step(left()))
        finally:
            tree.close()
        if killed:
            returncode = tree.proc.poll()
        elif ended["left_running"]:
            problems.append(
                "the session exited and left processes running; they were killed with it before anything "
                "else was done"
            )
        problems += ended["problems"]
        stdout_tail = _tail(log)
    session = SupervisedSession(
        returncode=returncode,
        killed=killed,
        elapsed_s=0.0,
        stdout_tail=stdout_tail,
        reaped=bool(ended["reaped"]),
        recovery_reserve_s=round(reserve, 3),
        problems=problems,
        execution_id=execution_id,
        tree=ended,
    )
    reason: str | None
    if killed:
        session.evidence = {"accepted": False, "why": "not read: the session was killed"}
        if not session.reaped:
            problems.append(
                "the killed session had not exited when its reap's time ran out: it was not reaped, and the "
                "recovery ran without waiting for it"
            )
        reason = (
            f"killed by the supervisor {hard_end_s - reserve:.1f} s after its start, before the session's "
            f"hard end ({hard_end_s:.1f} s): the last {reserve:.1f} s are kept for this recovery"
        )
    elif returncode != 0:
        session.evidence = {
            "accepted": False,
            "why": f"not read: the session ended with exit code {returncode}",
        }
        reason = f"the session ended with exit code {returncode}"
    else:
        accepted, why = evidence_of_this_execution(Path(out_dir), Path(manifest), execution_id, left)
        session.evidence = {"accepted": accepted, "why": why}
        reason = (
            None if accepted else f"the session ended without a complete evidence manifest of its own: {why}"
        )
    if reason is not None:
        session.recovery = _recover_in_child(
            manifest, out_dir, retailer, reason=reason, end=end, execution_id=execution_id
        )
    session.elapsed_s = round(time.monotonic() - t0, 3)
    return session


def _recover_in_child(
    manifest: Path, out_dir: Path, retailer: str, *, reason: str, end: float, execution_id: str
) -> dict[str, Any]:
    """The recovery in its own process, ended by ``end`` (on the monotonic clock) whatever happens in it
    (1.7.1; 1.7.2: the end is passed on the monotonic clock, which a wall-clock jump cannot move)."""
    seconds = end - time.monotonic()
    if seconds <= RECOVERY_MARGIN_S:
        return {
            "completed": False,
            "ended_by": reason,
            "problems": [
                f"no time was left for a recovery before the session's end ({max(0.0, seconds):.2f} s): "
                "the rows and files stay as the session left them, their money held, for the next recovery"
            ],
        }
    command = [
        sys.executable,
        "-I",
        "-m",
        "classic_probe.supervisor",
        "recover",
        os.fspath(Path(manifest).resolve()),
        os.fspath(Path(out_dir).resolve()),
        retailer,
        "--reason",
        reason,
        "--until-monotonic",
        repr(end - RECOVERY_MARGIN_S),
        "--execution-id",
        execution_id,
    ]
    proc = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        out, err = proc.communicate(timeout=max(MIN_STEP_S, end - time.monotonic() - RECOVERY_KILL_S))
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            proc.communicate(timeout=RECOVERY_KILL_S)
        except subprocess.TimeoutExpired:
            pass
        return {
            "completed": False,
            "ended_by": reason,
            "problems": [
                f"the recovery had not ended by the session's end and was killed after {seconds:.1f} s: what "
                "it wrote stays, and the next recovery completes it"
            ],
        }
    try:
        result = json.loads(out.decode("utf-8").strip().splitlines()[-1])
    except (ValueError, IndexError):
        result = None
    if not isinstance(result, dict):
        return {
            "completed": False,
            "ended_by": reason,
            "problems": [
                f"the recovery gave no readable result (exit code {proc.returncode}): "
                + err.decode("utf-8", "replace")[-500:]
            ],
        }
    return result


def recover_session(
    manifest: Path,
    out_dir: Path,
    retailer: str,
    *,
    reason: str,
    until_monotonic: float | None = None,
    execution_id: str | None = None,
) -> dict[str, Any]:
    """After a session that did not end by itself: what it left, made safe and written down.

    ``until_monotonic`` (on the monotonic clock; None: no bound) bounds all of it (1.7.1; 1.7.2: monotonic):
    each wait for the ledger's lock ends by then, less the time kept to write the manifest. What could not be
    done is listed in ``problems`` and ``completed`` is False; a row not marked keeps its money held for the
    next recovery. ``execution_id`` names the run recovered, in the manifest written."""

    def time_left() -> float:
        return float("inf") if until_monotonic is None else until_monotonic - time.monotonic()

    def ledger_time() -> float:
        return time_left() - FINAL_WRITE_S

    bound: Callable[[], float] | None = None if until_monotonic is None else ledger_time
    problems: list[str] = []
    led = ledger_mod.open_from_manifest(manifest, time_left=bound)
    try:
        unfinished: int | None = None
        try:
            unfinished = led.recover()
        except ledger_mod.LockNotObtained as exc:
            problems.append(
                f"the rows left reserved or sent were not marked unknown ({exc}): they stay as the session "
                "left them, their money held, for the next recovery"
            )
        store = CaptureStore(out_dir, retailer)
        captures = store.recover(led, time_left=ledger_time, min_left_s=0.0)
        for item in captures["not_reached"]:
            problems.append(f"capture file {item['what']} not reached: {item['why']}")
        responses, checked = store.verify(led, time_left=ledger_time, min_left_s=0.0)
        if not checked:
            problems.append("not every capture was checked against its file before the session's end")
        data: dict[str, Any] = {
            "campaign_id": led.campaign_id,
            "ledger_genesis_id": led.genesis_id,
            "execution_id": execution_id,
            "offline": led.offline,
            "complete": False,
            "ended_by": reason,
            "captures_checked": checked,
            "rows_recovered_as_unknown": unfinished,
            "capture_recovery": captures,
            "recovery_completed": not problems,
            "recovery_problems": problems,
        }
        try:
            data.update(
                totals=led.totals().as_dict(), dispatches=led.rows(), events=led.events(), responses=responses
            )
        except sqlite3.OperationalError as exc:
            problems.append(f"the ledger could not be read before the session's end: {exc}")
            data.update(responses=responses, recovery_completed=False)
        result: dict[str, Any] = {
            "completed": not problems,
            "ended_by": reason,
            "problems": problems,
            "rows_recovered_as_unknown": unfinished,
            "capture_recovery": captures,
        }
        if time_left() <= 0:
            problems.append("no time was left to write the recovered manifest")
            result["completed"] = False
            return result
        out_dir.mkdir(parents=True, exist_ok=True)
        write_json(out_dir / RECOVERED, data)
        result["manifest"] = RECOVERED
        return result
    finally:
        led.close()


def main(argv: Sequence[str] | None = None) -> int:
    """The supervisor's recovery in its own process (1.7.1), printing its result as one JSON line::

    python -I -m classic_probe.supervisor recover MANIFEST OUT_DIR RETAILER --reason TEXT
        [--until-monotonic SECONDS] [--execution-id ID]

    ``--until-monotonic`` is a reading of the system-wide monotonic clock (``time.monotonic()``) at which the
    recovery must have ended (1.7.2: not the wall clock)."""
    parser = argparse.ArgumentParser(prog="classic_probe.supervisor")
    sub = parser.add_subparsers(dest="command", required=True)
    rec = sub.add_parser("recover", help="recover a session that did not end by itself (OFFLINE)")
    rec.add_argument("manifest", type=Path)
    rec.add_argument("out_dir", type=Path)
    rec.add_argument("retailer")
    rec.add_argument("--reason", required=True)
    rec.add_argument("--until-monotonic", type=float, default=None)
    rec.add_argument("--execution-id", default=None)
    args = parser.parse_args(argv)
    try:
        result = recover_session(
            args.manifest,
            args.out_dir,
            args.retailer,
            reason=args.reason,
            until_monotonic=args.until_monotonic,
            execution_id=args.execution_id,
        )
    except Exception as exc:  # noqa: BLE001 - reported to the supervisor, which records it
        print(
            json.dumps(
                {
                    "completed": False,
                    "ended_by": args.reason,
                    "problems": [f"the recovery failed: {type(exc).__name__}: {exc}"],
                }
            )
        )
        return 1
    print(json.dumps(result, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
