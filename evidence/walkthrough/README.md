# Recorded walkthrough on Hamza's VM (1.10.0rc6)

A terminal recording of real commands as they ran on 2026-11-17 (05:05:35Z to 05:16:00Z) on Hamza's own Azure test VM (Ubuntu 24.04), **not
on the client's VM**. Nothing was typed in afterwards and nothing was edited: `record_cast.py` ran each command
while recording its output with its real timing. The published copy masks private identifiers (the VM's host name,
home folders) and nothing else ([`../../manifests/REDACTIONS.csv`](../../manifests/REDACTIONS.csv)).

It is the slice R7w of the full-scope run R7 (run `01M7KQ5GZVF5VK1S9FGTG6YFC9`), live, on the Oxylabs Web API credit Hamza supplied
for this delivery, every submission reserved in that credit's own ledger before it was sent
([`../ledger/`](../ledger/README.md)). The slice is a ledger stage of its own, with a ceiling of 110
submissions:

1. the release, the run's state (interrupted by the SIGTERM that ended the previous slice, resumable) and the ledger;
2. the run resumed as a service, two lanes, its log followed, then stopped with SIGTERM after 12 pages: 12 pages collected (05:05:39Z to 05:11:01Z), then `systemctl stop` at 05:11:03Z: exit 75, the run `interrupted` and resumable (the signal reached the collector 2 s after Hard Cider 08194 had stopped the run, as an automatic resume began, so the run's recorded stop is `PROVIDER_ERROR`);
3. a second start for the store refused before any request: exit 9 in 0.2 s at 05:11:07Z ("has an unfinished run 01M7KQ5GZVF5VK1S9FGTG6YFC9"), no submission attempted;
4. the run resumed again with the slice stopper beside it, to 100 reservations in the stage (then
   SIGTERM, resumable) unless the run completed first: the run resumed at 05:11:10Z and collected 3 pages, then Hard Cider 08194 stopped it again at 05:15:54Z (exit 75, resumable: OR-22, OR-23), before the target: the stage held 35 reservations, all settled, none unknown;
5. a publication of the run as it then stood: refused at 05:15:58Z with exit 6 ("run 01M7KQ5GZVF5VK1S9FGTG6YFC9 is a partial dataset: only complete runs are published");
6. the coverage of the CSV rows and the named records traced to their stored pages (when the run has exported), the
   ledger after the slice, and the collector units left running: no export yet, so no coverage and no trace (the run, interrupted, exports its records when it ends; R7's export is that of its copy finalized offline, in [`../runs/R7fin_copy/`](../runs/R7fin_copy/RUN_REPORT.md)); the ledger's chain verified, no active lease, Mariano's committed USD 0.4305 and USD 4.4695 spendable, 9 unknown outcomes held; no collector unit left running (only the recorder itself and the slice's watcher).

Each step's narration was recorded before the step ran, so it says what the step is for, not how it ended; the
outcome is the command's own output and exit code, as recorded.

| File | What it is |
|---|---|
| [`walkthrough_r7w.webm`](walkthrough_r7w.webm) | the video, rendered from the recording (WebM) |
| [`walkthrough_r7w.cast`](walkthrough_r7w.cast) | the recording itself (asciinema v2, real timing): `asciinema play walkthrough_r7w.cast` |
| [`steps_r7w.json`](steps_r7w.json) | each step's command and narration, as recorded |
| [`raw/`](raw/) | each step's complete output, numbered in the order of the steps |

`raw/` holds each step's complete output as the command wrote it (the recording shows the collector's JSON log
lines condensed to time, level, event and message by `record_cast.py`; the raw files keep them whole).
`steps_r7w.json` gives every step's command and narration; `make_walk_steps6.py` wrote it and `r7w_walk.sh` started
the recording (the tools are in [`../tools/`](../tools/README.md)). The video is rendered on Hamza's VM from the
recording by `render_cast.py` (Playwright's Chromium, its own encoder): idle time between two lines is capped and
each command's end is held for a few seconds, so it is shorter than the recording; the `.cast` file (asciinema v2)
keeps the real timing.

Not shown here, and still open: the client's VM (a separately authorized window), the twice-weekly schedule (enabled
only after a full-scope publication protected by its gates, and by the client's decision) and the client's own
review.
