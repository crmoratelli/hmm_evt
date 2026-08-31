#!/usr/bin/env bash
set -euo pipefail
SUITE_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
# shellcheck source=lib.sh
source "${SUITE_DIR}/lib.sh"

[[ -x "${SUITE_DIR}/benchmark/periodic_bench" ]] || die "run ./build_image.sh first"
"${SUITE_DIR}/validate_environment.sh" >/dev/null
mkdir -p "${RESULT_ROOT}"

values=()
for i in {1..7}; do
  value="$(as_root chrt -f "${RT_PRIORITY}" taskset -c "${CPU_RT}" \
    "${SUITE_DIR}/benchmark/periodic_bench" --period "${PERIOD_NS}" \
    --cpu-load "${CPU_LOAD}" --calibrate-only)"
  [[ "${value}" =~ ^[0-9]+$ ]] || die "invalid calibration result: ${value}"
  values+=("${value}")
done
median="$(printf '%s\n' "${values[@]}" | sort -n | sed -n '4p')"

tmp="${CALIBRATION_FILE}.tmp"
{
  printf 'BENCH_ITERS=%s\n' "${median}"
  printf 'CALIBRATED_AT=%q\n' "$(date -Is)"
  printf 'CALIBRATION_SAMPLES=%q\n' "${values[*]}"
  printf 'PERIOD_NS=%s\nCPU_LOAD=%s\nCPU_RT=%s\n' "${PERIOD_NS}" "${CPU_LOAD}" "${CPU_RT}"
} > "${tmp}"
mv "${tmp}" "${CALIBRATION_FILE}"
log "fixed BENCH_ITERS=${median}; samples=${values[*]}"
