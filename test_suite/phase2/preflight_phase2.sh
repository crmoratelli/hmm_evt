#!/usr/bin/env bash
set -euo pipefail

PHASE2_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
SUITE_DIR="$(cd -- "${PHASE2_DIR}/.." && pwd)"
# shellcheck source=../lib.sh
source "${SUITE_DIR}/lib.sh"
# shellcheck source=config_phase2.sh
source "${PHASE2_DIR}/config_phase2.sh"

check_only=0
if [[ "${1:-}" == "--check-only" ]]; then
  check_only=1
elif [[ -n "${1:-}" ]]; then
  die "usage: $0 [--check-only]"
fi

source_file="${SUITE_DIR}/phase1/periodic_v2.c"
binary="${PHASE2_DIR}/periodic_v2"
[[ "$(sha256sum "${source_file}" | awk '{print $1}')" == "${PHASE2_SOURCE_SHA256}" ]] \
  || die "phase1 source differs from the approved Phase 2 source"

export RESULT_ROOT="${PHASE2_RESULT_ROOT}"
export CALIBRATION_FILE="${PHASE2_CALIBRATION_FILE}"
TDPS_REQUIRE_TRACING=0 "${SUITE_DIR}/validate_environment.sh"
load_calibration

[[ "${BENCH_ITERS}" == 151994 ]] || die "expected BENCH_ITERS=151994, got ${BENCH_ITERS}"
[[ "${PERIOD_NS}" == 5000000 ]] || die "expected PERIOD_NS=5000000"
[[ "${DEADLINE_NS}" == 3000000 ]] || die "expected DEADLINE_NS=3000000"
[[ "${CPU_RT}" == 3 ]] || die "expected CPU_RT=3"
[[ "${CPU_SIBLING}" == 11 ]] || die "expected CPU_SIBLING=11"
[[ "${RT_PRIORITY}" == 80 ]] || die "expected RT_PRIORITY=80"
cpulist_contains "${HOUSEKEEPING_CPUS}" "${PHASE2_LOGGER_CPU}" \
  || die "logger CPU ${PHASE2_LOGGER_CPU} is not a housekeeping CPU"
[[ "${PHASE2_LOGGER_CPU}" != "${CPU_RT}" && "${PHASE2_LOGGER_CPU}" != "${CPU_SIBLING}" ]] \
  || die "logger CPU shares the RT physical core"

mkdir -p "${PHASE2_RESULT_ROOT}" "${PHASE2_STAGE_ROOT}" "${IO_TEMP_PATH}"
[[ "$(findmnt -n -T "${PHASE2_RESULT_ROOT}" -o FSTYPE)" == ext4 ]] \
  || die "Phase 2 result/sink root is not ext4"
[[ "$(findmnt -n -T "${IO_TEMP_PATH}" -o FSTYPE)" == ext4 ]] \
  || die "I/O stress path is not ext4"
[[ "$(findmnt -n -T "${PHASE2_RESULT_ROOT}" -o SOURCE)" == "$(findmnt -n -T "${IO_TEMP_PATH}" -o SOURCE)" ]] \
  || die "functional sink and I/O stress do not share the same storage source"
[[ "$(findmnt -n -T "${PHASE2_STAGE_ROOT}" -o FSTYPE)" == tmpfs ]] \
  || die "Phase 2 staging root is not tmpfs"

if (( check_only )); then
  [[ -x "${binary}" ]] || die "missing Phase 2 binary; run preflight without --check-only"
else
  make -C "${PHASE2_DIR}" clean all
fi
"${binary}" --version | grep -F 'TDPS phase1 schema=2 fixed64 catch-up fixed-jobs' >/dev/null \
  || die "unexpected benchmark version"
binary_sha="$(sha256sum "${binary}" | awk '{print $1}')"

if (( ! check_only )); then
  started_buildkit=0
  if ! pgrep -x buildkitd >/dev/null; then
    as_root systemctl start buildkit 2>/dev/null || die "BuildKit is required for nerdctl build"
    started_buildkit=1
  fi
  as_root nerdctl --namespace "${TDPS_NAMESPACE}" build --tag "${PHASE2_IMAGE}" "${PHASE2_DIR}"
  if (( started_buildkit )); then as_root systemctl stop buildkit 2>/dev/null || true; fi
fi

embedded_sha="$(as_root nerdctl --namespace "${TDPS_NAMESPACE}" run --rm --net none \
  --entrypoint /usr/bin/sha256sum "${PHASE2_IMAGE}" /usr/local/bin/periodic_v2 | awk '{print $1}')"
[[ "${embedded_sha}" == "${binary_sha}" ]] || die "container binary differs from Phase 2 host binary"
as_root nerdctl --namespace "${TDPS_NAMESPACE}" run --rm --net none \
  "${PHASE2_IMAGE}" --version | grep -F 'schema=2' >/dev/null \
  || die "container benchmark version check failed"

jobs=$((PHASE2_DURATION_S * 1000000000 / PERIOD_NS))
offered_bytes=$((jobs * PHASE2_RECORD_BYTES))
available_shm="$(df -Pk "${PHASE2_STAGE_ROOT}" | awk 'NR==2 {print $4 * 1024}')"
(( available_shm >= 256 * 1024 * 1024 )) || die "less than 256 MiB available in tmpfs"

printf 'phase2_preflight=OK\n'
printf 'SOURCE_SHA256=%s\nBINARY_SHA256=%s\nIMAGE=%s\n' \
  "${PHASE2_SOURCE_SHA256}" "${binary_sha}" "${PHASE2_IMAGE}"
printf 'BENCH_ITERS=%s\nPERIOD_NS=%s\nDEADLINE_NS=%s\nJOBS_PER_FULL_RUN=%s\n' \
  "${BENCH_ITERS}" "${PERIOD_NS}" "${DEADLINE_NS}" "${jobs}"
printf 'OFFERED_BYTES_PER_RUN=%s\nQUEUE_CAPACITY=%s\nLOGGER_CPU=%s\n' \
  "${offered_bytes}" "${PHASE2_QUEUE_CAPACITY}" "${PHASE2_LOGGER_CPU}"
