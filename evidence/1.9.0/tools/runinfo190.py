"""Read-only summary of runs in marianos_q190 (no request): status, stop, counts, segments, findings, event kinds,
listing pages by taxonomy and the store checks.

usage: <qwt venv python> -I runinfo190.py RUN [RUN ...]     (PSYCOPG_IMPL=python and libpq on PATH)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

PORT = Path(r"C:\m8\pg\data\postmaster.pid").read_text().splitlines()[3].strip()
E = create_engine(f"postgresql+psycopg://postgres:@127.0.0.1:{PORT}/marianos_q190")


def q(c, sql: str, **p):
    return [dict(r._mapping) for r in c.execute(text(sql), p)]


def main(runs: list[str]) -> None:
    with E.connect() as c:
        for run in runs:
            r = q(c, "select id, status, stop_code, left(stop_detail, 300) as stop_detail, started_at, finished_at, "
                     "counts, attempt, parser_version from runs where id=:r", r=run)
            print("RUN", json.dumps(r, default=str, indent=1))
            print("SEGMENTS", json.dumps(q(c, "select * from collection_segments where run_id=:r order by id", r=run),
                                         default=str))
            print("FINDINGS", json.dumps(q(c, "select gate, severity, code, left(message, 240) as message from "
                                              "validation_findings where run_id=:r order by id", r=run), default=str))
            ev = q(c, "select code, count(*) as n from events where run_id=:r group by 1 order by 2 desc", r=run)
            print("EVENTS", json.dumps(ev, default=str))
            print("ATTEST", json.dumps(q(c, "select phase, result, observed_location_id, modality, count(*) as n from "
                                            "store_attestations where run_id=:r group by 1,2,3,4", r=run), default=str))
            print("TASKS", json.dumps(q(c, "select kind, state, count(*) as n from tasks where run_id=:r group by 1,2 "
                                           "order by 1,2", r=run), default=str))


if __name__ == "__main__":
    main(sys.argv[1:])
