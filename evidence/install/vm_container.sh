#!/usr/bin/env bash
# On the owner VM (as the admin user, sudo for docker): the real container of the pinned candidate, built from the
# verified tree in $W/src with the repository's Dockerfile, then run: its version, its own configuration check, and
# against PostgreSQL (the candidate's own database, DB, already migrated, through the host's socket, as
# the service user's uid, read only): validate-config --check-db and status. No provider request, no key in the
# container. Records in $W/logs/container/CONTAINER.jsonl.
set -u
W="${W:?}"; COMMIT="${COMMIT:?}"; L="$W/logs/container"; mkdir -p "$L"; cd "$W/src" || exit 9
TAG="marianos-collector:${TAG_VERSION:?}"
DB_URL="postgresql://marianos@/${DB:?}?host=/var/run/postgresql"
U="$(id -u marianos):$(id -g marianos)"
: > "$L/CONTAINER.jsonl"
step() {
  local label="$1"; shift
  local s e code
  s=$(date -u +%FT%TZ); "$@" > "$L/$label.log" 2>&1; code=$?; e=$(date -u +%FT%TZ)
  printf '{"label":"%s","utc_start":"%s","utc_end":"%s","exit_code":%s,"last_line":%s}\n' "$label" "$s" "$e" "$code" \
    "$(tail -1 "$L/$label.log" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read().strip()[:300]))')" >> "$L/CONTAINER.jsonl"
}
step docker_version sudo docker version --format '{{.Server.Version}}'
step build sudo docker build --pull --build-arg "SOURCE_COMMIT=$COMMIT" --build-arg "BUILT_AT=$(date -u +%FT%TZ)" -t "$TAG" .
step image_id sudo docker image inspect --format '{{.Id}} {{.Created}} {{.Size}}' "$TAG"
step run_version sudo docker run --rm "$TAG" --version
step run_build_info sudo docker run --rm --entrypoint cat "$TAG" /app/BUILD_INFO.json
step run_validate_config sudo docker run --rm "$TAG" validate-config
step run_validate_config_db sudo docker run --rm --user "$U" -v /var/run/postgresql:/var/run/postgresql \
  -e "MARIANOS_COLLECTOR_DATABASE_URL=$DB_URL" "$TAG" validate-config --check-db
step run_status sudo docker run --rm --user "$U" -v /var/run/postgresql:/var/run/postgresql \
  -e "MARIANOS_COLLECTOR_DATABASE_URL=$DB_URL" "$TAG" status --store marianos-53100502-pickup
step containers_left sudo docker ps -a --filter "ancestor=$TAG" --format '{{.ID}} {{.Status}}'
echo ALL_DONE >> "$L/CONTAINER.jsonl"
