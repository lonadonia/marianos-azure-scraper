# Diagnosis: the intermittent HTTP 403 from marianos.com

Prepared 2026-10-23 from saved evidence only (no request was made for this analysis). It covers every
Scrapfly Cloud Browser session of this project whose start was recorded with its browser identity: the
application collector's pilot (2026-10-19/20, `deploy_validation/*_scrapfly_pilot`) and this standalone
collector's runs of 2026-10-21, 2026-10-22 and 2026-10-23. The dashboard-era server runs of 2026-10-20
(one refusal, at least four served sessions) did not record the browser identity and are left out.

## What a refusal is

The retailer's edge (Akamai) answers the first page of the session with HTTP 403 and its own
"Access Denied" error page (`errors.edgesuite.net`, a "Reference #18.…" number, about 300 bytes, no
application state). The provider's side worked in every case: the CDP connection opened, the provider's
browser loaded robots.txt from the site (HTTP 200) and the account answered. The collector's challenge
check recognised each page (`http_403`, `access_denied_text`, `akamai_reference_id`,
`edgesuite_error_page`, `missing_initial_state`), stopped the run, closed the browser and held the store.

| Failure class | Seen | Where |
|---|---|---|
| Provider authentication or account error | 0 | every session connected; account readings succeeded |
| Provider connection failure | 0 confirmed | 2026-10-19 23:26 robots.txt got no response at all (cause not visible: provider or edge) |
| Retailer refusal (HTTP 403, Akamai) | 4 sessions | 2026-10-20 00:34, 2026-10-21 18:58, 2026-10-23 13:21, 2026-10-23 14:23 |
| Page load timeout, no response | 1 session | 2026-10-23 14:21 (45 s, no document) |
| Store verification failure | 0 | no refused session reached the store picker |
| Collector defect or resource exhaustion | 1 (2026-10-20) | a pilot stopped by the workstation's low memory; its browser stayed open until the provider's limit. Since fixed: the browser is always closed, and `auto_close=true` makes the provider close it when the connection drops |

## Every recorded session

The provider picks the browser platform at random for each session unless the `os` connection parameter
is set; it was never set before 2026-10-23. "Identical settings" therefore did not mean identical
sessions.

| Session start (UTC) | Collector | Platform (user agent) | First retailer response | Outcome |
|---|---|---|---|---|
| 2026-10-19 23:26 | pilot 1 | Linux | none (robots.txt unanswered) | failed |
| 2026-10-19 23:34 | pilot 2 | macOS | 200 | served |
| 2026-10-20 00:22 | pilot 3 | Windows | 200 | served |
| 2026-10-20 00:34 | pilot 4 | Linux | 403 (and 429) | refused |
| 2026-10-20 00:52 | pilot 5, session 1 | macOS | 200 | served |
| 2026-10-20 00:52 | pilot 5, session 2 | Windows | 200 (one 429 later) | served |
| 2026-10-21 18:58 | standalone `01M5FX7R…` | Linux | 403, Reference #18.6424c317.1792609094.7b3c88e3 | refused |
| 2026-10-22 13:30 | standalone campaign | macOS | 200 | served |
| 2026-10-22 13:44 | standalone campaign | macOS | 200 | served |
| 2026-10-22 13:52 | standalone campaign | macOS | 200 | served |
| 2026-10-23 13:21 | standalone `01M5MERN…` | Linux | 403, Reference #18.cad11102.1792761696.1129578e | refused |
| 2026-10-23 14:14 | standalone `01M5MHSN…` | Windows | 200 | served (189 products) |
| 2026-10-23 14:18 | `01M5MHSN…` resumed | macOS | 200 | served |
| 2026-10-23 14:21 | standalone `01M5MJ67…` | Windows | none (page load timed out after 45 s) | failed |
| 2026-10-23 14:23 | `01M5MJ67…` resumed | Linux | 403, Reference #18.935bca17.1792765435.f527a32 | refused |
| 2026-10-23 21:30 | 1.2.0 `01M5NAQK…`, `os=macos` requested | **Linux** | 200 | served (16 page steps) |
| 2026-10-23 21:51 | `01M5NAQK…` resumed, `os=macos` requested | **Windows** | 200 | served (11 page steps) |

Before the live test of 2026-10-23 21:30: Linux 5 of 5 sessions failed (4 refused, 1 unanswered); Windows
and macOS 9 of 10 served (macOS 6 of 6, Windows 3 of 4), 1 timed out (Fisher's exact test, two-sided
p ≈ 0.002). With the two sessions of the live test: Linux 5 of 6 failed, Windows and macOS 11 of 12 served
(p ≈ 0.005). The sample is small and the proxy address of each session is not visible to the collector.

## Findings

Confirmed:

* The refusals are the retailer's edge answering the first document request of a new session; none
  happened after a store was selected, and none came from the provider.
* The same URLs were served and refused (the Crackers listing on 2026-10-23, Fresh Fruit on other days),
  so the page requested is not the trigger.
* The connection parameters were the same, but the platform the provider emulated was not: every Linux
  session before 2026-10-23 21:30 failed; the Linux session of the live test was served.

Hypothesis tested on 2026-10-23 (below): the edge rejects the provider's Linux desktop browser identity, or
Linux sessions are routed through addresses it rejects. The exact rule the edge applies is not visible from
outside and is not claimed.

## Live test of the hypothesis (2026-10-23, release 1.2.0 candidate)

`acquisition.scrapfly.browser_os` passes the provider's documented `os` connection parameter
(https://scrapfly.io/docs/cloud-browser-api/getting-started: `linux`, `windows` or `macos`, a random
desktop platform when omitted). Run `01M5NAQKQ0H28DCGK5BE8XCP2N` requested `os=macos` (the connection
record of both sessions shows it), chosen before the first request:

* session 1 (21:30 UTC): the provider's browser reported a **Linux** user agent (Chrome 155.0.8059.84, as in
  the refused sessions) and was **served**: store selected and verified, 16 page steps;
* session 2 (21:51 UTC, the resume): it reported **Windows** and was served: store selected and verified
  again, 11 page steps.

Results: (1) the provider did not present the requested platform, so `os=macos` cannot be credited with
anything; (2) a Linux session was served, so "Linux sessions are refused" is not a rule, only an association
in a small sample. The refusal trigger remains **unidentified**. Release 1.2.0 therefore delivers
`browser_os: null` (the provider's choice, as before); the setting stays available, documented and
recorded with every session. The collector sets no user agent or other fingerprint value itself, solves no
challenge (the provider's `solve_captcha` stays off), and a refusal still stops the run, closes the browser
and holds the store until an operator releases it. A refusal remains a stop with evidence, never a reason
to try other identities.

## Session lifecycle reviewed with the evidence

* Lease: the task's lease (120 s) is renewed every 30 s while a page loads or the store picker runs; the
  2026-10-22 lease defect (a slow store selection outliving the lease) is fixed and tested.
* Navigation timeout: 45 s per page; a timeout stops the step as a provider error (resumable), the
  browser is closed.
* Cleanup: the browser is closed in every exit path; when an external Ctrl+Break also stops Playwright's
  driver, the close cannot be confirmed (2 of 5 sessions on 2026-10-23), and the provider closes the
  browser itself when the connection drops (`auto_close=true`).
* Session length: 1.2.0 asks for the provider's maximum (1,800 s) and opens a new session after 60 % of
  it, so a session never reaches the provider's limit during a page.
* The live test also found two collector defects unrelated to the refusals, both fixed in 1.2.0: a Load
  More click that timed out on a visible, enabled button (an overlay is the likely cause; the full browser
  message was cut) failed the listing's task, and a listing whose Load More ended at the site's result
  window (`availableCount` 250 of 328 results) was labelled DONE (docs/VERIFICATION.md).

## Provider support (not sent)

A support request would give: the account fingerprint (`…fe16cf` for the key used from 2026-10-23
20:46 UTC; `…ab738f` before), the session start times above in UTC, the connection parameters (residential
pool, `country=us`, `target_url=https://www.marianos.com/`, blocking of images, fonts and media, the
tracking blacklist, cache), the platform of each session, the requested URL and the Akamai reference
numbers, with the question whether Linux sessions use a different address pool. It contains no key,
cookie or personal data. Nothing has been sent.
