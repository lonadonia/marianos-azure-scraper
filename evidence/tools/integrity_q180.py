"""Offline, read only: G13's integrity reading of the qualification runs, computed by the installed collector's own
Pipeline.integrity over marianos_q180 and the runs' stored files (no request; nothing is written).

    <venv python> -I integrity_q180.py RUN [RUN ...]
"""
import sys
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import marianos_headless
from marianos_headless.storage.local import LocalStorageAdapter
from marianos_headless.worker.pipeline import Pipeline

port = Path(r"C:\m6\pg\data\postmaster.pid").read_text().splitlines()[3].strip()
engine = create_engine(f"postgresql+psycopg://postgres:@127.0.0.1:{port}/marianos_q180")
me = SimpleNamespace(storage=LocalStorageAdapter(Path(r"C:\m6\q180\data")))
print("collector", marianos_headless.__version__, "from", Path(marianos_headless.__file__).parent)
with Session(engine) as s:
    for run in sys.argv[1:]:
        tasks_terminal, artifacts_ok, records_ok = Pipeline.integrity(me, s, run)  # type: ignore[arg-type]
        print(f"{run}: tasks_terminal={tasks_terminal} artifact_hashes_verified={artifacts_ok} records_verified={records_ok}")
    s.rollback()
