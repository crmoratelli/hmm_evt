#!/usr/bin/env bash
set -euo pipefail
SUITE_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
# shellcheck source=lib.sh
source "${SUITE_DIR}/lib.sh"

scenario="${1:-}"
substrate="${2:-}"
rep="${3:-}"
trace_mode="${4:-full}"
sequence="${5:-0}"
[[ "${scenario}" =~ ^(control|io|churn)$ ]] || die "scenario must be control, io, or churn"
[[ "${substrate}" =~ ^(host|container)$ ]] || die "substrate must be host or container"
[[ "${trace_mode}" =~ ^(none|telemetry|full)$ ]] || die "trace mode must be none, telemetry, or full"
[[ "${rep}" =~ ^[0-9]+$ ]] || die "invalid replication"

load_calibration
sudo_keepalive_pid=""
if (( EUID != 0 )); then
  sudo -v
  ( while sleep 60; do sudo -n true || exit; done ) &
  sudo_keepalive_pid=$!
fi
run_id="$(printf '%04d_%s_%s_run%02d_%s' "${sequence}" "${scenario}" "${substrate}" "${rep}" "${trace_mode}")"
run_dir="${RESULT_ROOT}/runs/${run_id}"
[[ ! -e "${run_dir}" ]] || die "run already exists: ${run_dir}"
mkdir -p "${run_dir}"
stage_dir="/dev/shm/tdps-causal-${run_id}"
[[ ! -e "${stage_dir}" ]] || die "staging directory already exists: ${stage_dir}"
mkdir -p "${stage_dir}"

telemetry_pid="" interference_pid="" fifo_reader_pid="" trace_started=0
io_run_path=""
cleanup() {
  set +e
  stop_process_group "${interference_pid}"
  if [[ -n "${telemetry_pid}" ]]; then kill "${telemetry_pid}" 2>/dev/null; wait "${telemetry_pid}" 2>/dev/null; fi
  if [[ -n "${fifo_reader_pid}" ]]; then kill "${fifo_reader_pid}" 2>/dev/null; wait "${fifo_reader_pid}" 2>/dev/null; fi
  if [[ -n "${sudo_keepalive_pid}" ]]; then kill "${sudo_keepalive_pid}" 2>/dev/null; wait "${sudo_keepalive_pid}" 2>/dev/null; fi
  if (( trace_started )); then "${SUITE_DIR}/collect_trace.sh" stop "${stage_dir}" || true; fi
  as_root nerdctl --namespace "${TDPS_NAMESPACE}" rm -f "tdps-bench-${sequence}" >/dev/null 2>&1 || true
  while read -r id; do
    [[ -n "${id}" ]] && as_root nerdctl --namespace "${TDPS_NAMESPACE}" rm -f "${id}" >/dev/null 2>&1 || true
  done < <(as_root nerdctl --namespace "${TDPS_NAMESPACE}" ps -aq --filter 'name=tdps-churn-' 2>/dev/null || true)
  if [[ -n "${io_run_path}" ]]; then rmdir "${io_run_path}" 2>/dev/null || true; fi
  if [[ -d "${stage_dir}" ]]; then
    rm -f "${stage_dir}/shock.fifo" 2>/dev/null || true
    cp -a "${stage_dir}/." "${run_dir}/" 2>/dev/null || true
    rm -rf -- "${stage_dir}" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

cat > "${stage_dir}/metadata.env" <<EOF
RUN_ID=${run_id}
SEQUENCE=${sequence}
SCENARIO=${scenario}
SUBSTRATE=${substrate}
REPLICATION=${rep}
TRACE_MODE=${trace_mode}
BENCH_ITERS=${BENCH_ITERS}
PERIOD_NS=${PERIOD_NS}
DEADLINE_NS=${DEADLINE_NS}
DURATION_S=${DURATION_S}
CPU_RT=${CPU_RT}
CPU_SIBLING=${CPU_SIBLING}
HOUSEKEEPING_CPUS=${HOUSEKEEPING_CPUS}
SHOCK_THRESHOLD_NS=${SHOCK_THRESHOLD_NS}
STARTED_AT=$(date -Is)
EOF
cat /proc/cmdline > "${stage_dir}/cmdline.txt"

if [[ "${trace_mode}" == full ]]; then
  "${SUITE_DIR}/collect_trace.sh" start "${stage_dir}"
  trace_started=1
else
  mkfifo "${stage_dir}/shock.fifo"
  # Keep one reader open so the benchmark's nonblocking FIFO open succeeds.
  ( exec 9<>"${stage_dir}/shock.fifo"; IFS= read -r line <&9 && printf '%s\n' "${line}" > "${stage_dir}/first_shock.txt" ) &
  fifo_reader_pid=$!
fi

if [[ "${trace_mode}" != none ]]; then
  setsid taskset -c "${HOUSEKEEPING_CPUS}" python3 "${SUITE_DIR}/collect_telemetry.py" \
    --out "${stage_dir}/telemetry.jsonl" --interval "${TELEMETRY_INTERVAL_S}" &
  telemetry_pid=$!
fi

case "${scenario}" in
  control) log "control observation: no interference" ;;
  io)
    io_run_path="${IO_TEMP_PATH}/${run_id}"
    mkdir -p "${io_run_path}"
    printf 'IO_RUN_PATH=%s\n' "${io_run_path}" >> "${stage_dir}/metadata.env"
    setsid taskset -c "${HOUSEKEEPING_CPUS}" stress-ng \
      --io "${IO_WORKERS}" --hdd "${HDD_WORKERS}" --hdd-bytes "${HDD_BYTES}" \
      --temp-path "${io_run_path}" --timeout "$((DURATION_S + INTERFERENCE_WARMUP_S + 60))s" \
      >"${stage_dir}/interference.log" 2>&1 &
    interference_pid=$!
    ;;
  churn)
    setsid bash -c '
      set -uo pipefail
      namespace="$1"; cpus="$2"; image="$3"; size="$4"; seq="$5"; log_file="$6"
      n=0
      while true; do
        name="tdps-churn-${seq}-${n}"
        start="$(date +%s%N)"
        if sudo nerdctl --namespace "$namespace" run --rm --net none --name "$name" \
          --cpuset-cpus "$cpus" "$image" sh -c \
          "dd if=/dev/zero of=/tmp/payload bs=1M count=$size status=none"; then rc=0; else rc=$?; fi
        printf "%s,%s,%s,%s\n" "$n" "$start" "$(date +%s%N)" "$rc" >> "$log_file"
        n=$((n+1))
      done
    ' _ "${TDPS_NAMESPACE}" "${HOUSEKEEPING_CPUS}" "${CHURN_IMAGE}" "${CHURN_WRITE_MB}" \
      "${sequence}" "${stage_dir}/churn.csv" >"${stage_dir}/interference.log" 2>&1 &
    interference_pid=$!
    ;;
esac

if [[ "${scenario}" != control ]]; then
  sleep "${INTERFERENCE_WARMUP_S}"
  kill -0 "${interference_pid}" 2>/dev/null || die "interference ended during warm-up"
fi

# The IRQ interval begins only after warm-up and instrumentation startup. All
# observer artifacts stay on tmpfs until the interval is closed.
snapshot_managed_irqs "${stage_dir}/managed_irqs_before.csv"
printf 'MEASUREMENT_STARTED_AT=%s\n' "$(date -Is)" >> "${stage_dir}/metadata.env"

benchmark_log="${stage_dir}/benchmark.log"
if [[ "${substrate}" == host ]]; then
  as_root chrt -f "${RT_PRIORITY}" taskset -c "${CPU_RT}" \
    "${SUITE_DIR}/benchmark/periodic_bench" \
    --period "${PERIOD_NS}" --deadline "${DEADLINE_NS}" --duration "${DURATION_S}" \
    --iters "${BENCH_ITERS}" --out "${stage_dir}/samples.csv" --mlock \
    --shock-threshold "${SHOCK_THRESHOLD_NS}" --shock-fifo "${stage_dir}/shock.fifo" \
    >"${benchmark_log}" 2>&1
  as_root chown "$(id -u):$(id -g)" "${stage_dir}/samples.csv" "${benchmark_log}"
else
  as_root nerdctl --namespace "${TDPS_NAMESPACE}" run --rm --net none \
    --name "tdps-bench-${sequence}" --pid host --cpuset-cpus "${CPU_RT}" \
    --cap-add SYS_NICE --cap-add IPC_LOCK --ulimit rtprio=99 --ulimit memlock=-1 \
    --volume "${stage_dir}:/results" \
    --entrypoint /usr/bin/chrt "${BENCH_IMAGE}" -f "${RT_PRIORITY}" \
    /usr/local/bin/periodic_bench --period "${PERIOD_NS}" --deadline "${DEADLINE_NS}" \
    --duration "${DURATION_S}" --iters "${BENCH_ITERS}" --out /results/samples.csv --mlock \
    --shock-threshold "${SHOCK_THRESHOLD_NS}" --shock-fifo /results/shock.fifo \
    >"${benchmark_log}" 2>&1
fi

# periodic_bench writes samples.csv only after its timed loop. Because the file
# is on tmpfs, this snapshot excludes result persistence I/O while still
# covering the complete measurement interval.
snapshot_managed_irqs "${stage_dir}/managed_irqs_after.csv"
printf 'MEASUREMENT_COMPLETED_AT=%s\n' "$(date -Is)" >> "${stage_dir}/metadata.env"
irq_activity=0
if ! compare_irq_snapshots "${stage_dir}/managed_irqs_before.csv" \
    "${stage_dir}/managed_irqs_after.csv" "${stage_dir}/managed_irq_delta.csv"; then
  irq_activity=1
  : > "${stage_dir}/INVALID_IRQ_ACTIVITY"
  printf 'VALID=0\nINVALID_REASON=managed_irq_activity_during_measurement\n' >> "${stage_dir}/metadata.env"
fi

stop_process_group "${interference_pid}"
interference_pid=""
if [[ -n "${io_run_path}" ]]; then rmdir "${io_run_path}" 2>/dev/null || true; fi
if [[ -n "${telemetry_pid}" ]]; then kill "${telemetry_pid}"; wait "${telemetry_pid}" || true; telemetry_pid=""; fi
if (( trace_started )); then "${SUITE_DIR}/collect_trace.sh" stop "${stage_dir}"; trace_started=0; fi
if [[ -n "${fifo_reader_pid}" ]]; then kill "${fifo_reader_pid}" 2>/dev/null || true; wait "${fifo_reader_pid}" 2>/dev/null || true; fifo_reader_pid=""; fi
rm -f "${stage_dir}/shock.fifo"

# Persist observer artifacts only after the IRQ measurement interval is closed.
cp -a "${stage_dir}/." "${run_dir}/"
rm -rf -- "${stage_dir}"

python3 - "${run_dir}/samples.csv" > "${run_dir}/summary.txt" <<'PY'
import csv, statistics, sys
with open(sys.argv[1], newline='') as f: rows=list(csv.DictReader(f))
values=sorted(int(r['response_ns']) for r in rows)
misses=sum(int(r['miss']) for r in rows)
def q(p): return values[min(len(values)-1, int(p*(len(values)-1)))]
print(f"jobs={len(rows)}")
print(f"misses={misses}")
print(f"max_response_ns={max(values)}")
print(f"p99_response_ns={q(.99)}")
print(f"p999_response_ns={q(.999)}")
print(f"median_execution_ns={int(statistics.median(int(r['execution_ns']) for r in rows))}")
print(f"max_wakeup_delay_ns={max(int(r['wakeup_delay_ns']) for r in rows)}")
print(f"observed_cpus={','.join(sorted({r['cpu'] for r in rows}, key=int))}")
PY

printf 'COMPLETED_AT=%s\n' "$(date -Is)" >> "${run_dir}/metadata.env"
if (( irq_activity )); then
  die "observation invalidated: managed IRQ activity during measurement (see ${run_dir}/managed_irq_delta.csv)"
fi
wait_for_recovery
sleep "${BETWEEN_OBSERVATIONS_S}"
trap - EXIT INT TERM
if [[ -n "${sudo_keepalive_pid}" ]]; then kill "${sudo_keepalive_pid}" 2>/dev/null || true; wait "${sudo_keepalive_pid}" 2>/dev/null || true; fi
log "completed ${run_id}"
