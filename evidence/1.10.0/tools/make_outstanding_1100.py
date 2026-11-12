"""Writes review/OUTSTANDING_REQUIREMENTS_1.10.0.csv: every requirement still open after 1.10.0rc3, with its kind
(MANDATORY, or CONDITIONAL: an optional route or an owner's decision, not a requirement of the candidate), the matrix
rows and audit groups it gathers, its state, owner, blocker, the exact evidence that would close it and the next
action. Refuses a matrix id or audit group that does not exist, and a mandatory open matrix row left out.

    python -I make_outstanding_1100.py <review/ACCEPTANCE_MATRIX.csv> <out.csv>"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

MATRIX, OUT = Path(sys.argv[1]), Path(sys.argv[2])
Q = "evidence/1.10.0/QUALIFICATION_EVIDENCE_REQUIREMENTS.md"
NS = "evidence/1.10.0/budget/NEXT_STAGES.json"
QUEUE = "evidence/1.9.0/live/INCOMPLETE_QUEUE_190.csv"
HEAD = ["item", "kind", "requirement", "matrix_ids", "audit_groups", "qualification_item", "state_1.10.0rc3",
        "owner", "blocker", "exact_evidence_needed", "next_action"]  # fmt: skip
M, C = "MANDATORY", "CONDITIONAL (optional route or owner's decision)"
ROWS = [
    ["OR-01", M, "Every configured CSV route read completely: rows 0 to 27, every applicable page and every child or "
     "brand partition, with no production sampling cap", "M09; M10; M62; B07; B28", "G3", "Q4",
     "C1 implemented and proved offline; live coverage unchanged since 2026-11-09: of 302 product listings, 42 "
     "complete (444 products), 38 stopped at a repeated page (2,659 stated, 965 read), 222 not collected (72 measured "
     "at 11,244 products, 150 not measured); the Coupons route apart (OR-04)", "Hamza, then the client",
     "the hold on live work; C1 not yet shown on the live site; the full scope does not fit the trial credit (1.8 "
     "estimate, scenario B: 3,928 to 6,277 submissions a run, USD 5.89 to 9.41 at the list rate); the client's "
     "account and authorization",
     f"one logical run of the candidate in which every planned listing ends DONE or EMPTY by the source's own count "
     f"and every partition union reaches its listing's total (G3 PASS), with listing_pages.csv, "
     f"deferred_requests.json, coverage_reconciliation.csv and coverage_by_csv_row.csv ({Q} §2)",
     f"Hamza decides on S6; S7 (rows 0 to 21 from {QUEUE}, runs of at most 200 submissions) once S6 has recovered "
     f"requests; the full collection on the client's account"],
    ["OR-02", M, "Listings above the 250-result window read through their subdivisions, each reading bound to its "
     "filter and the union reconciled with the listing's total", "B07; M09", "G3", "Q4",
     "13 listings of the queue measured above 250 (5,464 products); none completed live; C1 asks a first page "
     "without filters again (offline proof; the saved Frozen answers stay 24 of 273, incomplete)", "Hamza",
     "the hold; first pages answered without filters (form B) on 2026-11-09; S6b not approved",
     "S6b's run: Natural Organic > Frozen (18010) DONE, every brand reading DONE or EMPTY under its own filter, the "
     "distinct union equal to the total the source reports (273 on 2026-11-09); then the other 12 the same way",
     f"Hamza decides on S6b (86 requests, USD 0.129; {NS})"],
    ["OR-03", M, "Cat Food (row 22, 27021) read completely: 231 distinct products across 232 slots", "M09", "G3",
     "Q4", "unchanged: Q2 read 232 slots holding 231 products (0002310014492 shown twice); the three reads of "
     "2026-11-09 stopped at page 2's repeat", "Hamza", "the hold on live work",
     "a read of every page on the candidate, each judged, the distinct count reconciled with the stated total and "
     "the duplicate slot named", "within S6 (rows 22 to 27 include Cat Food)"],
    ["OR-04", M, "The separate Coupons route (row 0) read in each run that includes it", "M09; M26", "G3; G4",
     "Q4", "unchanged: it lists offers, not products, and is read once per run; on 2026-11-09 it showed 24 cards in "
     "5 reads and none in 5", "Hamza", "the hold on live work; the page's list did not load in half the reads",
     "the route's reading in the qualifying run with its card count and verdict; an answer whose list did not load "
     "recorded as not read, never as zero coupons; no coupon attached to a product without the product's own page",
     "within S7 or the full collection (row 0)"],
    ["OR-05", M, "Digital deals linked to products for the client's examples, with product-bound terms",
     "M26; B29", "G4", "-",
     "0001780014939 complete (kept); 0001780014941 and 0003980014995 unread (pages brought unrendered); "
     "0002310014848 unread and not shown on its rendered product page; headlines kept and flagged, savings-only "
     "payable prices empty", "Hamza / client",
     "product pages are rendered only sometimes (5 of 22 over 2026-11-06 and 2026-11-09; 1 of the 5 showed a "
     "coupon); the hold on live work",
     "for each UPC a rendered product page of store 53100502 PICKUP whose Savings section names the coupon with its "
     "ID, terms (quantity, eligibility, redemption limits), displayed expiry, clipping instruction and qualifying "
     "products naming the product; a rendered page without a Savings section is recorded as such and closes nothing",
     "with or after S6, as Hamza decides; or the client accepts headline-only coupons flagged as unread"],
    ["OR-06", M, "C1 shown on the live site, and the defects a live run finds corrected in a new revision",
     "B45; M10", "G3; G5", "-", "proved offline only (21 C1 cases fail on 1.9.0rc4 and pass on 1.10.0rc3)",
     "Hamza", "the hold on live work",
     "S6's run: deferred_requests.json with every request set aside and every answer, recovered or not, with "
     "request IDs and stored-page hashes; the stage record, ledger rows and run report",
     f"Hamza decides on S6 (130 requests, USD 0.195; {NS})"],
    ["OR-07", M, "At least 500 distinct fresh valid products in one logical run of the candidate", "M36; B26; M37",
     "G5", "Q1", "not run on 1.10.0rc3; S4c's 700 are 1.9.0rc4's, in a run G3 rejected", "Hamza",
     "the hold on live work", f"{Q} Q1 and §2", "S6 can supply it (rows 22 to 27: 1,190 products stated)"],
    ["OR-08", M, "Proof of the designated pickup store on that run", "M14; M15; M16; B02; B25", "G5", "Q2",
     "credited for 1.8.0rc4 and later live runs; not run on 1.10.0rc3", "Hamza", "the hold on live work",
     f"{Q} Q2", "with S6"],
    ["OR-09", M, "Natural missing-product retention", "M64; B32; B13", "G5", "Q3",
     "not observed on any revision; none manufactured", "time (Hamza runs)",
     "two complete runs with a genuine disappearance between them", f"{Q} Q3", "observed when it happens"],
    ["OR-10", M, "An authentic stock transition in a repeat", "M40", "G5", "Q3",
     "not observed; none manufactured", "time (Hamza runs)", "two runs with a genuine availability change",
     "a product whose availability differs between two live observations of the same store and fulfillment, each "
     "with its stored page", "observed when it happens"],
    ["OR-11", M, "Protected full-scope publication", "M32; M33; B18; B33; B28", "G5", "Q4",
     "a refused publication now reported as unsuccessful (exit 6); the last-good protections pass as controls; no "
     "full-scope run", "Hamza, the client", "a complete full-scope run (OR-01); the client's publication target",
     f"{Q} Q4", "after full coverage"],
    ["OR-12", M, "Measured concurrency, runtime and cost of the candidate", "M43; M53; B19; B39", "G6", "Q5",
     "C1 under two lanes proved offline; no measured full run; four departments unmeasured; no confirmed account "
     "rate", "Hamza", "the hold on live work; a comparison stage not yet proposed with a ceiling",
     f"{Q} Q5; the four departments' census", "after S6, a one-lane and two-lane comparison stage for Hamza's "
     "decision"],
    ["OR-13", M, "Client Azure acceptance: install, migrations, suites, Docker, offline replay and the release on "
     "the client's VM", "M01; M42; M44; M68; B03; B24", "G1", "Q6",
     "not executed; nothing attempted for 1.10 (no restart, SSH, key or Azure test: outside this task's authority)",
     "Hamza (timing), then the client",
     "the VM is deallocated; the short window is the owner's decision; the restart and the new key are the client's",
     f"{Q} Q6 (review/ACCEPTANCE_RUNBOOK.md on the client's VM)", "the owner decides when to ask for the window"],
    ["OR-14", M, "Authorized twice-weekly operation per store", "M02; M45; M66; M67; B19", "G6", "Q7",
     "schedules off; capacity stated by test only", "the client, then time", "the client's authorization",
     f"{Q} Q7", "after a protected full-scope publication and the client's authorization"],
    ["OR-15", M, "The client's review and acceptance of a fresh observed run", "M41", "G6", "Q6",
     "not claimed: the client has not reviewed or accepted 1.10.0rc3", "the client",
     "no qualifying run of the candidate yet",
     "the client's own statement after observing the runbook's commands and comparing random records",
     "after Q1 to Q4"],
    ["OR-16", M, "The client's offer and size examples observed live", "B09; B10", "G4", "-",
     "corrected offline with real captures; the products are not in rows 22 to 27", "Hamza",
     "the hold on live work",
     "the examples observed fresh in a qualifying run with their offer wording and size exported by the rules",
     "within S7 or the full collection"],
    ["OR-17", M, "A walkthrough of the final release on the client's environment", "M56; B40", "G1", "Q6",
     "credited for 1.8.0rc4 and 1.8.0rc5 on Hamza's workstation; none for 1.10.0rc3", "Hamza, after the client's "
     "access", "the client's VM access", "a recording of the real commands and outputs, labelled, with pending "
     "live work stated", "after the client's VM checks"],
    ["OR-18", M, "Support period and IP terms", "M57; B41", "G10", "-", "not agreed", "the client and Hamza",
     "an agreement", "a signed agreement", "agree the terms"],
    ["OR-C1", C, "The Classic Web Scraper API route", "M51; B20; B21; B23", "G6", "-",
     "disabled; Mariano's pins probe 1.7.3; Walmart's corrected 1.7.4 linked, not adopted",
     "the client (choice, approval); Hamza (the pin)",
     "the client's choice; no documented Classic page parameter for Mariano's", "a documented page contract and an "
     "approved build", "only if the client chooses it; moving the pin to 1.7.4 is the owner's decision"],
    ["OR-C2", C, "Restoring the Scrapfly browser route", "M58; M59; M60", "G9", "-", "not chosen; not used",
     "the client; the provider", "a decision", "a served session verifying the store", "only if chosen"],
    ["OR-C3", C, "The Kroger production API", "M50", "G9", "-", "not chosen; production approval absent",
     "the Kroger account owner", "Kroger's production approval", "a production token and a same-store comparison",
     "only if chosen"],
    ["OR-C4", C, "A second live store", "M04", "G9", "-", "not named", "the client", "a decision",
     "the new store key run isolated, with its own store checks", "only if the client names one"],
    ["OR-C5", C, "Lifting the hold on live work; the ceilings of S6 and S6b", "-", "G3", "-",
     "on hold; S6 and S6b proposed, not approved; S7 and full collection deferred", "Hamza", "Hamza's decision",
     f"Hamza's explicit approval of each stage's ceiling, recorded before it runs ({NS})", "decide"],
]

matrix = list(csv.DictReader(MATRIX.open(encoding="utf-8", newline="")))
known = {r["id"]: r for r in matrix}
named: set[str] = set()
for r in ROWS:
    assert len(r) == len(HEAD), r[0]
    for mid in (x.strip() for x in r[3].split(";")):
        if mid != "-":
            assert mid in known, (r[0], mid)
            named.add(mid)
    for g in (x.strip() for x in r[4].split(";")):
        assert g in {f"G{i}" for i in range(1, 11)}, (r[0], g)
# Every matrix row whose own columns leave something to do must appear here.
open_rows = {i for i, r in known.items() if r["remaining_action"].strip().lower() not in ("none", "")
             or r["status"].split()[0] in ("PARTIAL", "BLOCKED", "NOT")}  # fmt: skip
# Closed by its own columns although its remaining action carries a qualifier; excepted by its exact text, so that
# any change to the row brings it back to this check.
CLOSED_AS_WRITTEN = {"M28": ("SYNTHETIC TEST", "none (no live card showed one)", "none")}
for mid, (status, action, owner) in CLOSED_AS_WRITTEN.items():
    r = known[mid]
    assert (r["status"], r["remaining_action"], r["next_owner"]) == (status, action, owner), mid
    open_rows.discard(mid)
missing = sorted(open_rows - named)
assert not missing, missing
with OUT.open("w", encoding="utf-8", newline="") as fh:
    w = csv.writer(fh, lineterminator="\n")
    w.writerow(HEAD)
    w.writerows(ROWS)
print(len(ROWS), "items:", sum(r[1] == M for r in ROWS), "mandatory,", sum(r[1] == C for r in ROWS),
      "conditional; matrix rows named:", len(named), "of", len(known))  # fmt: skip
