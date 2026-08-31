#!/usr/bin/env bash
set -euo pipefail
SUITE_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
# shellcheck source=lib.sh
source "${SUITE_DIR}/lib.sh"

for command in nerdctl ctr taskset chrt cpupower stress-ng trace-cmd python3 gcc make; do need_cmd "${command}"; done

fail=0
check() { if eval "$1"; then log "OK: $2"; else log "FAIL: $2"; fail=1; fi; }

cmdline="$(cat /proc/cmdline)"
for token in "${EXPECTED_CMDLINE[@]}"; do
  check '[[ " '"${cmdline}"' " == *" '"${token}"' "* ]]' "cmdline ${token}"
done

check '[[ "$(cat /proc/sys/kernel/sched_rt_runtime_us)" == -1 ]]' "unlimited RT runtime"
check '[[ "$(systemctl is-active containerd)" == active ]]' "containerd active"
check '[[ "$(systemctl is-active kubelet 2>/dev/null || true)" != active ]]' "kubelet inactive"
check '[[ -z "$(as_root ctr --namespace k8s.io tasks list -q)" ]]' "no Kubernetes tasks"
check '[[ "$(cat /sys/devices/system/cpu/isolated)" == *"'"${CPU_RT}"'* ]]' "CPU ${CPU_RT} isolated"
check '[[ "$(cat /sys/devices/system/cpu/isolated)" == *"'"${CPU_SIBLING}"'* ]]' "CPU ${CPU_SIBLING} isolated"
check '[[ "$(cat /sys/devices/system/cpu/cpu'"${CPU_RT}"'/topology/thread_siblings_list)" == "'"${CPU_RT},${CPU_SIBLING}"'" ]]' "SMT topology ${CPU_RT},${CPU_SIBLING}"

for path in /sys/devices/system/cpu/cpu[0-9]*/cpufreq; do
  [[ -d "${path}" ]] || continue
  check '[[ "$(cat '"${path}"'/scaling_governor)" == performance ]]' "performance governor: ${path}"
  check '[[ "$(cat '"${path}"'/scaling_min_freq)" == 3800000 ]]' "minimum 3.8 GHz: ${path}"
  check '[[ "$(cat '"${path}"'/scaling_max_freq)" == 3800000 ]]' "maximum 3.8 GHz: ${path}"
done
if [[ -r /sys/devices/system/cpu/cpufreq/boost ]]; then
  check '[[ "$(cat /sys/devices/system/cpu/cpufreq/boost)" == 0 ]]' "CPU boost disabled"
fi

irq_offenders=()
for affinity in /proc/irq/[0-9]*/effective_affinity_list; do
  [[ -r "${affinity}" ]] || continue
  cpus="$(cat "${affinity}")"
  if cpulist_contains "${cpus}" "${CPU_RT}" || cpulist_contains "${cpus}" "${CPU_SIBLING}"; then
    irq_offenders+=("${affinity%/effective_affinity_list}:${cpus}")
  fi
done
if ((${#irq_offenders[@]})); then
  printf 'IRQ affinity offenders:\n%s\n' "${irq_offenders[*]}" >&2
  fail=1
else
  log "OK: device IRQs exclude CPUs ${CPU_RT},${CPU_SIBLING}"
fi

tracefs="$(tracefs_path)" || die "tracefs is unavailable"
for event in sched/sched_switch sched/sched_wakeup block/block_rq_issue block/block_rq_complete; do
  check '[[ -e "'"${tracefs}"'/events/'"${event}"'/enable" ]]' "trace event ${event}"
done

available_kb="$(df -Pk "${IO_TEMP_PATH}" | awk 'NR==2 {print $4}')"
check '(( '"${available_kb:-0}"' >= 25 * 1024 * 1024 ))' "at least 25 GiB free at ${IO_TEMP_PATH}"
check 'as_root nerdctl --namespace "'"${TDPS_NAMESPACE}"'" info >/dev/null' "nerdctl namespace ${TDPS_NAMESPACE}"

mkdir -p "${RESULT_ROOT}"
{
  date -Is
  uname -a
  printf 'cmdline=%s\n' "${cmdline}"
  lscpu
  cpupower frequency-info || true
  mount | grep -E 'tracefs| on /tmp | on /home ' || true
  df -h "${RESULT_ROOT}" "${IO_TEMP_PATH}"
  as_root nerdctl --namespace "${TDPS_NAMESPACE}" info
} > "${RESULT_ROOT}/validated_environment.txt" 2>&1

(( fail == 0 )) || die "environment validation failed"
log "environment approved"
