#!/usr/bin/env bash

set -euo pipefail

SUITE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=config.sh
source "${SUITE_DIR}/config.sh"

log() { printf '[%(%FT%T%z)T] %s\n' -1 "$*"; }
die() { log "ERROR: $*" >&2; exit 1; }
need_cmd() { command -v "$1" >/dev/null 2>&1 || die "missing command: $1"; }

as_root() {
  if (( EUID == 0 )); then "$@"; else sudo "$@"; fi
}

tracefs_path() {
  if [[ -d /sys/kernel/tracing ]]; then printf '%s\n' /sys/kernel/tracing;
  elif [[ -d /sys/kernel/debug/tracing ]]; then printf '%s\n' /sys/kernel/debug/tracing;
  else return 1; fi
}

dirty_kb() {
  awk '/^(Dirty|Writeback):/ { total += $2 } END { print total + 0 }' /proc/meminfo
}

wait_for_recovery() {
  local deadline=$((SECONDS + RECOVERY_TIMEOUT_S)) value
  as_root sync
  while (( SECONDS < deadline )); do
    value="$(dirty_kb)"
    if (( value <= DIRTY_LIMIT_KB )); then
      log "storage recovered: Dirty+Writeback=${value} kB"
      return 0
    fi
    sleep 2
  done
  die "storage did not recover: Dirty+Writeback=$(dirty_kb) kB"
}

load_calibration() {
  [[ -r "${CALIBRATION_FILE}" ]] || die "run ./calibrate.sh first (${CALIBRATION_FILE})"
  # shellcheck disable=SC1090
  source "${CALIBRATION_FILE}"
  [[ "${BENCH_ITERS:-}" =~ ^[0-9]+$ ]] || die "invalid BENCH_ITERS in calibration file"
}

stop_process_group() {
  local pid="${1:-}"
  [[ -n "${pid}" ]] || return 0
  if kill -0 "${pid}" 2>/dev/null; then
    kill -TERM -- "-${pid}" 2>/dev/null || kill -TERM "${pid}" 2>/dev/null || true
    for _ in {1..50}; do kill -0 "${pid}" 2>/dev/null || return 0; sleep 0.1; done
    kill -KILL -- "-${pid}" 2>/dev/null || kill -KILL "${pid}" 2>/dev/null || true
  fi
}

csv_escape() {
  local value="${1//\"/\"\"}"
  printf '"%s"' "${value}"
}

cpulist_contains() {
  local list="$1" target="$2" item first last
  local -a items=()
  IFS=',' read -r -a items <<< "${list}"
  for item in "${items[@]}"; do
    if [[ "${item}" == *-* ]]; then
      first="${item%-*}"; last="${item#*-}"
      (( target >= first && target <= last )) && return 0
    elif [[ "${item}" == "${target}" ]]; then return 0
    fi
  done
  return 1
}

list_contains_csv() {
  local list="$1" target="$2" item
  local -a items=()
  IFS=',' read -r -a items <<< "${list}"
  for item in "${items[@]}"; do
    [[ "${item}" == "${target}" ]] && return 0
  done
  return 1
}

irq_total() {
  local irq="$1"
  awk -v key="${irq}:" '
    $1 == key {
      total=0
      for (i=2; i<=NF && $i ~ /^[0-9]+$/; i++) total += $i
      print total
      found=1
    }
    END { if (!found) print "NA" }
  ' /proc/interrupts
}

snapshot_managed_irqs() {
  local output="$1" irq
  printf 'irq,total\n' > "${output}"
  IFS=',' read -r -a irqs <<< "${MANAGED_DORMANT_IRQS}"
  for irq in "${irqs[@]}"; do
    printf '%s,%s\n' "${irq}" "$(irq_total "${irq}")" >> "${output}"
  done
}

compare_irq_snapshots() {
  local before="$1" after="$2" output="$3"
  python3 - "${before}" "${after}" "${output}" <<'PY'
import csv, sys
def load(path):
    with open(path, newline="") as f:
        return {r["irq"]: r["total"] for r in csv.DictReader(f)}
before, after = load(sys.argv[1]), load(sys.argv[2])
invalid = False
with open(sys.argv[3], "w", newline="") as f:
    w = csv.writer(f); w.writerow(("irq", "before", "after", "delta"))
    for irq in before:
        b, a = before[irq], after.get(irq, "NA")
        delta = "NA" if "NA" in (a, b) else int(a) - int(b)
        w.writerow((irq, b, a, delta))
        invalid |= delta == "NA" or delta != 0
raise SystemExit(1 if invalid else 0)
PY
}
