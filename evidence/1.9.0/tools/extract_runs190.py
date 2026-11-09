"""Extract live runs of 1.9.0 from marianos_q190 (read only; no request), for the evidence archive. The 1.8.0 tool
(evidence/tools/extract_runs180.py) adapted to the 1.9 database copy; no whole-database dump is written.

    PSYCOPG_IMPL=python PATH=<pgserver bin>:$PATH <venv python> -X utf8 extract_runs190.py OUT_DIR RUN [RUN ...]

OUT_DIR/runs/<run>/db/<table>.csv   every row of each run-scoped table for the run (JSON columns as JSON text)
OUT_DIR/runs/<run>/data/...         the run's stored files (pages, product data, exports) from C:/m8/q190/data/runs
OUT_DIR/db_global/<table>.csv       the tables without run_id (stores, category_sources, settings, audit_log,
                                    publication_pointer, alembic_version), runs, publications and provider_usage in full
OUT_DIR/SHA256SUMS.txt               every file above
"""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine, text

DATA = Path(r"C:\m8\q190\data\runs\marianos-53100502-pickup")
PORT = Path(r"C:\m8\pg\data\postmaster.pid").read_text().splitlines()[3].strip()
URL = f"postgresql+psycopg://postgres:@127.0.0.1:{PORT}/marianos_q190"
GLOBAL = ("stores", "category_sources", "settings", "audit_log", "publication_pointer", "alembic_version", "provider_usage",
          "runs", "publications")


def cell(v: object) -> str:
    if v is None:
        return ""
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False, sort_keys=True, default=str)
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, Decimal):
        return format(v, "f")
    if isinstance(v, bytes):
        return v.hex()
    return str(v)


def dump(c, sql: str, params: dict, path: Path, order: str) -> int:
    res = c.execute(text(f"{sql} ORDER BY {order}"), params)
    cols = list(res.keys())
    rows = res.all()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(cols)
        for r in rows:
            w.writerow([cell(v) for v in r])
    return len(rows)


def main(out: Path, runs: list[str]) -> None:
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"{out} is not empty: never overwritten")
    e = create_engine(URL)
    counts: dict[str, dict[str, int]] = {}
    with e.connect() as c:
        tabs = [r[0] for r in c.execute(text(
            "select table_name from information_schema.columns where table_schema='public' and column_name='run_id' "
            "order by 1"))]
        for run in runs:
            counts[run] = {}
            for t in tabs:
                cols = [r[0] for r in c.execute(text(
                    "select column_name from information_schema.columns where table_name=:t"), {"t": t})]
                order = "id" if "id" in cols else "run_id"
                counts[run][t] = dump(c, f'SELECT * FROM "{t}" WHERE run_id=:r', {"r": run},
                                      out / f"runs/{run}/db/{t}.csv", order)
            counts[run]["runs"] = dump(c, 'SELECT * FROM "runs" WHERE id=:r', {"r": run}, out / f"runs/{run}/db/runs.csv",
                                       "id")
            src = DATA / run
            n = 0
            for p in sorted(x for x in src.rglob("*") if x.is_file()):
                dst = out / f"runs/{run}/data/{p.relative_to(src).as_posix()}"
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, dst)
                n += 1
            counts[run]["data_files"] = n
        for t in GLOBAL:
            cols = [r[0] for r in c.execute(text("select column_name from information_schema.columns where table_name=:t"),
                                            {"t": t})]
            order = "id" if "id" in cols else cols[0]
            counts.setdefault("global", {})[t] = dump(c, f'SELECT * FROM "{t}"', {}, out / f"db_global/{t}.csv", order)
    lines = []
    for p in sorted(x for x in out.rglob("*") if x.is_file() and x.name != "SHA256SUMS.txt"):
        lines.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(out).as_posix()}\n")
    (out / "SHA256SUMS.txt").write_text("".join(lines), "utf-8")
    print(json.dumps(counts, indent=1))
    print("files", len(lines))


if __name__ == "__main__":
    main(Path(sys.argv[1]), sys.argv[2:])
