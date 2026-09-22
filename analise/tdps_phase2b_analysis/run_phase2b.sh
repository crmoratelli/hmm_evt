#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "usage: $0 /path/to/tdps_phase2_results [output_dir]" >&2
  exit 2
fi

root="$(realpath "$1")"
output="${2:-phase2b_results}"
python3 "$(dirname "$0")/phase2b_analysis.py" --root "$root" --output "$output"

