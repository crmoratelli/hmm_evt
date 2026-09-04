#!/usr/bin/env bash
set -euo pipefail
SUITE_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
# shellcheck source=lib.sh
source "${SUITE_DIR}/lib.sh"

action="${1:-}"
run_dir="${2:-}"
[[ -n "${action}" && -n "${run_dir}" ]] || die "usage: $0 start|stop RUN_DIR"
tracefs="$(tracefs_path)" || die "tracefs unavailable"
state="${run_dir}/trace.state"
fifo="${run_dir}/shock.fifo"

event_list=(
  sched/sched_switch sched/sched_wakeup sched/sched_wakeup_new
  sched/sched_migrate_task sched/sched_process_fork sched/sched_process_exec sched/sched_process_exit
  irq/irq_handler_entry irq/irq_handler_exit irq/softirq_entry irq/softirq_exit
  block/block_rq_issue block/block_rq_complete
  writeback/writeback_dirty_page writeback/writeback_start writeback/writeback_written
  writeback/writeback_write_inode_start writeback/writeback_write_inode
  vmscan/mm_vmscan_direct_reclaim_begin vmscan/mm_vmscan_direct_reclaim_end
  ext4/ext4_sync_file_enter ext4/ext4_sync_file_exit
  workqueue/workqueue_execute_start workqueue/workqueue_execute_end
  cgroup/cgroup_mkdir cgroup/cgroup_rmdir cgroup/cgroup_attach_task
  power/cpu_frequency
)

enable_event() {
  local event="$1" file="${tracefs}/events/${event}/enable"
  if [[ -e "${file}" ]]; then echo 1 | as_root tee "${file}" >/dev/null; printf '%s\n' "${event}" >> "${run_dir}/trace_events_enabled.txt";
  else printf '%s\n' "${event}" >> "${run_dir}/trace_events_missing.txt"; fi
}

case "${action}" in
  start)
    mkdir -p "${run_dir}"
    rm -f "${fifo}" "${state}" "${run_dir}/trace.frozen" \
      "${run_dir}/trace_events_enabled.txt" "${run_dir}/trace_events_missing.txt"
    mkfifo "${fifo}"
    as_root sh -c "echo 0 > '${tracefs}/tracing_on'; echo nop > '${tracefs}/current_tracer'; echo > '${tracefs}/trace'; echo 0 > '${tracefs}/events/enable'"
    if grep -qw mono "${tracefs}/trace_clock"; then echo mono | as_root tee "${tracefs}/trace_clock" >/dev/null; fi
    echo "${TRACE_BUFFER_KB}" | as_root tee "${tracefs}/buffer_size_kb" >/dev/null
    [[ ! -e "${tracefs}/options/overwrite" ]] || echo 1 | as_root tee "${tracefs}/options/overwrite" >/dev/null
    for event in "${event_list[@]}"; do enable_event "${event}"; done
    # Linux 6.8 returns EBADF when trace_marker is written while tracing_on=0.
    # Enable the ring first, then insert the temporal anchor.
    echo 1 | as_root tee "${tracefs}/tracing_on" >/dev/null
    printf 'TDPS_TRACE_START realtime=%s\n' "$(date +%s%N)" | as_root tee "${tracefs}/trace_marker" >/dev/null

    (
      exec 9<>"${fifo}"
      if IFS= read -r shock <&9; then
        printf '%s\n' "${shock}" > "${run_dir}/first_shock.txt"
        printf '%s\n' "${shock}" | as_root tee "${tracefs}/trace_marker" >/dev/null
        sleep "${TRACE_POST_SHOCK_S}"
        echo 0 | as_root tee "${tracefs}/tracing_on" >/dev/null
        date -Is > "${run_dir}/trace.frozen"
      fi
    ) >"${run_dir}/trace_watcher.log" 2>&1 &
    watcher=$!
    printf 'WATCHER_PID=%s\nTRACEFS=%q\n' "${watcher}" "${tracefs}" > "${state}"
    log "circular trace started; watcher=${watcher}"
    ;;
  stop)
    [[ -r "${state}" ]] || die "missing trace state: ${state}"
    # shellcheck disable=SC1090
    source "${state}"
    if [[ "$(cat "${TRACEFS}/tracing_on")" != 0 ]]; then
      printf 'TDPS_TRACE_END no_threshold_shock=1 realtime=%s\n' "$(date +%s%N)" | as_root tee "${TRACEFS}/trace_marker" >/dev/null
      echo 0 | as_root tee "${TRACEFS}/tracing_on" >/dev/null
    fi
    kill "${WATCHER_PID}" 2>/dev/null || true
    wait "${WATCHER_PID}" 2>/dev/null || true
    {
      for stats in "${TRACEFS}"/per_cpu/cpu*/stats; do
        printf '===== %s =====\n' "${stats}"
        as_root cat "${stats}"
      done
    } > "${run_dir}/trace_buffer_stats.txt"
    as_root trace-cmd extract -o "${run_dir}/trace.dat"
    as_root chown "$(id -u):$(id -g)" "${run_dir}/trace.dat"
    as_root trace-cmd report --stat "${run_dir}/trace.dat" > "${run_dir}/trace_stats.txt" 2>&1 || true
    as_root sh -c "echo 0 > '${TRACEFS}/events/enable'; echo > '${TRACEFS}/trace'"
    rm -f "${fifo}" "${state}"
    log "trace saved to ${run_dir}/trace.dat"
    ;;
  *) die "unknown action: ${action}" ;;
esac
