"""Offline replay of one stored run's listings against the 1.9 baseline queue (release 1.10.0rc7). No network.

    uv run --frozen python -I tools/replay_routes.py RUN_DIR QUEUE_190.csv LABEL OUT_DIR
        [--compare LABEL=OUT_DIR]

RUN_DIR is a run's saved evidence (private): the table copies ``db_tasks.csv``, ``db_listing_pages.csv``,
``db_page_fetches.csv`` and ``db_runs.csv``, the export (``export/provenance.json``,
``export/memberships.json``, ``export/coverage_reconciliation.csv``) and the stored pages
(``stored/<run>/live/dom/<fetch>.html.gz``). Nothing in it is changed. QUEUE_190.csv is the 1.9 baseline
queue (``evidence/coverage/INCOMPLETE_QUEUE_190.csv``: 302 product listings and the Coupons route).

For every listing of the run's plan the replay

* takes the run's counted pages (completed, contiguous from page 1, as the collector counts them) and, for
  each, hashes the stored page and compares the hash with the one the page's row recorded, then reads the
  stored page again with the collector's own parser (``parse_initial_state``, ``search_summary``) and
  compares the products it lists, in order, with the identities the row recorded. A page whose capture is
  missing, or whose hash or products differ, is UNVERIFIABLE (named with its run, page and fetch);
* for a listing the run recorded as empty, looks for the store's own page stating 0 results: a page row, or
  else the listing's stored page read again (its total, store and fulfillment);
* audits the listing with ``marianos_headless.collection.route_audit`` (the code the collector, the export,
  G3 and the publication use from 1.10.0rc7): every product its counted pages list must be accounted for by
  a record of the run placed under the listing (export ``provenance.json`` and ``memberships.json``),
  sponsored placements, cross-listed, excluded and carried records kept apart; a listing read through
  subdivisions by their union.

It writes ``routes_<LABEL>.csv`` (one line per baseline listing, the Coupons route apart),
``summary_<LABEL>.json`` (counts, the complete listings, the replay ID and the hashes of every input) and
``detail/<LABEL>/<listing>.json`` (page by page: fetch, hash, time, products, what is missing), each detail
file named with its SHA-256 in the CSV. With ``--compare``, the listings complete here and not in the named
run, and those complete in both.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from marianos_headless import __version__
from marianos_headless.collection import pagination, route_audit
from marianos_headless.collection.reconciliation import route_key
from marianos_headless.sites.marianos.initial_state import InitialStateNotFound, parse_initial_state
from marianos_headless.sites.marianos.search_state import search_summary

csv.field_size_limit(10**9)
LOCATION, MODALITY = "53100502", "PICKUP"


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def rows_of(p: Path) -> list[dict[str, str]]:
    with p.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def js(v: str) -> Any:
    return json.loads(v) if v else None


class Page:
    """A listing page row of the copy, with the attributes ``pagination.completed_pages`` reads."""

    def __init__(self, r: dict[str, str]):
        self.r = r
        self.requested_page = int(r["requested_page"])
        self.state = r["state"]
        self.attempt = int(r["attempt"] or 1)
        self.identities = [str(u) for u in (js(r["identities"]) or [])]
        self.sponsored = [str(u) for u in (js(r["sponsored"]) or [])]
        self.total = int(r["total"]) if r["total"] else None


def reread(dom: Path) -> dict[str, Any]:
    """The stored page read again with the collector's parser."""
    try:
        html = gzip.decompress(dom.read_bytes()).decode("utf-8")
        summary = search_summary(parse_initial_state(html))
    except (OSError, EOFError, InitialStateNotFound, ValueError) as exc:
        return {"error": f"{type(exc).__name__}: {str(exc)[:120]}"}
    if summary is None:
        return {"error": "no search state in the page"}
    return {
        "organic": list(summary.organic),
        "total": summary.total,
        "location_id": summary.location_id,
        "modality": summary.modality,
        "taxonomy_id": summary.taxonomy_id,
    }


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")  # type: ignore[union-attr]
    args = sys.argv[1:]
    compare = None
    if "--compare" in args:
        i = args.index("--compare")
        compare = args[i + 1]
        del args[i : i + 2]
    run_dir, queue_path, label, out = Path(args[0]), Path(args[1]), args[2], Path(args[3])
    run = rows_of(run_dir / "db_runs.csv")[0]
    run_id = run["id"]
    inputs = {
        name: sha256_file(run_dir / name)
        for name in (
            "db_tasks.csv",
            "db_listing_pages.csv",
            "db_page_fetches.csv",
            "db_runs.csv",
            "export/provenance.json",
            "export/memberships.json",
            "export/coverage_reconciliation.csv",
        )
    }
    inputs["queue"] = sha256_file(queue_path)
    tool = sha256_file(Path(__file__))
    rid = hashlib.sha256(json.dumps([label, run_id, inputs, tool], sort_keys=True).encode()).hexdigest()[:12]
    replay_id = f"RPL-{label}-{rid}"
    dom_dir = run_dir / "stored" / run_id / "live" / "dom"

    tasks = [t for t in rows_of(run_dir / "db_tasks.csv") if t["kind"] == "listing_node"]
    pages_by: dict[tuple[str, str], list[Page]] = defaultdict(list)
    for r in rows_of(run_dir / "db_listing_pages.csv"):
        pages_by[(route_key(r["category_source_id"], r["taxonomy_id"]), r["partition_key"] or "")].append(
            Page(r)
        )
    fetches_by_task: dict[str, list[dict[str, str]]] = defaultdict(list)
    for f in rows_of(run_dir / "db_page_fetches.csv"):
        fetches_by_task[f["task_id"]].append(f)
    prov = json.loads((run_dir / "export" / "provenance.json").read_text(encoding="utf-8"))
    records: dict[str, route_audit.RecordFact] = {}
    kinds: dict[str, str] = {}
    for upc, rec in prov["records"].items():
        status = "historical" if rec.get("observation_kind") != "fresh" else str(rec.get("status"))
        seen_under = str(((rec.get("observation") or {}).get("node")) or "")
        records[str(upc)] = route_audit.RecordFact(status, tuple(rec.get("reasons") or ()), seen_under)
        kinds[str(upc)] = str(rec.get("observation_kind"))
    placed: dict[str, set[tuple[str, str | None]]] = defaultdict(set)
    paid: dict[str, set[str]] = defaultdict(set)
    stores = set()
    for m in json.loads((run_dir / "export" / "memberships.json").read_text(encoding="utf-8")):
        if m.get("run_id") != run_id or m.get("via") not in ("organic", "paid"):
            continue
        stores.add((m.get("location_id"), m.get("fulfillment")))
        where = route_key(m.get("category_source_id"), m.get("listing"))
        if m["via"] == "organic":
            placed[where].add((str(m["key"]), m.get("page_fetch_id") or None))
        else:
            paid[where].add(str(m["key"]))
    if stores - {(LOCATION, MODALITY)}:
        print(f"REFUSED: the run's placements name another store: {sorted(stores)}")
        return 2
    published = {
        (r["csv_row"], r["listing_id"]): r
        for r in rows_of(run_dir / "export" / "coverage_reconciliation.csv")
    }

    routes: list[route_audit.RouteEvidence] = []
    page_detail: dict[str, list[dict[str, Any]]] = {}
    unverifiable: list[dict[str, Any]] = []
    nodes: dict[str, dict[str, Any]] = {}
    for t in tasks:
        cur = js(t["cursor"]) or {}
        node: dict[str, Any] = cur.get("node") or {}
        listing = str(node.get("taxonomy_id") or "")
        key = route_key(node.get("category_source_id"), listing)
        if key in nodes:
            print(f"REFUSED: two tasks of the plan for listing {key}")
            return 2
        nodes[key] = {**node, "_task": t, "_cursor": cur}
        status = str(cur.get("status") or "")
        if t["state"] != "succeeded":
            status = "NOT_COLLECTED"
        elif status not in ("DONE", "EMPTY", "PARTITIONED"):
            status = "INCOMPLETE"
        desc = pagination.node_filter(node.get("partition_filter") or "")
        pkey = pagination.partition_digest(desc) if desc else ""
        mine = sorted(pages_by.get((key, pkey), []), key=lambda p: (p.requested_page, p.attempt))
        done: list[Page] = pagination.completed_pages(mine)  # type: ignore[arg-type, assignment]
        evidence = []
        detail = []
        for p in done:
            r = p.r
            fetch = r["page_fetch_id"] or None
            dom = dom_dir / f"{fetch}.html.gz" if fetch else None
            check: dict[str, Any] = {"capture": "missing"}
            if dom is not None and dom.is_file():
                digest = sha256_file(dom)
                again = reread(dom)
                check = {
                    "capture": "present",
                    "sha256_matches": digest == r["response_sha256"],
                    "products_match": again.get("organic") == p.identities,
                    "reread_total": again.get("total"),
                    "reread_store": [again.get("location_id"), again.get("modality")],
                    **({"reread_error": again["error"]} if "error" in again else {}),
                }
            ok = check.get("sha256_matches") is True and check.get("products_match") is True
            if not ok:
                unverifiable.append(
                    {
                        "run": run_id,
                        "listing": listing,
                        "key": key,
                        "page": p.requested_page,
                        "fetch": fetch,
                        "check": check,
                    }
                )
            bound = r["store_check"] == "PASS" and r["location_id"] == LOCATION and r["modality"] == MODALITY
            evidence.append(
                route_audit.PageEvidence(
                    page=p.requested_page,
                    identities=tuple(p.identities),
                    sponsored=tuple(p.sponsored),
                    fetch_id=fetch,
                    sha256=r["response_sha256"] or None,
                    observed_at=r["observed_at"],
                    total=p.total,
                    location_id=r["location_id"],
                    modality=r["modality"],
                    url=r["url"],
                    attempt=p.attempt,
                    verdict=r["verdict"],
                    store_bound=bound,
                )
            )
            detail.append(
                {
                    "page": p.requested_page,
                    "attempt": p.attempt,
                    "url": r["url"],
                    "fetch": fetch,
                    "sha256": r["response_sha256"],
                    "observed_at": r["observed_at"],
                    "returned_listing": r["returned_taxonomy_id"],
                    "requested_filter": js(r["requested_filter"]) or {},
                    "total": p.total,
                    "store": [r["location_id"], r["modality"], r["store_check"]],
                    "identities": p.identities,
                    "sponsored": p.sponsored,
                    "capture_check": check,
                }
            )
        zero = any(
            p.state == "completed"
            and p.total == 0
            and p.r["store_check"] == "PASS"
            and p.r["location_id"] == LOCATION
            and p.r["modality"] == MODALITY
            for p in mine
        )
        zero_from = "page row" if zero else ""
        if status == "EMPTY" and not zero:
            # 1.10.0rc6 kept no row for a page stating 0 results: its stored page, read again.
            for f in fetches_by_task.get(t["id"], []):
                dom = dom_dir / f"{f['id']}.html.gz"
                if not dom.is_file():
                    continue
                again = reread(dom)
                if (again.get("total"), again.get("location_id"), again.get("modality")) == (
                    0,
                    LOCATION,
                    MODALITY,
                ):
                    zero, zero_from = True, f"stored page {f['id']} read again (sha256 {sha256_file(dom)})"
                    break
        totals = tuple(sorted({p.total for p in mine if p.total is not None}))
        total = totals[-1] if totals else cur.get("total")
        stepped = not mine or all(p.r["route"] == "search" for p in mine)
        routes.append(
            route_audit.RouteEvidence(
                key=key,
                listing=listing,
                cursor_status=status,
                parent=route_key(node.get("category_source_id"), node["parent"])
                if node.get("parent")
                else "",
                kind=str(node.get("kind") or ""),
                reason=str(cur.get("reason") or ""),
                total=total if isinstance(total, int) else None,
                totals_seen=totals,
                pages=tuple(evidence),
                placements=frozenset(placed.get(key, set())),
                paid=frozenset(paid.get(key, set())),
                fetches=frozenset(p.r["page_fetch_id"] for p in mine if p.r["page_fetch_id"]),
                zero_result=zero,
                without_page_rows=stepped,
                stepped=tuple(str(u) for u in (cur.get("seen") or [])) if stepped else (),
            )
        )
        page_detail[key] = detail
        nodes[key]["_zero"] = zero_from
    verdicts = route_audit.audit(routes, records)

    def flatten(key: str) -> list[str]:
        out = [key]
        for c in verdicts[key].children:
            out += flatten(c)
        return out

    queue = rows_of(queue_path)
    top = {
        (str(n.get("row_index")), str(n.get("taxonomy_id"))): k
        for k, n in nodes.items()
        if not n.get("parent")
    }
    lines: list[dict[str, Any]] = []
    coupons = None
    (out / "detail" / label).mkdir(parents=True, exist_ok=True)
    for q in queue:
        if q["row_kind"] == "coupon_catalogue":
            coupons = q
            continue
        found = top.get((q["csv_row"], q["taxonomy_id"]))
        matched = q["csv_row"] if found else ""
        if found is None:
            others = [k for (_, tax), k in top.items() if tax == q["taxonomy_id"]]
            if len(others) == 1:
                found = others[0]
                matched = str(nodes[found].get("row_index"))
        base: dict[str, Any] = {
            "replay_id": replay_id,
            "run_label": label,
            "run_id": run_id,
            "store": LOCATION,
            "fulfillment": MODALITY,
            "csv_row": q["csv_row"],
            "row_category": q["row_category"],
            "taxonomy_id": q["taxonomy_id"],
            "listing": q["listing"],
            "state_1_9_baseline": q["latest_1_9_state"],
        }
        if found is None:
            lines.append({**base, "status_rc7": "NOT_IN_THE_RUN"})
            continue
        v, n = verdicts[found], nodes[found]
        family = flatten(found)
        pages = [dict(p, listing=verdicts[k].listing) for k in family for p in page_detail.get(k, [])]
        route_detail: dict[str, Any] = {
            "replay_id": replay_id,
            "run": run_id,
            "listing": v.listing,
            "audit": v.as_dict(),
            "subdivisions": {verdicts[k].listing: verdicts[k].as_dict() for k in family[1:]},
            "zero_result_evidence": n["_zero"],
            "pages": pages,
            "fresh_linked": sorted(v.union_accounted or v.accounted),
            "expected": sorted(v.union_expected or set(v.expected)),
        }
        blob = (json.dumps(route_detail, indent=1, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
        fname = v.listing.replace("~", "_") + (
            f"_row{n.get('row_index')}"
            if sum(1 for x in nodes.values() if str(x.get("taxonomy_id")) == v.listing) > 1
            else ""
        )
        dpath = out / "detail" / label / f"{fname}.json"
        dpath.write_bytes(blob)
        unverified = [u for u in unverifiable if u["key"] in family]
        obs = sorted(p["observed_at"] for p in pages if p.get("observed_at"))
        missing_all = {**v.missing, **{u: w for k in family[1:] for u, w in verdicts[k].missing.items()}}
        rc6 = published.get((str(n.get("row_index")), v.listing), {})
        lines.append(
            {
                **base,
                "matched_row": matched,
                "listing_id": v.listing,
                "parent": n.get("parent") or "",
                "kind": n.get("kind") or "",
                "partition_filter": n.get("partition_filter") or "",
                "requested_url": n.get("url") or "",
                "subdivisions": len(family) - 1,
                "pages_counted": sum(1 for _ in pages),
                "requested_pages": " ".join(f"{p['listing']}:{p['page']}" for p in pages)[:2000],
                "returned_listings": " ".join(sorted({str(p["returned_listing"]) for p in pages})),
                "pages_sha256": hashlib.sha256("".join(str(p["sha256"]) for p in pages).encode()).hexdigest()
                if pages
                else "",
                "first_observed_at": obs[0] if obs else "",
                "last_observed_at": obs[-1] if obs else "",
                "reported_total": v.total if v.total is not None else "",
                "distinct_source_upcs": len(v.union_expected or set(v.expected)),
                "fresh_stored_linked": len(v.union_accounted or v.accounted),
                "fresh_valid": v.fresh_valid + sum(verdicts[k].fresh_valid for k in family[1:]),
                "cross_listed": v.cross_listed + sum(verdicts[k].cross_listed for k in family[1:]),
                "supported_exclusions": len(v.excluded) + sum(len(verdicts[k].excluded) for k in family[1:]),
                "duplicates": v.duplicates + sum(verdicts[k].duplicates for k in family[1:]),
                "sponsored_placements": len(v.sponsored)
                + sum(len(verdicts[k].sponsored) for k in family[1:]),
                "missing_upcs": len(missing_all),
                "unexpected_upcs": len(v.unexpected) + sum(len(verdicts[k].unexpected) for k in family[1:]),
                "missing_by_page": "; ".join(
                    f"{verdicts[k].listing}:{pg}:{len(u)}"
                    for k in family
                    for pg, u in sorted(verdicts[k].missing_by_page.items())
                ),
                "zero_result_evidence": n["_zero"],
                "captures_verified": sum(
                    1
                    for p in pages
                    if p["capture_check"].get("sha256_matches") and p["capture_check"].get("products_match")
                ),
                "captures_unverifiable": len(unverified),
                "cursor_status": v.cursor_status,
                "status_rc6_export": rc6.get("status", ""),
                "unique_identities_rc6_export": rc6.get("unique_identities", ""),
                "status_rc7": v.status
                if not unverified or v.status not in ("DONE", "EMPTY")
                else "UNVERIFIABLE",
                "final_reason": (
                    v.reason if not unverified else f"{v.reason}; {len(unverified)} page(s) unverifiable"
                )[:600],
                "detail_file": f"detail/{label}/{fname}.json",
                "detail_sha256": hashlib.sha256(blob).hexdigest(),
            }
        )
    fields: list[str] = []
    for x in lines:
        fields += [k for k in x if k not in fields]
    with (out / f"routes_{label}.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(lines)
    by: dict[str, int] = defaultdict(int)
    for x in lines:
        by[x["status_rc7"]] += 1
    complete = sorted(
        f"{x['csv_row']}|{x['taxonomy_id']}" for x in lines if x["status_rc7"] in ("DONE", "EMPTY")
    )
    rc6_complete = sorted(
        f"{x['csv_row']}|{x['taxonomy_id']}" for x in lines if x.get("status_rc6_export") in ("DONE", "EMPTY")
    )
    row0 = next(
        (r for r in rows_of(run_dir / "export" / "coverage_by_csv_row.csv") if r["csv_row"] == "0"), None
    )
    summary: dict[str, Any] = {
        "replay_id": replay_id,
        "made_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "evidence_type": "offline replay of a stored live run (no request made); not a live run",
        "run_label": label,
        "run_id": run_id,
        "run_code": (js(run["config_snapshot"]) or {}).get("code"),
        "replay_code": {"collector_version": __version__, "tool_sha256": tool},
        "inputs_sha256": inputs,
        "store": [LOCATION, MODALITY],
        "baseline_listings": len(lines),
        "by_status_rc7": dict(sorted(by.items())),
        "complete_rc7": len(complete),
        "complete_rc7_with_products": sum(1 for x in lines if x["status_rc7"] == "DONE"),
        "complete_rc7_empty": sum(1 for x in lines if x["status_rc7"] == "EMPTY"),
        "complete_by_the_published_rc6_export": len(rc6_complete),
        "rc6_complete_not_complete_rc7": sorted(set(rc6_complete) - set(complete)),
        "complete_keys": complete,
        "pages_counted": sum(len(v) for v in page_detail.values()),
        "pages_unverifiable": unverifiable,
        "coupons_row_0": {"queue": coupons["listing"] if coupons else None, "export_row": row0},
        "records": {
            "fresh": sum(1 for k in kinds.values() if k == "fresh"),
            "fresh_valid": sum(1 for u, k in kinds.items() if k == "fresh" and records[u].status == "valid"),
            "carried": sum(1 for k in kinds.values() if k != "fresh"),
        },
    }
    if compare:
        other_label, other_dir = compare.split("=", 1)
        other = json.loads((Path(other_dir) / f"summary_{other_label}.json").read_text(encoding="utf-8"))
        theirs = set(other["complete_keys"])
        summary["compared_with"] = {
            "run_label": other_label,
            "replay_id": other["replay_id"],
            "complete_here_not_there": sorted(set(complete) - theirs),
            "complete_in_both": sorted(set(complete) & theirs),
            "complete_there_not_here": sorted(theirs - set(complete)),
        }
    (out / f"summary_{label}.json").write_text(
        json.dumps(summary, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    print(
        f"{replay_id}: {len(lines)} baseline listings; rc7 {dict(sorted(by.items()))}; "
        f"complete {len(complete)} (rc6 export {len(rc6_complete)}); pages counted "
        f"{summary['pages_counted']}, unverifiable {len(unverifiable)}"
    )
    if compare:
        c = summary["compared_with"]
        print(
            f"vs {c['run_label']}: complete here not there {len(c['complete_here_not_there'])}, in both "
            f"{len(c['complete_in_both'])} {c['complete_in_both']}, there not here "
            f"{len(c['complete_there_not_here'])}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
