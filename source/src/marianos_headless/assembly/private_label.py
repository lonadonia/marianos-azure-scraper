"""Retailer private-label detection for ``store_brand`` (brief §6.2 #5, docx §5).

Primary signal: the product's brand is in ``private_label_brands.yaml``. Secondary signals: a known
UPC prefix and a title that starts with a private-label brand. A brand that is known and *not*
private label, contradicted by a positive secondary signal, is a conflict: the result is "no" with
``PRIVATE_LABEL_SIGNAL_CONFLICT``.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from marianos_headless.core.findings import RecordFlag
from marianos_headless.core.settings import PrivateLabelConfig

_MARKS = re.compile(r"[®™©℠]")


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = _MARKS.sub("", text).replace("’", "'").replace("‘", "'")
    return re.sub(r"\s+", " ", text).strip().casefold()


@dataclass(frozen=True)
class PrivateLabelResult:
    is_private_label: bool
    value: str  # the store_brand output value
    signals: dict[str, bool | None]
    flags: tuple[RecordFlag, ...] = ()


class PrivateLabelDetector:
    def __init__(self, config: PrivateLabelConfig, positive_value: str = "yes", negative_value: str = "no"):
        # Longest first, so "Kroger Mercado" wins over "Kroger" and "Roundy's Select" over "Roundy's".
        self._brands = sorted({_norm(b) for b in config.brands}, key=len, reverse=True)
        self._prefixes = tuple(config.upc_prefix_signals)
        self._yes = positive_value
        self._no = negative_value

    def brand_in_list(self, brand: str) -> bool:
        return _norm(brand) in self._brands

    def title_brand(self, title: str) -> str | None:
        t = _norm(title)
        for b in self._brands:
            if t == b or (t.startswith(b) and not t[len(b)].isalnum()):
                return b
        return None

    def detect(
        self, *, title: str, upc: str | None, brand: str | None = None, require_brand: bool = False
    ) -> PrivateLabelResult:
        """``require_brand``: only the brand decides; without one the result is "no" (the secondary
        signals are still reported)."""
        brand_signal: bool | None = self.brand_in_list(brand) if brand else None
        upc_signal = bool(upc and upc.startswith(self._prefixes)) if self._prefixes else None
        title_signal = self.title_brand(title) is not None if title else None
        signals = {"brand": brand_signal, "upc_prefix": upc_signal, "title_prefix": title_signal}
        if require_brand and brand_signal is None:
            return PrivateLabelResult(False, self._no, signals)

        if brand_signal is True:
            return PrivateLabelResult(True, self._yes, signals)
        secondary_positive = bool(upc_signal) or bool(title_signal)
        if brand_signal is False:
            if secondary_positive:
                return PrivateLabelResult(
                    False, self._no, signals, (RecordFlag.PRIVATE_LABEL_SIGNAL_CONFLICT,)
                )
            return PrivateLabelResult(False, self._no, signals)
        if secondary_positive:
            return PrivateLabelResult(True, self._yes, signals)
        return PrivateLabelResult(False, self._no, signals)
