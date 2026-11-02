"""Why a campaign or a retailer's part of it stopped."""

from __future__ import annotations

from enum import StrEnum


class Stop(StrEnum):
    # The response
    BLOCKED = "STOP_BLOCKED"  # a challenge or refusal of the retailer
    WRONG_CONTEXT = "STOP_WRONG_CONTEXT"  # another store or fulfillment than the target's
    UNVERIFIED_CONTEXT = "STOP_UNVERIFIED_CONTEXT"  # the response cannot show the store or fulfillment
    WRONG_IDENTITY = "STOP_WRONG_IDENTITY"  # a product page of another product
    REPEATED_PAGE = "STOP_REPEATED_PAGE"  # a page that does not advance
    EMPTY_RESPONSE = "STOP_EMPTY_RESPONSE"  # no product where the previous response promised a page
    UNSUPPORTED_RESPONSE = "STOP_UNSUPPORTED_RESPONSE"  # not the documented structure
    PARSER_FAILED = "STOP_PARSER_FAILED"  # parse_status_code says the parsed content cannot be relied on
    # The account
    AUTHORIZATION = "STOP_AUTHORIZATION"  # 401
    ENTITLEMENT = "STOP_ENTITLEMENT"  # 403: the account has no access to this resource
    BAD_REQUEST = "STOP_BAD_REQUEST"  # 400, 422: a fault on our side, which the documentation says is billed
    # The limits (a retailer's own quota stops that retailer's part only; the rest stop the campaign)
    RETAILER_QUOTA = "STOP_RETAILER_QUOTA"
    RETAILER_FUNDS = "STOP_RETAILER_FUNDS"  # the retailer's own share of the money limit
    TOTAL_REQUESTS = "STOP_TOTAL_REQUESTS"
    FUNDS = "STOP_FUNDS"
    DEADLINE = "STOP_DEADLINE"
    # The request itself
    RETRIES_EXHAUSTED = "STOP_RETRIES_EXHAUSTED"  # a documented transient error that did not clear
    IN_FLIGHT_UNKNOWN = (
        "STOP_IN_FLIGHT_UNKNOWN"  # no answer in time: its remote outcome and charge are unknown
    )
    OPERATOR = "STOP_OPERATOR"


# A retailer's own request quota ends that retailer's part: the other retailer's share is still reserved for
# it.
RETAILER_ONLY = frozenset({Stop.RETAILER_QUOTA, Stop.RETAILER_FUNDS})
