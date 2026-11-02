# Walkthroughs

Terminal recordings of real commands as they ran on Hamza's workstation (Windows 11), not on the client's VM. Nothing
was typed in afterwards. Each video is rendered from its recording; the recordings, each step's raw output, the
closing frames and the recording scripts are in [`evidence/walkthrough/`](../evidence/walkthrough/).

| Video | Length | Size (bytes) | SHA-256 | What it shows |
|---|---|---|---|---|
| [`WALKTHROUGH_1.8.0rc4_part1.webm`](WALKTHROUGH_1.8.0rc4_part1.webm) | 2:23 | 15,190,012 | `0a970fc6f4fb943ce8bbb218f73de6a0aa42c133e8d0e79dc07d0ec0de1daa19` | **Live, 1.8.0rc4:** the release and clean checkout, then run Q2 at Vernon Hills Pickup with its planned kill and the resume |
| [`WALKTHROUGH_1.8.0rc4_part2.webm`](WALKTHROUGH_1.8.0rc4_part2.webm) | 1:33 | 10,510,358 | `cbadfeecedf5d20ac22f7e0f7ec44b5bdc1ed688e200fbc168b6c75acb2f5849` | **Live, 1.8.0rc4:** Q2 after its unplanned stop: the resume, the pages, the export, validation, coverage and record checks |
| [`WALKTHROUGH_1.8.0rc5_part3.webm`](WALKTHROUGH_1.8.0rc5_part3.webm) | 0:41 | 3,935,295 | `33502444ed2ce10ddd023c69ec6a4974c99085073fbefa9c8166980bb7587962` | **Offline, 1.8.0rc5:** its version and change from rc4, the G13 regressions, the integrity re-check of the live data and the full suite's result |

Parts 1 and 2 are the live evidence, and they ran **1.8.0rc4**. Part 3 shows **1.8.0rc5 offline only**: there is no
live run of 1.8.0rc5 and no full category list in any part. Steps and narration:
[`steps_180.json`](../evidence/walkthrough/steps_180.json) (part 1),
[`steps_180_part2.json`](../evidence/walkthrough/steps_180_part2.json) (part 2) and
[`steps_185_part3.json`](../evidence/walkthrough/steps_185_part3.json) (part 3).
