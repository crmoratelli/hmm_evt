#!/usr/bin/env python3
"""Build run-level and cell-level Phase 2 campaign summaries."""
from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    args = parser.parse_args()
    summaries = []
    for path in sorted((args.root / "runs").glob("*/summary.json")):
        if (path.parent / "COMPLETED").exists():
            summaries.append(json.loads(path.read_text()))
    if not summaries:
        raise SystemExit("no completed Phase 2 runs")

    run_fields = list(summaries[0])
    with (args.root / "run_summary.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=run_fields)
        writer.writeheader()
        writer.writerows(summaries)

    groups: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for row in summaries:
        groups[(row["architecture"], row["scenario"], row["substrate"])].append(row)
    cell_rows = []
    for (architecture, scenario, substrate), rows in sorted(groups.items()):
        cell_rows.append({
            "architecture": architecture,
            "scenario": scenario,
            "substrate": substrate,
            "completed_runs": len(rows),
            "total_jobs": sum(row["jobs"] for row in rows),
            "total_nominal_exposure_ns": sum(row["nominal_exposure_ns"] for row in rows),
            "total_misses": sum(row["misses"] for row in rows),
            "total_miss_episodes": sum(row["miss_episodes"] for row in rows),
            "total_delivery_shocks": sum(row["delivery_shocks_ge_threshold"] for row in rows),
            "total_dropped": sum(row["dropped"] for row in rows),
            "runs_with_misses": sum(row["misses"] > 0 for row in rows),
            "runs_with_drops": sum(row["dropped"] > 0 for row in rows),
            "median_of_run_median_response_ns": int(statistics.median(row["median_response_ns"] for row in rows)),
            "max_response_ns": max(row["max_response_ns"] for row in rows),
        })
    with (args.root / "cell_summary.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(cell_rows[0]))
        writer.writeheader()
        writer.writerows(cell_rows)
    print(f"completed_runs={len(summaries)} cells={len(cell_rows)}")


if __name__ == "__main__":
    main()

