#!/usr/bin/env bash
# PRIVATE OPS (owner VM, root: sudo env RUN=<run id> TAG=<label> bash -s < this): the installed 1.10.0rc6's
# validate-export --run RUN, offline (it reads the database and the stored pages, no provider request), alone on the
# VM, as the service user with the service's environment, in a transient unit bounded at MemoryMax=3G with no swap
# (the same bound as OR-20's run on F2, vm_or20.sh). Records in $O: the command's JSON output, its stderr, its exit
# code, GNU time's peak RSS and elapsed time, systemd's memory peak, and any OOM line of the kernel log.
set -u
[[ "${RUN:-}" =~ ^[0-9A-Z]{26}$ ]] || { echo "RUN must be a run id"; exit 2; }
[[ "${TAG:-}" =~ ^[A-Za-z0-9]{1,12}$ ]] || { echo "TAG must be a short label"; exit 2; }
O=/var/lib/marianos-collector/ops-rc6/validate_$TAG
CURRENT=/opt/marianos-collector/current
# COPY_ENV: an isolated copy's env file (vm_copy_target6.sh), for a run left resumable on the target and finalized in
# the copy; it must hold no credential file. Without it, the service's own environment.
ENVF="${COPY_ENV:-/etc/marianos-collector/collector.env}"
[ -z "${COPY_ENV:-}" ] || grep -q '^OXYLABS_WEB_API_KEY_FILE=/dev/null$' "$ENVF" || { echo "REFUSED: COPY_ENV holds a credential file"; exit 2; }
echo "environment: $ENVF"
[ "$(id -u)" -eq 0 ] || { echo "run as root"; exit 2; }
# Any collector or stage unit running (the post-install unit that may have started this script excepted).
systemctl list-units --no-legend --state=running 'marianos-*' | grep -v -E '^\s*marianos-postinstall-' | grep -q .   && { echo "REFUSED: a collector unit is running"; systemctl list-units --no-legend --state=running 'marianos-*'; exit 9; }
v=$("$CURRENT/venv/bin/python" -I -c 'import marianos_headless; print(marianos_headless.__version__)')
[ "$v" = "1.10.0rc6" ] || { echo "REFUSED: the current release is $v"; exit 2; }
[ -e "$O/validate_export_$TAG.json" ] && { echo "REFUSED: $O already holds a result"; exit 2; }
install -d -m 750 -o marianos -g marianos "$O"
s=$(date -u +%FT%TZ); t0=$(date +%s.%N)
systemd-run --wait --pipe --collect --unit=marianos-validate-$TAG -p MemoryMax=3G -p MemorySwapMax=0 \
  --uid=marianos --gid=marianos -p EnvironmentFile="$ENVF" \
  -p EnvironmentFile="$CURRENT/release.env" -p WorkingDirectory=/var/lib/marianos-collector \
  -p NoNewPrivileges=yes -p PrivateTmp=yes \
  /usr/bin/time -v -o "$O/time.txt" "$CURRENT/venv/bin/marianos-collector" validate-export --run "$RUN" \
  > "$O/validate_export_$TAG.json" 2> "$O/validate_export_$TAG.stderr"
code=$?
t1=$(date +%s.%N); e=$(date -u +%FT%TZ)
journalctl -k --since "$s" --no-pager 2>/dev/null | grep -i -E "oom|out of memory|killed process" > "$O/kernel_oom.txt" || true
python3 - "$O" "$code" "$s" "$e" "$t0" "$t1" "$v" "$RUN" "$TAG" <<'PY' | tee "$O/VALIDATE_SUMMARY.json"
import json, re, sys
o, code, s, e, t0, t1, v, run, tag = sys.argv[1:10]
tm = open(f"{o}/time.txt", encoding="utf-8", errors="replace").read()
err = open(f"{o}/validate_export_{tag}.stderr", encoding="utf-8", errors="replace").read()
def grab(label):
    m = re.search(rf"{re.escape(label)}:\s*(.+)", tm)
    return m.group(1).strip() if m else None
peak = re.search(r"Memory peak:\s*(.+)", err)
out = {"command": f"marianos-collector validate-export --run {run}", "release": v,
       "utc_start": s, "utc_end": e, "wall_seconds": round(float(t1) - float(t0), 1), "exit_code": int(code),
       "gnu_time_max_rss_kib": grab("Maximum resident set size (kbytes)"), "gnu_time_elapsed": grab("Elapsed (wall clock) time (h:mm:ss or m:ss)"),
       "gnu_time_exit_status": grab("Exit status"), "systemd_memory_peak": peak.group(1).strip() if peak else None,
       "memory_bound": "MemoryMax=3G, no swap", "kernel_oom_lines": sum(1 for _ in open(f"{o}/kernel_oom.txt"))}
try:
    raw = open(f"{o}/validate_export_{tag}.json", encoding="utf-8").read()
    d = json.loads(raw[raw.index("{"):]) if raw.strip() else None
except Exception as x:
    d = None; out["output_parse_error"] = repr(x)[:300]
if isinstance(d, dict):
    out["output_keys"] = sorted(d)
    for k in ("passed", "statuses", "capture_check", "source_check", "manifest", "counts", "records"):
        if k in d:
            val = d[k]
            out[k] = val if not isinstance(val, list) else {"list_len": len(val), "first": val[:3]}
print(json.dumps(out, indent=1, default=str))
PY
echo "exit $code"
