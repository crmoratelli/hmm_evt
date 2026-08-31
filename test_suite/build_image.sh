#!/usr/bin/env bash
set -euo pipefail
SUITE_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
# shellcheck source=lib.sh
source "${SUITE_DIR}/lib.sh"

need_cmd make
need_cmd nerdctl
make -C "${SUITE_DIR}/benchmark" clean all

started_buildkit=0
if ! pgrep -x buildkitd >/dev/null; then
  as_root systemctl start buildkit 2>/dev/null || die "BuildKit is required for nerdctl build"
  started_buildkit=1
fi

as_root nerdctl --namespace "${TDPS_NAMESPACE}" build \
  --tag "${BENCH_IMAGE}" "${SUITE_DIR}/benchmark"

if (( started_buildkit )); then as_root systemctl stop buildkit 2>/dev/null || true; fi

as_root nerdctl --namespace "${TDPS_NAMESPACE}" run --rm --net none \
  --entrypoint /usr/bin/chrt "${BENCH_IMAGE}" --version >/dev/null
as_root nerdctl --namespace "${TDPS_NAMESPACE}" pull "${CHURN_IMAGE}" >/dev/null
log "built and validated ${BENCH_IMAGE}"
