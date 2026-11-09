"""What must be true before a future Classic request, all of it checked before anything is reserved or sent.

Live mode is disabled in this build (:data:`LIVE_ENABLED`): turning it on takes a code change, a new version
and the owner's approval. :func:`evaluate` states every missing condition, so an owner can see what is
outstanding without any request: an explicit approval naming this campaign and this ledger, the account's
target entitlement verified by its owner, the account's maximum rates confirmed, and credentials present.

Credentials are read only by :func:`load_credentials`, and it is called only on the live path after every
other gate has passed. No offline mode reaches it.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from classic_probe.ledger import Ledger
from classic_probe.money import RateCard, UnknownRate

LIVE_ENABLED = False

ENV_USERNAME = "OXYLABS_CLASSIC_USERNAME"
ENV_PASSWORD = "OXYLABS_CLASSIC_PASSWORD"

REQUIRED_CLASSES = ("walmart_search", "walmart_product")
# 1.6.0: the sources each retailer's steps use. A campaign is refused for a retailer whose sources are not
# verified in the account's entitlement and priced in its confirmed rate card; the category step's URL form
# is priced too.
REQUIRED_BY_RETAILER = {
    "walmart": (*REQUIRED_CLASSES, "url_only"),
    "marianos": ("marianos_search", "marianos_product", "url_only"),
}


class LiveDisabled(RuntimeError):
    """This build makes no provider request."""


@dataclass(frozen=True)
class Credentials:
    username: str
    password: str

    def __repr__(self) -> str:
        return "Credentials(<hidden>)"


def load_credentials() -> Credentials:
    """The API username and password from the environment. Only the live path calls this."""
    username, password = os.environ.get(ENV_USERNAME, ""), os.environ.get(ENV_PASSWORD, "")
    if not username or not password:
        raise LiveDisabled(f"{ENV_USERNAME} and {ENV_PASSWORD} are not both set")
    return Credentials(username, password)


def credentials_present() -> bool:
    """Whether both variables are set; the values are not kept or shown."""
    return bool(os.environ.get(ENV_USERNAME)) and bool(os.environ.get(ENV_PASSWORD))


def evaluate(
    ledger: Ledger,
    *,
    approval: Mapping[str, Any] | None,
    entitlement: Mapping[str, Any] | None,
    rates: Mapping[str, Any] | None,
    credentials: bool,
    retailer: str,
) -> list[str]:
    """Everything that prevents dispatch now (empty: nothing does). Reads local files only."""
    missing: list[str] = []
    if ledger.offline:
        missing.append("this ledger is an offline test ledger: it never authorizes a provider request")
    if not approval or approval.get("approved") is not True:
        missing.append("no explicit approval")
    else:
        if approval.get("campaign_id") != ledger.campaign_id:
            missing.append("the approval names another campaign")
        if approval.get("ledger_genesis_id") != ledger.genesis_id:
            missing.append("the approval names another ledger: this one could spend a second allowance")
        if not str(approval.get("approved_by") or "").strip():
            missing.append("the approval does not say who approved it")
        if retailer not in (approval.get("retailers") or []):
            missing.append(f"the approval does not include {retailer}")
    if not entitlement or entitlement.get("verified") is not True:
        missing.append("the account's target entitlement is not verified")
    else:
        if not str(entitlement.get("verified_by") or "").strip():
            missing.append("the entitlement does not say who verified it")
        granted = entitlement.get("targets") or []
        required = REQUIRED_BY_RETAILER.get(retailer, REQUIRED_CLASSES)
        missing.extend(
            f"no verified entitlement for {c}" for c in required if c not in granted and c != "url_only"
        )
        if entitlement.get("response_mode") != "realtime":
            missing.append("the Realtime response mode is not confirmed")
    if not rates:
        missing.append("the account's maximum billing rates are not confirmed")
    elif rates.get("synthetic") is not False:
        # The example and test rate cards say "synthetic": true; a card has to say false to be considered.
        missing.append(
            "the rate card is SYNTHETIC or does not say otherwise: it is not the account's confirmed rates"
        )
    else:
        try:
            card = RateCard.load(rates)
            for request_class in REQUIRED_BY_RETAILER.get(retailer, REQUIRED_CLASSES):
                card.worst_case(request_class, 1)
        except UnknownRate as exc:
            missing.append(str(exc))
    if not credentials:
        missing.append("credentials are not present")
    return missing
