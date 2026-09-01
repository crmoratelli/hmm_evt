#!/usr/bin/env bash
set -euo pipefail
SUITE_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
# shellcheck source=lib.sh
source "${SUITE_DIR}/lib.sh"

need_cmd taskset
need_cmd cpupower
need_cmd nerdctl
need_cmd ctr
as_root true

cmdline="$(cat /proc/cmdline)"
for token in "${EXPECTED_CMDLINE[@]}"; do
  [[ " ${cmdline} " == *" ${token} "* ]] || die "missing kernel parameter: ${token}"
done

siblings="$(cat "/sys/devices/system/cpu/cpu${CPU_RT}/topology/thread_siblings_list")"
[[ "${siblings}" == "${CPU_RT},${CPU_SIBLING}" || "${siblings}" == "${CPU_SIBLING},${CPU_RT}" ]] \
  || die "CPU ${CPU_RT} siblings are '${siblings}', expected ${CPU_RT},${CPU_SIBLING}"

[[ "$(systemctl is-active kubelet 2>/dev/null || true)" != active ]] || die "kubelet is active"
[[ -z "$(as_root ctr --namespace k8s.io tasks list -q)" ]] || die "Kubernetes tasks are active"
[[ "$(systemctl is-active containerd)" == active ]] || die "containerd is not active"

as_root sysctl -w kernel.sched_rt_runtime_us=-1 >/dev/null
as_root systemctl stop irqbalance 2>/dev/null || true

# Keep global unbound workqueues away from the benchmark core and its idle SMT
# sibling. Per-CPU kernel threads cannot be moved by this interface.
if [[ -w /sys/devices/virtual/workqueue/cpumask ]] || as_root test -w /sys/devices/virtual/workqueue/cpumask; then
  workqueue_mask="$(cpulist_to_hexmask "${HOUSEKEEPING_CPUS}")"
  printf '%s\n' "${workqueue_mask}" | as_root tee /sys/devices/virtual/workqueue/cpumask >/dev/null
fi

# Re-apply housekeeping affinity after irqbalance is stopped. Managed/per-CPU
# IRQs may reject writes; validate_environment permits only the audited,
# continuously monitored dormant managed vectors.
for affinity in /proc/irq/[0-9]*/smp_affinity_list; do
  [[ -e "${affinity}" ]] || continue
  printf '%s\n' "${HOUSEKEEPING_CPUS}" | as_root tee "${affinity}" >/dev/null 2>&1 || true
done

as_root sh -c '
  set -eu
  for path in /sys/devices/system/cpu/cpu[0-9]*/cpufreq; do
    [ -d "$path" ] || continue
    echo performance > "$path/scaling_governor"
    echo 3800000 > "$path/scaling_min_freq"
    echo 3800000 > "$path/scaling_max_freq"
  done
  boost=/sys/devices/system/cpu/cpufreq/boost
  [ ! -e "$boost" ] || echo 0 > "$boost"
'

as_root mkdir -p "${RESULT_ROOT}" "${IO_TEMP_PATH}"
owner_uid="${SUDO_UID:-$(id -u)}"
owner_gid="${SUDO_GID:-$(id -g)}"
as_root chown "${owner_uid}:${owner_gid}" "${RESULT_ROOT}" "${IO_TEMP_PATH}"
as_root chmod 0775 "${RESULT_ROOT}" "${IO_TEMP_PATH}"

log "RT environment configured; running strict validation"
exec "${SUITE_DIR}/validate_environment.sh"
