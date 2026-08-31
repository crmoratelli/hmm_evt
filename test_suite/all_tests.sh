#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/config.sh"
source "${SCRIPT_DIR}/helpers.sh"

ALL_TESTS=(
  baseline_cfs
  rt_isolated
  interf_same_core
  interf_host_cross_core
  interf_docker_cross_core
  interf_memory
  interf_io
  quota_17
  quota_15
  quota_13
  sharing_shared_pool
  migration_unpinned
  churn_runtime
)

usage() {
  cat <<'EOF'
Usage:
  ./all_tests.sh --tests <test[,test2,...]>
  ./all_tests.sh --all

Parameters:
  -t, --tests   Run one specific test or a comma-separated set of tests
  -a, --all     Run all tests
  -h, --help    Show this help message

Available tests:
  baseline_cfs              Bare-metal vs Docker baseline under CFS
  rt_isolated               Bare-metal vs Docker with isolated CPU and SCHED_FIFO
  interf_same_core          CPU stress on the same real-time core
  interf_host_cross_core    Host CPU stress on non-real-time cores
  interf_docker_cross_core  Docker CPU stress on non-real-time cores
  interf_memory             Memory pressure on non-real-time cores
  interf_io                 I/O stress on non-real-time cores
  quota_17                  Docker CFS quota at 20% CPU
  quota_15                  Docker CFS quota at 15% CPU
  quota_13                  Docker CFS quota at 12% CPU
  sharing_shared_pool       cpu.shares with benchmark and hogs in the same shared CPU pool
  migration_unpinned        Docker execution without CPU pinning
  churn_runtime             Real-time execution under container churn

Examples:
  ./all_tests.sh --tests baseline_cfs
  ./all_tests.sh --tests rt_isolated
  ./all_tests.sh --tests sharing_shared_pool
  ./all_tests.sh --tests baseline_cfs,rt_isolated,interf_host_cross_core,interf_memory
  ./all_tests.sh --all
EOF
}

cleanup() {
  stop_hogs_all_shared || true
  stop_hogs_all || true
  if [[ -n "${SUDO_KEEPALIVE_PID:-}" ]]; then
    kill "${SUDO_KEEPALIVE_PID}" 2>/dev/null || true
  fi
}

trim() {
  local value="$1"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s' "${value}"
}

contains_test() {
  local needle="$1"
  shift || true
  local item
  for item in "$@"; do
    [[ "${item}" == "${needle}" ]] && return 0
  done
  return 1
}

require_file_contains() {
  local file="$1"
  local pattern="$2"
  local desc="$3"

  if [[ ! -r "${file}" ]]; then
    log "ERROR: could not read ${file} (${desc})."
    return 1
  fi

  if ! grep -Eq "${pattern}" "${file}"; then
    log "ERROR: validation failed for ${desc} in ${file}."
    return 1
  fi

  return 0
}

check_default_kernel_config() {
  log "Checking whether the system is in the default configuration required by baseline_cfs..."

  need_cmd docker
  need_cmd taskset
  need_cmd cpupower

  mkdir -p "${RESULT_DIR}"

  local cmdline
  cmdline="$(cat /proc/cmdline 2>/dev/null || true)"

  local forbidden_cmdline=(
    '(^|[[:space:]])idle=poll([[:space:]]|$)'
    '(^|[[:space:]])processor\.max_cstate=0([[:space:]]|$)'
    '(^|[[:space:]])isolcpus=([^[:space:]]*)'
    '(^|[[:space:]])nohz_full=([^[:space:]]*)'
    '(^|[[:space:]])rcu_nocbs=([^[:space:]]*)'
    '(^|[[:space:]])irqaffinity=([^[:space:]]*)'
  )

  local token
  for token in "${forbidden_cmdline[@]}"; do
    if [[ "${cmdline}" =~ ${token} ]]; then
      echo
      echo "❌ ERROR: baseline_cfs requires the default kernel/system configuration."
      echo "   RT/isolation parameters were found in /proc/cmdline."
      echo "   Current cmdline: ${cmdline}"
      echo
      echo "👉 Reboot the system without these parameters before running baseline_cfs."
      return 1
    fi
  done

  require_file_contains "/sys/devices/system/cpu/cpuidle/current_driver" '.+' \
    "active cpuidle driver" || return 1

  if [[ -r /sys/devices/system/cpu/smt/control ]]; then
    local smt_state
    smt_state="$(cat /sys/devices/system/cpu/smt/control 2>/dev/null || true)"
    if [[ "${smt_state}" == "off" || "${smt_state}" == "forceoff" ]]; then
      echo
      echo "❌ ERROR: SMT/Hyper-Threading is disabled (${smt_state})."
      echo "   baseline_cfs requires the default system configuration."
      echo
      return 1
    fi
  fi

  if [[ -r /proc/sys/kernel/sched_rt_runtime_us ]]; then
    local rt_runtime
    rt_runtime="$(cat /proc/sys/kernel/sched_rt_runtime_us 2>/dev/null || true)"
    if [[ "${rt_runtime}" == "-1" ]]; then
      echo
      echo "❌ ERROR: kernel.sched_rt_runtime_us=-1 detected."
      echo "   baseline_cfs requires the default kernel configuration."
      echo
      return 1
    fi
  fi

  log "Informational check:"
  cpupower frequency-info || true
  cpupower idle-info || true
  grep -m1 "cpu MHz" /proc/cpuinfo || true

  log "OK: environment is compatible with the default configuration required by baseline_cfs."
}

run_baseline_cfs() {
  local test_name="baseline_cfs"
  initial_check
  log "==================== ${test_name} ===================="
  for i in {1..10}; do
    log "---- ${test_name} - run ${i}/10 ----"
    run_host_va  "${RESULT_DIR}/host_cpu${CPU_RT}-${test_name}.csv"
    run_docker_va "docker_cpu${CPU_RT}-${test_name}.csv"
    mv "${RESULT_DIR}/host_cpu${CPU_RT}-${test_name}.csv" "${RESULT_DIR}/host_cpu${CPU_RT}-${test_name}-run${i}.csv"
    mv "${RESULT_DIR}/docker_cpu${CPU_RT}-${test_name}.csv" "${RESULT_DIR}/docker_cpu${CPU_RT}-${test_name}-run${i}.csv"
    sleep 10
  done
}

run_rt_isolated() {
  local test_name="rt_isolated"
  initial_check
  log "==================== ${test_name} ===================="
  for i in {1..10}; do
    log "---- ${test_name} - run ${i}/10 ----"
    run_host_vb  "${RESULT_DIR}/host_cpu${CPU_RT}-${test_name}.csv"
    run_docker_vb "docker_cpu${CPU_RT}-${test_name}.csv"
    mv "${RESULT_DIR}/host_cpu${CPU_RT}-${test_name}.csv" "${RESULT_DIR}/host_cpu${CPU_RT}-${test_name}-run${i}.csv"
    mv "${RESULT_DIR}/docker_cpu${CPU_RT}-${test_name}.csv" "${RESULT_DIR}/docker_cpu${CPU_RT}-${test_name}-run${i}.csv"
    sleep 10
  done
}

run_interf_same_core() {
  local test_name="interf_same_core"
  initial_check
  log "---- ${test_name} (HOST stress on CPU ${CPU_RT}) ----"
  for i in {1..10}; do
    log "---- ${test_name} - run ${i}/10 ----"
    start_stress_host "${test_name}" taskset -c "${CPU_RT}" stress-ng --cpu 1 --cpu-method matrixprod --timeout 5000s
    local stress_pid="${STRESS_PID}"
    sleep 0.2
    if ! kill -0 "${stress_pid}" 2>/dev/null; then
      log "WARNING: ${test_name} disturbance ended early (pid=${stress_pid})."
    fi
    run_host_vb "${RESULT_DIR}/host_cpu${CPU_RT}-${test_name}.csv"
    run_docker_vb "docker_cpu${CPU_RT}-${test_name}.csv"
    stop_bg "${stress_pid}" "stress-ng (${test_name})"
    mv "${RESULT_DIR}/host_cpu${CPU_RT}-${test_name}.csv" "${RESULT_DIR}/host_cpu${CPU_RT}-${test_name}-run${i}.csv"
    mv "${RESULT_DIR}/docker_cpu${CPU_RT}-${test_name}.csv" "${RESULT_DIR}/docker_cpu${CPU_RT}-${test_name}-run${i}.csv"
    sleep 10
  done
}

run_interf_host_cross_core() {
  local test_name="interf_host_cross_core"
  initial_check
  log "---- ${test_name} (HOST stress on non-real-time cores) ----"
  for i in {1..10}; do
    log "---- ${test_name} - run ${i}/10 ----"
    start_stress_host "${test_name}" taskset -c "${OTHER_CPUS}" stress-ng --cpu 12 --cpu-method matrixprod --timeout 5000s
    local stress_pid="${STRESS_PID}"
    sleep 0.2
    if ! kill -0 "${stress_pid}" 2>/dev/null; then
      log "WARNING: ${test_name} disturbance ended early (pid=${stress_pid})."
    fi
    run_host_vb "${RESULT_DIR}/host_cpu${CPU_RT}-${test_name}.csv"
    run_docker_vb "docker_cpu${CPU_RT}-${test_name}.csv"
    stop_bg "${stress_pid}" "stress-ng (${test_name})"
    mv "${RESULT_DIR}/host_cpu${CPU_RT}-${test_name}.csv" "${RESULT_DIR}/host_cpu${CPU_RT}-${test_name}-run${i}.csv"
    mv "${RESULT_DIR}/docker_cpu${CPU_RT}-${test_name}.csv" "${RESULT_DIR}/docker_cpu${CPU_RT}-${test_name}-run${i}.csv"
    sleep 10
  done
}

run_interf_docker_cross_core() {
  local test_name="interf_docker_cross_core"
  initial_check
  log "---- ${test_name} (DOCKER stress on non-real-time cores) ----"
  for i in {1..10}; do
    log "---- ${test_name} - run ${i}/10 ----"
    start_stress_docker "${test_name}" \
      --cpuset-cpus="${OTHER_CPUS}" alpine sh -c \
      'apk add --no-cache stress-ng >/dev/null 2>&1; stress-ng --cpu 12 --cpu-method matrixprod --timeout 10000'
    local stress_pid="${STRESS_PID}"
    local stress_cname="${STRESS_CNAME}"
    sleep 0.2
    if ! kill -0 "${stress_pid}" 2>/dev/null; then
      log "WARNING: ${test_name} disturbance ended early (pid=${stress_pid})."
    fi
    run_host_vb "${RESULT_DIR}/host_cpu${CPU_RT}-${test_name}.csv"
    run_docker_vb "docker_cpu${CPU_RT}-${test_name}.csv"
    stop_stress_docker "${stress_cname}" "stress-ng (${test_name})"
    stop_bg "${stress_pid}" "docker run (${test_name})" || true
    mv "${RESULT_DIR}/host_cpu${CPU_RT}-${test_name}.csv" "${RESULT_DIR}/host_cpu${CPU_RT}-${test_name}-run${i}.csv"
    mv "${RESULT_DIR}/docker_cpu${CPU_RT}-${test_name}.csv" "${RESULT_DIR}/docker_cpu${CPU_RT}-${test_name}-run${i}.csv"
    sleep 10
  done
}

run_interf_memory() {
  local test_name="interf_memory"
  initial_check
  log "---- ${test_name} (HOST memory stress on non-real-time cores) ----"
  for i in {1..10}; do
    log "---- ${test_name} - run ${i}/10 ----"
    start_stress_host "${test_name}" taskset -c "${OTHER_CPUS}" stress-ng --vm 2 --vm-bytes 80% --mmap 2 --timeout 5000s
    local stress_pid="${STRESS_PID}"
    sleep 0.2
    if ! kill -0 "${stress_pid}" 2>/dev/null; then
      log "WARNING: ${test_name} disturbance ended early (pid=${stress_pid})."
    fi
    run_host_vb "${RESULT_DIR}/host_cpu${CPU_RT}-${test_name}.csv"
    run_docker_vb "docker_cpu${CPU_RT}-${test_name}.csv"
    stop_bg "${stress_pid}" "stress-ng (${test_name})"
    mv "${RESULT_DIR}/host_cpu${CPU_RT}-${test_name}.csv" "${RESULT_DIR}/host_cpu${CPU_RT}-${test_name}-run${i}.csv"
    mv "${RESULT_DIR}/docker_cpu${CPU_RT}-${test_name}.csv" "${RESULT_DIR}/docker_cpu${CPU_RT}-${test_name}-run${i}.csv"
    sleep 10
  done
}

run_interf_io() {
  local test_name="interf_io"
  initial_check
  log "---- ${test_name} (HOST I/O stress on non-real-time cores) ----"
  for i in {1..10}; do
    log "---- ${test_name} - run ${i}/10 ----"
    start_stress_host "${test_name}" taskset -c "${OTHER_CPUS}" stress-ng --io 4 --hdd 2 --hdd-bytes 10G --timeout 5000s
    local stress_pid="${STRESS_PID}"
    sleep 0.2
    if ! kill -0 "${stress_pid}" 2>/dev/null; then
      log "WARNING: ${test_name} disturbance ended early (pid=${stress_pid})."
    fi
    run_host_vb "${RESULT_DIR}/host_cpu${CPU_RT}-${test_name}.csv"
    run_docker_vb "docker_cpu${CPU_RT}-${test_name}.csv"
    stop_bg "${stress_pid}" "stress-ng (${test_name})"
    mv "${RESULT_DIR}/host_cpu${CPU_RT}-${test_name}.csv" "${RESULT_DIR}/host_cpu${CPU_RT}-${test_name}-run${i}.csv"
    mv "${RESULT_DIR}/docker_cpu${CPU_RT}-${test_name}.csv" "${RESULT_DIR}/docker_cpu${CPU_RT}-${test_name}-run${i}.csv"
    sleep 10
  done
}

run_quota_17() {
  local test_name="quota_17"
  initial_check
  log "---- ${test_name} (Docker CFS quota at 17%) ----"
  for i in {1..10}; do
    log "---- ${test_name} - run ${i}/10 ----"
    docker run --rm \
      --cpuset-cpus="${CPU_RT}" \
      --cpu-period=100000 \
      --cpu-quota=17000 \
      -v "${RESULT_DIR}:/out" "${IMAGE}" \
      ./periodic_bench --period "${PERIOD}" --deadline "${DEADLINE}" --duration "${DURATION}" --out "/out/${test_name}.csv"
    mv "${RESULT_DIR}/${test_name}.csv" "${RESULT_DIR}/${test_name}-run${i}.csv"
    sleep 10
  done
}

run_quota_15() {
  local test_name="quota_15"
  initial_check
  log "---- ${test_name} (Docker CFS quota at 15%) ----"
  for i in {1..10}; do
    log "---- ${test_name} - run ${i}/10 ----"
    docker run --rm \
      --cpuset-cpus="${CPU_RT}" \
      --cpu-period=100000 \
      --cpu-quota=15000 \
      -v "${RESULT_DIR}:/out" "${IMAGE}" \
      ./periodic_bench --period "${PERIOD}" --deadline "${DEADLINE}" --duration "${DURATION}" --out "/out/${test_name}.csv"
    mv "${RESULT_DIR}/${test_name}.csv" "${RESULT_DIR}/${test_name}-run${i}.csv"
    sleep 10
  done
}

run_quota_13() {
  local test_name="quota_13"
  initial_check
  log "---- ${test_name} (Docker CFS quota at 13%) ----"
  for i in {1..10}; do
    log "---- ${test_name} - run ${i}/10 ----"
    docker run --rm \
      --cpuset-cpus="${CPU_RT}" \
      --cpu-period=100000 \
      --cpu-quota=13000 \
      -v "${RESULT_DIR}:/out" "${IMAGE}" \
      ./periodic_bench --period "${PERIOD}" --deadline "${DEADLINE}" --duration "${DURATION}" --out "/out/${test_name}.csv"
    mv "${RESULT_DIR}/${test_name}.csv" "${RESULT_DIR}/${test_name}-run${i}.csv"
    sleep 10
  done
}

run_sharing_shared_pool() {
  local test_name="sharing_shared_pool"
  initial_check
  log "---- ${test_name} (cpu.shares with real contention in the same cpuset) ----"
  log "Sanity check: SHARED_CPUS=${SHARED_CPUS} (benchmark + hogs compete here)"
  log "Sanity check: cpu.shares benchmark=${BENCH_SHARES}, hogs=${HOG_SHARES}"
  log "Note: ${test_name} uses CFS (no chrt). This measures real competition via cpu.shares."

  for k in $(seq 0 2 "${HOG_MAX}"); do
    stop_hogs_all_shared
    if (( k > 0 )); then
      start_hogs_k_shared "${k}"
      sleep 0.3
    else
      log "No hogs (k=0)."
    fi

    for i in {1..10}; do
      run_docker_vb_shares "docker_${test_name}_k${k}-run${i}.csv"
      sleep 10
    done
  done
  stop_hogs_all_shared
}

run_docker_nomask() {
  local out="$1"
  log "DOCKER benchmark without cpuset pinning -> ${out}"
  docker run --rm \
    -v "${RESULT_DIR}:/out" \
    "${IMAGE}" \
    ./periodic_bench --period "${PERIOD}" --deadline "${DEADLINE}" --duration "${DURATION}" \
    --out "/out/${out}"
}

run_migration_unpinned() {
  local test_name="migration_unpinned"
  initial_check
  log "---- ${test_name} (no pinning: migration and scheduler noise) ----"

  log "${test_name}: control case (pinned on CPU ${CPU_RT})"
  for i in {1..10}; do
    run_docker_va "${test_name}_pinned.csv"
    mv "${RESULT_DIR}/${test_name}_pinned.csv" "${RESULT_DIR}/${test_name}_pinned-run${i}.csv"
    sleep 10
  done

  log "${test_name}: treatment case (without --cpuset-cpus)"
  for i in {1..10}; do
    run_docker_nomask "${test_name}_nomask.csv"
    mv "${RESULT_DIR}/${test_name}_nomask.csv" "${RESULT_DIR}/${test_name}_nomask-run${i}.csv"
    sleep 10
  done
}

run_churn_runtime() {
  initial_check

  local test_name="churn_runtime"
  local out_host="${RESULT_DIR}/host_cpu${CPU_RT}-${test_name}.csv"
  local out_docker="docker_cpu${CPU_RT}-${test_name}.csv"

  log "---- ${test_name} (realistic orchestration-induced container churn) ----"
  log "${test_name}: ensuring local 'alpine' image is available (pull if needed)..."
  docker image inspect alpine >/dev/null 2>&1 || docker pull alpine >/dev/null

  for i in {1..10}; do
    start_stress_host "${test_name}-churn" taskset -c "${OTHER_CPUS}" bash -lc '
      set -euo pipefail
      while true; do
        docker run --rm \
          --cpuset-cpus="'"${OTHER_CPUS}"'" \
          alpine sh -c "dd if=/dev/zero of=/tmp/x bs=1M count=50 >/dev/null 2>&1"
      done
    '

    local churn_pid="${STRESS_PID}"
    sleep 0.2

    if (( i % 2 == 1 )); then
      log "${test_name} run ${i}: HOST first, then DOCKER"
      log "${test_name}: HOST RT benchmark in parallel with churn -> ${out_host}"
      run_host_vb "${out_host}"

      log "${test_name}: DOCKER RT benchmark in parallel with churn -> ${out_docker}"
      run_docker_vb "${out_docker}"
    else
      log "${test_name} run ${i}: DOCKER first, then HOST"
      log "${test_name}: DOCKER RT benchmark in parallel with churn -> ${out_docker}"
      run_docker_vb "${out_docker}"

      log "${test_name}: HOST RT benchmark in parallel with churn -> ${out_host}"
      run_host_vb "${out_host}"
    fi

    stop_bg "${churn_pid}" "docker churn workload (${test_name})"

    mv "${out_host}" "${out_host%.csv}-run${i}.csv"
    mv "${RESULT_DIR}/${out_docker}" "${RESULT_DIR}/${out_docker%.csv}-run${i}.csv"
    sleep 10
  done
}

run_test() {
  local test_name="$1"
  case "${test_name}" in
    baseline_cfs) run_baseline_cfs ;;
    rt_isolated) run_rt_isolated ;;
    interf_same_core) run_interf_same_core ;;
    interf_host_cross_core) run_interf_host_cross_core ;;
    interf_docker_cross_core) run_interf_docker_cross_core ;;
    interf_memory) run_interf_memory ;;
    interf_io) run_interf_io ;;
    quota_17) run_quota_17 ;;
    quota_15) run_quota_15 ;;
    quota_13) run_quota_13 ;;
    sharing_shared_pool) run_sharing_shared_pool ;;
    migration_unpinned) run_migration_unpinned ;;
    churn_runtime) run_churn_runtime ;;
    *)
      echo "Error: unknown test '${test_name}'." >&2
      return 1
      ;;
  esac
}

add_tests_from_arg() {
  local raw="$1"
  local entries=()
  local entry
  IFS=',' read -r -a entries <<< "${raw}"

  for entry in "${entries[@]}"; do
    local test_name
    test_name="$(trim "${entry}")"
    [[ -z "${test_name}" ]] && continue

    if ! contains_test "${test_name}" "${ALL_TESTS[@]}"; then
      echo "Error: invalid test '${test_name}'." >&2
      echo "Valid tests: ${ALL_TESTS[*]}" >&2
      exit 1
    fi

    if ! contains_test "${test_name}" "${selected_tests[@]}"; then
      selected_tests+=("${test_name}")
    fi
  done
}

declare -a selected_tests=()
run_all=false

while (($# > 0)); do
  case "$1" in
    -t|--tests)
      if (($# < 2)); then
        echo "Error: parameter '$1' requires a list of tests." >&2
        usage
        exit 1
      fi
      add_tests_from_arg "$2"
      shift 2
      ;;
    -a|--all)
      run_all=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Error: unknown parameter '$1'." >&2
      usage
      exit 1
      ;;
  esac
done

if [[ "${run_all}" == true ]] && ((${#selected_tests[@]} > 0)); then
  echo "Error: use only one selection mode: --tests or --all." >&2
  exit 1
fi

declare -a tests_to_run=()
if [[ "${run_all}" == true ]]; then
  tests_to_run=("${ALL_TESTS[@]}")
else
  tests_to_run=("${selected_tests[@]}")
fi

if ((${#tests_to_run[@]} == 0)); then
  echo "Error: provide --tests or --all." >&2
  usage
  exit 1
fi

sudo_keep_alive
trap cleanup EXIT
mkdir -p "${RESULT_DIR}"

log "==================== ALL TESTS ===================="
log "Selected tests: ${tests_to_run[*]}"

for idx in "${!tests_to_run[@]}"; do
  run_test "${tests_to_run[idx]}"

  if (( idx < ${#tests_to_run[@]} - 1 )); then
    log "Cooldown between test blocks: 60s"
    sleep 60
  fi
done

log "✅ All tests completed. Results available in: ${RESULT_DIR}"
ls -lh "${RESULT_DIR}" | sed -n '1,200p'
