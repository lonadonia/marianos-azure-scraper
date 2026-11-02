"""Validation gates G1–G14 (brief §12).

Gates are pure functions over a :class:`RunEvidence` snapshot, so the same logic validates live runs,
fixture runs and test inputs. Any FAIL makes the run ineligible for publication. FAIL can never be
overridden.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from marianos_headless.core.findings import DataMode, RunCode, Severity
from marianos_headless.core.schema import OUTPUT_FIELDS, format_violations, shape_violations
from marianos_headless.core.settings import Settings
from marianos_headless.core.text import price_tokens


class GateStatus(StrEnum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass(frozen=True)
class Finding:
    gate: str
    severity: Severity
    code: str
    message: str
    scope: str = "run"  # run | category | node | record
    ref: str | None = None
    metrics: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class GateResult:
    gate: str
    status: GateStatus
    findings: list[Finding] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AttestationSummary:
    phase: str  # preflight | task_start | periodic | final
    passed: bool
    failed_checks: tuple[str, ...] = ()


@dataclass(frozen=True)
class CategoryOutcome:
    row_index: int
    name: str
    status: str  # DONE | FAILED | BLOCKED | INCOMPLETE | SKIPPED
    assigned_records: int = 0
    prior_good: int | None = None
    zero_rule_holds: bool = False  # explicit "no results" state and prior baseline also 0
    node_coverage: Mapping[str, float] = field(default_factory=dict)


@dataclass
class RunEvidence:
    mode: DataMode
    attestations: Sequence[AttestationSummary] = ()
    challenges_detected: int = 0
    categories: Sequence[CategoryOutcome] = ()
    exported_records: Sequence[Mapping[str, str]] = ()
    # The identity of each exported record, in the same order: its UPC, or the retailer's own product ID
    # where the listing shows no UPC (Walmart ``wm:<item id>``). Empty: the records' ``upc`` field.
    exported_keys: Sequence[str] = ()
    valid_upcs: frozenset[str] = frozenset()  # identities of the valid records
    # Fields every exported record must fill (G8). ``upc`` is required where the retailer shows it on
    # every listing (Mariano's); Walmart shows UPCs only on product pages ("scrape when available").
    required_fields: tuple[str, ...] = ("product_title", "url", "upc", "category")
    canary_upcs: Sequence[str] = ()
    price_comparisons: int = 0
    price_mismatches: int = 0
    contract_canary_ok: bool | None = None
    captured_schema_failures: int = 0
    tasks_all_terminal: bool | None = None
    artifact_hashes_verified: bool | None = None
    manifest_complete: bool | None = None


def record_keys(ev: RunEvidence) -> list[str]:
    if ev.exported_keys:
        return list(ev.exported_keys)
    return [r.get("upc", "") for r in ev.exported_records]


def _status(findings: Sequence[Finding]) -> GateStatus:
    if any(f.severity is Severity.FAIL for f in findings):
        return GateStatus.FAIL
    if any(f.severity is Severity.WARN for f in findings):
        return GateStatus.WARN
    return GateStatus.PASS


def g1_location(ev: RunEvidence, s: Settings) -> GateResult:
    f: list[Finding] = []
    phases = {a.phase for a in ev.attestations}
    for required in ("preflight", "final"):
        if required not in phases:
            f.append(Finding("G1", Severity.FAIL, RunCode.LOCATION_MISMATCH, f"no {required} attestation"))
    for a in ev.attestations:
        if not a.passed:
            f.append(
                Finding(
                    "G1",
                    Severity.FAIL,
                    RunCode.LOCATION_MISMATCH,
                    f"{a.phase} attestation failed: {', '.join(a.failed_checks)}",
                )
            )
    return GateResult("G1", _status(f), f, {"attestations": len(ev.attestations)})


def g2_access(ev: RunEvidence, s: Settings) -> GateResult:
    f: list[Finding] = []
    if ev.challenges_detected:
        f.append(
            Finding("G2", Severity.FAIL, RunCode.CHALLENGE_DETECTED, f"{ev.challenges_detected} challenge(s)")
        )
    for c in ev.categories:
        if c.status == "BLOCKED":
            f.append(
                Finding(
                    "G2", Severity.FAIL, RunCode.CHALLENGE_DETECTED, "category blocked", "category", c.name
                )
            )
    return GateResult("G2", _status(f), f)


def g3_coverage(ev: RunEvidence, s: Settings) -> GateResult:
    f: list[Finding] = []
    warn_below = s.gates.coverage_warn_below
    fail_below = s.gates.coverage_fail_below
    if not ev.categories:
        f.append(Finding("G3", Severity.FAIL, RunCode.NODE_INCOMPLETE, "no category outcomes recorded"))
    for c in ev.categories:
        if c.status != "DONE":
            f.append(
                Finding(
                    "G3", Severity.FAIL, RunCode.NODE_INCOMPLETE, f"status {c.status}", "category", c.name
                )
            )
        for node, ratio in c.node_coverage.items():
            if ratio < fail_below:
                f.append(
                    Finding(
                        "G3", Severity.FAIL, RunCode.NODE_INCOMPLETE, f"coverage {ratio:.3f}", "node", node
                    )
                )
            elif ratio < warn_below:
                f.append(
                    Finding(
                        "G3", Severity.WARN, RunCode.NODE_INCOMPLETE, f"coverage {ratio:.3f}", "node", node
                    )
                )
    return GateResult("G3", _status(f), f)


def g4_yield(ev: RunEvidence, s: Settings) -> GateResult:
    f: list[Finding] = []
    if not ev.categories:
        f.append(Finding("G4", Severity.FAIL, RunCode.ZERO_YIELD_SUSPECT, "no category outcomes recorded"))
    for c in ev.categories:
        if c.assigned_records == 0 and not c.zero_rule_holds:
            f.append(
                Finding("G4", Severity.FAIL, RunCode.ZERO_YIELD_SUSPECT, "0 records", "category", c.name)
            )
            continue
        if c.prior_good:
            drop = 1 - c.assigned_records / c.prior_good
            if drop > s.yield_.fail_drop_vs_last_good:
                sev = Severity.FAIL
            elif drop > s.yield_.warn_drop_vs_last_good:
                sev = Severity.WARN
            else:
                continue
            f.append(
                Finding(
                    "G4",
                    sev,
                    RunCode.LOW_YIELD,
                    f"drop {drop:.0%} vs last good",
                    "category",
                    c.name,
                    {"assigned": c.assigned_records, "prior_good": c.prior_good},
                )
            )
    return GateResult("G4", _status(f), f)


def g5_schema(ev: RunEvidence, s: Settings) -> GateResult:
    f = [
        Finding("G5", Severity.FAIL, "SCHEMA_INVALID", "; ".join(p), "record", key)
        for r, key in zip(ev.exported_records, record_keys(ev), strict=True)
        if (p := shape_violations(r))
    ]
    return GateResult("G5", _status(f), f, {"checked": len(ev.exported_records)})


def g6_formats(ev: RunEvidence, s: Settings) -> GateResult:
    f = [
        Finding("G6", Severity.FAIL, "SCHEMA_INVALID", "; ".join(p), "record", key)
        for r, key in zip(ev.exported_records, record_keys(ev), strict=True)
        if (p := format_violations(r))
    ]
    return GateResult("G6", _status(f), f)


def g7_duplicates(ev: RunEvidence, s: Settings) -> GateResult:
    counts = Counter(record_keys(ev))
    dups = {u: n for u, n in counts.items() if n > 1}
    f = [Finding("G7", Severity.FAIL, "DUPLICATE_UPC", f"{n} records", "record", u) for u, n in dups.items()]
    return GateResult("G7", _status(f), f, {"duplicates": sum(n - 1 for n in dups.values())})


def field_completeness(records: Sequence[Mapping[str, str]]) -> dict[str, float]:
    n = len(records)
    if n == 0:
        return {k: 0.0 for k in OUTPUT_FIELDS}
    return {k: sum(1 for r in records if r.get(k)) / n for k in OUTPUT_FIELDS}


def g8_completeness(ev: RunEvidence, s: Settings) -> GateResult:
    records = ev.exported_records
    comp = field_completeness(records)
    f: list[Finding] = []
    for k in ev.required_fields:
        if records and comp[k] < 1.0:
            f.append(Finding("G8", Severity.FAIL, "FIELD_INCOMPLETE", f"{k} {comp[k]:.1%} non-empty", ref=k))
    valid = [r for r, key in zip(records, record_keys(ev), strict=True) if key in ev.valid_upcs]
    if valid:
        priced = sum(1 for r in valid if r.get("regular_price") or r.get("sale_price")) / len(valid)
        if priced < s.gates.price_completeness_warn_below:
            f.append(Finding("G8", Severity.WARN, "FIELD_INCOMPLETE", f"prices {priced:.1%} of valid"))
    if not records:
        f.append(Finding("G8", Severity.FAIL, "FIELD_INCOMPLETE", "no exported records"))
    return GateResult("G8", _status(f), f, {"completeness": comp})


def g9_canaries(ev: RunEvidence, s: Settings) -> GateResult:
    present = {
        key
        for r, key in zip(ev.exported_records, record_keys(ev), strict=True)
        if r.get("regular_price") or r.get("sale_price")
    }
    missing = [u for u in ev.canary_upcs if u not in present]
    sev = Severity.FAIL if s.gates.canary_missing_is_fail else Severity.WARN
    f = [
        Finding("G9", sev, RunCode.CANARY_MISSING, "canary missing or unpriced", "record", u) for u in missing
    ]
    return GateResult("G9", _status(f), f, {"canaries": len(ev.canary_upcs), "missing": len(missing)})


def g10_reconciliation(ev: RunEvidence, s: Settings) -> GateResult:
    f: list[Finding] = []
    rate = ev.price_mismatches / ev.price_comparisons if ev.price_comparisons else 0.0
    if rate > s.gates.reconciliation_fail_above:
        f.append(Finding("G10", Severity.FAIL, "PRICE_DOM_JSON_MISMATCH", f"{rate:.2%} mismatched"))
    elif rate > s.gates.reconciliation_warn_above:
        f.append(Finding("G10", Severity.WARN, "PRICE_DOM_JSON_MISMATCH", f"{rate:.2%} mismatched"))
    return GateResult(
        "G10", _status(f), f, {"compared": ev.price_comparisons, "mismatched": ev.price_mismatches}
    )


def deal_price_supported(description: str, price: str) -> bool:
    """G11: a deal price must appear as a displayed ``$`` amount in its own description."""
    return not price or price in price_tokens(description)


def g11_promotion_sanity(ev: RunEvidence, s: Settings) -> GateResult:
    f: list[Finding] = []
    for r in ev.exported_records:
        for desc_key, price_key in (
            ("volume_deals_description", "volume_deals_price"),
            ("digital_deals_description", "digital_deals_price"),
        ):
            if not deal_price_supported(r.get(desc_key, ""), r.get(price_key, "")):
                f.append(
                    Finding(
                        "G11",
                        Severity.FAIL,
                        "DEAL_PRICE_UNSUPPORTED",
                        f"{price_key} not in {desc_key}",
                        "record",
                        r.get("upc") or None,
                    )
                )
    return GateResult("G11", _status(f), f)


def g12_site_contract(ev: RunEvidence, s: Settings) -> GateResult:
    f: list[Finding] = []
    if ev.contract_canary_ok is not True:
        f.append(Finding("G12", Severity.FAIL, RunCode.SITE_CONTRACT_DRIFT, "contract canary did not pass"))
    if ev.captured_schema_failures:
        f.append(
            Finding(
                "G12",
                Severity.FAIL,
                RunCode.SITE_CONTRACT_DRIFT,
                f"{ev.captured_schema_failures} captured responses failed schema checks",
            )
        )
    return GateResult("G12", _status(f), f)


def g13_integrity(ev: RunEvidence, s: Settings) -> GateResult:
    f: list[Finding] = []
    for name, ok in (
        ("tasks_all_terminal", ev.tasks_all_terminal),
        ("artifact_hashes_verified", ev.artifact_hashes_verified),
        ("manifest_complete", ev.manifest_complete),
    ):
        if ok is not True:
            f.append(Finding("G13", Severity.FAIL, RunCode.INTEGRITY_ERROR, f"{name} not confirmed"))
    return GateResult("G13", _status(f), f)


def g14_contest(ev: RunEvidence, s: Settings) -> GateResult:
    """Contest readiness. A FAIL here marks the run contest-not-ready but does not block publication."""
    f: list[Finding] = []
    valid = [r for r, key in zip(ev.exported_records, record_keys(ev), strict=True) if key in ev.valid_upcs]
    categories = {r.get("category") for r in valid if r.get("category")}
    if ev.mode is not DataMode.LIVE:
        f.append(
            Finding(
                "G14", Severity.FAIL, "CONTEST_NOT_READY", "FIXTURE data never counts as contest evidence"
            )
        )
    if len(valid) < s.contest.min_valid_records:
        f.append(Finding("G14", Severity.FAIL, "CONTEST_NOT_READY", f"{len(valid)} valid records"))
    if len(categories) < s.contest.min_categories:
        f.append(Finding("G14", Severity.FAIL, "CONTEST_NOT_READY", f"{len(categories)} categories"))
    return GateResult("G14", _status(f), f, {"valid_records": len(valid), "categories": len(categories)})


GATES: tuple[tuple[str, Callable[[RunEvidence, Settings], GateResult]], ...] = (
    ("G1", g1_location),
    ("G2", g2_access),
    ("G3", g3_coverage),
    ("G4", g4_yield),
    ("G5", g5_schema),
    ("G6", g6_formats),
    ("G7", g7_duplicates),
    ("G8", g8_completeness),
    ("G9", g9_canaries),
    ("G10", g10_reconciliation),
    ("G11", g11_promotion_sanity),
    ("G12", g12_site_contract),
    ("G13", g13_integrity),
    ("G14", g14_contest),
)

NON_BLOCKING = frozenset({"G14"})


@dataclass
class ValidationOutcome:
    results: list[GateResult]

    @property
    def publishable(self) -> bool:
        return all(r.status is not GateStatus.FAIL for r in self.results if r.gate not in NON_BLOCKING)

    @property
    def contest_ready(self) -> bool:
        return self.publishable and all(r.status is not GateStatus.FAIL for r in self.results)


def run_gates(ev: RunEvidence, s: Settings) -> ValidationOutcome:
    results = [fn(ev, s) for _, fn in GATES]
    if not s.contest.enabled:
        results = [r for r in results if r.gate != "G14"]
    return ValidationOutcome(results)
