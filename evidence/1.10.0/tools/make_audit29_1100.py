"""Adds the 1.10.0rc3 state to review/AUDIT_29_RECONCILIATION.csv beside the unchanged 1.9.0rc4 columns: for each of
the ten groups of the 29 audit items, its state on 1.10.0rc3, the evidence, what remains, who acts next and on what
condition.

The 1.9.0rc4 file's row G7 had 11 fields where 8 belong: its text was put in after the file was written, and its
commas were not quoted. This script re-quotes that row (its text unchanged) and refuses any other uneven row; the
correction is listed in manifests/DOC_CORRECTIONS.md.

    python -I make_audit29_1100.py <review/AUDIT_29_RECONCILIATION.csv> <facts.json>"""

from __future__ import annotations

import csv
import io
import json
import sys
from pathlib import Path

PATH = Path(sys.argv[1])
FACTS = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
SUITES = FACTS["suites"]
R = "review/TECHNICAL_REPORT_1.10.0.md"
E = "evidence/1.10.0"
Q = f"{E}/QUALIFICATION_EVIDENCE_REQUIREMENTS.md"
OUT = "review/OUTSTANDING_REQUIREMENTS_1.10.0.csv"
HEAD_190 = ["group", "audit_items", "required_handling", "state_1.9.0rc4", "evidence", "what_remains", "next_owner",
            "condition"]  # fmt: skip
NEW = ["state_1.10.0rc3", "evidence_1.10.0rc3", "what_remains_1.10.0rc3", "next_owner_1.10.0rc3",
       "condition_1.10.0rc3"]  # fmt: skip
G = {
    "G1": (f"LOCAL CHECKS DONE ON 1.10.0rc3; CLIENT CHECKS NOT EXECUTED: no VM restart, SSH connection, key "
           f"installation or Azure test in this task (outside its authority). On the exact candidate: {SUITES}",
           f"{R} §6, §11; {E}/tests/",
           "install, migrations, suites, Docker and offline replay on the client's VM (review/ACCEPTANCE_RUNBOOK.md)",
           "Hamza (when to ask is the owner's decision), then the client",
           "the owner decides on the short window; the client restarts the VM and installs the new key with the old "
           "one revoked"),
    "G2": ("UNCHANGED: corrected offline in 1.9; the T06 and T07 regressions (test_segment_end_t06.py, "
           "test_partitions_190.py) pass on 1.10.0rc3 within its integration suite; T05 belongs to the probe 1.7.3, "
           "unchanged", f"{R} §6; {E}/tests/", "none offline", "-", "-"),
    "G3": ("C1 DONE OFFLINE; LIVE COVERAGE UNCHANGED: C1 implemented in one change and proved offline (28 tests: the "
           "21 C1 cases fail on 1.9.0rc4 and pass on 1.10.0rc3, the 7 controls pass on both; four on answers saved "
           "on 2026-11-09, two of them replayed through the collector, the rest synthetic, each labelled). No live "
           "stage, so the queue of 2026-11-09 stands: 42 of 302 "
           "product listings complete, 38 stopped at a repeated page, 222 not collected, the Coupons route apart; "
           "Cat Food 231 of 232 slots; no above-window union", f"{R} §3, §4, §7; {E}/c1/; {OUT}",
           "S6 (later-page recovery) and S6b (brand union above the window) on the live site; then S7 and full "
           "coverage", "Hamza, then the client",
           "Hamza lifts the hold and approves S6 (130 requests, USD 0.195) and S6b (86 requests, USD 0.129); S7 "
           "once S6 has recovered requests; full coverage needs the client's account and authorization"),
    "G4": ("PARTIAL, RE-CHECKED IN THE SAVED SOURCES: 0001780014939 complete (kept); 0001780014941 and 0003980014995 "
           "unread (pages brought unrendered); 0002310014848 unread and not shown on its rendered product page; "
           "stage O1 rendered 3 of 14 product pages (corrected from 1 of 14); the PPM traces, offer and size rules, "
           "original URLs and UPCs and the 22-string schema preserved, their tests passing",
           f"{R} §7, §8; {E}/coupons/COUPON_EVIDENCE_CHECK.json",
           "rendered product pages for the three examples, each coupon bound to its product (ID, terms, expiry, "
           "clipping instruction, qualifying products)", "Hamza / client",
           "a live stage approved for rendered product pages, or the client's acceptance of headline-only coupons "
           "flagged as unread"),
    "G5": ("NOT QUALIFIED FOR 1.10.0rc3: no live run of the candidate; 1.9.0rc4's results (S4c's 700, S5b2's "
           "recovery) stay 1.9.0rc4's and are not relabelled; the refused-publication result corrected offline (exit "
           "6; the last-good controls pass on both revisions); the later evidence's contents fixed in advance (Q1 to "
           "Q5)", f"{R} §5, §7; {Q}",
           "a run of the candidate that completes its scope with at least 500 fresh valid products; natural "
           "retention; a protected full-scope publication", "Hamza, then the client",
           "S6 shows requests recovered; a full scope needs the client's account and authorization; retention needs "
           "time and is never manufactured"),
    "G6": ("PARTIAL, LIVE UNCHANGED: C1 under two lanes proved offline (synthetic, G13 PASS); the gain of a second "
           "lane, the four departments' census and a full run are not measured; C1's worst case added to the cost "
           "basis; Classic disabled, Mariano's pin 1.7.3 kept and Walmart's 1.7.4 linked; client acceptance not "
           "claimed", f"{R} §4, §9, §10; {E}/budget/NEXT_STAGES.json; review/SHARED_CLASSIC_PROBE.md",
           "an uninterrupted one-lane against two-lane comparison on the candidate; the four departments' census; "
           "the client's cadence, Classic and acceptance decisions", "Hamza, then the client",
           "a stage approved for the comparison; the client's decisions"),
    "G7": ("DONE IN 1.9 (unchanged). For C1 the same 28 tests were also run on 1.9.0rc4, which lacks C1: its 21 "
           "C1 cases fail there by their own checks and pass on 1.10.0rc3; the 7 controls pass on both",
           f"{R} §4; {E}/c1/CASES_BEFORE_AFTER.csv", "nothing", "-", "-"),
    "G8": ("DONE: 1.10 columns added beside the unchanged earlier ones; corrected: stage O1's rendered product pages "
           "(3 of 14, not 1 of 14), the state of 0002310014848, and this file's row G7 of 1.9.0rc4 (11 fields where "
           "8 belong: re-quoted, text unchanged); times in UTC", f"{R} §8; manifests/DOC_CORRECTIONS.md", "none",
           "-", "-"),
    "G9": ("CONDITIONAL, NOT CHOSEN: none used or enabled; no provider switched", f"{R} §1, §11", "a decision",
           "client", "only if the client chooses one"),
    "G10": ("STATED: Hamza owns the publication and the evidence; the baseline tag, captures, datasets and results "
            "kept unchanged (no tag moved); the coupon re-check read the private captures without changing them; "
            "support and IP terms not agreed", f"{R} §2, §11; {E}/README.md", "the support and IP terms",
            "client and Hamza", "an agreement"),
}

rows = list(csv.reader(io.StringIO(PATH.read_bytes().decode("utf-8"))))
head, body = rows[0], rows[1:]
assert head == HEAD_190, head
assert all(len(v) == len(NEW) for v in G.values())
fixed, rows_out = [], []
for r in body:
    if len(r) != len(head):
        # Only the known case: G7, whose state cell holds three unquoted commas (11 fields).
        assert r[0] == "G7" and len(r) == 11, r
        r = [*r[:3], ",".join(r[3:7]), *r[7:]]
        assert r[3].endswith("the same 29 tests on the unchanged copy, passes") and r[5] == "nothing", r
        fixed.append("G7")
    assert len(r) == len(head), r
    rows_out.append([*r, *G[r[0]]])
assert [r[0] for r in rows_out] == [f"G{i}" for i in range(1, 11)], [r[0] for r in rows_out]
out = io.StringIO()
w = csv.writer(out, lineterminator="\n")
w.writerow([*head, *NEW])
w.writerows(rows_out)
text = out.getvalue()
assert {len(r) for r in csv.reader(io.StringIO(text))} == {len(head) + len(NEW)}, "uneven rows"
assert "@@" not in text, "placeholder left"
PATH.write_bytes(text.encode("utf-8"))
print(len(body), "groups;", "re-quoted:", fixed or "none")
