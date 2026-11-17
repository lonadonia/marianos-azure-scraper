# Check records against their source, without the VM

For a run's records, `check_sample.py` puts each exported value beside what the product's own tile displayed in the
stored page it was read from. It needs Python 3.10 or later and nothing else (standard library only), and it reads
the tile with Python's own HTML parser, independently of the collector.

```
python3 -I evidence/samples/check_sample.py evidence/samples/R7 --random 20 --fresh-only   # 20 records R7 observed itself
python3 -I evidence/samples/check_sample.py evidence/samples/R7 --random 20 --seed 7       # any 20 exported records, another draw
python3 -I evidence/samples/check_sample.py evidence/samples/R7 0084024314377 0001280052496   # named UPCs
```

For each record it prints, first, what the record is: **fresh** (observed by R7 itself, on R7's own page) or
**carried_forward** (an earlier run's observation, exported unchanged and read by that earlier run, on that run's
page), with its status when it is not plainly valid (for instance `price_conflict`); then the page (URL, observation
time, SHA-256 of the stored page), the exported title beside the tile's description, the exported prices beside the
tile's price text, and the exported price per measure beside the tile's own price-per-measure element, each line
ending with `same` or `DIFFERS`, or with whether the exported price appears in the tile's price text.

| Folder | Run | Records | What it holds |
|---|---|---|---|
| [`R7/`](R7/) | R7, the full-scope run of 1.10.0rc6 (all slices, one run, `01M7KQ5GZVF5VK1S9FGTG6YFC9`) | 10,536 (2,667 fresh, read by R7 itself; 7,869 carried, each named with the earlier run that read it) | `products.json` (the run's export) and `source_excerpts.jsonl.gz`: for each record, its kind and status, the tile cut from the stored page it was read from, with that page's run, URL, observation time and SHA-256 |

**What an excerpt is.** The stored pages (the provider's answers) stay private; an excerpt is the one product tile
of a stored page, cut out by `excerpts.py` on the VM, with the page's SHA-256. The private original can be produced
on request and its hash checked against the one printed here, against the run's `provenance.json`, and against
`STORED_PAGES_PRIVATE.csv` in the run's folder.

**What it does not check.** Fields the tile does not display (the size, for instance, comes from the page's own
product data: `item.customerFacingSize`) are checked by the run's own validation, not here. A record's URL can be
opened on the live site, but prices, offers and availability change over time: the excerpt is what the page showed
at the stated time, for store 53100502, PICKUP.

Draws made on 2026-11-17: [`CHECK_R7_FRESH_RANDOM_20_seed1.txt`](CHECK_R7_FRESH_RANDOM_20_seed1.txt), 20 of R7's own
records (20 fresh records: 0 differences), and [`CHECK_R7_RANDOM_20_seed1.txt`](CHECK_R7_RANDOM_20_seed1.txt), 20 of every
exported record, carried ones included (8 fresh and 12 carried records: 0 differences). The samples of 1.10.0rc5 (F2 and L1) are complete
at the tag [`review-1.10.0rc5-20261116`](https://github.com/lonadonia/marianos-azure-scraper/tree/review-1.10.0rc5-20261116/evidence/samples);
this `check_sample.py` reproduces their published draw byte for byte (their excerpts state no kind, so
`--fresh-only` refuses them).
