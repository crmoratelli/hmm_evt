# =========================
# Sudo keep-alive
# =========================
sudo_keep_alive() {
    sudo -v

    # Keep sudo active while the script is running
    ( while true; do
        sudo -n true
        sleep 60
    done ) &
    SUDO_KEEPALIVE_PID=$!

    # Ensure the keep-alive process is terminated on exit
    trap 'kill ${SUDO_KEEPALIVE_PID} 2>/dev/null || true' EXIT
}

check_default_kernel_config() {
  log "Checking whether the system is in the default kernel/system configuration required by baseline_cfs..."

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
      log "ERROR: baseline_cfs requires the default kernel configuration, but /proc/cmdline contains RT/isolation parameters."
      log "Current cmdline: ${cmdline}"
      return 1
    fi
  done

  require_file_contains "/sys/devices/system/cpu/cpuidle/current_driver" '.+' \
    "active cpuidle driver" || return 1

  if [[ -r /sys/devices/system/cpu/smt/control ]]; then
    local smt_state
    smt_state="$(cat /sys/devices/system/cpu/smt/control 2>/dev/null || true)"
    if [[ "${smt_state}" == "off" || "${smt_state}" == "forceoff" ]]; then
      log "ERROR: SMT/Hyper-Threading is disabled (${smt_state}). baseline_cfs requires the default system configuration."
      return 1
    fi
  fi

  if [[ -r /proc/sys/kernel/sched_rt_runtime_us ]]; then
    local rt_runtime
    rt_runtime="$(cat /proc/sys/kernel/sched_rt_runtime_us 2>/dev/null || true)"
    if [[ "${rt_runtime}" == "-1" ]]; then
      log "ERROR: kernel.sched_rt_runtime_us=-1 detected. baseline_cfs requires the default kernel configuration."
      return 1
    fi
  fi

  log "OK: environment is compatible with the default configuration required by baseline_cfs."
}

# =========================
# Initial checks
# =========================
configure_test_environment() {
  log "Configuring CPUs: performance governor, 3.8 GHz, boost disabled..."
  sudo sh -c '
    set -e
    for f in /sys/devices/system/cpu/cpu[0-9]*/cpufreq; do
      [ -d "$f" ] || continue
      echo performance > "$f/scaling_governor"
      echo 3800000 > "$f/scaling_min_freq"
      echo 3800000 > "$f/scaling_max_freq"
    done
    [ ! -w /sys/devices/system/cpu/cpufreq/boost ] || echo 0 > /sys/devices/system/cpu/cpufreq/boost
  '
  local bad=0 f gov min max
  for f in /sys/devices/system/cpu/cpu[0-9]*/cpufreq; do
    [ -d "$f" ] || continue
    gov=$(cat "$f/scaling_governor"); min=$(cat "$f/scaling_min_freq"); max=$(cat "$f/scaling_max_freq")
    [[ "$gov" == performance && "$min" == 3800000 && "$max" == 3800000 ]] || { log "ERROR: invalid state at $f"; bad=1; }
  done
  [[ "$bad" == 0 ]] || return 1
  [[ ! -r /sys/devices/system/cpu/cpufreq/boost || $(cat /sys/devices/system/cpu/cpufreq/boost) == 0 ]] || { log "ERROR: boost is enabled"; return 1; }
}

record_environment() {
  local out="$1"
  { date -Is; hostname; uname -a; cat /proc/cmdline; cat /sys/devices/system/cpu/isolated 2>/dev/null || true; cat /sys/devices/system/cpu/cpufreq/boost 2>/dev/null || true; lscpu -e=CPU,CORE,SOCKET,NODE; } > "$out"
}

initial_check() {
    need_cmd docker
    need_cmd taskset
    need_cmd cpupower

    mkdir -p "${RESULT_DIR}"

    configure_test_environment
    record_environment "${RESULT_DIR}/environment.log"
    log "Preparing system settings (RT runtime)..."
    sudo sysctl -w kernel.sched_rt_runtime_us=-1
    sudo sh -c 'echo 0 > /sys/devices/system/cpu/cpufreq/boost' || true

    log "Informational check:"
    cpupower frequency-info || true
    cpupower idle-info || true
    grep -m1 "cpu MHz" /proc/cpuinfo || true

    log "Checking boot parameters (cmdline)..."

    CMDLINE="$(cat /proc/cmdline)"

    missing=()

    grep -qw "idle=poll" <<<"${CMDLINE}" || missing+=("idle=poll")
    grep -qw "processor.max_cstate=0" <<<"${CMDLINE}" || missing+=("processor.max_cstate=0")

    if (( ${#missing[@]} > 0 )); then
    echo
    echo "❌ ERROR: required kernel boot parameters are missing from /proc/cmdline"
    echo "   Expected: idle=poll processor.max_cstate=0"
    echo "   Found: ${CMDLINE}"
    echo "   Missing: ${missing[*]}"
    echo
    echo "👉 Reboot the system with these parameters before running the tests."
    exit 1
    fi

    log "Boot parameters OK: idle=poll and processor.max_cstate=0"
}

# =========================
# Helpers
# =========================
log() { echo -e "[$(date '+%F %T')] $*"; }

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || { echo "Error: command '$1' not found."; exit 1; }
}

kill_tree() {
  # kill_tree <pid> <signal>
  local pid="$1"
  local sig="${2:-TERM}"

  # Get direct children and kill them recursively
  local children
  children="$(pgrep -P "${pid}" 2>/dev/null || true)"
  for c in ${children}; do
    kill_tree "${c}" "${sig}"
  done

  kill "-${sig}" "${pid}" 2>/dev/null || true
}

stop_bg() {
  # stop_bg <pid> <name>
  local pid="${1:-}"
  local name="${2:-process}"

  [[ -z "${pid}" ]] && return 0

  if kill -0 "${pid}" >/dev/null 2>&1; then
    log "Stopping ${name} (pid=${pid})..."

    # First try TERM on the whole tree
    kill_tree "${pid}" TERM

    # Wait up to 5s
    for _ in {1..50}; do
      if ! kill -0 "${pid}" >/dev/null 2>&1; then
        wait "${pid}" 2>/dev/null || true
        log "${name} stopped (TERM)."
        return 0
      fi
      sleep 0.1
    done

    log "${name} did not stop with TERM; sending KILL to the process tree..."
    kill_tree "${pid}" KILL
    wait "${pid}" 2>/dev/null || true
    log "${name} stopped (KILL)."
  fi
}

run_host_va() {
  local out="${1}"
  log "HOST benchmark -> ${out}"
  sudo taskset -c "${CPU_RT}" ./benchmark/periodic_bench \
    --period "${PERIOD}" --deadline "${DEADLINE}" --duration "${DURATION}" \
    --out "${out}"
}

run_docker_va() {
  local out="${1}"
  log "DOCKER benchmark -> ${out}"
  docker run --rm \
    --cpus=1 \
    --cpuset-cpus="${CPU_RT}" \
    -v "${RESULT_DIR}:/out" \
    "${IMAGE}" \
    ./periodic_bench --period "${PERIOD}" --deadline "${DEADLINE}" --duration "${DURATION}" \
    --out "/out/${out}"
}

run_host_vb() {
  local out="${1}"
  log "HOST RT benchmark -> ${out}"
  sudo chrt -f 80 taskset -c "${CPU_RT}" ./benchmark/periodic_bench \
    --period "${PERIOD}" --deadline "${DEADLINE}" --duration "${DURATION}" \
    --out "${out}"
}

run_docker_vb() {
  local out="${1}"
  log "DOCKER RT benchmark -> ${out}"

  docker run --rm \
    --cap-add=sys_nice \
    --ulimit rtprio=99 \
    --ulimit memlock=-1 \
    --cpuset-cpus="${CPU_RT}" \
    -v "${RESULT_DIR}:/out" \
    "${IMAGE}" \
    chrt -f 80 ./periodic_bench \
      --period "${PERIOD}" --deadline "${DEADLINE}" --duration "${DURATION}" \
      --out "/out/${out}"
}


start_stress_host() {
  local name="$1"; shift
  log "Starting HOST disturbance: ${name}"

  # Create a new session (new PGID) to avoid sharing the script's PGID
  (
    set +e
    setsid "$@" >/dev/null 2>&1
  ) &

  STRESS_PID=$!
  STRESS_PGID="$STRESS_PID"  # with setsid, PGID is usually equal to PID
}

stop_stress_docker() {
  local cname="${1:-}"
  local name="${2:-container-stress}"

  if [[ -z "${cname}" ]]; then return 0; fi

  log "Stopping ${name} (container=${cname})..."
  docker stop -t 2 "${cname}" >/dev/null 2>&1 || true

  # If it still exists, force kill
  if docker ps -a --format '{{.Names}}' | grep -qx "${cname}"; then
    docker kill "${cname}" >/dev/null 2>&1 || true
  fi
}


start_stress_docker() {
  local name="$1"; shift
  log "Starting DOCKER disturbance: ${name}"

  STRESS_CNAME="stress_${name}_$$"

  (
    set +e
    docker run --rm --name "${STRESS_CNAME}" "$@" >/dev/null 2>&1
  ) &

  STRESS_PID=$!
}


start_hogs_k() {
  local k="$1"
  log "Starting ${k} hogs (shares=${HOG_SHARES}, cpus=${OTHER_CPUS})..."
  for i in $(seq 1 "${k}"); do
    docker run -d --rm \
      --name "${HOG_PREFIX}${i}" \
      --cpu-shares="${HOG_SHARES}" \
      --cpuset-cpus="${OTHER_CPUS}" \
      "${HOG_IMAGE}" \
      sh -c "while true; do :; done" >/dev/null
  done
}


stop_hogs_all() {
  local ids
  ids="$(docker ps -q --filter "name=^/${HOG_PREFIX}[0-9]+$" 2>/dev/null || true)"
  if [[ -n "${ids}" ]]; then
    log "Stopping hogs..."
    docker stop ${ids} >/dev/null 2>&1 || true
  fi
}


run_docker_vb_shares() {
  local out="${1}"
  log "DOCKER CFS benchmark with cpu.shares -> ${out}"

  docker run --rm \
    --cpuset-cpus="${SHARED_CPUS}" \
    --cpu-shares="${BENCH_SHARES}" \
    -v "${RESULT_DIR}:/out" \
    "${IMAGE}" \
    ./periodic_bench \
      --period "${PERIOD}" \
      --deadline "${DEADLINE}" \
      --duration "${DURATION}" \
      --out "/out/${out}"
}

start_hogs_k_shared() {
  local k="$1"
  log "Starting ${k} hogs in SHARED_CPUS=${SHARED_CPUS} (hog_shares=${HOG_SHARES})..."
  for i in $(seq 1 "${k}"); do
    docker run -d --rm \
      --name "${HOG_PREFIX}${i}" \
      --cpu-shares="${HOG_SHARES}" \
      --cpuset-cpus="${SHARED_CPUS}" \
      "${HOG_IMAGE}" \
      sh -c "while :; do :; done" >/dev/null
  done
}

stop_hogs_all_shared() {
  # Docker "name" filter is substring match (not regex); use prefix and stop them all.
  local ids
  ids="$(docker ps -q --filter "name=${HOG_PREFIX}" 2>/dev/null || true)"
  if [[ -n "${ids}" ]]; then
    log "Stopping hogs (${HOG_PREFIX}*)..."
    docker stop ${ids} >/dev/null 2>&1 || true
  fi
}



build_shared_cpus() {
  local rt="${CPU_RT}"
  local n="${SHARED_POOL_N}"

  local total
  total="$(nproc)"

  if (( n < 1 )); then
    echo "ERROR: SHARED_POOL_N must be >= 1" >&2
    return 1
  fi

  if (( n > total )); then
    echo "WARN: SHARED_POOL_N=${n} > nproc=${total}; using ${total}" >&2
    n="${total}"
  fi

  # Build candidate list excluding rt
  local cand=()
  for c in $(seq 0 $((total-1))); do
    if [[ "${c}" != "${rt}" ]]; then
      cand+=("${c}")
    fi
  done

  # Start cpulist with RT core, then fill with first (n-1) candidates
  SHARED_CPUS="${rt}"
  local need=$((n-1))
  for ((i=0; i<need; i++)); do
    SHARED_CPUS+=",${cand[$i]}"
  done
}

build_shared_cpus || exit 1
log "sharing_shared_pool: using SHARED_CPUS=${SHARED_CPUS} (pool size=${SHARED_POOL_N}, includes CPU_RT=${CPU_RT})"
