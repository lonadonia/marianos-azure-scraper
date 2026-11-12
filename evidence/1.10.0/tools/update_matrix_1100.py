"""Adds the 1.10.0rc3 state to review/ACCEPTANCE_MATRIX.csv without rewriting any earlier column: two new columns,
``status_1.10.0rc3`` and ``evidence_1.10.0rc3``. 1.10.0rc3 is an offline candidate: no row gains live evidence from
it, and the earlier columns stand for the revisions they name (live evidence of 1.9.0rc4 or earlier does not qualify
1.10.0rc3)."""

from __future__ import annotations

import csv
import io
import json
import sys
from pathlib import Path

PATH = Path(sys.argv[1])
# The values measured by this task, filled in before the CSV is written (never substituted into the CSV text):
# "suites" (what the candidate's offline suites gave, in words, from the test records) and "ledger_line".
FACTS = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
SUITES, LEDGER_LINE = FACTS["suites"], FACTS["ledger_line"]
R ="review/TECHNICAL_REPORT_1.10.0.md"
E = "evidence/1.10.0"
Q = f"{E}/QUALIFICATION_EVIDENCE_REQUIREMENTS.md"
OUT = "review/OUTSTANDING_REQUIREMENTS_1.10.0.csv"
UNCHANGED = (
    "UNCHANGED BY 1.10: 1.10.0rc3 is an offline candidate and ran no live stage; `status` and `status_1.9.0rc4` "
    f"stand for the revisions they name and do not qualify 1.10.0rc3; {SUITES}",
    f"{E}/tests/",
)
S = {
    "M01": ("NOT EXECUTED: nothing attempted for 1.10 (no VM restart, no SSH connection, no key installed, no Azure "
            "test: outside this task's authority); the client's VM stays deallocated; when to ask for the short "
            "window is the owner's decision", f"{R} §11; {Q} (Q6); {OUT}"),
    "M02": ("NOT ENABLED: schedules off; the C1 waits fall inside a run (each re-ask at least 300 s after the "
            "previous answer, at most 2 per request, other listings read meanwhile); the twice-weekly fit is not "
            "re-measured", f"{R} §3.3; {Q} (Q7)"),
    "M05": ("OFFLINE, SYNTHETIC (C1): a worker killed while a re-ask is out resumes with that re-ask counted, its "
            "reservation held once as possibly charged, at most one re-ask left and at least 300 s later, no "
            "completed page asked again (test_c1_a_worker_killed_while_a_reask_is_out_...); live evidence stays "
            "1.9.0rc4's (S5b2)", f"{R} §4 case 4; {E}/c1/CASES_BEFORE_AFTER.csv"),
    "M09": ("OPEN, COVERAGE UNCHANGED: C1 implemented and proved offline (a request answered with a repeat, or "
            "above the window without filters, is asked again at most twice); no live run, so the queue of "
            "2026-11-09 stands: 42 of 302 product listings complete, 38 stopped at a repeated page, 222 not "
            "collected, the Coupons route apart; Cat Food 231 of 232 slots", f"{R} §3, §4, §7; {OUT}; "
            "evidence/1.9.0/live/INCOMPLETE_QUEUE_190.csv"),
    "M10": ("OFFLINE (C1): a later page answered with earlier pages' products is set aside and asked again instead "
            "of ending the listing; a genuine next page resumes the traversal and only new products count; replay "
            "of the saved Batteries answers read to 96 of 96; live pagination evidence stays 1.8.0rc4's",
            f"{R} §4 cases 1, 2; {E}/c1/CASES_BEFORE_AFTER.csv"),
    "M13": ("OFFLINE (C1): spent re-asks leave a listing INCOMPLETE with its original reason followed by what each "
            "re-ask brought; never DONE or EMPTY because re-asks ran out", f"{R} §3.4, §4 cases 1, 3"),
    "M17": ("PRESERVED: 22 fields, in order, all strings, gupc and unit_price empty (tests/unit/test_schema.py passes "
            "on 1.10.0rc3); C1 adds the file deferred_requests.json beside the export, no field", f"{R} §7; "
            f"{E}/tests/"),
    "M24": ("PRESERVED: the two PPM traces (0084024314377 at $19.99/oz, 0001280052496 at $7.99/oz) exported as "
            "displayed and flagged, unchanged; their tests pass on 1.10.0rc3", f"{R} §7; evidence/1.9.0/m3_ppm/"),
    "M26": ("PARTIAL, RE-CHECKED IN THE SAVED SOURCES: 0001780014939 complete (coupon 4257015, kept); 0001780014941 "
            "and 0003980014995 unread (pages brought unrendered); 0002310014848 unread AND not shown on its rendered "
            "product page (stage O1 request 7524541411266425857: no Savings section); headlines kept and flagged, "
            "savings-only payable prices left empty; completing them needs rendered product pages (live)",
            f"{R} §7, §8; {E}/coupons/COUPON_EVIDENCE_CHECK.json"),
    "M31": ("CORRECTED OFFLINE (cf3b8eb, kept apart from C1): a validated run whose automatic publication is refused "
            "now ends unsuccessful (exit 6, ERROR PUBLICATION_REFUSED, summary.publication) instead of exit 0; "
            "reproduced on 1.9.0rc4 (3 cases fail there, 3 controls pass on both)", f"{R} §5; "
            f"{E}/publication_result/"),
    "M32": ("PRESERVED (controls on both revisions): a refused publication left the last published dataset in place; "
            "C1's repeat case, rejected by G3, left the pointer, latest.json, manifest and products file unchanged",
            f"{R} §4 case 1, §5"),
    "M33": ("UNCHANGED (live 1.8.0rc3 on a local target); a refused publication is now reported as unsuccessful "
            "(M31); a production target still awaits the client's approval", f"{R} §5; {Q} (Q4)"),
    "M34": ("OFFLINE, SYNTHETIC (C1): a re-ask is counted and committed before it is sent; one cut by a killed "
            "worker stays counted, its reservation held once as possibly charged; live evidence stays 1.9.0rc4's",
            f"{R} §3.3, §4 case 4"),
    "M36": ("NOT QUALIFIED FOR 1.10.0rc3: no live run of the candidate. S4c's 700 distinct fresh valid products are "
            "1.9.0rc4's, in a run G3 rejected, and are not counted for 1.10.0rc3; what the later run must show is "
            "fixed in advance (Q1)", f"{R} §7; {Q} (Q1); {OUT}"),
    "M37": ("PENDING FOR THE CANDIDATE: the run report a qualifying run of 1.10.0rc3 must carry is specified (runtime, "
            "totals, coverage, duplicates, deal and PPM examples, store proof, cost); none exists yet",
            f"{Q} §2"),
    "M38": ("OFFLINE, SYNTHETIC (C1): see M05 and M34; live recovery evidence stays 1.9.0rc4's", f"{R} §4 case 4"),
    "M39": ("NOT RUN ON 1.10.0rc3: earlier repeats stand for their revisions; a carried record keeps its own date while "
            "a page repeats (control on both revisions)", f"{R} §4 case 5"),
    "M40": ("NOT OBSERVED: none manufactured; it needs two runs with a genuine change between them", f"{Q} (Q3); "
            f"{OUT}"),
    "M41": ("NOT CLAIMED: the client has not reviewed or accepted 1.10.0rc3", f"{OUT}"),
    "M42": ("CARRIED, NOT FOR 1.10: the 1.7.0rc2 Azure test-VM evidence covers neither 1.10.0rc3 nor the client's VM; "
            "no Azure test in this task", f"{Q} (Q6)"),
    "M43": ("NOT CLOSED: C1 under two lanes proved offline (synthetic: 2 requests in flight at most, each request set "
            "aside asked once more, every page row with its stored page, G13 PASS); the gain of a second lane is not "
            "measured", f"{R} §4 case 4; {Q} (Q5)"),
    "M44": ("NOT EXECUTED: no Docker host used; waits for the client's VM", f"{Q} (Q6)"),
    "M51": ("NOT TESTED: Classic disabled; Mariano's still pins probe 1.7.3; Walmart's corrected probe 1.7.4 (a "
            "Windows supervisor fix, its proof Walmart's) is linked, not adopted: moving the pin is the owner's "
            "decision", "review/SHARED_CLASSIC_PROBE.md; " f"{R} §10"),
    "M52": (f"NO SPENDING IN 1.10: no request sent; the shared trial ledger read, not written ({LEDGER_LINE})",
            f"{E}/budget/LEDGER_STATUS.json"),
    "M53": ("PARTIAL: measurements unchanged; C1 adds at most 2 submissions per request set aside, each reserved at "
            "its worst case, and waits of at least 300 s that other listings fill; no measured full run",
            f"{R} §3.3, §9; {E}/budget/NEXT_STAGES.json; {Q} (Q5)"),
    "M56": ("UNCHANGED: the walkthrough is 1.8.0rc4's and 1.8.0rc5's on Hamza's workstation; none recorded for "
            "1.10.0rc3 or on the client's environment", f"{OUT}"),
    "M57": ("OPEN: support and IP terms not agreed", f"{OUT}"),
    "M62": ("OFFLINE (C1): a listing whose request was set aside and not recovered keeps its original reason with "
            "what each re-ask brought; deferred_requests.json exported by a run that set any aside",
            f"{R} §3.4, §3.5"),
    "M67": ("UNCHANGED: schedules off (shipped configuration); nothing enabled in this task", f"{R} §11"),
    "M68": ("NOT EXECUTED: no Azure test in this task", f"{Q} (Q6); {OUT}"),
    "M69": ("WORKSTATION: the test sessions' throwaway PostgreSQL servers end with each session; the stage database "
            "stays stopped; no timer, schedule, VM or provider session opened", f"{E}/tests/"),
    "B04": ("OFFLINE (C1): a repeated page still never advances the listing; it is set aside and asked again, and a "
            "re-ask's products count only when new to the listing", f"{R} §3.4, §4"),
    "B05": ("OFFLINE, SYNTHETIC (C1): the checkpoint stays at the request set aside; a resume finds it with its "
            "history, and no completed page is asked again", f"{R} §3.3, §4 case 4"),
    "B06": ("UNCHANGED DIAGNOSIS: form A/B is a correlation observed on 2026-11-09, its cause not established; C1 "
            "reacts to what an answer contains, not to a cause", f"{R} §3.1"),
    "B07": ("PARTIAL: a first page above the window that names no subdivision is asked again for its filters; every "
            "brand reading must answer for its own filter and the union must reach the total (synthetic; the replay "
            "of Frozen stays 24 of 273, incomplete); no live partitioned union (S6b proposed, not approved)",
            f"{R} §3, §4 case 3, §9"),
    "B08": ("OFFLINE (C1): runs that set a request aside export deferred_requests.json with every answer; the "
            "coverage files keep their form", f"{R} §3.5"),
    "B13": ("PRESERVED (control on both revisions): products carried from an earlier run keep its date while a page "
            "repeats", f"{R} §4 case 5"),
    "B18": ("OFFLINE: the refused-publication result corrected (exit 6); the last-good protections pass as controls on "
            "both revisions", f"{R} §5; {E}/publication_result/"),
    "B20": ("UNCHANGED PIN: Mariano's keeps probe 1.7.3 (classic-probe-1.7.3/); Walmart's 1.7.4 and its Windows "
            "regression linked, attributed to Walmart", "review/SHARED_CLASSIC_PROBE.md"),
    "B22": ("OFFLINE, SYNTHETIC (C1): each re-ask reserved at its worst case in the collector's ledger and at the "
            "account-wide gate before dispatch; a re-ask the ceiling refuses is neither sent nor counted; no live "
            "stage", f"{R} §3.3, §4 case 4"),
    "B26": ("NOT QUALIFIED FOR 1.10.0rc3 (see M36)", f"{Q} (Q1)"),
    "B28": ("NOT MET: live coverage unchanged (M09); S6 and S6b proposed, not approved; S7 and full collection "
            "deferred", f"{R} §7, §9; {OUT}"),
    "B29": ("NOT EXTENDED, COUNT CORRECTED: stage O1's saved answers state run_js true for 3 of 14 product pages, "
            "not 1 of 14 (2 of 8 on 2026-11-09)", f"{R} §8"),
    "B35": ("OFFLINE (C1): each request set aside keeps every answer: request asked, context returned, product "
            "identities, stored page SHA-256, fetch ID, provider request ID, counts, verdict and what followed",
            f"{R} §3.5"),
    "B36": ("KEPT: C1 proved offline only; replays of saved answers and synthetic pages labelled as such; no 1.9 "
            "result relabelled as 1.10", f"{R} §4"),
    "B39": ("PARTIAL: C1's worst case stated (at most 2 submissions per request set aside); S6 and S6b priced at the "
            "list rate; no account rate confirmed", f"{E}/budget/NEXT_STAGES.json"),
    "B42": ("BEFORE PUBLICATION: the candidate's tree extracted with its line ends unconverted, checked file for file "
            "against the tree before and after, installed from its lock, and its unit suite, C1 cases, publication "
            "cases, ruff, format and mypy run there (the whole integration suite ran in the development worktree "
            "at the same commit); the published tag is checked again from a fresh clone after the push (checksums "
            "written last, frozen trees)", f"{E}/tests/; manifests/"),
    "B43": ("NOTHING SENT: no message to the client or a provider, no request, no purchase, no schedule, no "
            "publication of data", f"{R} §1"),
    "B45": ("OPEN FOR THE CANDIDATE: no live run of 1.10.0rc3; what it still needs validated live is named (S6 for "
            "C1, then Q1 to Q7); the parser-version defect found by its own unit suite on 1.10.0rc2 was corrected in "
            "1.10.0rc3", f"{R} §6, §9; {Q}"),
}

text = PATH.read_bytes().decode("utf-8")
rows = list(csv.reader(io.StringIO(text)))
head, body = rows[0], rows[1:]
assert "status_1.10.0rc3" not in head and head[-2:] == ["status_1.9.0rc4", "evidence_1.9.0rc4"], head
assert all(len(r) == len(head) for r in body)
ids = {r[0] for r in body}
unknown = set(S) - ids
assert not unknown, unknown
out = io.StringIO()
w = csv.writer(out, lineterminator="\n")
w.writerow([*head, "status_1.10.0rc3", "evidence_1.10.0rc3"])
for r in body:
    w.writerow([*r, *S.get(r[0], UNCHANGED)])
PATH.write_bytes(out.getvalue().encode("utf-8"))
check = list(csv.reader(io.StringIO(out.getvalue())))
assert {len(r) for r in check} == {len(head) + 2}, "uneven rows"
assert "@@" not in out.getvalue(), "placeholder left"
print(len(body), "rows;", len(S), "with a 1.10 statement;", len(body) - len(S), "unchanged")
