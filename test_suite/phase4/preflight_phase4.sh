#!/usr/bin/env bash
set -euo pipefail

PHASE4_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
SUITE_DIR="$(cd -- "${PHASE4_DIR}/.." && pwd)"
source "${SUITE_DIR}/lib.sh"
source "${PHASE4_DIR}/config_phase4.sh"

check_only=0
[[ "${1:-}" == "--check-only" ]] && check_only=1
[[ -z "${1:-}" || "${1:-}" == "--check-only" ]] || die "usage: $0 [--check-only]"

export RESULT_ROOT="${PHASE4_RESULT_ROOT}"
TDPS_REQUIRE_TRACING=0 "${SUITE_DIR}/validate_environment.sh"
need_cmd taskset
need_cmd chrt
need_cmd python3
need_cmd gcc
need_cmd make

[[ "${CPU_RT}" == 3 ]] || die "expected CPU_RT=3"
[[ "${CPU_SIBLING}" == 11 ]] || die "expected CPU_SIBLING=11"
[[ "${RT_PRIORITY}" == 80 ]] || die "expected RT_PRIORITY=80"
[[ "${PHASE4_PERIOD_NS}" == 5000000 ]] || die "Phase 4 protocol fixes T=5 ms"
[[ "${PHASE4_DEADLINE_NS}" == "${PHASE4_PERIOD_NS}" ]] || die "Phase 4 requires D=T"
(( PHASE4_SHOCK_JOB >= 50 && PHASE4_JOBS - PHASE4_SHOCK_JOB >= 100 )) \
  || die "insufficient pre/post-shock jobs"

mkdir -p "${PHASE4_RESULT_ROOT}" "${PHASE4_STAGE_ROOT}"
[[ "$(findmnt -n -T "${PHASE4_STAGE_ROOT}" -o FSTYPE)" == tmpfs ]] \
  || die "Phase 4 staging root is not tmpfs"

if (( ! check_only )); then make -C "${PHASE4_DIR}" clean all; fi
binary="${PHASE4_DIR}/periodic_phase4"
[[ -x "${binary}" ]] || die "missing binary; run preflight without --check-only"
"${binary}" --version | grep -F 'TDPS phase4 schema=1 controlled-block fixed-jobs' >/dev/null \
  || die "unexpected benchmark version"

printf 'phase4_preflight=OK\n'
printf 'SOURCE_SHA256=%s\nBINARY_SHA256=%s\n' \
  "$(sha256sum "${PHASE4_DIR}/periodic_phase4.c" | awk '{print $1}')" \
  "$(sha256sum "${binary}" | awk '{print $1}')"
printf 'PERIOD_NS=%s\nDEADLINE_NS=%s\nJOBS=%s\nSHOCK_JOB=%s\n' \
  "${PHASE4_PERIOD_NS}" "${PHASE4_DEADLINE_NS}" "${PHASE4_JOBS}" "${PHASE4_SHOCK_JOB}"
