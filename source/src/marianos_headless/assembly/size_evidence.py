"""Size evidence of one product (release 1.8.0).

The size slot of a card is the retailer's ``customerFacingSize``. For most products it is the pack size. For
some it is a serving ("2 tbsp" on Avocado Green Goddess Dip & Spread 8 oz., UPC 0073679800140, whose own
product data states ``pidSizeQuantity`` 8 ``OUNCES`` and whose name states 8 oz.). This module compares the
observations attached to the *same* product and decides what is exported; it never borrows a sibling's size,
never computes a size and never reads a serving as a package weight.

Observations compared, all of the same product, each kept in the record's provenance:

    displayed       the size slot of the card (``customerFacingSize``)
    product_data    ``pidSizeQuantity`` with ``pidSizeUnitOfMeasureName``
    title           a pack measure the product's own name states ("... 8 oz.")
    detail          the size the product's own page shows, when it was read
    package_weight  ``item.weight`` ("0.5 [lb_av]"), a separate field of the product's data
    price_basis     the pack the retailer's unit price was worked out on (regular price over unit price)

Rules (``assess_size``), in order:

    R1  Displayed size agrees with the product data, or nothing can be compared: the displayed size is
        exported. Multipacks count: "4 cans / 12 fl oz" agrees with 48 FLUID OUNCES (a check, not an export).
    R2  Count against weight or volume is not a conflict: they are different aspects of the same pack
        ("12 ct" with 1 EACH; "12 ct" with 7.5 OUNCES). The product data's 1 EACH is one sale unit and 1
        POUNDS without a package weight of its own is its default: neither states a pack size. Dose strengths,
        dimensions and weight limits in the name ("500 mg", "8 in", "up to 22 lb") are never pack measures:
        the name is read only for an actual conflict and only for weight and volume.
    R3  Displayed size is a serving (tbsp, tsp, serving, cup, slice): a serving is never a package weight.
    When
        the product data and the name or page state the same pack measure, those words are exported. With
        only the product data, or only the name, its own quantity and unit are exported. With neither, or
        when they disagree, the size is left empty and the conflict reported.
    R4  Displayed size and product data disagree in the same dimension. The product's name or page decides
        when it agrees with exactly one of them. Without one, the two remaining fields decide only together:
        the package weight and the price basis must both agree with the same side. A product data quantity
        that is a whole multiple of the displayed size is a multipack stated by its unit: the displayed size
        is kept. Anything else: the size is left empty and the conflict reported. The basis and the package
        weight only choose between stated sizes: neither is ever exported, so no size is computed.
    R5  A product sold by weight whose size slot shows one unit of weight ("1 lb"): that is the unit its price
        is stated in, not a pack size; the size is left empty and the reason recorded. Its product data's
        quantity is an average or a case size, never exported.

Every outcome other than R1/R2 sets a resolution in ``SizeAssessment`` that goes to the supporting files, not
to the 22-field record. A displayed price per unit in the size slot ("$0.98/lb") is handled before this
module.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from marianos_headless.core.text import collapse_ws

_NUM = r"(\d+(?:\.\d+)?|\d*\.\d+)"
# Base units: ounces for weight, fluid ounces for volume.
_WEIGHT = {
    "oz": 1.0, "oz.": 1.0, "ozs": 1.0, "ounce": 1.0, "ounces": 1.0,
    "lb": 16.0, "lb.": 16.0, "lbs": 16.0, "lbs.": 16.0, "pound": 16.0, "pounds": 16.0,
    "g": 0.035274, "gram": 0.035274, "grams": 0.035274,
    "kg": 35.274, "kilogram": 35.274, "kilograms": 35.274,
}  # fmt: skip
_VOLUME = {
    "fl oz": 1.0, "fl. oz": 1.0, "fl. oz.": 1.0, "fl oz.": 1.0, "fo": 1.0, "floz": 1.0,
    "fluid ounce": 1.0, "fluid ounces": 1.0,
    "ml": 0.033814, "milliliter": 0.033814, "milliliters": 0.033814,
    "l": 33.814, "liter": 33.814, "liters": 33.814, "litre": 33.814, "litres": 33.814,
    "qt": 32.0, "quart": 32.0, "quarts": 32.0, "pt": 16.0, "pint": 16.0, "pints": 16.0,
    "gal": 128.0, "gallon": 128.0, "gallons": 128.0,
}  # fmt: skip
_SERVING = (
    "tbsp",
    "tablespoon",
    "tablespoons",
    "tsp",
    "teaspoon",
    "teaspoons",
    "serving",
    "servings",
    "cup",
    "cups",
)
MAX_SERVING_CUPS = 4.0  # "41.5 Cup" names a container's capacity, not a serving
_PID_UNITS: dict[str, tuple[str, float]] = {
    "OUNCES": ("weight", 1.0),
    "POUNDS": ("weight", 16.0),
    "FLUID OUNCES": ("volume", 1.0),
    "PINT": ("volume", 16.0),
    "EACH": ("count", 1.0),
    "COUNT": ("count", 1.0),
    "PACK": ("count", 1.0),
    "PIECE": ("count", 1.0),
}
TOLERANCE = 0.03  # label rounding: 355 ml is printed as 12 fl oz; 1.75 L as 59.2 fl oz


def _unit_alternation() -> str:
    names = sorted({*_WEIGHT, *_VOLUME}, key=len, reverse=True)
    return "|".join(re.escape(n) for n in names)


_MEASURE = re.compile(rf"(?<![\w.]){_NUM}\s*-?\s*({_unit_alternation()})(?![a-z])", re.I)
_MULTI = re.compile(
    rf"^\s*{_NUM}\s*(?:ct|count|pk|pack|packs|cans?|bottles?|pouch(?:es)?|boxes|bags?|cups|bars|sticks|slices|"
    r"pc|pcs|pieces?|rolls?)\b[^\d]{0,12}"
    rf"{_NUM}\s*-?\s*({_unit_alternation()})(?![a-z])",
    re.I,
)
_TIMES = re.compile(rf"^\s*{_NUM}\s*[x×/-]\s*{_NUM}\s*-?\s*({_unit_alternation()})(?![a-z])", re.I)
_PACK_OF = re.compile(
    rf"^\s*{_NUM}\s*({_unit_alternation()})\.?\s*,?\s*{_NUM}\s*(?:pk|pack|ct|count)\b",
    re.I,
)
_COUNT = re.compile(rf"^\s*{_NUM}\s*(?:ct|count|ea|each|pk|pack|pc|pcs|pieces?|rolls?|bars?|kit)\b", re.I)
_RANGE = re.compile(rf"\b{_NUM}\s*(?:-|to)\s*{_NUM}\s*(?:lb|lbs|oz|pounds?|ounces?|kg|g)\b", re.I)
_SERVING_RE = re.compile(rf"^\s*{_NUM}?\s*(?:{'|'.join(_SERVING)})\b\.?\s*$", re.I)
_FRACTION = re.compile(rf"^\s*([1-9])\s*/\s*([2-9])\s*-?\s*({_unit_alternation()})(?![a-z])", re.I)


class SizeResolution(StrEnum):
    AGREE = "agree"  # the displayed size agrees with the product data (R1)
    NOT_COMPARABLE = "not_comparable"  # nothing to compare it with, or different aspects (R1, R2)
    UNIT_DENOMINATOR = "unit_denominator"  # R5: "1 lb" on a product sold by weight is the price's unit
    SERVING_REPLACED = (
        "serving_replaced"  # R3: a serving; the pack size comes from the same product's evidence
    )
    DISPLAYED_KEPT = "displayed_kept"  # R4: a conflict the evidence settles for the displayed size
    REPLACED = "replaced"  # R4: a conflict the evidence settles against the displayed size
    UNRESOLVED = "unresolved"  # R3/R4: no evidence settles it: the size stays empty


@dataclass(frozen=True)
class Measure:
    kind: str  # weight | volume | count | serving
    value: float  # base units: ounces, fluid ounces, count; the amount for a serving
    text: str
    # "18 ct / 24 oz" states the whole pack and "4 cans / 12 fl oz" one unit of it: the second reading.
    each: float | None = None

    def same_dimension(self, other: Measure) -> bool:
        """Weight against volume counts as one dimension: the retailer's own data mixes them (a drink shown
        as "16 oz" with 16 FLUID OUNCES)."""
        return {self.kind, other.kind} <= {"weight", "volume"} or self.kind == other.kind


def _close(x: float, y: float) -> bool:
    return abs(x - y) <= TOLERANCE * max(x, y)


def agrees(a: Measure, b: Measure) -> bool:
    if not a.same_dimension(b):
        return False
    return any(
        _close(x, y) for x in (a.value, a.each) for y in (b.value, b.each) if x is not None and y is not None
    )


def _base(unit: str) -> tuple[str, float] | None:
    u = collapse_ws(unit).casefold()
    if u in _WEIGHT:
        return "weight", _WEIGHT[u]
    if u in _VOLUME:
        return "volume", _VOLUME[u]
    return None


def parse_size(text: str) -> Measure | None:
    """The measure a size text states; None when it states none this module can read."""
    t = collapse_ws(text)
    if not t:
        return None
    if _RANGE.search(t):
        return None  # "10-14 lb": a range is never a pack size (the approximate-weight rule reads it)
    if _SERVING_RE.match(t):
        m = re.match(_NUM, t.strip())
        amount = float(m.group(1)) if m else 1.0
        if "cup" in t.casefold() and amount > MAX_SERVING_CUPS:
            return None
        return Measure("serving", amount, t)
    m = _FRACTION.match(t)
    if m and int(m.group(1)) < int(m.group(2)):  # "1/2 gal"
        base = _base(m.group(3))
        if base:
            return Measure(base[0], int(m.group(1)) / int(m.group(2)) * base[1], t)
    for rx in (_MULTI, _TIMES):
        m = rx.match(t)
        if m:
            base = _base(m.group(3))
            if base:
                one = float(m.group(2)) * base[1]
                return Measure(base[0], float(m.group(1)) * one, t, each=one)
    m = _PACK_OF.match(t)
    if m:
        base = _base(m.group(2))
        if base:
            one = float(m.group(1)) * base[1]
            return Measure(base[0], float(m.group(3)) * one, t, each=one)
    m = _COUNT.match(t)
    if m:
        return Measure("count", float(m.group(1)), t)
    m = _MEASURE.search(t)
    if m:
        base = _base(m.group(2))
        if base:
            return Measure(base[0], float(m.group(1)) * base[1], t)
    return None


def product_data_measure(quantity: Any, unit: Any) -> Measure | None:
    """``pidSizeQuantity`` with ``pidSizeUnitOfMeasureName``; units without a pack measure (USES, SQUARE FOOT,
    INCHES, RANDOM WEIGHT, RECONSTITUTED OUNCES) compare with nothing."""
    try:
        q = float(quantity)
    except (TypeError, ValueError):
        return None
    spec = _PID_UNITS.get(str(unit or "").strip().upper())
    if spec is None or q <= 0:
        return None
    return Measure(spec[0], q * spec[1], f"{quantity} {unit}")


_BASIS_UNITS: dict[str, tuple[str, float]] = {
    "PER OUNCE": ("weight", 1.0),
    "PER POUND": ("weight", 16.0),
    "PER FLUID OUNCE": ("volume", 1.0),
    "PER EACH": ("count", 1.0),
    "PER COUNT": ("count", 1.0),
}


def price_basis_measure(price: Any, amount: Any, unit: Any) -> Measure | None:
    """The pack the retailer's own unit price was worked out on: its regular price over its unit price, for
    example USD 4.99 at 62.38 cents PER OUNCE is 8 oz. Evidence used only to choose between sizes the product
    states; it is never exported, so no size is computed."""
    spec = _BASIS_UNITS.get(str(unit or "").strip().upper())
    try:
        cents = float(str(price)) * 100
        per = float(str(amount))
    except ValueError:
        return None
    if spec is None or per <= 0 or cents <= 0:
        return None
    return Measure(spec[0], cents / per * spec[1], f"USD {price} at {amount} cents {unit}")


_PACKAGE_WEIGHT = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*\[lb_av\]\s*$")


def package_weight_measure(value: Any) -> Measure | None:
    """``item.weight`` ("0.5 [lb_av]"), a field of its own beside the pid size. Exactly 1.0 is its default
    (1.0 with 1 POUNDS on whole turkeys of 10-14 lb), so it states nothing."""
    m = _PACKAGE_WEIGHT.match(str(value or ""))
    if not m or float(m.group(1)) in (0.0, 1.0):
        return None
    return Measure("weight", float(m.group(1)) * 16.0, str(value))


_TITLE_MEASURE = re.compile(rf"(?<![\w.-]){_NUM}\s*-?\s*({_unit_alternation()})(?![a-z])", re.I)


def title_measures(title: str) -> list[Measure]:
    """Weights and volumes the product's name states ("8 oz."). Milligrams, inches and counts are never read
    here: a dose, a dimension or a count is not a pack weight."""
    out: list[Measure] = []
    for m in _TITLE_MEASURE.finditer(collapse_ws(title)):
        base = _base(m.group(2))
        if base:
            out.append(Measure(base[0], float(m.group(1)) * base[1], m.group(0).strip()))
    return out


@dataclass(frozen=True)
class SizeAssessment:
    exported: str  # the value of the record's ``weight``
    resolution: SizeResolution
    rule: str = ""  # which rule of this module decided
    reason: str = ""
    observations: dict[str, str] = field(default_factory=dict)

    @property
    def conflict(self) -> bool:
        return self.resolution not in (SizeResolution.AGREE, SizeResolution.NOT_COMPARABLE)

    def as_dict(self) -> dict[str, Any]:
        return {
            "exported": self.exported,
            "resolution": self.resolution.value,
            "rule": self.rule,
            "reason": self.reason,
            "observations": self.observations,
        }


def _is_one_unit(text: str) -> bool:
    return bool(re.fullmatch(r"1(?:\.0+)?\s*(?:lb|lbs|lb\.|pound|oz|ounce|kg)\.?", text.strip(), re.I))


def _pid_is_default(p: Measure, package: Measure | None) -> bool:
    """1 POUNDS, the product data's default for a product of no fixed pack (``item.weight`` 1.0 or none)."""
    return p.kind == "weight" and p.value == 16.0 and package is None


def _pack_text(best: Measure, page: Measure | None, basis: Measure | None, detail: str, pid: Measure) -> str:
    """The exported text of a settled pack size: words a source states, never the computed basis."""
    if best is page:
        return collapse_ws(detail)
    if best is basis:
        return _pid_text(pid)
    return best.text.rstrip(". ")


def _pid_text(m: Measure) -> str:
    """The product data's own quantity and unit, in the units the retailer uses in its size slot."""
    q, unit = m.text.split(" ", 1)
    short = {"OUNCES": "oz", "POUNDS": "lb", "FLUID OUNCES": "fl oz", "PINT": "pint"}.get(unit.upper(), unit)
    return f"{q} {short}"


def assess_size(
    displayed: str,
    *,
    title: str = "",
    pid_quantity: Any = None,
    pid_unit: Any = None,
    detail: str = "",
    sold_by_weight: bool = False,
    ppm_unit: str = "",
    basis: Measure | None = None,
    package: Measure | None = None,
) -> SizeAssessment:
    """What the record's ``weight`` is for one product, from that product's own observations."""
    shown = collapse_ws(displayed)
    obs = {
        "displayed": shown,
        "product_data": "" if pid_quantity is None else f"{pid_quantity} {pid_unit or ''}".strip(),
        "title": title,
        "detail": collapse_ws(detail),
        "package_weight": package.text if package is not None else "",
        "price_basis": basis.text if basis is not None else "",
    }
    d, p = parse_size(shown), product_data_measure(pid_quantity, pid_unit)
    if sold_by_weight and d is not None and d.kind == "weight" and _is_one_unit(shown):
        return SizeAssessment(
            "",
            SizeResolution.UNIT_DENOMINATOR,
            "R5",
            f"the product is sold by weight and its size slot shows {shown!r}, the unit its price is "
            "stated in" + (f" ({ppm_unit})" if ppm_unit else "") + ", not a pack size",
            obs,
        )
    names = [m for m in title_measures(title) if m.kind in ("weight", "volume")]
    page = parse_size(detail) if detail else None
    if page is not None and page.kind in ("weight", "volume"):
        names = [page, *names]

    if d is not None and d.kind == "serving":
        pack_data = p if p is not None and p.kind in ("weight", "volume") else None
        if pack_data is not None:
            both = [m for m in names if agrees(m, pack_data)]
            if both:
                return SizeAssessment(
                    _pack_text(both[0], page, basis, detail, pack_data),
                    SizeResolution.SERVING_REPLACED,
                    "R3",
                    f"the size slot shows a serving ({shown!r}); the product's own data "
                    f"({obs['product_data']}) and its name or page ({both[0].text!r}) state the same "
                    "pack size",
                    obs,
                )
            if not names:
                return SizeAssessment(
                    _pid_text(pack_data),
                    SizeResolution.SERVING_REPLACED,
                    "R3",
                    f"the size slot shows a serving ({shown!r}); the product's own data states the pack size "
                    f"({obs['product_data']})",
                    obs,
                )
        elif len({round(m.value, 2) for m in names}) == 1:
            return SizeAssessment(
                collapse_ws(detail) if names[0] is page else names[0].text.rstrip(". "),
                SizeResolution.SERVING_REPLACED,
                "R3",
                f"the size slot shows a serving ({shown!r}); the product's name or page states the pack size "
                f"({names[0].text!r})",
                obs,
            )
        return SizeAssessment(
            "",
            SizeResolution.UNRESOLVED,
            "R3",
            f"the size slot shows a serving ({shown!r}) and the product's other evidence does not settle the "
            "pack size",
            obs,
        )

    if d is None or p is None or not d.same_dimension(p):
        return SizeAssessment(
            shown, SizeResolution.NOT_COMPARABLE, "R1" if d is None or p is None else "R2", "", obs
        )
    if agrees(d, p):
        return SizeAssessment(shown, SizeResolution.AGREE, "R1", "", obs)
    if (
        (d.kind == "count" and d.value == 1)
        or (p.kind == "count" and p.value == 1)
        or _pid_is_default(p, package)
    ):
        return SizeAssessment(shown, SizeResolution.NOT_COMPARABLE, "R2", "", obs)

    for_d = [m for m in names if agrees(m, d)]
    for_p = [m for m in names if agrees(m, p)]
    if for_d and not for_p:
        return SizeAssessment(
            shown,
            SizeResolution.DISPLAYED_KEPT,
            "R4",
            f"the product data states {obs['product_data']}; the product's name or page agrees with the "
            f"displayed size ({for_d[0].text!r})",
            obs,
        )
    if for_p and not for_d:
        return SizeAssessment(
            _pack_text(for_p[0], page, basis, detail, p),
            SizeResolution.REPLACED,
            "R4",
            f"the size slot shows {shown!r}; the product data ({obs['product_data']}) and the product's "
            f"name or page ({for_p[0].text!r}) state the same pack size",
            obs,
        )
    if not for_d and not for_p:
        fields = [m for m in (package, basis) if m is not None]
        if len(fields) == 2 and all(agrees(m, d) for m in fields) and not any(agrees(m, p) for m in fields):
            return SizeAssessment(
                shown,
                SizeResolution.DISPLAYED_KEPT,
                "R4",
                f"the product data states {obs['product_data']}; the package weight and the basis of the "
                "retailer's unit price both agree with the displayed size",
                obs,
            )
        if len(fields) == 2 and all(agrees(m, p) for m in fields) and not any(agrees(m, d) for m in fields):
            return SizeAssessment(
                _pid_text(p),
                SizeResolution.REPLACED,
                "R4",
                f"the size slot shows {shown!r}; the product data ({obs['product_data']}), the package "
                "weight and the basis of the retailer's unit price agree on the pack size",
                obs,
            )
        ratio = p.value / d.value
        if ratio >= 2 and abs(ratio - round(ratio)) <= 0.01 * ratio:
            return SizeAssessment(
                shown,
                SizeResolution.DISPLAYED_KEPT,
                "R4",
                f"the product data's {obs['product_data']} is {round(ratio)} times the displayed size: "
                "a multipack stated by its unit",
                obs,
            )
    return SizeAssessment(
        "",
        SizeResolution.UNRESOLVED,
        "R4",
        f"the size slot shows {shown!r} and the product data states {obs['product_data']}; no other "
        "observation of the product settles it",
        obs,
    )
