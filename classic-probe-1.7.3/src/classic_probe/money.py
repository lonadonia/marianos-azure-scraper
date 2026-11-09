"""Money and billing units, in exact decimal arithmetic. A float is refused, and units are never mixed.

A rate is known only when the account's owner has confirmed it (:class:`RateCard`). No rate ships with this
package: the published list prices are not this account's rates, and an unknown rate prevents dispatch. The
worst case is the highest confirmed rate of the request class (a target can be force-rendered, which the
documentation says counts as rendered traffic) times the most billable results the request can return. Only a
rate in US dollars per result gives a bound: any other unit is kept apart and refused, because it cannot be
reserved against a limit in dollars.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

USD_PER_RESULT = "usd_per_result"


class UnknownRate(ValueError):
    """No reliable upper bound for this request class."""


def usd(value: Any) -> Decimal:
    """An exact amount from text or an int. A float has already lost its exactness, so it is refused."""
    if isinstance(value, float | bool):
        raise TypeError(f"money must be text or an integer, not {type(value).__name__}")
    try:
        amount = Decimal(str(value))
    except InvalidOperation:
        raise ValueError(f"not an amount: {value!r}") from None
    if not amount.is_finite() or amount < 0:
        raise ValueError(f"not an amount: {value!r}")
    return amount


@dataclass(frozen=True)
class Rate:
    unit: str
    plain: Decimal  # per result, without rendering
    rendered: Decimal  # per result, rendered


@dataclass(frozen=True)
class RateCard:
    """The account's maximum billing rates, confirmed by its owner."""

    confirmed_by: str
    confirmed_at: str
    basis: str
    rates: Mapping[str, Rate]

    @classmethod
    def load(cls, data: Mapping[str, Any]) -> RateCard:
        for key in ("confirmed_by", "confirmed_at", "basis"):
            if not str(data.get(key) or "").strip():
                raise UnknownRate(f"the rate card has no {key}: its rates are not confirmed")
        rates: dict[str, Rate] = {}
        for name, row in dict(data.get("rates") or {}).items():
            if row.get("plain") is None or row.get("rendered") is None:
                raise UnknownRate(f"the rate of {name} is not stated")
            rates[name] = Rate(str(row.get("unit") or ""), usd(row["plain"]), usd(row["rendered"]))
        return cls(str(data["confirmed_by"]), str(data["confirmed_at"]), str(data["basis"]), rates)

    def worst_case(self, request_class: str, max_results: int) -> Decimal:
        """The most this request can cost, in dollars, or :class:`UnknownRate`."""
        rate = self.rates.get(request_class)
        if rate is None:
            raise UnknownRate(f"no confirmed rate for {request_class}")
        if rate.unit != USD_PER_RESULT:
            raise UnknownRate(
                f"{request_class} is billed in {rate.unit!r}: it gives no bound in dollars, and billing "
                "units are not interchangeable"
            )
        return max(rate.plain, rate.rendered) * max_results

    def estimate(self, request_class: str, results: int, *, rendered: bool) -> Decimal:
        rate = self.rates[request_class]
        return (rate.rendered if rendered else rate.plain) * results
