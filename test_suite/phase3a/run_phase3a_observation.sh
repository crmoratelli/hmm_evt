#!/usr/bin/env bash
set -euo pipefail

PHASE3A_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
SUITE_DIR="$(cd -- "${PHASE3A_DIR}/.." && pwd)"
# shellcheck source=../lib.sh
source "${SUITE_DIR}/lib.sh"
# shellcheck source=config_phase3a.sh
source "${PHASE3A_DIR}/config_phase3a.sh"

sink_kind="${1:-}"
rep="${2:-}"
sequence="${3:-}"
[[ "${sink_kind}" =~ ^(ext4|tmpfs)$ ]] || die "sink must be ext4 or tmpfs"
[[ "${rep}" =~ ^[0-9]+$ ]] || die "invalid replication"
[[ "${sequence}" =~ ^[0-9]+$ ]] || die "invalid sequence"

load_calibration
binary="${SUITE_DIR}/phase1/periodic_v2"
[[ -x "${binary}" ]] || die "missing phase1 binary; run preflight_phase3a.sh"
[[ "$(sha256sum "${SUITE_DIR}/phase1/periodic_v2.c" | awk '{print $1}')" == "${PHASE3A_SOURCE_SHA256}" ]] \
  || die "phase1 source hash differs from the approved source"

jobs=$((DURATION_S * 1000000000 / PERIOD_NS))
run_id="$(printf '%04d_io_host_inline_%s_run%02d' "${sequence}" "${sink_kind}" "${rep}")"
run_dir="${PHASE3A_RESULT_ROOT}/runs/${run_id}"
stage_dir="${PHASE3A_TMPFS_ROOT}/${run_id}"
[[ ! -e "${run_dir}" ]] || die "run already exists: ${run_dir}"
[[ ! -e "${stage_dir}" ]] || die "stage already exists: ${stage_dir}"
mkdir -p "${run_dir}" "${stage_dir}"

if [[ "${sink_kind}" == ext4 ]]; then
  sink_path="${run_dir}/functional.bin"
else
  sink_path="${stage_dir}/functional.bin"
fi
samples_path="${stage_dir}/samples.csv"

sudo_keepalive_pid="" interference_pid="" telemetry_pid=""
cleanup() {
  set +e
  stop_process_group "${interference_pid}"
  if [[ -n "${telemetry_pid}" ]]; then kill "${telemetry_pid}" 2>/dev/null; wait "${telemetry_pid}" 2>/dev/null; fi
  if [[ -n "${sudo_keepalive_pid}" ]]; then kill "${sudo_keepalive_pid}" 2>/dev/null; wait "${sudo_keepalive_pid}" 2>/dev/null; fi
  if [[ -d "${stage_dir}" ]]; then cp -a "${stage_dir}/." "${run_dir}/" 2>/dev/null || true; fi
}
trap cleanup EXIT INT TERM

if (( EUID != 0 )); then
  sudo -v
  ( while sleep 60; do sudo -n true || exit; done ) &
  sudo_keepalive_pid=$!
fi

wait_for_recovery
cat > "${stage_dir}/metadata.env" <<EOF
RUN_ID=${run_id}
SEQUENCE=${sequence}
SCENARIO=io
SUBSTRATE=host
ARCHITECTURE=inline
SINK_KIND=${sink_kind}
SINK_PATH=${sink_path}
REPLICATION=${rep}
BENCH_ITERS=${BENCH_ITERS}
PERIOD_NS=${PERIOD_NS}
DEADLINE_NS=${DEADLINE_NS}
DURATION_S=${DURATION_S}
JOBS=${jobs}
CPU_RT=${CPU_RT}
CPU_SIBLING=${CPU_SIBLING}
HOUSEKEEPING_CPUS=${HOUSEKEEPING_CPUS}
RT_PRIORITY=${RT_PRIORITY}
SOURCE_SHA256=${PHASE3A_SOURCE_SHA256}
BINARY_SHA256=$(sha256sum "${binary}" | awk '{print $1}')
GIT_COMMIT=$(git -C "${SUITE_DIR}/.." rev-parse HEAD 2>/dev/null || printf unknown)
GIT_BRANCH=$(git -C "${SUITE_DIR}/.." rev-parse --abbrev-ref HEAD 2>/dev/null || printf unknown)
STRESS_COMMAND='taskset -c ${HOUSEKEEPING_CPUS} stress-ng --io 4 --hdd 2 --hdd-bytes 10G --temp-path ${IO_TEMP_PATH}/${run_id}'
STARTED_AT=$(date -Is)
EOF
cat /proc/cmdline > "${stage_dir}/cmdline.txt"

io_run_path="${IO_TEMP_PATH}/${run_id}"
mkdir -p "${io_run_path}"
setsid taskset -c "${HOUSEKEEPING_CPUS}" stress-ng \
  --io 4 --hdd 2 --hdd-bytes 10G \
  --temp-path "${io_run_path}" --timeout "$((DURATION_S + INTERFERENCE_WARMUP_S + 60))s" \
  >"${stage_dir}/interference.log" 2>&1 &
interference_pid=$!

setsid taskset -c "${HOUSEKEEPING_CPUS}" python3 "${SUITE_DIR}/collect_telemetry.py" \
  --out "${stage_dir}/telemetry.jsonl" --interval "${TELEMETRY_INTERVAL_S}" &
telemetry_pid=$!

sleep "${INTERFERENCE_WARMUP_S}"
kill -0 "${interference_pid}" 2>/dev/null || die "I/O stress ended during warm-up"
kill -0 "${telemetry_pid}" 2>/dev/null || die "telemetry ended during warm-up"

snapshot_managed_irqs "${stage_dir}/managed_irqs_before.csv"
printf 'MEASUREMENT_STARTED_AT=%s\n' "$(date -Is)" >> "${stage_dir}/metadata.env"

benchmark_cmd=(
  "${binary}" --mode inline --period "${PERIOD_NS}" --deadline "${DEADLINE_NS}"
  --jobs "${jobs}" --iters "${BENCH_ITERS}" --out "${samples_path}"
  --sink "${sink_path}" --mlock
)
printf '%q ' sudo chrt -f "${RT_PRIORITY}" taskset -c "${CPU_RT}" "${benchmark_cmd[@]}" \
  > "${stage_dir}/benchmark_command.txt"
printf '\n' >> "${stage_dir}/benchmark_command.txt"

as_root chrt -f "${RT_PRIORITY}" taskset -c "${CPU_RT}" "${benchmark_cmd[@]}" \
  >"${stage_dir}/benchmark.log" 2>&1

snapshot_managed_irqs "${stage_dir}/managed_irqs_after.csv"
printf 'MEASUREMENT_COMPLETED_AT=%s\n' "$(date -Is)" >> "${stage_dir}/metadata.env"
irq_valid=1
if compare_irq_snapshots "${stage_dir}/managed_irqs_before.csv" \
    "${stage_dir}/managed_irqs_after.csv" "${stage_dir}/managed_irq_delta.csv"; then
  printf 'VALID=1\nMANAGED_IRQ_ACTIVITY=0\n' >> "${stage_dir}/metadata.env"
else
  irq_valid=0
  printf 'VALID=0\nMANAGED_IRQ_ACTIVITY=1\nINVALID_REASON=managed_irq_activity_during_measurement\n' \
    >> "${stage_dir}/metadata.env"
  : > "${stage_dir}/INVALID_IRQ_ACTIVITY"
fi

stop_process_group "${interference_pid}"
interference_pid=""
kill "${telemetry_pid}" 2>/dev/null || true
wait "${telemetry_pid}" 2>/dev/null || true
telemetry_pid=""
rmdir "${io_run_path}" 2>/dev/null || true

cp -a "${stage_dir}/." "${run_dir}/"
expected_bytes=$((jobs * 64))
actual_bytes="$(stat -c %s "${sink_path}")"
[[ "${actual_bytes}" == "${expected_bytes}" ]] || die "functional output size ${actual_bytes}, expected ${expected_bytes}"

python3 "${PHASE3A_DIR}/summarize_phase3a.py" --run-dir "${run_dir}"
rm -rf -- "${stage_dir:?}"
wait_for_recovery
if (( ! irq_valid )); then
  die "observation invalidated by managed IRQ activity: ${run_id}"
fi
printf 'COMPLETED_AT=%s\n' "$(date -Is)" >> "${run_dir}/metadata.env"
: > "${run_dir}/COMPLETED"

sleep "${BETWEEN_OBSERVATIONS_S}"
trap - EXIT INT TERM
if [[ -n "${sudo_keepalive_pid}" ]]; then kill "${sudo_keepalive_pid}" 2>/dev/null || true; wait "${sudo_keepalive_pid}" 2>/dev/null || true; fi
log "completed ${run_id}"
