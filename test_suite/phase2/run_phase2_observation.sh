#!/usr/bin/env bash
set -euo pipefail

PHASE2_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
SUITE_DIR="$(cd -- "${PHASE2_DIR}/.." && pwd)"
# shellcheck source=../lib.sh
source "${SUITE_DIR}/lib.sh"
# shellcheck source=config_phase2.sh
source "${PHASE2_DIR}/config_phase2.sh"

architecture="${1:-}"
scenario="${2:-}"
substrate="${3:-}"
replication="${4:-}"
block="${5:-}"
sequence="${6:-}"
[[ "${architecture}" =~ ^(deferred|inline|async)$ ]] || die "invalid architecture"
[[ "${scenario}" =~ ^(control|io)$ ]] || die "invalid scenario"
[[ "${substrate}" =~ ^(host|container)$ ]] || die "invalid substrate"
[[ "${replication}" =~ ^[0-9]+$ && "${block}" =~ ^[0-9]+$ && "${sequence}" =~ ^[0-9]+$ ]] \
  || die "invalid replication, block, or sequence"

result_root="${PHASE2_ACTIVE_ROOT:-${PHASE2_RESULT_ROOT}}"
duration_s="${PHASE2_ACTIVE_DURATION_S:-${PHASE2_DURATION_S}}"
profile="${PHASE2_PROFILE:-full}"
[[ "${duration_s}" =~ ^[0-9]+$ ]] && (( duration_s > 0 )) || die "invalid duration"
export CALIBRATION_FILE="${PHASE2_CALIBRATION_FILE}"
load_calibration

binary="${PHASE2_DIR}/periodic_v2"
source_file="${SUITE_DIR}/phase1/periodic_v2.c"
[[ -x "${binary}" ]] || die "missing Phase 2 binary; run preflight_phase2.sh"
[[ "$(sha256sum "${source_file}" | awk '{print $1}')" == "${PHASE2_SOURCE_SHA256}" ]] \
  || die "approved source hash changed"

numerator=$((duration_s * 1000000000))
(( numerator % PERIOD_NS == 0 )) || die "duration is not an integer number of periods"
jobs=$((numerator / PERIOD_NS))
run_id="$(printf '%04d_%s_%s_%s_run%02d' "${sequence}" "${scenario}" "${substrate}" "${architecture}" "${replication}")"
run_dir="${result_root}/runs/${run_id}"
stage_dir="${PHASE2_STAGE_ROOT}/${profile}-${run_id}"
[[ ! -e "${run_dir}" ]] || die "run already exists: ${run_dir}"
[[ ! -e "${stage_dir}" ]] || die "stage already exists: ${stage_dir}"
mkdir -p "${run_dir}" "${stage_dir}"

samples_path="${stage_dir}/samples.csv"
sink_path="${run_dir}/functional.bin"
telemetry_pid="" interference_pid="" sudo_keepalive_pid="" completed=0
io_run_path=""
container_name="tdps-phase2-${profile}-${sequence}"

cleanup() {
  rc=$?
  set +e
  stop_process_group "${interference_pid}"
  if [[ -n "${telemetry_pid}" ]]; then kill "${telemetry_pid}" 2>/dev/null; wait "${telemetry_pid}" 2>/dev/null; fi
  as_root timeout 30s nerdctl --namespace "${TDPS_NAMESPACE}" rm -f "${container_name}" >/dev/null 2>&1 || true
  if [[ -n "${sudo_keepalive_pid}" ]]; then kill "${sudo_keepalive_pid}" 2>/dev/null; wait "${sudo_keepalive_pid}" 2>/dev/null; fi
  if [[ -d "${stage_dir}" ]]; then
    cp -a "${stage_dir}/." "${run_dir}/" 2>/dev/null || true
    rm -rf -- "${stage_dir:?}" 2>/dev/null || true
  fi
  if (( ! completed )); then
    printf 'FAILED_AT=%s\nEXIT_CODE=%s\n' "$(date -Is)" "${rc}" >> "${run_dir}/metadata.env" 2>/dev/null || true
    : > "${run_dir}/FAILED"
  fi
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
PROFILE=${profile}
STATE=running
SEQUENCE=${sequence}
BLOCK=${block}
REPLICATION=${replication}
ARCHITECTURE=${architecture}
SCENARIO=${scenario}
SUBSTRATE=${substrate}
SINK_KIND=shared_ext4
FUNCTIONAL_CONTRACT=kernel_acceptance_no_durability
ASYNC_FULL_POLICY=${PHASE2_FULL_POLICY}
ASYNC_QUEUE_CAPACITY=${PHASE2_QUEUE_CAPACITY}
LOGGER_CPU=${PHASE2_LOGGER_CPU}
LOGGER_POLICY=${PHASE2_LOGGER_POLICY}
LOGGER_PRIORITY=${PHASE2_LOGGER_PRIORITY}
BENCH_ITERS=${BENCH_ITERS}
PERIOD_NS=${PERIOD_NS}
DEADLINE_NS=${DEADLINE_NS}
DURATION_S=${duration_s}
JOBS=${jobs}
RECORD_BYTES=${PHASE2_RECORD_BYTES}
CPU_RT=${CPU_RT}
CPU_SIBLING=${CPU_SIBLING}
HOUSEKEEPING_CPUS=${HOUSEKEEPING_CPUS}
RT_PRIORITY=${RT_PRIORITY}
SOURCE_SHA256=${PHASE2_SOURCE_SHA256}
BINARY_SHA256=$(sha256sum "${binary}" | awk '{print $1}')
IMAGE=${PHASE2_IMAGE}
GIT_COMMIT=$(git -C "${SUITE_DIR}/.." rev-parse HEAD 2>/dev/null || printf unknown)
GIT_BRANCH=$(git -C "${SUITE_DIR}/.." rev-parse --abbrev-ref HEAD 2>/dev/null || printf unknown)
STRESS_COMMAND=taskset_housekeeping_stress-ng_io4_hdd2_hdd-bytes10G
STARTED_AT=$(date -Is)
EOF
cat /proc/cmdline > "${stage_dir}/cmdline.txt"

setsid taskset -c "${HOUSEKEEPING_CPUS}" python3 "${SUITE_DIR}/collect_telemetry.py" \
  --out "${stage_dir}/telemetry.jsonl" --interval "${TELEMETRY_INTERVAL_S}" &
telemetry_pid=$!

if [[ "${scenario}" == io ]]; then
  io_run_path="${IO_TEMP_PATH}/${profile}-${run_id}"
  mkdir -p "${io_run_path}"
  printf 'IO_RUN_PATH=%s\n' "${io_run_path}" >> "${stage_dir}/metadata.env"
  setsid taskset -c "${HOUSEKEEPING_CPUS}" stress-ng \
    --io 4 --hdd 2 --hdd-bytes 10G --temp-path "${io_run_path}" \
    --timeout "$((duration_s + INTERFERENCE_WARMUP_S + PHASE2_DRAIN_TIMEOUT_S + 60))s" \
    >"${stage_dir}/interference.log" 2>&1 &
  interference_pid=$!
fi

sleep "${INTERFERENCE_WARMUP_S}"
kill -0 "${telemetry_pid}" 2>/dev/null || die "telemetry ended during warm-up"
if [[ "${scenario}" == io ]]; then
  kill -0 "${interference_pid}" 2>/dev/null || die "I/O stress ended during warm-up"
fi

snapshot_managed_irqs "${stage_dir}/managed_irqs_before.csv"
printf 'MEASUREMENT_STARTED_AT=%s\n' "$(date -Is)" >> "${stage_dir}/metadata.env"

bench_args=(
  --mode "${architecture}" --period "${PERIOD_NS}" --deadline "${DEADLINE_NS}"
  --jobs "${jobs}" --iters "${BENCH_ITERS}" --out "${samples_path}"
  --sink "${sink_path}" --logger-cpu "${PHASE2_LOGGER_CPU}"
  --queue "${PHASE2_QUEUE_CAPACITY}" --mlock
)
timeout_s=$((duration_s + PHASE2_DRAIN_TIMEOUT_S))
if [[ "${substrate}" == host ]]; then
  printf '%q ' sudo timeout --signal=TERM --kill-after=10 "${timeout_s}s" \
    chrt -f "${RT_PRIORITY}" taskset -c "${CPU_RT}" "${binary}" "${bench_args[@]}" \
    > "${stage_dir}/benchmark_command.txt"
  printf '\n' >> "${stage_dir}/benchmark_command.txt"
  as_root timeout --signal=TERM --kill-after=10 "${timeout_s}s" \
    chrt -f "${RT_PRIORITY}" taskset -c "${CPU_RT}" "${binary}" "${bench_args[@]}" \
    >"${stage_dir}/benchmark.stdout" 2>"${stage_dir}/benchmark.log"
else
  container_args=(
    --mode "${architecture}" --period "${PERIOD_NS}" --deadline "${DEADLINE_NS}"
    --jobs "${jobs}" --iters "${BENCH_ITERS}" --out /results/samples.csv
    --sink /sink/functional.bin --logger-cpu "${PHASE2_LOGGER_CPU}"
    --queue "${PHASE2_QUEUE_CAPACITY}" --mlock
  )
  printf '%q ' sudo timeout --signal=TERM --kill-after=10 "${timeout_s}s" nerdctl \
    --namespace "${TDPS_NAMESPACE}" run --net none --name "${container_name}" \
    --pid host --cpuset-cpus "${CPU_RT},${PHASE2_LOGGER_CPU}" \
    --cap-add SYS_NICE --cap-add IPC_LOCK --ulimit rtprio=99 --ulimit memlock=-1 \
    --volume "${stage_dir}:/results" --volume "${run_dir}:/sink" \
    --entrypoint /usr/bin/taskset "${PHASE2_IMAGE}" -c "${CPU_RT}" \
    chrt -f "${RT_PRIORITY}" /usr/local/bin/periodic_v2 "${container_args[@]}" \
    > "${stage_dir}/benchmark_command.txt"
  printf '\n' >> "${stage_dir}/benchmark_command.txt"
  as_root timeout --signal=TERM --kill-after=10 "${timeout_s}s" \
    nerdctl --namespace "${TDPS_NAMESPACE}" run --net none --name "${container_name}" \
    --pid host --cpuset-cpus "${CPU_RT},${PHASE2_LOGGER_CPU}" \
    --cap-add SYS_NICE --cap-add IPC_LOCK --ulimit rtprio=99 --ulimit memlock=-1 \
    --volume "${stage_dir}:/results" --volume "${run_dir}:/sink" \
    --entrypoint /usr/bin/taskset "${PHASE2_IMAGE}" -c "${CPU_RT}" \
    chrt -f "${RT_PRIORITY}" /usr/local/bin/periodic_v2 "${container_args[@]}" \
    >"${stage_dir}/benchmark.stdout" 2>"${stage_dir}/benchmark.log"
fi

snapshot_managed_irqs "${stage_dir}/managed_irqs_after.csv"
printf 'MEASUREMENT_COMPLETED_AT=%s\nSTATE=measured\n' "$(date -Is)" >> "${stage_dir}/metadata.env"
runtime_invalid=0
if ! kill -0 "${telemetry_pid}" 2>/dev/null; then
  runtime_invalid=1
  printf 'VALID=0\nINVALID_REASON=telemetry_ended_during_measurement\n' >> "${stage_dir}/metadata.env"
  : > "${stage_dir}/INVALID_RUNTIME"
fi
if [[ "${scenario}" == io ]] && ! kill -0 "${interference_pid}" 2>/dev/null; then
  runtime_invalid=1
  printf 'VALID=0\nINVALID_REASON=io_stress_ended_during_measurement\n' >> "${stage_dir}/metadata.env"
  : > "${stage_dir}/INVALID_RUNTIME"
fi
if compare_irq_snapshots "${stage_dir}/managed_irqs_before.csv" \
    "${stage_dir}/managed_irqs_after.csv" "${stage_dir}/managed_irq_delta.csv"; then
  printf 'MANAGED_IRQ_ACTIVITY=0\n' >> "${stage_dir}/metadata.env"
else
  printf 'VALID=0\nMANAGED_IRQ_ACTIVITY=1\nINVALID_REASON=managed_irq_activity_during_measurement\n' \
    >> "${stage_dir}/metadata.env"
  : > "${stage_dir}/INVALID_IRQ_ACTIVITY"
fi

if [[ "${substrate}" == container ]]; then
  if as_root timeout 30s nerdctl --namespace "${TDPS_NAMESPACE}" rm -f "${container_name}"; then
    printf 'CONTAINER_CLEANUP=completed\n' >> "${stage_dir}/metadata.env"
  else
    printf 'VALID=0\nCONTAINER_CLEANUP=failed\nINVALID_REASON=container_cleanup_failed\n' \
      >> "${stage_dir}/metadata.env"
    die "container cleanup failed: ${container_name}"
  fi
fi

stop_process_group "${interference_pid}"
interference_pid=""
kill "${telemetry_pid}" 2>/dev/null || true
wait "${telemetry_pid}" 2>/dev/null || true
telemetry_pid=""
if [[ -n "${io_run_path}" ]]; then rmdir "${io_run_path}" 2>/dev/null || true; fi

cp -a "${stage_dir}/." "${run_dir}/"
python3 "${PHASE2_DIR}/summarize_phase2.py" --run-dir "${run_dir}" \
  --shock-threshold-ns "${PHASE2_SHOCK_THRESHOLD_NS}"
[[ ! -e "${run_dir}/INVALID_IRQ_ACTIVITY" ]] \
  || die "observation invalidated by managed IRQ activity: ${run_id}"
(( ! runtime_invalid )) || die "observation invalidated by observer/interference failure: ${run_id}"

printf 'VALID=1\nSTATE=completed\nCOMPLETED_AT=%s\n' "$(date -Is)" >> "${run_dir}/metadata.env"
: > "${run_dir}/COMPLETED"
rm -rf -- "${stage_dir:?}"
completed=1
wait_for_recovery
sleep "${BETWEEN_OBSERVATIONS_S}"
trap - EXIT INT TERM
if [[ -n "${sudo_keepalive_pid}" ]]; then kill "${sudo_keepalive_pid}" 2>/dev/null || true; wait "${sudo_keepalive_pid}" 2>/dev/null || true; fi
log "completed ${run_id}"
