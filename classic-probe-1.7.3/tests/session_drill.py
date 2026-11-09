"""A campaign session in its own process, for the supervisor and crash tests (OFFLINE).

    python -m tests.session_drill <manifest> <out> <mode> [<port>]

``loopback``: the isolated worker against a stub on 127.0.0.1:<port>, with a 20 s request allowance.
``loopback-crash-after-send``: the same, and the process dies once the answer is back, before its kept copy is
written (1.7.1, C4).
``loopback-crash-on-failure``: the same, and the process dies as soon as the request fails (no answer, or a
body cut short), before the failure is recorded anywhere (the client's review of 1.7.1, C4).
``crash-after-reserve`` | ``crash-after-send`` | ``crash-after-capture-file`` | ``crash-after-index``: a
replay of saved answers whose process dies at that point, as a killed process would (exit 23, no cleanup).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from classic_probe import campaign, captures, checks, gates, ledger, money
from classic_probe.targets import Target
from classic_probe.transport import (
    IsolatedHttpTransport,
    ProviderRequest,
    ProviderResponse,
    ReplayTransport,
    Transport,
    TransportFailed,
)
from tests import fixture_builder as fb
from tests.conftest import SYNTHETIC_RATES

WALMART = Target(
    retailer="walmart",
    store_id="3891",
    store_address="3900 Fountain Square Pl, Waukegan, IL 60085",
    fulfillment="PICKUP",
    store_id_verified=True,
    store_id_evidence="test",
    adapter="walmart",
    search_query="milk",
    category_probe_url="https://www.walmart.com/browse/food/fresh-fruits/976759_976793_9756351",
)


def die(*_a: Any, **_k: Any) -> Any:
    os._exit(23)


def main() -> None:
    manifest, out, mode = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
    led = ledger.open_from_manifest(manifest)
    card = money.RateCard.load(SYNTHETIC_RATES)
    tr: Transport
    if mode in ("loopback", "loopback-crash-after-send", "loopback-crash-on-failure"):
        isolated = IsolatedHttpTransport(
            gates.Credentials("loopback-user", "loopback-password"),
            work_dir=out / "work",
            loopback_port=int(sys.argv[4]),
        )
        tr = isolated
        timeout = 20.0
        if mode == "loopback-crash-on-failure":
            real_send = isolated.send

            def send(request: ProviderRequest, allowance_s: float) -> ProviderResponse:
                try:
                    return real_send(request, allowance_s)
                except TransportFailed:
                    os._exit(23)  # as a killed process would: nothing of the failure is recorded

            isolated.send = send  # type: ignore[method-assign]
        if (
            mode == "loopback-crash-after-send"
        ):  # the answer arrived; the process dies before keeping its copy
            captures.CaptureStore.persist = die  # type: ignore[method-assign]
    else:
        tr = ReplayTransport({k: [ProviderResponse(s, b) for s, b in v] for k, v in fb.complete().items()})
        timeout = 60.0
        if mode == "crash-after-reserve":
            led.mark_sent = die  # type: ignore[method-assign]
        elif mode == "crash-after-send":
            captures.CaptureStore.persist = die  # type: ignore[method-assign]
        elif mode == "crash-after-capture-file":
            led.record_capture = die  # type: ignore[method-assign]
        elif mode == "crash-after-index":
            checks.provider = die
        else:
            raise SystemExit(f"unknown mode {mode}")
    result = campaign.Campaign(led, tr, WALMART, card, out_dir=out, request_timeout_s=timeout).run()
    print(json.dumps(result.as_dict()))


if __name__ == "__main__":
    main()
