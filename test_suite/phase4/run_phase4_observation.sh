#!/usr/bin/env bash
set -euo pipefail

PHASE4_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
SUITE_DIR="$(cd -- "${PHASE4_DIR}/.." && pwd)"
source "${SUITE_DIR}/lib.sh"
source "${PHASE4_DIR}/config_phase4.sh"

level="${1:-}"; iters="${2:-}"; shock_ns="${3:-}"; replication="${4:-}"; block="${5:-}"; sequence="${6:-}"
[[ "${level}" =~ ^c[0-9]+$ ]] || die "invalid level"
for value in "${iters}" "${shock_ns}" "${replication}" "${block}" "${sequence}"; do
  [[ "${value}" =~ ^[0-9]+$ ]] || die "invalid numeric argument"
done

result_root="${PHASE4_ACTIVE_ROOT:-${PHASE4_RESULT_ROOT}}"
profile="${PHASE4_PROFILE:-full}"
run_id="$(printf '%04d_%s_b%08dns_run%02d' "${sequence}" "${level}" "${shock_ns}" "${replication}")"
run_dir="${result_root}/runs/${run_id}"
stage_dir="${PHASE4_STAGE_ROOT}/${profile}-${run_id}"
[[ ! -e "${run_dir}" && ! -e "${stage_dir}" ]] || die "run or stage already exists: ${run_id}"
mkdir -p "${run_dir}" "${stage_dir}"

completed=0
cleanup() {
  rc=$?; set +e
  if [[ -d "${stage_dir}" ]]; then cp -a "${stage_dir}/." "${run_dir}/" 2>/dev/null || true; rm -rf -- "${stage_dir:?}"; fi
  if (( ! completed )); then printf 'STATE=failed\nEXIT_CODE=%s\n' "${rc}" >> "${run_dir}/metadata.env" 2>/dev/null || true; : > "${run_dir}/FAILED"; fi
}
trap cleanup EXIT INT TERM

cat > "${stage_dir}/metadata.env" <<EOF
RUN_ID=${run_id}
PROFILE=${profile}
STATE=running
SEQUENCE=${sequence}
BLOCK=${block}
REPLICATION=${replication}
EXECUTION_LEVEL=${level}
BENCH_ITERS=${iters}
PERIOD_NS=${PHASE4_PERIOD_NS}
DEADLINE_NS=${PHASE4_DEADLINE_NS}
JOBS=${PHASE4_JOBS}
SHOCK_JOB=${PHASE4_SHOCK_JOB}
SHOCK_REQUESTED_NS=${shock_ns}
CPU_RT=${CPU_RT}
RT_PRIORITY=${RT_PRIORITY}
GIT_COMMIT=$(git -C "${SUITE_DIR}/.." rev-parse HEAD 2>/dev/null || printf unknown)
GIT_BRANCH=$(git -C "${SUITE_DIR}/.." rev-parse --abbrev-ref HEAD 2>/dev/null || printf unknown)
STARTED_AT=$(date -Is)
EOF
cat /proc/cmdline > "${stage_dir}/cmdline.txt"
snapshot_managed_irqs "${stage_dir}/managed_irqs_before.csv"

command=(sudo timeout --signal=TERM --kill-after=5 15s chrt -f "${RT_PRIORITY}" taskset -c "${CPU_RT}"
  "${PHASE4_DIR}/periodic_phase4" --period "${PHASE4_PERIOD_NS}" --deadline "${PHASE4_DEADLINE_NS}"
  --jobs "${PHASE4_JOBS}" --iters "${iters}" --shock-job "${PHASE4_SHOCK_JOB}"
  --shock-ns "${shock_ns}" --out "${stage_dir}/samples.csv" --mlock)
printf '%q ' "${command[@]}" > "${stage_dir}/benchmark_command.txt"; printf '\n' >> "${stage_dir}/benchmark_command.txt"
if (( EUID == 0 )); then command=("${command[@]:1}"); fi
"${command[@]}" >"${stage_dir}/benchmark.stdout" 2>"${stage_dir}/benchmark.log"

snapshot_managed_irqs "${stage_dir}/managed_irqs_after.csv"
compare_irq_snapshots "${stage_dir}/managed_irqs_before.csv" "${stage_dir}/managed_irqs_after.csv" \
  "${stage_dir}/managed_irq_delta.csv" || die "managed IRQ activity during observation"

python3 "${PHASE4_DIR}/validate_phase4_run.py" --run-dir "${stage_dir}"
printf 'VALID=1\nSTATE=completed\nCOMPLETED_AT=%s\n' "$(date -Is)" >> "${stage_dir}/metadata.env"
: > "${stage_dir}/COMPLETED"
cp -a "${stage_dir}/." "${run_dir}/"
rm -rf -- "${stage_dir:?}"
completed=1
trap - EXIT INT TERM
sleep "${PHASE4_BETWEEN_S}"
log "completed ${run_id}"
