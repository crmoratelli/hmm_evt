#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd -- "$(dirname -- "$0")" && pwd)"; SUITE="$(cd -- "${DIR}/.." && pwd)"
source "${SUITE}/lib.sh"; source "${DIR}/config_phase4b.sh"
level="${1:-}"; iters="${2:-}"; scenario="${3:-}"; rep="${4:-}"; block="${5:-}"; seq="${6:-}"
[[ "$level" =~ ^c(06|25|40)$ && "$iters" =~ ^[0-9]+$ && "$scenario" =~ ^(control|io)$ && "$rep" =~ ^[0-9]+$ && "$block" =~ ^[0-9]+$ && "$seq" =~ ^[0-9]+$ ]] || die "invalid arguments"
root="${PHASE4B_ACTIVE_ROOT:-$PHASE4B_RESULT_ROOT}"; duration="${PHASE4B_ACTIVE_DURATION_S:-$PHASE4B_DURATION_S}"; profile="${PHASE4B_PROFILE:-full}"
jobs=$((duration*1000000000/PHASE4B_PERIOD_NS)); id="$(printf '%04d_%s_%s_run%02d' "$seq" "$level" "$scenario" "$rep")"
run="${root}/runs/${id}"; stage="${PHASE4B_STAGE_ROOT}/${profile}-${id}"; io_path="${PHASE4B_IO_TEMP_PATH}/${profile}-${id}"
[[ ! -e "$run" && ! -e "$stage" ]] || die "run/stage already exists: $id"; mkdir -p "$run" "$stage"
telemetry_pid=; stress_pid=; keepalive_pid=; completed=0
cleanup(){ rc=$?; set +e; stop_process_group "$stress_pid"; [[ -z "$telemetry_pid" ]] || { kill "$telemetry_pid" 2>/dev/null; wait "$telemetry_pid" 2>/dev/null; }; [[ -z "$keepalive_pid" ]] || kill "$keepalive_pid" 2>/dev/null; if [[ -d "$stage" ]]; then cp -R "$stage"/. "$run"/ 2>/dev/null; rm -rf -- "${stage:?}"; fi; ((completed)) || { printf 'FAILED_AT=%s\nEXIT_CODE=%s\n' "$(date -Is)" "$rc" >>"$run/metadata.env"; : >"$run/FAILED"; }; }; trap cleanup EXIT INT TERM
if ((EUID!=0)); then sudo -v; (while sleep 60; do sudo -n true || exit; done)& keepalive_pid=$!; fi
wait_for_recovery
cat >"$stage/metadata.env" <<EOF
RUN_ID=$id
PROFILE=$profile
STATE=running
SEQUENCE=$seq
BLOCK=$block
REPLICATION=$rep
LEVEL=$level
SCENARIO=$scenario
ARCHITECTURE=inline
SUBSTRATE=host
BENCH_ITERS=$iters
PERIOD_NS=$PHASE4B_PERIOD_NS
DEADLINE_NS=$PHASE4B_DEADLINE_NS
DURATION_S=$duration
JOBS=$jobs
CPU_RT=$CPU_RT
RT_PRIORITY=$RT_PRIORITY
SOURCE_SHA256=$(sha256sum "$SUITE/phase1/periodic_v2.c"|awk '{print $1}')
BINARY_SHA256=$(sha256sum "$DIR/periodic_v2"|awk '{print $1}')
GIT_COMMIT=$(git -C "$SUITE/.." rev-parse HEAD 2>/dev/null || printf unknown)
STARTED_AT=$(date -Is)
EOF
cat /proc/cmdline >"$stage/cmdline.txt"
setsid taskset -c "$HOUSEKEEPING_CPUS" python3 "$SUITE/collect_telemetry.py" --out "$stage/telemetry.jsonl" --interval "$TELEMETRY_INTERVAL_S" & telemetry_pid=$!
if [[ "$scenario" == io ]]; then mkdir -p "$io_path"; printf 'IO_RUN_PATH=%s\n' "$io_path" >>"$stage/metadata.env"; setsid taskset -c "$HOUSEKEEPING_CPUS" stress-ng --io 4 --hdd 2 --hdd-bytes 10G --temp-path "$io_path" --timeout "$((duration+PHASE4B_WARMUP_S+120))s" >"$stage/interference.log" 2>&1 & stress_pid=$!; fi
sleep "$PHASE4B_WARMUP_S"; kill -0 "$telemetry_pid" || die "telemetry stopped"; [[ "$scenario" != io ]] || kill -0 "$stress_pid" || die "I/O stress stopped"
snapshot_managed_irqs "$stage/managed_irqs_before.csv"
args=(--mode inline --period "$PHASE4B_PERIOD_NS" --deadline "$PHASE4B_DEADLINE_NS" --jobs "$jobs" --iters "$iters" --out "$stage/samples.csv" --sink "$run/functional.bin" --queue 1024 --mlock)
printf '%q ' sudo timeout --signal=TERM --kill-after=10 "$((duration+120))s" chrt -f "$RT_PRIORITY" taskset -c "$CPU_RT" "$DIR/periodic_v2" "${args[@]}" >"$stage/benchmark_command.txt"; printf '\n' >>"$stage/benchmark_command.txt"
as_root timeout --signal=TERM --kill-after=10 "$((duration+120))s" chrt -f "$RT_PRIORITY" taskset -c "$CPU_RT" "$DIR/periodic_v2" "${args[@]}" >"$stage/benchmark.stdout" 2>"$stage/benchmark.log"
snapshot_managed_irqs "$stage/managed_irqs_after.csv"; runtime_bad=0
kill -0 "$telemetry_pid" 2>/dev/null || runtime_bad=1; [[ "$scenario" != io ]] || kill -0 "$stress_pid" 2>/dev/null || runtime_bad=1
compare_irq_snapshots "$stage/managed_irqs_before.csv" "$stage/managed_irqs_after.csv" "$stage/managed_irq_delta.csv" || { : >"$stage/INVALID_IRQ_ACTIVITY"; runtime_bad=1; }
stop_process_group "$stress_pid"; stress_pid=; kill "$telemetry_pid" 2>/dev/null || true; wait "$telemetry_pid" 2>/dev/null || true; telemetry_pid=; rmdir "$io_path" 2>/dev/null || true
cp -R "$stage"/. "$run"/; python3 "$DIR/validate_phase4b_run.py" --run-dir "$run" --jobs "$jobs" --cpu "$CPU_RT" --record-bytes "$PHASE4B_RECORD_BYTES"
((runtime_bad==0)) || die "runtime validation failed: $id"
printf 'VALID=1\nSTATE=completed\nCOMPLETED_AT=%s\n' "$(date -Is)" >>"$run/metadata.env"; : >"$run/COMPLETED"; rm -rf -- "${stage:?}"; completed=1; trap - EXIT INT TERM
[[ -z "$keepalive_pid" ]] || { kill "$keepalive_pid" 2>/dev/null || true; wait "$keepalive_pid" 2>/dev/null || true; }; sleep "$PHASE4B_BETWEEN_S"; log "completed $id"
