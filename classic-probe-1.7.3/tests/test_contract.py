"""Only documented request forms (OFFLINE)."""

from __future__ import annotations

import pytest

from classic_probe import contract


def test_the_documented_examples_are_accepted_as_written() -> None:
    # The two localization examples of the Walmart source pages (docs/DOCUMENTED_CONTRACT.md).
    contract.assert_documented(
        {
            "source": "walmart_search",
            "query": "milk",
            "store_id": "3520",
            "fulfillment_type": "pickup",
            "sort_by": "price_low",
            "parse": True,
        }
    )
    contract.assert_documented(
        {
            "source": "walmart_product",
            "product_id": "174916638",
            "store_id": "3520",
            "fulfillment_type": "pickup",
            "parse": True,
        }
    )
    contract.assert_documented(
        {"url": "https://www.walmart.com/browse/food/fresh-fruits/976759_976793_9756351"}
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"source": "walmart_search", "query": "milk", "page": 2},  # "page" is not documented: start_page is
        {"source": "walmart_search", "query": "milk", "store": "3891"},  # an invented name
        {"source": "walmart_search", "query": "milk", "fulfillment_type": "pickup"},  # pickup needs store_id
        {"source": "walmart_search", "query": "milk", "store_id": 3891},  # documented as a string
        {"source": "walmart_product", "product_id": "1", "start_page": 2},
        {"source": "walmart_search"},  # query is mandatory
        {
            "url": "https://www.walmart.com/cp/food/976759",
            "store_id": "3891",
        },  # no store parameter documented
        {
            "source": "walmart_category",
            "url": "https://www.walmart.com/cp/food/976759",
        },  # not a documented source
    ],
)
def test_an_undocumented_request_is_refused_before_it_can_be_planned(payload: dict[str, object]) -> None:
    with pytest.raises(contract.UndocumentedRequest):
        contract.assert_documented(payload)


@pytest.mark.parametrize("feature", ["geo_location", "render", "user_agent_type", "session_id"])
def test_a_documented_general_feature_is_never_used_and_says_why(feature: str) -> None:
    # Documented for every source ("you can include additional parameters such as user_agent_type,
    # geo_location, render"); geo_location on Walmart is on the forced-render list, so it would change the
    # billing class.
    with pytest.raises(contract.FeatureNotUsed) as exc:
        contract.assert_documented({"source": "walmart_search", "query": "milk", feature: "x"})
    assert "documented, but never used here" in str(exc.value)
    assert "forces rendering" in contract.NOT_USED_HERE["geo_location"]


def test_a_next_page_is_asked_for_only_when_the_previous_response_shows_it() -> None:
    p1 = contract.walmart_search("milk", "3891")
    assert contract.next_page_payload(p1, 2, 3)["start_page"] == 2
    with pytest.raises(contract.UndocumentedRequest):
        contract.next_page_payload(p1, 2, None)  # never page=2 blindly
    with pytest.raises(contract.UndocumentedRequest):
        contract.next_page_payload(p1, 4, 3)
    with pytest.raises(contract.UndocumentedRequest):
        contract.next_page_payload(contract.walmart_product("1", "3891"), 2, 3)


def test_the_probes_payloads_are_the_store_and_pickup_forms() -> None:
    assert contract.walmart_search("milk", "3891") == {
        "source": "walmart_search",
        "query": "milk",
        "store_id": "3891",
        "fulfillment_type": "pickup",
        "parse": True,
    }
    assert contract.walmart_product("7101", "3891")["fulfillment_type"] == "pickup"
    assert contract.ENDPOINT == "https://realtime.oxylabs.io/v1/queries"
