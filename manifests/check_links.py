"""Checks every link of the delivery's Markdown files offline (Python 3.10+, standard library only; release
1.10.0rc7). Run from the repository root:

    python3 -I manifests/check_links.py

* A relative link must name a file or folder of this repository (its #fragment is not checked).
* A link to this repository on GitHub (``/tree/<ref>/<path>`` or ``/blob/<ref>/<path>``) is checked in the local
  Git history: ``git cat-file -e <ref>:<path>``, the ref being a tag or a commit present locally. Nothing is fetched.
* Every other address (the store's product pages, provider documentation) is never visited: it is counted, by host,
  as "not visited".

Exit 0 when every repository path exists, 1 otherwise (each missing path is named with the file and line that link
it), 2 when a GitHub link names a ref this checkout does not hold.
"""

from __future__ import annotations

import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent.parent
REPO = "/lonadonia/marianos-azure-scraper/"
LINK = re.compile(r"\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
CODE_FENCE = re.compile(r"^\s*(```|~~~)")


def links(md: Path):
    fenced = False
    for n, line in enumerate(md.read_text(encoding="utf-8").splitlines(), 1):
        if CODE_FENCE.match(line):
            fenced = not fenced
            continue
        if fenced:
            continue
        text = re.sub(r"`[^`]*`", "", line)  # inline code is not a link
        for m in LINK.finditer(text):
            yield n, m.group(1)


def git_has(ref: str, path: str) -> bool | None:
    try:
        ok = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--verify", "--quiet", ref + "^{commit}"],
                            capture_output=True, check=False)
        if ok.returncode != 0:
            return None
        if not path:
            return True
        p = subprocess.run(["git", "-C", str(ROOT), "cat-file", "-e", f"{ref}:{path}"],
                           capture_output=True, check=False)
        return p.returncode == 0
    except OSError:
        return None


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")  # type: ignore[union-attr]
    missing, unknown_refs = [], []
    checked = github = 0
    not_visited: Counter[str] = Counter()
    files = sorted(p for p in ROOT.rglob("*.md") if ".git" not in p.relative_to(ROOT).parts)
    for md in files:
        rel_md = md.relative_to(ROOT).as_posix()
        for n, target in links(md):
            if target.startswith(("mailto:", "#")):
                continue
            parts = urlsplit(target)
            if parts.scheme in ("http", "https"):
                if parts.netloc == "github.com" and parts.path.startswith(REPO):
                    rest = parts.path[len(REPO):].split("/")
                    if len(rest) >= 2 and rest[0] in ("tree", "blob"):
                        ref, path = rest[1], unquote("/".join(rest[2:])).strip("/")
                        github += 1
                        found = git_has(ref, path)
                        if found is None:
                            unknown_refs.append(f"{rel_md}:{n}: {ref} (not in this checkout)")
                        elif not found:
                            missing.append(f"{rel_md}:{n}: {ref}:{path}")
                        continue
                not_visited[parts.netloc] += 1
                continue
            if parts.scheme:
                not_visited[parts.scheme + ":"] += 1
                continue
            path = unquote(parts.path)
            if not path:
                continue
            dest = (md.parent / path).resolve()
            checked += 1
            try:
                dest.relative_to(ROOT)
            except ValueError:
                missing.append(f"{rel_md}:{n}: {target} (outside the repository)")
                continue
            if not dest.exists():
                missing.append(f"{rel_md}:{n}: {target}")
    print(f"{len(files)} Markdown files; {checked} repository paths checked; {github} links to this repository's "
          f"history checked in Git; {sum(not_visited.values())} other addresses not visited")
    for host, count in sorted(not_visited.items()):
        print(f"  not visited: {host} ({count})")
    for m in missing:
        print(f"MISSING {m}")
    for u in unknown_refs:
        print(f"UNKNOWN REF {u}")
    if missing:
        print(f"links: FAIL ({len(missing)} missing)")
        return 1
    if unknown_refs:
        print(f"links: REFUSED ({len(unknown_refs)} refs not in this checkout)")
        return 2
    print("links: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
