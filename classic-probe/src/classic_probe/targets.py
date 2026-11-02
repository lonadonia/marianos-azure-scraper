"""The campaign's two retailer targets (``targets.json``)."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Never this campaign's Mariano's store: the Lakeshore East store of an earlier test, and its fulfillment.
FORBIDDEN_MARIANOS_STORE = "53100503"


class TargetRefused(ValueError):
    pass


@dataclass(frozen=True)
class Target:
    retailer: str
    store_id: str
    store_address: str
    fulfillment: str
    store_id_verified: bool
    store_id_evidence: str
    adapter: str  # "walmart", "marianos" or "none"
    search_query: str = ""
    category_probe_url: str = ""

    def live_problems(self) -> list[str]:
        """Why no request may be planned for this target now (empty: none)."""
        out = []
        if self.adapter == "none":
            out.append(
                f"{self.retailer}: this probe has no adapter for it (its share of the limits stays reserved)"
            )
        if not self.store_id or not self.store_id_verified:
            out.append(f"{self.retailer}: the retailer's store ID is not verified from the source")
        if self.fulfillment != "PICKUP":
            out.append(f"{self.retailer}: fulfillment {self.fulfillment}, not PICKUP")
        return out


def _target(name: str, data: Mapping[str, Any]) -> Target:
    t = Target(
        retailer=name,
        store_id=str(data.get("store_id") or ""),
        store_address=str(data.get("store_address") or ""),
        fulfillment=str(data.get("fulfillment") or ""),
        store_id_verified=data.get("store_id_verified_from_source") is True,
        store_id_evidence=str(data.get("store_id_evidence") or ""),
        adapter=str(data.get("adapter") or "none"),
        search_query=str(data.get("search_query") or ""),
        category_probe_url=str(data.get("category_probe_url") or ""),
    )
    if t.fulfillment != "PICKUP":
        raise TargetRefused(f"{name}: the campaign's fulfillment is PICKUP, not {t.fulfillment or 'empty'}")
    if name == "marianos" and t.store_id == FORBIDDEN_MARIANOS_STORE:
        raise TargetRefused(
            "marianos: 53100503 is the Lakeshore East store, not this campaign's Vernon Hills store"
        )
    if t.store_id_verified and not t.store_id_evidence:
        raise TargetRefused(f"{name}: a verified store ID needs its evidence")
    if t.adapter == "walmart" and (not t.search_query or not t.store_id):
        raise TargetRefused(f"{name}: the Walmart adapter needs a store ID and a search query")
    if t.adapter not in ("none", name):
        raise TargetRefused(f"{name}: the {t.adapter} adapter is not this retailer's")
    if t.adapter == "marianos" and (not t.search_query or not t.store_id or not t.store_id.isdigit()):
        raise TargetRefused(f"{name}: the Mariano's adapter needs an 8-digit store ID and a search query")
    return t


def load(path: Path) -> tuple[str, dict[str, Target]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    targets = {name: _target(name, row) for name, row in dict(data.get("retailers") or {}).items()}
    if set(targets) != {"walmart", "marianos"}:
        raise TargetRefused("the campaign has exactly two retailers: walmart and marianos")
    return str(data.get("campaign_id") or ""), targets
