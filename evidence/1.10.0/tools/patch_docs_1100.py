"""Edits the shared documents of the repository for the 1.10.0rc3 publication, by exact replacements: each old text
must occur exactly once, or nothing is written. Earlier texts stay at their tags.

    python -I patch_docs_1100.py <staging repository> <tag>

- review/ACCEPTANCE_RUNBOOK.md: the runbook names 1.10.0rc3, its tag, its tests and what remains;
- review/SHARED_CLASSIC_PROBE.md: the pin stays at 1.7.3; Walmart's 1.7.4 is linked and attributed to Walmart;
- review/TECHNICAL_REPORT_1.9.0.md and review/COST_AND_RUNTIME_REPORT.md: a note under each title (the text unchanged);
- review/TECHNICAL_REPORT.md (1.8.0rc5): its existing note points to the 1.10.0 report for the current state."""

from __future__ import annotations

import sys
from pathlib import Path

REPO, TAG = Path(sys.argv[1]), sys.argv[2]
T19 = "review-1.9.0rc4-20261109"
W_TAG = "review-1.6.8-probe174-20261111"
W = f"https://github.com/lonadonia/walmart-azure-scraper/tree/{W_TAG}"
WB = f"https://github.com/lonadonia/walmart-azure-scraper/blob/{W_TAG}"
AFTER_TITLE = "\x00after the title"  # a note put after the file's first line, its H1 title, with a blank line around it

EDITS: dict[str, list[tuple[str, str]]] = {
    "review/ACCEPTANCE_RUNBOOK.md": [
        ("# Acceptance runbook: Mariano's collector 1.9.0rc4\n", "# Acceptance runbook: Mariano's collector 1.10.0rc3\n"),
        ("None of these steps has been done with the client yet. For 1.9.0rc4, Hamza ran steps 1, 3 and 4 on the delivered\n"
         "trees ([`evidence/1.9.0/tests/`](../evidence/1.9.0/tests/)) and checked the published repository from a fresh clone\n"
         "after the push. Step 2, the checks on the client's VM, **has not been executed**: the VM is deallocated, and at the\n"
         "client's request no SSH attempt has been made ([`TECHNICAL_REPORT_1.9.0.md`](TECHNICAL_REPORT_1.9.0.md) §12). The\n"
         "1.8.0rc5 runbook stays at the tag `review-1.8.0rc5-20261102`.\n",
         "None of these steps has been done with the client yet. For 1.10.0rc3, an offline candidate, Hamza ran step 1 on\n"
         "the delivered tree ([`evidence/1.10.0/tests/`](../evidence/1.10.0/tests/)) and checked the published repository\n"
         "from a fresh clone after the push, with step 3's record check; the probe of step 4 is unchanged since 1.9.0rc4.\n"
         "Step 2, the checks on the client's VM, **has not been executed**: the VM is deallocated, and no restart, SSH\n"
         "connection, key installation or Azure test was part of this task\n"
         "([`TECHNICAL_REPORT_1.10.0.md`](TECHNICAL_REPORT_1.10.0.md) §11). The 1.9.0rc4 runbook stays at the tag\n"
         f"`{T19}` and the 1.8.0rc5 runbook at `review-1.8.0rc5-20261102`.\n"),
        ("Paths below are relative to the repository root. `source/` is collector 1.9.0rc4 and",
         "Paths below are relative to the repository root. `source/` is collector 1.10.0rc3 and"),
        (f"git checkout {T19}                      # this delivery's review tag\n",
         f"git checkout {TAG}                     # this delivery's review tag\n"),
        ("git diff --stat review-1.8.0rc5-probe171-20261105 HEAD -- source   # the correction diff since 1.8.0rc5\n",
         f"git diff --stat {T19} HEAD -- source   # the change since 1.9.0rc4 (C1, the publication result)\n"),
        ("uv run marianos-collector --version                           # marianos-azure-headless 1.9.0rc4\n",
         "uv run marianos-collector --version                           # marianos-azure-headless 1.10.0rc3\n"),
        ("- The version is 1.9.0rc4, and lint, format and types are clean\n"
         "  ([`wt_rc4_lint.json`](../evidence/1.9.0/tests/wt_rc4_lint.json)).\n"
         "- The suites pass. On the delivered tree (development commit `8abc2c1`, clean): unit 488 passed\n"
         "  ([`wt_rc4_unit.log`](../evidence/1.9.0/tests/wt_rc4_unit.log)); integration, with PostgreSQL started by\n"
         "  `pgserver`, 183 passed (the full suite against PostgreSQL, 32 min 41 s) ([`wt_rc4_integration.log`](../evidence/1.9.0/tests/wt_rc4_integration.log)). 1.8.0rc5's\n"
         "  576 passed in 26:02 stays its own historical result\n"
         "  ([`evidence/rc5-offline/t_full_rc5_x19b.log`](../evidence/rc5-offline/t_full_rc5_x19b.log)).\n",
         "- The version is 1.10.0rc3, and lint, format and types are clean\n"
         "  ([`cand_ruff_check.log`](../evidence/1.10.0/tests/cand_ruff_check.log),\n"
         "  [`cand_ruff_format.log`](../evidence/1.10.0/tests/cand_ruff_format.log),\n"
         "  [`cand_mypy.log`](../evidence/1.10.0/tests/cand_mypy.log)).\n"
         "- The suites pass. On the delivered tree (development commit `a1040f7`, clean): unit @@UNIT@@\n"
         "  ([`cand_unit.log`](../evidence/1.10.0/tests/cand_unit.log)); integration, with PostgreSQL started by\n"
         "  `pgserver`, @@INTEG@@ ([`cand_integration.log`](../evidence/1.10.0/tests/cand_integration.log)).\n"
         "  1.9.0rc4's 488 and 183 passed ([`evidence/1.9.0/tests/`](../evidence/1.9.0/tests/)) and 1.8.0rc5's 576 passed\n"
         "  in 26:02 ([`evidence/rc5-offline/t_full_rc5_x19b.log`](../evidence/rc5-offline/t_full_rc5_x19b.log)) stay\n"
         "  their own historical results.\n"),
        ("uv run pytest -q tests/unit/test_schedule_capacity.py         # 1.9 M8: the schedule's real capacity\n```\n",
         "uv run pytest -q tests/unit/test_schedule_capacity.py         # 1.9 M8: the schedule's real capacity\n"
         "uv run pytest -q tests/unit/test_reask.py                     # 1.10 C1: the re-ask rules\n"
         "uv run pytest -q tests/integration/test_reask_c1.py           # 1.10 C1: requests set aside and asked again (28)\n"
         "uv run pytest -q tests/integration/test_publication_result.py # 1.10: a refused publication ends unsuccessful (6)\n"
         "```\n\n"
         "The last two files were also run on an unchanged checkout of 1.9.0rc4: there their controls pass and the cases of\n"
         "what 1.10 adds fail ([`evidence/1.10.0/REPRODUCE.md`](../evidence/1.10.0/REPRODUCE.md) has the commands,\n"
         "[`TECHNICAL_REPORT_1.10.0.md`](TECHNICAL_REPORT_1.10.0.md) §4 and §5 the results).\n"),
        ("mkdir -p ~/marianos-190 && cd ~/marianos-190                  # this task's own folder\n"
         f"git clone --branch {T19} https://github.com/lonadonia/marianos-azure-scraper.git && cd marianos-azure-scraper\n",
         "mkdir -p ~/marianos-1100 && cd ~/marianos-1100                # this task's own folder\n"
         f"git clone --branch {TAG} https://github.com/lonadonia/marianos-azure-scraper.git && cd marianos-azure-scraper\n"),
        ("docker build -t marianos-collector:1.9.0rc4 . && docker image inspect marianos-collector:1.9.0rc4 --format '{{.Id}}'\n"
         "docker run --rm --network none marianos-collector:1.9.0rc4 --version\n"
         "docker run --rm --network none marianos-collector:1.9.0rc4 validate-config\n",
         "docker build -t marianos-collector:1.10.0rc3 . && docker image inspect marianos-collector:1.10.0rc3 --format '{{.Id}}'\n"
         "docker run --rm --network none marianos-collector:1.10.0rc3 --version\n"
         "docker run --rm --network none marianos-collector:1.10.0rc3 validate-config\n"),
        ("**Status in this delivery: not executed.** The VM is deallocated. At the client's request no SSH attempt has been\n"
         "made, no rule or key was changed and the VM was not started; the previously attached private key is not used. The\n"
         "checks wait for the client to confirm a restart window and to install `scraper_client_test_v2.pub` with the old\n"
         "key revoked.",
         "**Status in this delivery: not executed.** The VM is deallocated. No restart, SSH connection, key installation or\n"
         "Azure test was part of this task; no rule or key was changed and the previously attached private key is not used.\n"
         "When to ask for the short window is the owner's decision; the checks then wait for the client to restart the VM\n"
         "and to install `scraper_client_test_v2.pub` with the old key revoked."),
        ("stage S5b2 on 2026-11-09, with no completed page asked again\n"
         "([`TECHNICAL_REPORT_1.9.0.md`](TECHNICAL_REPORT_1.9.0.md) §10).\n",
         "stage S5b2 on 2026-11-09, with no completed page asked again\n"
         "([`TECHNICAL_REPORT_1.9.0.md`](TECHNICAL_REPORT_1.9.0.md) §10). 1.10.0rc3 has not run live; how it resumes a\n"
         "request it had set aside, including one cut while it was out, is shown offline\n"
         "([`TECHNICAL_REPORT_1.10.0.md`](TECHNICAL_REPORT_1.10.0.md) §4, case 4).\n"),
        ("[`TECHNICAL_REPORT_1.9.0.md`](TECHNICAL_REPORT_1.9.0.md) §15 separates the developer's remaining work from the access\n"
         "and decisions needed from the client, with dated milestones. In short:\n",
         "[`TECHNICAL_REPORT_1.10.0.md`](TECHNICAL_REPORT_1.10.0.md) §11 and\n"
         "[`OUTSTANDING_REQUIREMENTS_1.10.0.csv`](OUTSTANDING_REQUIREMENTS_1.10.0.csv) give every open item with its owner,\n"
         "blocker, the evidence that would close it and the next action. In short:\n"),
        ("- **A run that completes its scope.** On 2026-11-09 the site answered most later pages in form B (page 1's\n"
         "  products), so every 1.9 run stopped incomplete. The proposed change C1 and the stages S6, S6b and S7 are in\n"
         "  [`TECHNICAL_REPORT_1.9.0.md`](TECHNICAL_REPORT_1.9.0.md) §15.\n",
         "- **A run that completes its scope.** On 2026-11-09 the site answered most later pages in form B (page 1's\n"
         "  products), so every 1.9 run stopped incomplete. 1.10.0rc3 implements C1 (such a request is set aside and\n"
         "  asked again, at most twice, at least five minutes later), proved offline only; the live stages S6 and S6b are\n"
         "  proposed, not approved ([`TECHNICAL_REPORT_1.10.0.md`](TECHNICAL_REPORT_1.10.0.md) §9).\n"),
    ],
    "review/SHARED_CLASSIC_PROBE.md": [
        ("1.7.1 (tag `review-1.8.0rc5-probe171-20261105`), and on 2026-11-09 for **1.7.3**, with the collector 1.9.0rc4 (tag\n"
         "`review-1.9.0rc4-20261109`). The earlier texts stay at their tags.",
         "1.7.1 (tag `review-1.8.0rc5-probe171-20261105`), and on 2026-11-09 for **1.7.3**, with the collector 1.9.0rc4 (tag\n"
         f"`review-1.9.0rc4-20261109`). On @@DATE@@, with the collector 1.10.0rc3 (tag `{TAG}`), the pin stays at\n"
         "1.7.3 and Walmart's probe 1.7.4 is linked below. The earlier texts stay at their tags."),
        ("**The Walmart repository** still pins 1.7.2 (its delivery 1.6.8). The T05 change is in the shared CLI only; giving\n"
         "that repository the same pinned reference to 1.7.3 is a separate publication there, not made with this one.\n",
         "**Walmart's probe 1.7.4 (published by the Walmart project; its proof is Walmart's).** On 2026-11-11 the Walmart\n"
         f"repository published the shared probe **1.7.4** at its tag [`{W_TAG}`]({W}) (commit\n"
         "`00a18947668feb7d54bf5c019654d89bf0ad56a0`). It is 1.7.3 with the session's process supervision on Windows\n"
         "corrected (C2, the client's review of 1.7.2 there): a session runs only once a verified job object holds it, a\n"
         "failure refuses it with no fallback, and a cleanup that cannot be verified stays unknown. Nothing was run for it\n"
         "here and no Walmart file was changed for this publication:\n\n"
         "| | |\n"
         "|---|---|\n"
         f"| Corrected source | [`classic-probe-1.7.4/`]({W}/classic-probe-1.7.4): the probe's tree `07477cc61b2c1aa0871fb17965b132c131314fc6` "
         "(`oxylabs-classic-probe/`), development commit `a1def53747dfabcb2ad9ca97efc421c1e70f0ac6`, on 1.7.3 (`95f96a0`), so it keeps T05 |\n"
         f"| Windows regression | [`evidence/offline-tests/1.7.4-classic-probe/`]({W}/evidence/offline-tests/1.7.4-classic-probe): "
         f"[`REPRODUCE.md`]({WB}/evidence/offline-tests/1.7.4-classic-probe/REPRODUCE.md), "
         f"[`REPRODUCTION_ON_1.7.2_WINDOWS.log`]({WB}/evidence/offline-tests/1.7.4-classic-probe/REPRODUCTION_ON_1.7.2_WINDOWS.log) "
         "(the review tests failing on 1.7.2 by their output), "
         f"[`CANDIDATE_1.7.4_WINDOWS.log`]({WB}/evidence/offline-tests/1.7.4-classic-probe/CANDIDATE_1.7.4_WINDOWS.log) "
         "(passing on 1.7.4) |\n"
         f"| What changed and why | [`review/CLASSIC_PROBE_CORRECTIONS.md`]({WB}/review/CLASSIC_PROBE_CORRECTIONS.md) in the Walmart repository |\n"
         "| The Mariano's adapter | `src/classic_probe/marianos.py`, blob `9de6510bddbb0cae7fd86e09dac5ed32fc3487a4`: unchanged, the same as here |\n\n"
         "**Mariano's keeps the pin at 1.7.3** in this publication: 1.7.4's correction is the process supervision of a\n"
         "probe session on Windows, live Classic stays disabled for Mariano's, and moving the pin is the owner's decision (a\n"
         "separate publication, with the probe's offline suite run on the pinned tree).\n"),
        ("A Classic run for Mariano's, if the client chooses Classic and approves it, would use 1.7.3 or a later corrected\n"
         "revision, never the 1.6.0 copy in `classic-probe/`.",
         "A Classic run for Mariano's, if the client chooses Classic and approves it, would use 1.7.4 or a later corrected\n"
         "revision (1.7.3's Windows supervision is the one 1.7.4 corrects), never the 1.6.0 copy in `classic-probe/`."),
    ],
    "review/TECHNICAL_REPORT_1.9.0.md": [
        (AFTER_TITLE, "> **Note of @@DATE@@: current state in [`TECHNICAL_REPORT_1.10.0.md`](TECHNICAL_REPORT_1.10.0.md)**\n"
                      "> (release 1.10.0rc3). This report is the 1.9.0rc4 report as published on 2026-11-09, unchanged below this\n"
                      "> note. The 1.10.0 report's §8 corrects two of its statements: stage O1's saved answers state `run_js` true for\n"
                      "> **3 of 14** product pages, not 1 of 14 (§6 and §10 here), and 0002310014848's first product page was rendered\n"
                      "> and shows no Savings section.\n"),
    ],
    "review/COST_AND_RUNTIME_REPORT.md": [
        (AFTER_TITLE, "> **Note of @@DATE@@ (release 1.10.0rc3).** Section 0 says the provider rendered 1 of 14 product pages on\n"
                      "> 2026-11-06; the saved answers state **3 of 14** ([`TECHNICAL_REPORT_1.10.0.md`](TECHNICAL_REPORT_1.10.0.md)\n"
                      "> §8), so 5 of 22 over 2026-11-06 and 2026-11-09. No other figure here changes. C1 adds at most 2 submissions\n"
                      "> for each request set aside; the proposed stages S6 and S6b and their ceilings are in\n"
                      "> [`evidence/1.10.0/budget/NEXT_STAGES.json`](../evidence/1.10.0/budget/NEXT_STAGES.json).\n"),
    ],
    "review/TECHNICAL_REPORT.md": [
        ("> **Current state: [`TECHNICAL_REPORT_1.9.0.md`](TECHNICAL_REPORT_1.9.0.md)** (release 1.9.0rc4, 2026-11-09). This report is",
         "> **Current state: [`TECHNICAL_REPORT_1.10.0.md`](TECHNICAL_REPORT_1.10.0.md)** (release 1.10.0rc3, @@DATE@@; release "
         "1.9.0rc4: [`TECHNICAL_REPORT_1.9.0.md`](TECHNICAL_REPORT_1.9.0.md)). This report is"),
    ],
}

plans: dict[Path, str] = {}
for rel, edits in EDITS.items():
    path = REPO / rel
    text = path.read_bytes().decode("utf-8")
    assert "\r" not in text, rel
    for old, new in edits:
        if old == AFTER_TITLE:
            title, rest = text.split("\n", 1)
            assert title.startswith("# ") and rest.startswith("\n") and not rest.startswith("\n>"), rel
            text = title + "\n\n" + new + rest
            continue
        n = text.count(old)
        assert n == 1, (rel, n, old[:80])
        text = text.replace(old, new)
    plans[path] = text
for path, text in plans.items():
    path.write_bytes(text.encode("utf-8"))
    print("edited", path.relative_to(REPO).as_posix())
