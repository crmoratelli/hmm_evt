#!/usr/bin/env python3
"""Validate and summarize one Phase 3A observation."""
from __future__ import annotations

import argparse
import csv
import statistics
from pathlib import Path


def quantile(values: list[int], p: float) -> int:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(p * (len(ordered) - 1)))]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True, type=Path)
    args = parser.parse_args()
    with (args.run_dir / "samples.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise SystemExit("samples.csv is empty")

    jobs = [int(row["job"]) for row in rows]
    if jobs != list(range(len(rows))):
        raise SystemExit("job IDs are not contiguous and ordered")
    if any(int(row["accepted"]) != 1 or int(row["dropped"]) != 0 or int(row["delivery_errno"]) != 0 for row in rows):
        raise SystemExit("incomplete or failed functional delivery")

    response = [int(row["response_ns"]) for row in rows]
    execution = [int(row["execution_ns"]) for row in rows]
    wakeup = [int(row["wakeup_delay_ns"]) for row in rows]
    delivery = [int(row["delivery_finish_ns"]) - int(row["compute_finish_ns"]) for row in rows]
    misses = sum(int(row["miss"]) for row in rows)
    high = [value >= 10_000_000 for value in response]
    high_episodes = sum(flag and (index == 0 or not high[index - 1]) for index, flag in enumerate(high))
    miss_flags = [bool(int(row["miss"])) for row in rows]
    miss_episodes = sum(flag and (index == 0 or not miss_flags[index - 1]) for index, flag in enumerate(miss_flags))
    summary = {
        "jobs": len(rows),
        "misses": misses,
        "activations_ge_10ms": sum(high),
        "episodes_ge_10ms": high_episodes,
        "miss_episodes": miss_episodes,
        "median_response_ns": int(statistics.median(response)),
        "p99_response_ns": quantile(response, 0.99),
        "p999_response_ns": quantile(response, 0.999),
        "max_response_ns": max(response),
        "median_execution_ns": int(statistics.median(execution)),
        "max_wakeup_delay_ns": max(wakeup),
        "median_delivery_after_compute_ns": int(statistics.median(delivery)),
        "max_delivery_after_compute_ns": max(delivery),
    }
    with (args.run_dir / "summary.txt").open("w") as stream:
        for key, value in summary.items():
            stream.write(f"{key}={value}\n")
    for key, value in summary.items():
        print(f"{key}={value}")


if __name__ == "__main__":
    main()
