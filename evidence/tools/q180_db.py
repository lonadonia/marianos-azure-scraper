"""Read-only view of the qualification database marianos_q180: the provider ledger and the listing pages.

usage (from the clean worktree's environment, see q180.sh):  q180_db.py PORT [RUN_ID]
"""
import sys
from collections import Counter

from sqlalchemy import create_engine, text

port = sys.argv[1]
run = sys.argv[2] if len(sys.argv) > 2 else None
e = create_engine(f"postgresql+psycopg://postgres:@127.0.0.1:{port}/marianos_q180")
with e.connect() as c:
    rows = c.execute(
        text(
            "SELECT run_id, segment_id, purpose, state, cost_source, outcome, http_status, cost_usd, attempt, "
            "reserved_at, settled_at, target FROM provider_usage ORDER BY reserved_at"
        )
    ).all()
    print(f"provider_usage rows: {len(rows)}")
    by = Counter((r.run_id, r.state, r.cost_source) for r in rows)
    for k, n in sorted(by.items(), key=lambda kv: str(kv[0])):
        print("  ", k, n)
    usd = sum(r.cost_usd or 0 for r in rows)
    print(f"  sum cost_usd {usd:.4f}")
    for r in rows[-4:]:
        print(
            "   last:", r.reserved_at.strftime("%H:%M:%S"), r.purpose, r.state, r.cost_source, r.outcome,
            r.http_status, (r.target or "")[:90],
        )
    q = (
        "SELECT run_id, csv_row_index, taxonomy_id, requested_page, state, verdict, total, available, "
        "jsonb_array_length(identities) AS n, new_count, duplicates, store_check, segment_id, attempt "
        "FROM listing_pages "
    )
    if run:
        q += "WHERE run_id = :run "
    q += "ORDER BY observed_at"
    pages = c.execute(text(q), {"run": run} if run else {}).all()
    print(f"listing_pages: {len(pages)}")
    for p in pages:
        print(
            "  ", p.run_id[-6:], p.csv_row_index, p.taxonomy_id, "p", p.requested_page, p.state, p.verdict,
            "total", p.total, "avail", p.available, "cards", p.n, "new", p.new_count, "dup", p.duplicates,
            p.store_check, "seg", (p.segment_id or "")[-6:], "att", p.attempt,
        )
    runs = c.execute(
        text("SELECT id, status, stop_code, left(coalesce(stop_detail,''), 160) AS d FROM runs ORDER BY created_at")
    ).all()
    for r in runs:
        print("run", r.id, r.status, r.stop_code, r.d)
e.dispose()
