"""Record a terminal walkthrough as an asciinema v2 file. Every command in the steps file is run for real while it
is recorded, and its output is written to the recording as it arrives, with its own timing. Narration lines (``say``)
are the recorder's own text and start with ``#``. Nothing is typed in afterwards and nothing is edited.

usage: python -I record_cast.py STEPS.json OUT.cast RAWDIR

A step is one of:
  {"say": ["line", ...]}                                   narration
  {"cmd": "shown command", "argv": [...], "save": "name"}  a command; its whole output is saved to RAWDIR/name.txt and
                                                          shown as it arrives
  {"cmd": ..., "argv": ..., "save": ..., "view": "events"} the collector's JSON-lines log, shown one line per event
                                                          (time, level, event, message); the raw lines are saved
Lines longer than the terminal are cut at its width on screen only (the saved output is whole).
A step's argv may contain {RUN} (the run id the last "events" step created) and {RAW} (RAWDIR).
An "events" step may carry "kill_after": {"event": E, "count": N, "cmd": ..., "argv": [...], "save": ...}: when
the N-th event E has been shown, that command is run (and shown) while the step's own process is still running;
the step's process then ends however the command ended it, and its exit code is shown as it is.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

WIDTH, HEIGHT = 132, 40


class Cast:
    def __init__(self, path: Path, title: str) -> None:
        self.f = path.open("w", encoding="utf-8", newline="\n")
        self.t0 = time.monotonic()
        head = {"version": 2, "width": WIDTH, "height": HEIGHT, "timestamp": int(time.time()), "title": title,
                "env": {"SHELL": "bash", "TERM": "xterm-256color"}}  # fmt: skip
        self.f.write(json.dumps(head, ensure_ascii=False) + "\n")

    def out(self, text: str) -> None:
        self.f.write(json.dumps([round(time.monotonic() - self.t0, 3), "o", text], ensure_ascii=False) + "\n")
        self.f.flush()

    def line(self, text: str) -> None:
        self.out(text[:WIDTH] + "\r\n")


def event_line(raw: str) -> str:
    try:
        d = json.loads(raw)
    except ValueError:
        return raw
    if not isinstance(d, dict):
        return raw
    msg = d.get("message")
    if msg is None:
        msg = d.get("result") if "result" in d else d.get("data", "")
    if not isinstance(msg, str):
        msg = json.dumps(msg, ensure_ascii=False)
    return f"{str(d.get('ts', ''))[11:19]} {d.get('level', ''):<5} {d.get('event', '?')} {msg}"


def main() -> int:
    steps = json.loads(Path(sys.argv[1]).read_text("utf-8"))
    cast = Cast(Path(sys.argv[2]), steps["title"])
    raw = Path(sys.argv[3])
    raw.mkdir(parents=True, exist_ok=True)
    run_id = ""
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    for n, st in enumerate(steps["steps"], 1):
        if "say" in st:
            for s in st["say"]:
                cast.line("# " + s if s else "#")
                time.sleep(0.35)
            cast.line("")
            continue
        shown = st["cmd"].replace("{RUN}", run_id)
        argv = [a.replace("{RUN}", run_id).replace("{RAW}", str(raw)) for a in st["argv"]]
        cast.line("$ " + shown)
        name = f"{n:02d}_{st['save']}.txt"
        with (raw / name).open("w", encoding="utf-8", newline="\n") as keep:
            keep.write(f"# command: {' '.join(argv)}\n# started: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n")
            p = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
            assert p.stdout is not None
            kill = st.get("kill_after")
            seen = 0
            for b in iter(p.stdout.readline, b""):
                s = b.decode("utf-8", "replace").rstrip("\r\n")
                keep.write(s + "\n")
                keep.flush()
                if st.get("view") == "events":
                    if not run_id and '"RUN_CREATED"' in s:
                        try:
                            run_id = json.loads(s).get("run_id") or ""
                        except ValueError:
                            pass
                    cast.line(event_line(s))
                    if kill and f'"event": "{kill["event"]}"' in s:
                        seen += 1
                        if seen == kill["count"]:
                            cast.line("$ " + kill["cmd"])
                            k = subprocess.run(kill["argv"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
                            out = k.stdout.decode("utf-8", "replace")
                            (raw / f"{n:02d}_{kill['save']}.txt").write_text(out, "utf-8")
                            for x in out.splitlines():
                                cast.line(x)
                            cast.line(f"[exit {k.returncode}]")
                            print(f"step {n} kill: exit {k.returncode}", flush=True)
                else:
                    cast.line(s)
            code = p.wait()
            keep.write(f"# exit: {code}\n# ended: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n")
        cast.line(f"[exit {code}]")
        cast.line("")
        print(f"step {n} {st['save']}: exit {code}", flush=True)
        if code != 0 and st.get("stop_on_failure"):
            cast.line("# The step above failed; the recording stops here.")
            break
    cast.f.close()
    print("run", run_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
