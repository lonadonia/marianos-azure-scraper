"""JSON round-trip for DOM observations stored in ``product_observations.displayed``."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from marianos_headless.sites.marianos.dom_parsers import (
    CardObservation,
    PriceDisplay,
    PriceDisplayKind,
    ZoneOffer,
)


def card_to_dict(card: CardObservation) -> dict[str, Any]:
    d = asdict(card)
    d["price"]["kind"] = card.price.kind.value
    return d


def card_from_dict(d: dict[str, Any]) -> CardObservation:
    price = dict(d["price"])
    price["kind"] = PriceDisplayKind(price["kind"])
    zone = ZoneOffer(**d["zone"]) if d.get("zone") else None
    return CardObservation(
        position=d["position"],
        card_testid=d["card_testid"],
        upc=d["upc"],
        url=d["url"],
        title=d["title"],
        size_text=d["size_text"],
        price=PriceDisplay(**price),
        price_tag=d["price_tag"],
        zone=zone,
        image_src=d["image_src"],
        image_url=d["image_url"],
        snap_ebt=d["snap_ebt"],
        flags=tuple(d.get("flags", ())),
        ppm_text=d.get("ppm_text", ""),
    )
