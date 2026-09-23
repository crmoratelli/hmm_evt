#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd -- "$(dirname -- "$0")" && pwd)"; SUITE="$(cd -- "${DIR}/.." && pwd)"
source "${SUITE}/lib.sh"; source "${DIR}/config_phase4b.sh"
check_only=0; [[ "${1:-}" == --check-only ]] && check_only=1
[[ -z "${1:-}" || "${1:-}" == --check-only ]] || die "usage: $0 [--check-only]"
export RESULT_ROOT="${PHASE4B_RESULT_ROOT}"
TDPS_REQUIRE_TRACING=0 "${SUITE}/validate_environment.sh"
for cmd in taskset chrt python3 make stress-ng findmnt sha256sum; do need_cmd "$cmd"; done
python3 -c 'import pandas' || die "Python dependency missing: python3 -m pip install -r ${DIR}/requirements.txt"
[[ "${CPU_RT}" == 3 && "${CPU_SIBLING}" == 11 ]] || die "expected isolated SMT pair 3,11"
[[ "${RT_PRIORITY}" == 80 ]] || die "expected RT_PRIORITY=80"
[[ "${PHASE4B_PERIOD_NS}" == 5000000 && "${PHASE4B_DEADLINE_NS}" == 5000000 ]] || die "Phase 4B fixes T=D=5 ms"
mkdir -p "${PHASE4B_RESULT_ROOT}" "${PHASE4B_STAGE_ROOT}" "${PHASE4B_IO_TEMP_PATH}"
[[ "$(findmnt -n -T "${PHASE4B_STAGE_ROOT}" -o FSTYPE)" == tmpfs ]] || die "staging root must be tmpfs"
sink_fs="$(findmnt -n -T "${PHASE4B_RESULT_ROOT}" -o FSTYPE)"
io_fs="$(findmnt -n -T "${PHASE4B_IO_TEMP_PATH}" -o FSTYPE)"
[[ "$sink_fs" == ext4 && "$io_fs" == ext4 ]] || die "result and I/O paths must be ext4 (got $sink_fs/$io_fs)"
[[ "$(findmnt -n -T "${PHASE4B_RESULT_ROOT}" -o SOURCE)" == "$(findmnt -n -T "${PHASE4B_IO_TEMP_PATH}" -o SOURCE)" ]] || die "sink and stress paths must share the same filesystem"
(( check_only )) || make -C "$DIR" clean all
[[ -x "${DIR}/periodic_v2" ]] || die "missing binary; run preflight without --check-only"
printf 'phase4b_preflight=OK\nSOURCE_SHA256=%s\nBINARY_SHA256=%s\n' "$(sha256sum "${SUITE}/phase1/periodic_v2.c"|awk '{print $1}')" "$(sha256sum "${DIR}/periodic_v2"|awk '{print $1}')"
printf 'PERIOD_NS=%s\nDEADLINE_NS=%s\nFULL_DURATION_S=%s\nREPLICATIONS=%s\n' "$PHASE4B_PERIOD_NS" "$PHASE4B_DEADLINE_NS" "$PHASE4B_DURATION_S" "$PHASE4B_REPLICATIONS"
