"""Store context and attestation checks A1–A8 (brief §4.2, §5.4).

These functions are pure: the worker gathers observations (state, captured request URLs, header text)
and this module decides PASS/FAIL. A missing observation for a required check is a FAIL, never a pass.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from urllib.parse import parse_qs, urlsplit

from marianos_headless.core.settings import AttestationSettings, StoreConfig
from marianos_headless.sites.marianos.initial_state import dig

MODALITY_PREFERENCES_PATH = (
    "calypso",
    "useCases",
    "getModalityPreferences",
    "default",
    "response",
    "data",
    "modalityPreferences",
)
_CMS_SCOPE = re.compile(r"/(?P<state>[A-Z]{2})/(?P<division>\d{3})/(?P<store>\d{5})$")


@dataclass(frozen=True)
class StoreDetails:
    location_id: str
    division_number: str
    store_number: str
    vanity_name: str
    address_lines: tuple[str, ...]
    city: str
    state: str
    postal_code: str
    allowed_modalities: tuple[str, ...]
    brand: str
    banner: str


@dataclass(frozen=True)
class ModalityEntry:
    modality_type: str
    source: str
    is_trusted_source: bool | None
    destination_location_id: str | None


@dataclass(frozen=True)
class StoreContext:
    """What the page state says about the shopping context."""

    active_modality: str | None
    stores: tuple[StoreDetails, ...]
    modalities: tuple[ModalityEntry, ...]
    laf_store_ids: tuple[str, ...]
    has_manually_set_active_modality: bool | None
    cms_scopes: tuple[str, ...]  # "<STATE>/<DIVISION>/<STORE>" suffixes of dynamicdata keys
    site_version: str | None

    def store(self, location_id: str) -> StoreDetails | None:
        return next((s for s in self.stores if s.location_id == location_id), None)

    def active_modality_entry(self) -> ModalityEntry | None:
        return next((m for m in self.modalities if m.modality_type == self.active_modality), None)


def _store_details(raw: Mapping[str, Any]) -> StoreDetails:
    addr = dig(raw, "address", "address", default={}) or {}
    return StoreDetails(
        location_id=str(raw.get("locationId") or ""),
        division_number=str(raw.get("divisionNumber") or ""),
        store_number=str(raw.get("storeNumber") or ""),
        vanity_name=str(raw.get("vanityName") or ""),
        address_lines=tuple(addr.get("addressLines") or ()),
        city=str(addr.get("cityTown") or ""),
        state=str(addr.get("stateProvince") or ""),
        postal_code=str(addr.get("postalCode") or ""),
        allowed_modalities=tuple(raw.get("allowedModalities") or ()),
        brand=str(raw.get("brand") or ""),
        banner=str(raw.get("banner") or ""),
    )


def store_context_from_state(state: Mapping[str, Any]) -> StoreContext:
    prefs = dig(state, *MODALITY_PREFERENCES_PATH, default={}) or {}
    modalities = tuple(
        ModalityEntry(
            modality_type=str(m.get("modalityType") or ""),
            source=str(m.get("source") or ""),
            is_trusted_source=m.get("isTrustedSource"),
            destination_location_id=dig(m, "destination", "locationId"),
        )
        for m in prefs.get("modalities") or ()
    )
    laf_ids = tuple(
        str(sid)
        for laf in prefs.get("lafObject") or ()
        if (sid := dig(laf, "modality", "handoffLocation", "storeId"))
    )
    scopes: list[str] = []
    for key in state.get("dynamicdata") or {}:
        m = _CMS_SCOPE.search(key)
        if m:
            scopes.append(f"{m['state']}/{m['division']}/{m['store']}")
    return StoreContext(
        active_modality=prefs.get("activeModality"),
        stores=tuple(_store_details(s) for s in prefs.get("storeDetails") or ()),
        modalities=modalities,
        laf_store_ids=laf_ids,
        has_manually_set_active_modality=dig(state, "modalitySelectorState", "hasManuallySetActiveModality"),
        cms_scopes=tuple(dict.fromkeys(scopes)),
        site_version=dig(state, "meta", "siteVersion"),
    )


class CheckStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_APPLICABLE = "NOT_APPLICABLE"  # e.g. A4 before any data request was made


@dataclass(frozen=True)
class CheckResult:
    check: str
    status: CheckStatus
    observed: Any
    expected: Any
    message: str = ""


@dataclass(frozen=True)
class AttestationObservation:
    context: StoreContext
    header_vanity_name: str | None = None  # visible header text
    header_postal_code: str | None = None
    data_request_urls: tuple[str, ...] = ()  # captured products-search URLs since the last attestation
    laf_header_store_ids: tuple[str, ...] = ()  # storeId values seen in x-laf-object, if observable


@dataclass
class AttestationResult:
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c.status is not CheckStatus.FAIL for c in self.checks)

    def failures(self) -> list[CheckResult]:
        return [c for c in self.checks if c.status is CheckStatus.FAIL]


def request_location_id(url: str) -> str | None:
    values = parse_qs(urlsplit(url).query).get("filter.locationId")
    return values[0] if values else None


def request_fulfillment_methods(url: str) -> tuple[str, ...]:
    values = parse_qs(urlsplit(url).query).get("filter.fulfillmentMethods") or []
    out: list[str] = []
    for v in values:
        out.extend(x.strip().upper() for x in v.split(",") if x.strip())
    return tuple(out)


def _fulfillment_ok(methods: Sequence[str], modality: str) -> bool:
    if not methods:
        return False
    s = set(methods)
    if s <= {"DELIVERY", "SHIP"}:
        return False
    return modality in s


def attest(
    store: StoreConfig, obs: AttestationObservation, settings: AttestationSettings
) -> AttestationResult:
    ctx = obs.context
    res = AttestationResult()
    add = res.checks.append
    loc = store.location_id
    details = ctx.store(loc)

    # A1 location
    observed_ids = [s.location_id for s in ctx.stores]
    add(
        CheckResult(
            "A1_location",
            CheckStatus.PASS if details is not None and len(set(observed_ids)) == 1 else CheckStatus.FAIL,
            observed_ids,
            loc,
        )
    )

    # A2 modality
    modality = store.modality.value
    a2_ok = ctx.active_modality == modality and (
        details is not None and modality in details.allowed_modalities
    )
    add(
        CheckResult(
            "A2_modality",
            CheckStatus.PASS if a2_ok else CheckStatus.FAIL,
            {"active": ctx.active_modality, "allowed": details.allowed_modalities if details else None},
            modality,
        )
    )

    # A3 trust: never a DEFAULT_* source; the expected source is a Phase 0 deliverable.
    entry = ctx.active_modality_entry()
    source = entry.source if entry else ""
    msg = ""
    a3_ok = bool(entry) and not source.upper().startswith("DEFAULT_")
    if (
        a3_ok
        and settings.require_is_trusted_source
        and entry is not None
        and entry.is_trusted_source is not True
    ):
        a3_ok, msg = False, "isTrustedSource is not true"
    if a3_ok and not settings.trusted_modality_sources:
        a3_ok, msg = False, "expected trusted modality source not configured yet (Phase 0 deliverable)"
    if a3_ok and source not in settings.trusted_modality_sources:
        a3_ok, msg = False, f"source {source!r} not in configured trusted sources"
    if entry is not None and source.upper().startswith("DEFAULT_"):
        msg = f"modality source {source!r} is a site default, not an explicit selection"
    add(
        CheckResult(
            "A3_trust",
            CheckStatus.PASS if a3_ok else CheckStatus.FAIL,
            {
                "source": source,
                "isTrustedSource": entry.is_trusted_source if entry else None,
                "hasManuallySetActiveModality": ctx.has_manually_set_active_modality,
            },
            {"trusted_sources": list(settings.trusted_modality_sources)},
            msg,
        )
    )

    # A4 per-request location
    if obs.data_request_urls:
        ids = [request_location_id(u) for u in obs.data_request_urls]
        bad = [u for u, i in zip(obs.data_request_urls, ids, strict=True) if i != loc]
        add(
            CheckResult(
                "A4_per_request",
                CheckStatus.FAIL if bad else CheckStatus.PASS,
                {"requests": len(ids), "mismatched": bad[:5]},
                loc,
            )
        )
    else:
        add(CheckResult("A4_per_request", CheckStatus.NOT_APPLICABLE, {"requests": 0}, loc))

    # A5 LAF (state lafObject and, when observable, the x-laf-object request header)
    laf_ids = set(ctx.laf_store_ids) | set(obs.laf_header_store_ids)
    if laf_ids:
        add(
            CheckResult(
                "A5_laf", CheckStatus.PASS if laf_ids == {loc} else CheckStatus.FAIL, sorted(laf_ids), loc
            )
        )
    else:
        add(CheckResult("A5_laf", CheckStatus.NOT_APPLICABLE, [], loc))

    # A6 CMS scope suffix
    expected_scope_tail = f"{store.division_number}/{store.store_number}"
    if ctx.cms_scopes:
        ok = all(s.endswith(expected_scope_tail) for s in ctx.cms_scopes)
        add(
            CheckResult(
                "A6_cms_scope",
                CheckStatus.PASS if ok else CheckStatus.FAIL,
                list(ctx.cms_scopes),
                expected_scope_tail,
            )
        )
    else:
        add(
            CheckResult("A6_cms_scope", CheckStatus.FAIL, [], expected_scope_tail, "no store-scoped CMS keys")
        )

    # A7 visible header
    name_ok = (obs.header_vanity_name or "").strip() == store.expected.display_name
    zip_ok = obs.header_postal_code is None or obs.header_postal_code.strip() == store.expected.postal_code
    zip_state_ok = details is not None and details.postal_code == store.expected.postal_code
    add(
        CheckResult(
            "A7_visible",
            CheckStatus.PASS if name_ok and zip_ok and zip_state_ok else CheckStatus.FAIL,
            {
                "header_name": obs.header_vanity_name,
                "header_postal_code": obs.header_postal_code,
                "state_postal_code": details.postal_code if details else None,
            },
            {"display_name": store.expected.display_name, "postal_code": store.expected.postal_code},
        )
    )

    # A8 fulfillment methods on data requests
    if obs.data_request_urls:
        bad_f = [
            u for u in obs.data_request_urls if not _fulfillment_ok(request_fulfillment_methods(u), modality)
        ]
        add(
            CheckResult(
                "A8_fulfillment",
                CheckStatus.FAIL if bad_f else CheckStatus.PASS,
                {"mismatched": bad_f[:5]},
                f"includes {modality}; not DELIVERY/SHIP only",
            )
        )
    else:
        add(CheckResult("A8_fulfillment", CheckStatus.NOT_APPLICABLE, {}, modality))

    return res


def store_location_text(details: StoreDetails, visible_text: str | None = None) -> str:
    """Q-01 default: the address as the site displays it. Falls back to the state fields."""
    if visible_text:
        return visible_text
    street = ", ".join(details.address_lines)
    return f"{street}, {details.city}, {details.state} {details.postal_code}".strip(", ")


def unique_store_ids(contexts: Iterable[StoreContext]) -> set[str]:
    return {s.location_id for c in contexts for s in c.stores}
