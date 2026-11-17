#!/usr/bin/env bash
# PRIVATE OPS (owner VM, root): the published state of one target, read only (no provider request): the database's
# publication pointer and publications, latest.json, and the SHA-256 of every file under published/ and of every
# export of the run latest.json names. Two calls whose outputs are equal show the published dataset unchanged.
# Usage: pub_state.sh DB DATA STORE_KEY
set -u
DB="$1"; DATA="$2"; STORE="$3"
q() { sudo -u marianos psql -X -q -d "$DB" -At -F ' | ' -c "$1"; }
echo "== pointer (store_id | publication_id | version | updated_at | run_id | manifest_sha256)"
q "select p.store_id, p.publication_id, p.version, p.updated_at, pub.run_id, pub.manifest_sha256 from publication_pointer p join publications pub on pub.id = p.publication_id order by p.store_id"
echo "== publications (id | run_id | published_at | published_by | previous_publication_id | manifest_sha256)"
q "select id, run_id, published_at, published_by, previous_publication_id, manifest_sha256 from publications order by published_at"
echo "== every file under published/"
if [ -d "$DATA/published" ]; then
  ( cd "$DATA" && find published -type f -print0 | sort -z | xargs -0 -r sha256sum )
else
  echo "(no published/ folder)"
fi
L="$DATA/published/$STORE/latest.json"
if [ -f "$L" ]; then
  echo "== latest.json"
  cat "$L"; echo
  RUN=$(python3 -I -c 'import json,sys
d = json.load(open(sys.argv[1]))
print(d.get("run_id") or d.get("run") or "")' "$L")
  echo "== exports of the published run $RUN"
  if [ -n "$RUN" ] && [ -d "$DATA/runs/$STORE/$RUN/exports" ]; then
    ( cd "$DATA" && find "runs/$STORE/$RUN/exports" -type f -print0 | sort -z | xargs -0 -r sha256sum )
  else
    echo "(not found)"
  fi
fi
