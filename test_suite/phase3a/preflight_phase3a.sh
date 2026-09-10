#!/usr/bin/env bash
set -euo pipefail

PHASE3A_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
SUITE_DIR="$(cd -- "${PHASE3A_DIR}/.." && pwd)"
# shellcheck source=../lib.sh
source "${SUITE_DIR}/lib.sh"
# shellcheck source=config_phase3a.sh
source "${PHASE3A_DIR}/config_phase3a.sh"

source_file="${SUITE_DIR}/phase1/periodic_v2.c"
binary="${SUITE_DIR}/phase1/periodic_v2"

[[ "$(sha256sum "${source_file}" | awk '{print $1}')" == "${PHASE3A_SOURCE_SHA256}" ]] \
  || die "phase1 source hash differs from the approved source"

"${SUITE_DIR}/validate_environment.sh"
make -C "${SUITE_DIR}/phase1" clean all
"${binary}" --version
load_calibration

[[ "${BENCH_ITERS}" == 151994 ]] || die "expected BENCH_ITERS=151994, got ${BENCH_ITERS}"
[[ "${PERIOD_NS}" == 5000000 ]] || die "expected PERIOD_NS=5000000"
[[ "${DEADLINE_NS}" == 3000000 ]] || die "expected DEADLINE_NS=3000000"
[[ "${DURATION_S}" == 500 ]] || die "expected DURATION_S=500"
[[ "${CPU_RT}" == 3 ]] || die "expected CPU_RT=3"
[[ "${RT_PRIORITY}" == 80 ]] || die "expected RT_PRIORITY=80"

ext4_type="$(findmnt -n -T /home/ghost -o FSTYPE)"
tmp_type="$(findmnt -n -T /tmp -o FSTYPE)"
shm_type="$(findmnt -n -T /dev/shm -o FSTYPE)"
ext4_source="$(findmnt -n -T /home/ghost -o SOURCE)"
tmp_source="$(findmnt -n -T /tmp -o SOURCE)"
[[ "${ext4_type}" == ext4 ]] || die "/home/ghost is not ext4 (${ext4_type})"
[[ "${tmp_type}" == ext4 ]] || die "/tmp is not ext4 (${tmp_type})"
[[ "${ext4_source}" == "${tmp_source}" ]] || die "/home/ghost and /tmp are not on the same source"
[[ "${shm_type}" == tmpfs ]] || die "/dev/shm is not tmpfs (${shm_type})"

jobs=$((DURATION_S * 1000000000 / PERIOD_NS))
offered_bytes=$((jobs * 64))
available_shm="$(df -Pk /dev/shm | awk 'NR==2 {print $4 * 1024}')"
(( available_shm >= offered_bytes + 64 * 1024 * 1024 )) \
  || die "insufficient /dev/shm space"

printf 'phase3a_preflight=OK\n'
printf 'BENCH_ITERS=%s\nJOBS=%s\nOFFERED_BYTES=%s\n' "${BENCH_ITERS}" "${jobs}" "${offered_bytes}"
printf 'EXT4_SOURCE=%s\nTMPFS_SOURCE=%s\n' "${ext4_source}" "$(findmnt -n -T /dev/shm -o SOURCE)"
printf 'BINARY_SHA256=%s\n' "$(sha256sum "${binary}" | awk '{print $1}')"

