"""A separate process that reserves against a shared ledger (tests/test_ledger.py). OFFLINE: it sends nothing.

    python -m tests.ledger_worker <ledger> <campaign> <genesis> <retailer> <tries> [crash]

Prints the number of reservations it made. With ``crash`` it exits at once after its first reservation, as a
process killed between reserving and sending would.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from classic_probe import ledger, money


def main() -> None:
    path, campaign, genesis, retailer, tries = sys.argv[1:6]
    crash = len(sys.argv) > 6 and sys.argv[6] == "crash"
    led = ledger.Ledger.open(Path(path), campaign_id=campaign, genesis_id=genesis)
    made = 0
    for i in range(int(tries)):
        try:
            led.reserve(
                retailer=retailer,
                step=f"worker-{os.getpid()}-{i}",
                purpose="test",
                request_class="walmart_search",
                attempt=1,
                payload_sha256="0" * 64,
                amount_usd=money.usd("0.003"),
                request_timeout_s=60.0,
            )
        except ledger.LimitReached:
            continue
        made += 1
        if crash:
            os._exit(17)  # no cleanup, no commit of anything later: the reservation is already durable
    print(made)


if __name__ == "__main__":
    main()
