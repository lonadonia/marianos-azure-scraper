# Check records against their source, without the VM

For a run's records, `check_sample.py` puts each exported value beside what the product's own tile displayed in the
stored page it was read from. It needs Python 3.10 or later and nothing else (standard library only), and it reads
the tile with Python's own HTML parser, independently of the collector.

```
python3 -I evidence/samples/check_sample.py evidence/samples/F2 --random 20          # 20 records drawn at random
python3 -I evidence/samples/check_sample.py evidence/samples/F2 --random 20 --seed 7 # another draw, reproducible
python3 -I evidence/samples/check_sample.py evidence/samples/F2 0001111050508        # one or more named UPCs
python3 -I evidence/samples/check_sample.py evidence/samples/L1 0084024314377 0001280052496
```

For each record it prints the page (URL, observation time, SHA-256 of the stored page), the exported title beside
the tile's description, the exported prices beside the tile's price text, and the exported price per measure
beside the tile's own price-per-measure element, each line ending with `same` or `DIFFERS`, or with whether the
exported price appears in the tile's price text.

| Folder | Run | Records | What it holds |
|---|---|---|---|
| [`F2/`](F2/) | F2, the full run of the final candidate 1.10.0rc5 (all slices, one run) | 8,104 | `products.json` (the run's export) and `source_excerpts.jsonl.gz`: for each record, the tile cut from the stored page it was read from, with that page's URL, observation time and SHA-256 |
| [`L1/`](L1/) | L1, rows 22 to 27 on 1.10.0rc4 (a pilot, earlier the same day) | 1,168 | the same, for the scope that holds the client's named PPM and coupon examples (the full run did not reach rows 22 to 27) |

**What an excerpt is.** The stored pages (the provider's answers) stay private; an excerpt is the one product tile
of a stored page, cut out by `excerpts.py` on the VM, with the page's SHA-256. The private original can be produced
on request and its hash checked against the one printed here, against the run's `provenance.json`, and against
`STORED_PAGES_PRIVATE.csv` in the run's folder.

**What it does not check.** Fields the tile does not display (the size, for instance, comes from the page's own
product data: `item.customerFacingSize`) are checked by the run's own validation, not here. A record's URL can be
opened on the live site, but prices, offers and availability change over time: the excerpt is what the page showed
at the stated time, for store 53100502, PICKUP.

Sample from a draw on 2026-11-16: [`CHECK_F2_RANDOM_20_seed1.txt`](CHECK_F2_RANDOM_20_seed1.txt) (20 records drawn, 0 differences).
