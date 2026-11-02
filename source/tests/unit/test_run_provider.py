"""Release 1.7.0: the provider a run's credits are counted in (the unit of its segments' credits)."""

from __future__ import annotations

from typing import Any

import pytest

from marianos_headless.collection.limits import snapshot_provider


@pytest.mark.parametrize(
    ("snapshot", "provider"),
    [
        # the provider the run names for its whole life
        ({"provider": "oxylabs", "acquisition": {"browser_provider": "scrapfly"}}, "oxylabs"),
        ({"acquisition": {"browser_provider": "oxylabs"}}, "oxylabs"),  # a run created from settings only
        ({"acquisition": {}}, "scrapfly"),  # before release 1.3.0: Scrapfly was the only provider
        ({}, "scrapfly"),
        (None, "scrapfly"),
    ],
)
def test_the_provider_of_a_run_comes_from_its_snapshot(
    snapshot: dict[str, Any] | None, provider: str
) -> None:
    assert snapshot_provider(snapshot) == provider
