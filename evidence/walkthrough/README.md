# Recorded walkthrough on Hamza's VM (1.10.0rc5)

A terminal recording of real commands as they ran on 2026-11-16 on Hamza's own Azure test VM (Ubuntu 24.04), **not
on the client's VM**. Nothing was typed in afterwards and nothing was edited: `record_cast.py` ran each command
while recording its output with its real timing. The published copy masks private identifiers (the VM's host name,
home folders) and nothing else ([`../../manifests/REDACTIONS.csv`](../../manifests/REDACTIONS.csv)).

It is the last slice (F2d) of the full-scope run F2, live, on Hamza's Oxylabs Web API trial credit through the
shared ledger's gate:

1. the release and the run's state (interrupted at the previous slice's SIGTERM, resumable), and the ledger;
2. the run resumed as a service, two lanes, its log followed, then stopped with SIGTERM: exit 75, resumable;
3. a second start for the store refused before any request: exit 9;
4. the run resumed again, planned to run to the slice's ceiling (where the collector finalizes a run as a partial
   dataset, exit 4); after 8 submissions the collector stopped it instead, not resumable: exit 7
   (`STORE_NOT_VERIFIED`, the defect in [`../operations/STORE_STOP_F2.txt`](../operations/STORE_STOP_F2.txt)). This
   step's narration was recorded before the step ran and announces the ceiling; the recording is not edited;
5. its publication refused: exit 6 (only a complete run is published);
6. the coverage of the CSV rows as the run left them, records traced to the stored pages they were read from, the
   ledger after the slice, and no collector unit left running.

| File | What it is |
|---|---|
| [`WALK_SHA256SUMS.txt`](WALK_SHA256SUMS.txt) | SHA-256 of every file here |
| [`steps_f2d.json`](steps_f2d.json) | every step's command and narration |
| [`walkthrough_f2d.cast`](walkthrough_f2d.cast) | the recording (asciinema v2, real timing) |
| [`walkthrough_f2d.webm`](walkthrough_f2d.webm) | the video rendered from the recording |
| [`raw/`](raw/) | each step's complete output as written (14 files) |

`raw/` holds each step's complete output as the command wrote it (the recording shows the collector's JSON log
lines condensed to time, level, event and message by `record_cast.py`; the raw files keep them whole).
`steps_f2d.json` gives every step's command and narration; `make_walk_steps.py` wrote it (the tools are in
[`../tools/`](../tools/README.md)). The video is rendered
on Hamza's VM from the recording by `render_cast.py` (Playwright's Chromium, its own encoder): idle time between two lines is
capped and each command's end is held for a few seconds, so it is shorter than the recording; the `.cast` file
(asciinema v2) keeps the real timing.

Not shown, and still open: the full scope (beyond the trial credit), the client's VM (a separately authorized
window), the twice-weekly schedule (blocked until a protected full publication exists) and the client's own review.
