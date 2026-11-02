"""Audit and finding codes (brief Appendix C) and shared enums."""

from __future__ import annotations

from enum import StrEnum


class DataMode(StrEnum):
    """Every run and everything derived from it is either LIVE or FIXTURE. They are never mixed."""

    LIVE = "LIVE"
    FIXTURE = "FIXTURE"


class Severity(StrEnum):
    INFO = "INFO"
    WARN = "WARN"
    FAIL = "FAIL"


class RecordFlag(StrEnum):
    APPROX_WEIGHT = "APPROX_WEIGHT"
    RELATIVE_PRICE = "RELATIVE_PRICE"
    SOLD_BY_WEIGHT = "SOLD_BY_WEIGHT"
    PRICE_NOT_DISPLAYED = "PRICE_NOT_DISPLAYED"
    PLU_CODE = "PLU_CODE"
    SHIP_ONLY = "SHIP_ONLY"
    LOCATION_UNATTESTED = "LOCATION_UNATTESTED"
    NO_UPC = "NO_UPC"
    UPC_SOURCE_MISMATCH = "UPC_SOURCE_MISMATCH"
    PRICE_DOM_JSON_MISMATCH = "PRICE_DOM_JSON_MISMATCH"
    # The product's own data states the displayed price for no store (release 1.8.0rc2): exported as
    # displayed, never counted as valid.
    PRICE_STORE_NOT_STATED = "PRICE_STORE_NOT_STATED"
    PPM_NOT_DISPLAYED = "PPM_NOT_DISPLAYED"
    PPM_DOM_JSON_MISMATCH = "PPM_DOM_JSON_MISMATCH"
    PRIVATE_LABEL_SIGNAL_CONFLICT = "PRIVATE_LABEL_SIGNAL_CONFLICT"
    MULTIPLE_DIGITAL_PRICES = "MULTIPLE_DIGITAL_PRICES"
    MULTIPLE_VOLUME_PRICES = "MULTIPLE_VOLUME_PRICES"
    OTHER_PROMO_UNCLASSIFIED = "OTHER_PROMO_UNCLASSIFIED"
    CASHBACK_OFFER_EXCLUDED = "CASHBACK_OFFER_EXCLUDED"
    POINTS_OFFER_EXCLUDED = "POINTS_OFFER_EXCLUDED"
    MODALITY_RESTRICTED_OFFER = "MODALITY_RESTRICTED_OFFER"
    PER_WEIGHT_DEAL_PRICE = "PER_WEIGHT_DEAL_PRICE"
    OFFER_TAG_UNOBSERVED = "OFFER_TAG_UNOBSERVED"
    SPONSORED_ONLY_MEMBERSHIP = "SPONSORED_ONLY_MEMBERSHIP"
    SCHEMA_INVALID = "SCHEMA_INVALID"
    IMAGE_NOT_OBSERVABLE = "IMAGE_NOT_OBSERVABLE"
    SIZE_TEXT_NOT_A_SIZE = "SIZE_TEXT_NOT_A_SIZE"  # e.g. a picture's view name ("Front") in the size slot
    MODALITY_NOT_OFFERED = "MODALITY_NOT_OFFERED"  # the product response omits the configured fulfillment
    DEAL_PRICE_NOT_BELOW_PRICE = "DEAL_PRICE_NOT_BELOW_PRICE"  # a coupon headline price >= the shown price
    MARKETPLACE_OFFER = "MARKETPLACE_OFFER"  # a marketplace seller's offer: no local store price
    OUT_OF_STOCK = "OUT_OF_STOCK"  # the source says the product is unavailable now (kept, never deleted)
    PRICE_RANGE = "PRICE_RANGE"  # only a price range for several options is displayed
    # A product of the store's assortment shown this time without an offer for the store (kept with its
    # identity, prices empty; never another store's or fulfillment's price).
    NO_LOCAL_OFFER = "NO_LOCAL_OFFER"
    # Not observed by this run: an earlier run's verified observation kept unchanged (its own crawl date).
    CARRIED_FORWARD = "CARRIED_FORWARD"
    # The card shows only an estimated item price ("about $1.64 each") for a product sold by weight: the
    # estimate is kept in the supporting log, never exported as a fixed price (release 1.4.0).
    ESTIMATED_PRICE_ONLY = "ESTIMATED_PRICE_ONLY"
    # The title states a weight range ("(10-14 Lb)") while no weight is displayed: listed in the eligibility
    # report (release 1.4.0). Since release 1.5.0 the approximate-weight rule also reads it for a product sold
    # by weight (``records.approx_weight_sources``).
    WEIGHT_RANGE_IN_TITLE = "WEIGHT_RANGE_IN_TITLE"
    # Rebuilt from an earlier run's stored page and observation with the current rules (``reprocess``, release
    # 1.5.0): an audited correction with the original observation time and crawl date, never a fresh one.
    REPROCESSED = "REPROCESSED"
    # The observations of one product's size disagree (release 1.8.0, ``assembly.size_evidence``): settled by
    # the product's own evidence, with the reason in the supporting files, or left empty and reported.
    SIZE_CONFLICT_RESOLVED = "SIZE_CONFLICT_RESOLVED"
    SIZE_CONFLICT_UNRESOLVED = "SIZE_CONFLICT_UNRESOLVED"
    # "1 lb" on a product sold by weight: the unit its price is stated in, not a pack size.
    SIZE_IS_UNIT_OF_PRICE = "SIZE_IS_UNIT_OF_PRICE"


class RunCode(StrEnum):
    LOCATION_MISMATCH = "LOCATION_MISMATCH"
    CHALLENGE_DETECTED = "CHALLENGE_DETECTED"
    RATE_LIMITED = "RATE_LIMITED"
    ABNORMAL_LATENCY = "ABNORMAL_LATENCY"
    SITE_CONTRACT_DRIFT = "SITE_CONTRACT_DRIFT"
    ZERO_YIELD_SUSPECT = "ZERO_YIELD_SUSPECT"
    LOW_YIELD = "LOW_YIELD"
    NODE_INCOMPLETE = "NODE_INCOMPLETE"
    CANARY_MISSING = "CANARY_MISSING"
    INTEGRITY_ERROR = "INTEGRITY_ERROR"


# Flags that keep a record out of the canonical export (brief §6.3), with the setting that gates it.
# Selling by weight (RELATIVE_PRICE, SOLD_BY_WEIGHT) is not one of them since release 1.4.0: only
# approximate-weight wording in the weight is (the client's rule).
EXCLUSION_FLAGS: frozenset[RecordFlag] = frozenset(
    {
        RecordFlag.APPROX_WEIGHT,
        RecordFlag.SHIP_ONLY,
        RecordFlag.LOCATION_UNATTESTED,
        RecordFlag.NO_UPC,
        RecordFlag.SCHEMA_INVALID,
        RecordFlag.MARKETPLACE_OFFER,
    }
)
