"""Self-test of check_sample.py --strict (release 1.10.0rc7; Python 3.10+, standard library only).

    python3 -I evidence/samples/selftest_check_sample.py evidence/samples/R7

Each case copies three records of the published sample (products.json and their source excerpts) into a
temporary folder, changes one thing, and runs check_sample.py on it, with and without --strict. Without --strict
the script reports and exits 0 whatever it finds (its interactive use, unchanged); with --strict it must exit 0 only
for a genuine match. Nothing is written outside the temporary folder. The output ends with "selftest: PASS" when
every case ends with the exit code it must.
"""

from __future__ import annotations

import gzip
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
UPCS = ("0084024314377", "0001280052496")  # the client's two price-per-measure examples
ABSENT = "0000000000017"  # a UPC no export holds (leading zeros kept)


def load(data: Path) -> tuple[list[dict], dict[str, dict]]:
    products = json.loads((data / "products.json").read_text(encoding="utf-8"))
    records = products if isinstance(products, list) else products.get("products", [])
    ex: dict[str, dict] = {}
    with gzip.open(data / "source_excerpts.jsonl.gz", "rt", encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            ex[d["upc"]] = d
    return records, ex


def write(folder: Path, records: list[dict], ex: dict[str, dict], *, excerpts: bool = True) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "products.json").write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
    if excerpts:
        with gzip.open(folder / "source_excerpts.jsonl.gz", "wt", encoding="utf-8") as f:
            for r in records:
                if r["upc"] in ex:
                    f.write(json.dumps(ex[r["upc"]], ensure_ascii=False) + "\n")
    return folder


def run(folder: Path, *args: str) -> tuple[int, str]:
    p = subprocess.run(
        [sys.executable, "-I", str(HERE / "check_sample.py"), str(folder), *args],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    last = [x for x in p.stdout.splitlines() if x.startswith(("strict: PASS", "strict: FAIL", "REFUSED", "differences"))]
    return p.returncode, (last[-1] if last else p.stdout[-200:])


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")  # type: ignore[union-attr]
    records, ex = load(Path(sys.argv[1]))
    by_upc = {r["upc"]: r for r in records}
    picked = [dict(by_upc[u]) for u in UPCS if u in by_upc]
    if len(picked) != len(UPCS):
        print(f"REFUSED: the sample does not hold {', '.join(UPCS)}")
        return 2
    third = next(dict(r) for r in records if r["upc"] not in UPCS and ex.get(r["upc"], {}).get("excerpt"))
    base = [*picked, third]
    names = [r["upc"] for r in base]
    results = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        genuine = write(root / "genuine", base, ex)
        altered = [dict(r) for r in base]
        altered[0]["ppm"] = altered[0]["ppm"].replace("$", "$1")  # one value changed after the export
        altered_dir = write(root / "altered", altered, ex)
        priced = [dict(r) for r in base]
        priced[1]["regular_price"] = "99.99"
        priced_dir = write(root / "price", priced, ex)
        no_excerpt = dict(ex)
        no_excerpt[base[2]["upc"]] = {**ex[base[2]["upc"]], "excerpt": ""}
        no_excerpt_dir = write(root / "no_excerpt", base, no_excerpt)
        no_file = write(root / "no_file", base, ex, excerpts=False)
        (root / "expect.txt").write_text("# expected UPCs\n" + "\n".join([*names, ABSENT]) + "\n", encoding="utf-8")
        (root / "expect.csv").write_text("upc,listing\n" + "".join(f"{u},27021\n" for u in names), encoding="utf-8")
        (root / "documented.csv").write_text(f"upc,reason\n{ABSENT},approximate weight (sold by the pound)\n", encoding="utf-8")
        (root / "undocumented.csv").write_text(f"upc,reason\n{ABSENT},\n", encoding="utf-8")
        cases = [
            ("interactive use: a difference is reported, exit 0", altered_dir, [*names], 0),
            ("strict: a genuine match", genuine, ["--strict", *names], 0),
            ("strict: a genuine match against an expected list (CSV, leading zeros)", genuine, ["--strict", "--expect", str(root / "expect.csv")], 0),
            ("strict: an altered price per measure", altered_dir, ["--strict", *names], 1),
            ("strict: an exported price the tile does not show", priced_dir, ["--strict", *names], 1),
            ("strict: an expected UPC missing from the export", genuine, ["--strict", "--expect", str(root / "expect.txt")], 1),
            ("strict: the same UPC as a documented exclusion", genuine, ["--strict", "--expect", str(root / "expect.txt"), "--exclusions", str(root / "documented.csv")], 0),
            ("strict: an exclusion without a reason is not one", genuine, ["--strict", "--expect", str(root / "expect.txt"), "--exclusions", str(root / "undocumented.csv")], 1),
            ("strict: a record without its excerpt", no_excerpt_dir, ["--strict", *names], 1),
            ("strict: no excerpt file at all", no_file, ["--strict", *names], 2),
            ("strict: nothing asked for", genuine, ["--strict"], 1),
        ]
        for name, folder, args, want in cases:
            code, last = run(folder, *args)
            results.append(code == want)
            print(f"{'ok  ' if code == want else 'BAD '} exit {code} (must be {want})  {name}  [{last}]")
    print("selftest: PASS" if all(results) else "selftest: FAIL")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
