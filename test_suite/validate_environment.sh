#!/usr/bin/env bash
set -euo pipefail
SUITE_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
# shellcheck source=lib.sh
source "${SUITE_DIR}/lib.sh"

for command in nerdctl ctr taskset chrt cpupower stress-ng trace-cmd python3 gcc make; do need_cmd "${command}"; done

fail=0
ok() { log "OK: $*"; }
bad() { log "FAIL: $*"; fail=1; }

cmdline="$(cat /proc/cmdline)"
for token in "${EXPECTED_CMDLINE[@]}"; do
  if [[ " ${cmdline} " == *" ${token} "* ]]; then ok "cmdline ${token}"; else bad "cmdline ${token}"; fi
done

[[ "$(cat /proc/sys/kernel/sched_rt_runtime_us)" == -1 ]] && ok "unlimited RT runtime" || bad "unlimited RT runtime"
[[ "$(systemctl is-active containerd)" == active ]] && ok "containerd active" || bad "containerd active"
[[ "$(systemctl is-active kubelet 2>/dev/null || true)" != active ]] && ok "kubelet inactive" || bad "kubelet inactive"
[[ -z "$(as_root ctr --namespace k8s.io tasks list -q)" ]] && ok "no Kubernetes tasks" || bad "no Kubernetes tasks"

isolated_cpus="$(cat /sys/devices/system/cpu/isolated 2>/dev/null || true)"
cpulist_contains "${isolated_cpus}" "${CPU_RT}" && ok "CPU ${CPU_RT} isolated" || bad "CPU ${CPU_RT} isolated (reported: ${isolated_cpus:-none})"
cpulist_contains "${isolated_cpus}" "${CPU_SIBLING}" && ok "CPU ${CPU_SIBLING} isolated" || bad "CPU ${CPU_SIBLING} isolated (reported: ${isolated_cpus:-none})"

siblings="$(cat "/sys/devices/system/cpu/cpu${CPU_RT}/topology/thread_siblings_list")"
if [[ "${siblings}" == "${CPU_RT},${CPU_SIBLING}" || "${siblings}" == "${CPU_SIBLING},${CPU_RT}" ]]; then
  ok "SMT topology ${siblings}"
else
  bad "SMT topology ${siblings}; expected ${CPU_RT},${CPU_SIBLING}"
fi

for path in /sys/devices/system/cpu/cpu[0-9]*/cpufreq; do
  [[ -d "${path}" ]] || continue
  [[ "$(cat "${path}/scaling_governor")" == performance ]] && ok "performance governor: ${path}" || bad "performance governor: ${path}"
  [[ "$(cat "${path}/scaling_min_freq")" == 3800000 ]] && ok "minimum 3.8 GHz: ${path}" || bad "minimum 3.8 GHz: ${path}"
  [[ "$(cat "${path}/scaling_max_freq")" == 3800000 ]] && ok "maximum 3.8 GHz: ${path}" || bad "maximum 3.8 GHz: ${path}"
done
if [[ -r /sys/devices/system/cpu/cpufreq/boost ]]; then
  [[ "$(cat /sys/devices/system/cpu/cpufreq/boost)" == 0 ]] && ok "CPU boost disabled" || bad "CPU boost disabled"
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
  [[ -e "${tracefs}/events/${event}/enable" ]] && ok "trace event ${event}" || bad "trace event ${event}"
done

available_kb="$(df -Pk "${IO_TEMP_PATH}" | awk 'NR==2 {print $4}')"
(( ${available_kb:-0} >= 25 * 1024 * 1024 )) && ok "at least 25 GiB free at ${IO_TEMP_PATH}" || bad "at least 25 GiB free at ${IO_TEMP_PATH}"
if as_root nerdctl --namespace "${TDPS_NAMESPACE}" info >/dev/null; then ok "nerdctl namespace ${TDPS_NAMESPACE}"; else bad "nerdctl namespace ${TDPS_NAMESPACE}"; fi

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
