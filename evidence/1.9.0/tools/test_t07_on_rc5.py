"""T07 reproduction on the published 1.8.0rc5 (ee5ec99): the test of release 1.9.0
(tests/integration/test_partitions_190.py::test_a_provider_failure_that_pauses_the_run_is_not_reported_as_a_limit),
written with 1.8.0rc5's own test helpers (tests/integration/test_listing_pages.py, tests/listing_site.py), unchanged
otherwise. Copied into a 1.8.0rc5 checkout for one run, then removed. Expected on 1.8.0rc5: FAIL, because the pause
is recorded as RUN_LIMIT_REACHED (worker/runner.py: "RUN_STOPPED" if not resumable else "RUN_LIMIT_REACHED")."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select

from marianos_headless.core.settings import Settings
from marianos_headless.db.models import Event, Run
from tests.integration.test_listing_pages import _run, env  # noqa: F401
from tests.listing_site import Site, products

pytestmark = [pytest.mark.postgres]


def test_a_provider_failure_that_pauses_the_run_is_not_reported_as_a_limit(
    env: dict[str, Any],  # noqa: F811
    settings: Settings,
) -> None:
    site = Site({"03001": products(60)})
    site.on("03001", 2, *(["fail"] * 12))
    run_id, status = _run(env, settings, site)
    assert status == "interrupted"
    with env["factory"]() as s:
        run = s.get(Run, run_id)
        assert run is not None and run.stop_code == "PROVIDER_ERROR"
        codes = set(s.scalars(select(Event.code).where(Event.run_id == run_id)))
        print("event codes:", sorted(codes))
        assert "RUN_PAUSED_ON_FAILURE" in codes and "RUN_LIMIT_REACHED" not in codes
