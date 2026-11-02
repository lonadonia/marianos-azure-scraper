"""Write the steps of part 2 of the 1.8.0rc4 walkthrough (steps_180_part2.json) for record_cast.py."""
import json
from pathlib import Path

Q = "/c/m6/tools/q180.sh"
SHOW = "/c/m6/walk/show.sh"
STORE = "marianos-53100502-pickup"
Q1C = "01M6E49AHDXSQA04JQZ0HZ40GH"
Q2 = "01M6E5V6CASQ8F00VC8PE9TFYW"
EXP = "C:/m6/q180/exports"
QWT = "C:/m6/qwt/headless/marianos-azure-headless"


def sh(cmd: str, save: str, **kw: object) -> dict:
    return {"cmd": cmd, "argv": ["bash", "-c", cmd], "save": save, **kw}


steps = [
    {"say": [
        "Mariano's collector 1.8.0rc4: walkthrough, PART 2 (recorded 2026-11-02 on Hamza's workstation, Windows 11, NOT",
        "on the client's VM). Every command runs for real while it is recorded; nothing is typed in afterwards.",
        "",
        "Why there is a part 2: part 1 ended without warning at 13:45:43Z. The workstation ran short of memory (a web",
        "browser opened for a sign-in) and the tool that ran the recording stopped its background tasks: the recorder,",
        "and the collector with it, in the middle of Q2's resume (row 26 School Office, after its fourth page step). It",
        "is a second, UNPLANNED forced stop of Q2 (the first, at 13:13:01Z, was the planned kill). Nothing else changed:",
        "same release 1.8.0rc4, same database, same configuration, same limits (95 submissions per run; ceiling 200 /",
        "USD 0.30). Q2 is resumed once more below; then its export and checks, which part 1 did not reach.",
        "",
        "Live scope: store 53100502 Marianos Vernon Hills, 1720 N Milwaukee Ave, Vernon Hills IL 60061, PICKUP, through",
        "the Oxylabs Web API on Hamza's own account (not the client's Classic account). CSV rows 22-27 only: a",
        "qualification scope, NOT the client's full category list.",
    ]},
    sh("git -C C:/m6/qwt log -1 --format='%H %s'", "p2_release"),
    sh(f"bash {Q} status --store {STORE} | bash {SHOW} status -", "p2_status_before"),
    sh(f"bash {SHOW} run {Q2}", "p2_segments_before"),
    {"say": ["Q2 as the stop left it: its second segment is still open and one submission is still 'reserved'. The",
             "resume below must close that segment as abandoned and settle the submission as unknown (possibly charged)."]},
    sh(f"bash {Q} resume --store {STORE}", "p2_resume", view="events"),
    sh(f"bash {SHOW} run {Q2}", "p2_segments"),
    sh(f"bash {SHOW} pages {Q2}", "p2_pages"),
    sh(f"bash {Q} export --run {Q2} --out {EXP}/{Q2} | bash {SHOW} result -", "p2_export"),
    sh(f"bash {Q} validate-export --run {Q2} | bash {SHOW} result -", "p2_validate"),
    sh(f"bash {SHOW} coverage {EXP}/{Q2}", "p2_coverage"),
    sh(f"bash {SHOW} records {EXP}/{Q2} 2", "p2_records"),
    sh(f"bash {SHOW} flagged {EXP}/{Q2}", "p2_flagged"),
    sh(f"bash {SHOW} compare {EXP}/{Q1C} {EXP}/{Q2}", "p2_q1c_vs_q2"),
    sh(f"bash {Q} status --store {STORE} | bash {SHOW} status -", "p2_status_end"),
    {"say": ["The regressions of the client's findings and of today's fixes (pagination, promotions, pack size, price",
             "attribution, the two rc4 export defects), on their own test database:"]},
    sh(
        f"bash /c/m6/tools/t2.sh {QWT} marianos_test_walk tests/unit/test_client_findings_180.py "
        "tests/unit/test_export_manifest_180.py tests/integration/test_page_regressions.py -p no:randomly",
        "p2_regressions",
    ),
    {"say": [
        "Not shown here, and not done:",
        "  - the client's full category list (28 rows) has not been collected at this store; rows 22-27 only;",
        "  - the Oxylabs Classic probe has never sent a request: its live mode is disabled pending approval;",
        "  - publication went only to this stage's own local folder; schedules stay disabled;",
        "  - the checks on the client's VM are reported separately (offline only, no provider request).",
        "End of the walkthrough (part 2 of 2).",
    ]},
]
doc = {"title": "Mariano's collector 1.8.0rc4 walkthrough, part 2 (recorded 2026-11-02)", "steps": steps}
Path(r"C:\m6\walk\steps_180_part2.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", "utf-8")
print("ok", len(steps))
