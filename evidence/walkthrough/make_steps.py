"""Write the steps of the 1.8.0rc4 walkthrough (steps_180.json) for record_cast.py."""
import json
from pathlib import Path

Q = "/c/m6/tools/q180.sh"
SHOW = "/c/m6/walk/show.sh"
STORE = "marianos-53100502-pickup"
Q1C = "01M6E49AHDXSQA04JQZ0HZ40GH"
EXP = "C:/m6/q180/exports"
QWT = "C:/m6/qwt/headless/marianos-azure-headless"


def sh(cmd: str, save: str, **kw: object) -> dict:
    return {"cmd": cmd, "argv": ["bash", "-c", cmd], "save": save, **kw}


steps = [
    {"say": [
        "Mariano's collector 1.8.0rc4: a recorded walkthrough.",
        "Recorded on 2026-11-02 on Hamza's workstation (Windows 11), NOT on the client's VM. Every command below runs",
        "for real while it is recorded, and its output appears as it arrives; nothing is typed in afterwards. The",
        "collector writes JSON lines: they are shown one line per event (time, level, event, message), cut at the",
        "screen's width. The whole outputs are kept beside this recording. The video shortens idle time only.",
        "",
        "Live scope: store 53100502 Marianos Vernon Hills, 1720 N Milwaukee Ave, Vernon Hills IL 60061, PICKUP, through",
        "the Oxylabs Web API on Hamza's own account (not the client's Classic account). CSV rows 22-27 only: a",
        "qualification scope, NOT the client's full category list. q180.sh sets this stage's database, configuration,",
        "data folder and key file, then runs the collector's command line (python -m marianos_headless.cli).",
    ]},
    sh(f"git -C C:/m6/qwt log -1 --format='%H %s'", "release"),
    sh(f"git -C C:/m6/qwt status --short | wc -l", "clean_checkout"),
    sh(f"bash {Q} --version", "version"),
    sh(f"bash {Q} validate-config --check-db | bash {SHOW} result -", "validate_config"),
    {"say": [
        "Earlier today at this store (same stage, same database):",
        "  Q1  (1.8.0rc1) stopped itself at the canary: a product's data stated its price for no store. Fixed in rc2.",
        "  Q1b (1.8.0rc2) stopped itself on three grids drawn as 'mini' product cards. Fixed in rc3.",
        "  Q1c (1.8.0rc3) was killed hard while a page was in flight, resumed, read rows 23-26 to their end and was",
        "      published to this stage's own local folder: it is the last-good dataset now.",
        "  1.8.0rc4 fixes two defects found in Q1c's export (coverage files not read back; collector version 1.7.0).",
    ]},
    sh(f"bash {Q} status --store {STORE} | bash {SHOW} status -", "status_before"),
    sh(f"bash {SHOW} run {Q1C}", "q1c_segments"),
    {"say": [
        "Q2: the repeat run, started now from 1.8.0rc4, rows 22-27 (rows 23-26 repeat Q1c). After its fourth collected",
        "page step the collector is killed hard (taskkill /F /T), as if the machine stopped; then it is resumed.",
    ]},
    sh(
        f"bash {Q} run --store {STORE}",
        "q2_run",
        view="events",
        kill_after={
            "event": "PAGE_COLLECTED",
            "count": 4,
            "cmd": r"powershell -NoProfile -ExecutionPolicy Bypass -File C:\m6\tools\q180_kill.ps1 -Out C:\m6\q180\ev\q2_kill.txt",
            "argv": ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", r"C:\m6\tools\q180_kill.ps1",
                     "-Out", r"C:\m6\q180\ev\q2_kill.txt"],
            "save": "q2_kill",
        },
    ),
    sh(f"bash {Q} status --store {STORE} | bash {SHOW} status -", "status_after_kill"),
    sh(f"bash {Q} resume --store {STORE}", "q2_resume", view="events"),
    sh(f"bash {SHOW} run {{RUN}}", "q2_segments"),
    sh(f"bash {SHOW} pages {{RUN}}", "q2_pages"),
    sh(f"bash {Q} export --run {{RUN}} --out {EXP}/{{RUN}} | bash {SHOW} result -", "q2_export"),
    sh(f"bash {Q} validate-export --run {{RUN}} | bash {SHOW} result -", "q2_validate"),
    sh(f"bash {SHOW} coverage {EXP}/{{RUN}}", "q2_coverage"),
    sh(f"bash {SHOW} records {EXP}/{{RUN}} 2", "q2_records"),
    sh(f"bash {SHOW} flagged {EXP}/{{RUN}}", "q2_flagged"),
    sh(f"bash {SHOW} compare {EXP}/{Q1C} {EXP}/{{RUN}}", "q1c_vs_q2"),
    sh(f"bash {Q} status --store {STORE} | bash {SHOW} status -", "status_end"),
    {"say": ["The regressions of the client's findings and of today's fixes (pagination, promotions, pack size, price",
             "attribution, the two rc4 export defects), on their own test database:"]},
    sh(
        f"bash /c/m6/tools/t2.sh {QWT} marianos_test_walk tests/unit/test_client_findings_180.py "
        "tests/unit/test_export_manifest_180.py tests/integration/test_page_regressions.py -p no:randomly",
        "regressions",
    ),
    {"say": [
        "Not shown here, and not done:",
        "  - the client's full category list (28 rows) has not been collected at this store; rows 22-27 only;",
        "  - the Oxylabs Classic probe has never sent a request: its live mode is disabled pending approval;",
        "  - publication went only to this stage's own local folder; schedules stay disabled;",
        "  - the checks on the client's VM are reported separately (offline only, no provider request).",
        "End of the walkthrough.",
    ]},
]
doc = {"title": "Mariano's collector 1.8.0rc4 walkthrough (recorded 2026-11-02)", "steps": steps}
Path(r"C:\m6\walk\steps_180.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", "utf-8")
print("ok", len(steps))
