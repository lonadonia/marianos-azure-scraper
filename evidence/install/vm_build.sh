#!/usr/bin/env bash
# On the owner VM as the login user (env W ARCHIVE WANT_TREE WANT_SHA bash -s < this): the pinned candidate's tree checked against its Git tree id,
# then its wheel, hashed lock export and configuration archive built from it. Refuses to reuse a folder.
set -euo pipefail
W="${W:?}"
ARCHIVE="${ARCHIVE:?}"
WANT_TREE="${WANT_TREE:?}"
WANT_SHA="${WANT_SHA:?}"
[ -e "$W/src" ] && { echo "REFUSED: $W/src exists"; exit 2; }
echo "start $(date -u +%FT%TZ)"
echo "$WANT_SHA  $ARCHIVE" | sha256sum -c -
mkdir -p "$W/src" "$W/rel" "$W/logs"
tar -xzf "$ARCHIVE" -C "$W/src"
cd "$W/src"
git init -q .
git -c core.autocrlf=false -c core.fileMode=true add -A -f .
GOT=$(git write-tree)
rm -rf .git
echo "files: $(find . -type f | wc -l)  tree: $GOT"
[ "$GOT" = "$WANT_TREE" ] && echo "TREE MATCHES the pinned candidate ($WANT_TREE)" || { echo "TREE MISMATCH"; exit 3; }
python3.12 --version; uv --version
uv build --wheel --out-dir "$W/rel" > "$W/logs/build.log" 2>&1; echo "uv build exit $?"; tail -1 "$W/logs/build.log"
uv export --frozen --no-dev --no-emit-project --format requirements-txt -o "$W/rel/requirements.lock.txt" > "$W/logs/export.log" 2>&1; echo "uv export exit $?"
tar -czf "$W/rel/config.tgz" -C config .
cp deploy/vm/marianos deploy/vm/*.sh deploy/vm/collector.env.example "$W/rel/"
echo "lock export: $(grep -c -- '--hash=sha256' "$W/rel/requirements.lock.txt") hashes, $(grep -cE '^[a-zA-Z0-9_.-]+==' "$W/rel/requirements.lock.txt") packages"
( cd "$W/rel" && sha256sum -- * ) | tee "$W/rel.SHA256SUMS"
echo "end $(date -u +%FT%TZ)"
