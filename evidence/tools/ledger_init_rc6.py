"""PRIVATE OPS on the owner VM (as the service user): the new credential's own campaign, one envelope for
Mariano's. Refuses an existing ledger (oxytrial_ledger.init). Prints the summary (no secret in it).

    python3.12 -I ledger_init_rc6.py DIR FINGERPRINT
"""
import json
import sys
from pathlib import Path

d = Path(sys.argv[1])
sys.path.insert(0, str(d))
import oxytrial_ledger as otl  # noqa: E402

CAMPAIGN = "oxylabs-marianos-20261116"
led = otl.Ledger.init(
    d,
    campaign_id=CAMPAIGN,
    cap_usd="5.00",
    headroom_usd="0.10",
    credential_fingerprint=sys.argv[2],
    rate_usd_per_result="0.0015",
    rate_source="oxylabs.io/pricing/web-scraper-api read 2026-11-03: the highest non-AI row (Custom domain, JS) "
    "USD 1.50 per 1,000 results; a list price, not a confirmed account rate (the dashboard balance is not "
    "readable by API)",
    authority="Hamza's brief of 2026-11-16 (closeout after 1.10.0rc5): USD 5 of free credit authorized for "
    "Mariano's on the Oxylabs Web API credential he supplied; on his own infrastructure; no top-up, paid overage, "
    "Oxylabs Classic, other provider, client VM or client billing",
    actor="closeout-1.10.0rc6",
    extra={
        "credential_relation": "the supplied credential's fingerprint differs from the earlier trial key "
        "(…4aef98); whether it belongs to a new account or is a rotation or credit on the earlier account cannot "
        "be read through the API. Per the brief it gets this distinct USD 5 envelope, reconciled once: the "
        "earlier campaign oxylabs-trial-20261103 records the hand-over and makes no reservation with it",
        "not_carried": "the earlier campaign's Mariano's envelope left USD 0.312; it is not added here",
        "headroom_reason": "USD 0.10 kept inside the USD 5 cap: every submission is reserved and settled at the "
        "highest non-AI list price (USD 0.0015 a result, above the unrendered custom-domain rate), so the cap bounds "
        "the spend; the earlier campaign kept 0.50",
        "supersedes": sys.argv[3] if len(sys.argv) > 3 else "",
    },
)
led.set_envelope("marianos", "4.90", reason="the whole allocatable amount of this credential's USD 5 (cap 5.00 "
                 "less the 0.10 headroom) for Mariano's; no other project uses this campaign", actor="closeout-1.10.0rc6")
s = led.summary()
print(json.dumps({k: s[k] for k in ("campaign_id", "cap_usd", "headroom_usd", "allocatable_usd", "envelopes_total_usd",
                                    "committed_usd", "spendable_campaign_usd", "active_lease")}, indent=1))
print(json.dumps({"chain": led.verify_chain(), "meta_fingerprint": led.meta().get("credential_fingerprint")}))
