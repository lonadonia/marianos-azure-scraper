"""provider_usage of the qualification runs: states, costs and outcomes, and every non-ok settlement (read only)."""
import sys
from collections import Counter
from pathlib import Path

from sqlalchemy import create_engine, text

port = Path(r"C:\m6\pg\data\postmaster.pid").read_text().splitlines()[3].strip()
e = create_engine(f"postgresql+psycopg://postgres:@127.0.0.1:{port}/marianos_q180")
runs = sys.argv[1:]
with e.connect() as c:
    q = text("SELECT run_id, segment_id, purpose, target, attempt, reserved_at, settled_at, units, cost_usd, state, cost_source, "
             "outcome, http_status, request_id FROM provider_usage ORDER BY reserved_at")
    rows = [r for r in c.execute(q) if not runs or r.run_id in runs]
    by = Counter((r.run_id, r.state, r.cost_source) for r in rows)
    for k, v in sorted(by.items(), key=lambda x: str(x)):
        print(f"{v:>4}  {k[0]}  {k[1]:<9} {k[2]}")
    print("total", len(rows), "usd", sum(r.cost_usd or 0 for r in rows))
    print("not ok:")
    for r in rows:
        if r.cost_source != "rule" or (r.http_status or 200) != 200:
            print(f"  {r.run_id[-6:]} ..{str(r.segment_id)[-6:]} {r.purpose:<8} try {r.attempt} {str(r.reserved_at)[11:19]}-{str(r.settled_at)[11:19]}"
                  f" {r.state:<9} {r.cost_source:<8} usd {r.cost_usd} http {r.http_status} outcome {str(r.outcome)[:70]} {str(r.target)[-45:]}")
