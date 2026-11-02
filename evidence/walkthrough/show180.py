"""Read-only views used in the 1.8.0rc3 walkthrough: what the collector printed or stored, set out in short lines.
Nothing here changes the database or a file, and nothing is sent anywhere.

usage (the qualification environment, see C:/m6/tools/q180.sh; the run's own database marianos_q180):
  show180.py status -            a `status` result read from stdin: each run, the published dataset, the provider ledger
  show180.py result -            any other command's result line read from stdin, as indented JSON (cut at 60 lines)
  show180.py run RUN             the run's release, segments (with how each ended) and provider submissions
  show180.py pages RUN           every listing page response of the run, in order, with its verdict
  show180.py coverage DIR        an export's coverage by CSV row and by listing, and its identity sets
  show180.py records DIR [N]     the first N records of an export's products_fresh.json, all 22 fields
  show180.py flagged DIR         the export's records that are not valid, with their reasons
  show180.py compare DIR1 DIR2   two runs' fresh exports: identities in both, in one only, prices that differ
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path


def db():
    from sqlalchemy import create_engine

    port = Path(r"C:\m6\pg\data\postmaster.pid").read_text().splitlines()[3].strip()
    return create_engine(f"postgresql+psycopg://postgres:@127.0.0.1:{port}/marianos_q180")


def result_from_stdin() -> dict:
    for line in sys.stdin:
        if line.startswith("{"):
            d = json.loads(line)
            if d.get("event") == "RESULT":
                return d
    raise SystemExit("no RESULT line on stdin")


def t(s: object) -> str:
    return "" if s is None else str(s)[:19].replace("T", " ")


def status() -> None:
    r = result_from_stdin()["result"]
    for st in r["stores"]:
        print(f"store {st['store']}  hold: {st['hold'] or 'none'}")
        for x in st["runs"]:
            c = x.get("canary") or {}
            print(f"  run {x['run_id']}  {x['status']:<10} dataset {x['dataset']:<8} complete {x['collection_complete']}"
                  f"  canary {c.get('status', '-')}")  # fmt: skip
            if x.get("stop_code"):
                print(f"      stop {x['stop_code']}: {str(x.get('stop_detail'))[:100]}")
            if x.get("records_by_status"):
                print(f"      records {x['records_by_status']}")
        pub = st.get("published")
        print(f"  published: {json.dumps(pub)[:150] if pub else 'nothing'}")
    p = r.get("provider") or {}
    u, cl = p.get("used") or {}, p.get("ceiling") or {}
    print(f"provider {p.get('service')}")
    print(f"  used {u.get('submissions')} submissions, USD {u.get('usd')} ({u.get('unknown')} unknown, kept as possibly charged)")
    print(f"  ceiling {cl.get('submissions')} / USD {cl.get('usd')} since {t(cl.get('since'))}; room {p.get('room_submissions')} submissions")


def result() -> None:
    d = result_from_stdin()
    lines = json.dumps(d.get("result"), indent=1, ensure_ascii=False).splitlines()
    for s in lines[:60]:
        print(s)
    if len(lines) > 60:
        print(f"... ({len(lines) - 60} more lines in the saved output)")
    print(f"exit_code {d.get('exit_code')}")


def run(rid: str) -> None:
    from sqlalchemy import text

    with db().connect() as c:
        r = c.execute(text("SELECT * FROM runs WHERE id=:r"), {"r": rid}).mappings().one()
        keep = [k for k in r.keys() if any(w in k for w in ("version", "commit", "revision", "parser", "release"))]
        print(f"run {rid}  status {r['status']}  " + "  ".join(f"{k} {r[k]}" for k in keep))
        print("segments (each start or resume; how it ended):")
        for s in c.execute(text("SELECT * FROM collection_segments WHERE run_id=:r ORDER BY started_at"), {"r": rid}).mappings():
            end = t(s["ended_at"]) or f"last seen {t(s['heartbeat_at'])}, found {t(s['recovered_at'])}"
            print(f"  {s['id']}  {s['trigger']:<8} {t(s['started_at'])} -> {end:<44} {s['end_state'] or 'open':<9}"
                  f" steps {s['steps']:<3} stop {s['stop_code'] or '-'}")  # fmt: skip
        rows = c.execute(text("SELECT purpose, state, cost_source, cost_usd, outcome FROM provider_usage WHERE run_id=:r"), {"r": rid}).all()
        n = Counter((x.purpose, x.state, x.cost_source) for x in rows)
        print(f"provider submissions: {len(rows)}, USD {sum(x.cost_usd for x in rows):.4f} at the reserve rate")
        for k, v in sorted(n.items()):
            print(f"  {v:>3}  {k[0]:<10} {k[1]:<9} cost {k[2]}")


def pages(rid: str) -> None:
    from sqlalchemy import text

    q = text("SELECT csv_row_index, taxonomy_id, requested_page, returned_page, attempt, state, verdict, new_count, duplicates,"
             " total, location_id, modality, observed_at, segment_id, detail FROM listing_pages WHERE run_id=:r ORDER BY observed_at")  # fmt: skip
    print("row listing page->got try state      verdict      new dup total store    fulfil. observed  segment")
    with db().connect() as c:
        for x in c.execute(q, {"r": rid}):
            print(f"{x[0]:>3} {x[1]:<7} {x[2]:>4}->{t(x[3]):<3} {x[4]:>3} {x[5]:<9} {x[6]:<12} {x[7]:>3} {x[8]:>3} {t(x[9]):>5} "
                  f"{t(x[10]):<8} {t(x[11]):<7} {t(x[12])[11:19]}  ..{str(x[13])[-6:]}"
                  + (f"  {x[14][:40]}" if x[14] else ""))  # fmt: skip


def coverage(d: Path) -> None:
    j = json.loads((d / "coverage_reconciliation.json").read_text("utf-8"))
    print(f"run {j['run_id']}  store {j['store']['location_id']} {j['store']['fulfillment']}  CSV rows {j['csv_rows']}"
          f"  listings planned {j['listings_planned']}  complete rows {j['complete_rows']}  complete listings {j['complete_listings']}")  # fmt: skip
    print("by CSV row (rows outside this run's scope are listed in the file as NOT_ATTEMPTED):")
    with (d / "coverage_by_csv_row.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    skipped = 0
    for r in rows:
        if r["status"] == "NOT_ATTEMPTED":
            skipped += 1
            continue
        print(f"  row {r['csv_row']:>2} {r['category'][:26]:<26} pages {r['pages_completed']:>3} unique {r['unique_identities']:>4}"
              f"  {r['status']}: {r['completion_reason'][:60]}")  # fmt: skip
    print(f"  ({skipped} rows not attempted: not in this run's scope)")
    print("by listing:")
    with (d / "coverage_reconciliation.csv").open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            print(f"  {r['taxonomy_id'] if 'taxonomy_id' in r else r['listing_id']:<7} total {r['reported_total']:>4} pages {r['pages_completed']}/"
                  f"{r['pages_attempted']} not counted {r['responses_not_counted']} unique {r['unique_identities']:>4} dup {r['duplicates']:>3}"
                  f" gap {r['unresolved_gap'] or 0}  {r['status']}")  # fmt: skip
    i = j["identities"]
    print("identity sets: " + ", ".join(f"{k} {v}" for k, v in i.items() if isinstance(v, int)))
    for k, v in i["relations"].items():
        print(f"  {k}: {v}")
    print(f"  all relations hold: {i['holds']}")


FIELDS = ("zipcode store_name store_location store_logo store_brand category sub_category product_title weight regular_price "
          "sale_price volume_deals_description volume_deals_price digital_deals_description digital_deals_price image_url url upc "
          "gupc ppm unit_price crawl_date").split()  # fmt: skip


def records(d: Path, n: int) -> None:
    recs = json.loads((d / "products_fresh.json").read_text("utf-8"))
    print(f"products_fresh.json: {len(recs)} records; every record has these 22 keys in this order: "
          f"{all(list(r) == FIELDS for r in recs)}; every value a string: {all(isinstance(v, str) for r in recs for v in r.values())}")
    for r in recs[:n]:
        print("{")
        for k, v in r.items():
            print(f'  "{k}": {json.dumps(v, ensure_ascii=False)[:110]}')
        print("}")


def flagged(d: Path) -> None:
    recs = json.loads((d / "products.json").read_text("utf-8"))
    fresh = {r["upc"] for r in json.loads((d / "products_fresh.json").read_text("utf-8"))}
    by_upc = json.loads((d / "provenance.json").read_text("utf-8"))["records"]  # the supporting log, by UPC
    print(f"products.json {len(recs)} records; products_fresh.json {len(fresh)} (status valid); the others, with the")
    print("supporting log's status, reasons and flags (provenance.json):")
    n = 0
    for r in recs:
        if r["upc"] in fresh:
            continue
        x = by_upc.get(r["upc"], {})
        n += 1
        why = ",".join([*(x.get("reasons") or []), *(x.get("flags") or [])]) or "-"
        print(f"  {r['upc']}  {r['product_title'][:44]:<44} price {r['regular_price'] or '\"\"':<6} "
              f"{x.get('status', '?')}: {why[:60]}")  # fmt: skip
    print(f"{n} records exported but not valid")


def compare(a: Path, b: Path) -> None:
    ra = {r["upc"]: r for r in json.loads((a / "products_fresh.json").read_text("utf-8"))}
    rb = {r["upc"]: r for r in json.loads((b / "products_fresh.json").read_text("utf-8"))}
    both = ra.keys() & rb.keys()
    print(f"first {a.name}: {len(ra)} valid fresh; second {b.name}: {len(rb)} valid fresh")
    print(f"in both {len(both)}; first only {len(ra.keys() - rb.keys())}; second only {len(rb.keys() - ra.keys())}")
    for k in ("regular_price", "sale_price", "digital_deals_description", "volume_deals_description", "weight", "ppm"):
        diff = [u for u in both if ra[u][k] != rb[u][k]]
        print(f"  {k:<26} differs for {len(diff)}" + (f", e.g. {diff[0]}: {ra[diff[0]][k]!r} -> {rb[diff[0]][k]!r}" if diff else ""))
    for u in sorted(ra.keys() - rb.keys())[:5]:
        print(f"  first only: {u} {ra[u]['product_title'][:60]}")
    for u in sorted(rb.keys() - ra.keys())[:5]:
        print(f"  second only: {u} {rb[u]['product_title'][:60]}")


def main() -> int:
    cmd, args = sys.argv[1], sys.argv[2:]
    if cmd == "status":
        status()
    elif cmd == "result":
        result()
    elif cmd == "run":
        run(args[0])
    elif cmd == "pages":
        pages(args[0])
    elif cmd == "coverage":
        coverage(Path(args[0]))
    elif cmd == "records":
        records(Path(args[0]), int(args[1]) if len(args) > 1 else 2)
    elif cmd == "flagged":
        flagged(Path(args[0]))
    elif cmd == "compare":
        compare(Path(args[0]), Path(args[1]))
    else:
        raise SystemExit(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
