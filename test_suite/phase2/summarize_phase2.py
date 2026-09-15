#!/usr/bin/env python3
"""Validate and summarize one Phase 2 observation."""
from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
from pathlib import Path


def read_env(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text(errors="replace").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            result[key] = value
    return result


def quantile(values: list[int], probability: float) -> int:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(probability * (len(ordered) - 1)))]


def episodes(flags: list[bool], values: list[int]) -> list[dict[str, int]]:
    found: list[dict[str, int]] = []
    start = None
    for index, flag in enumerate(flags + [False]):
        if flag and start is None:
            start = index
        elif not flag and start is not None:
            segment = values[start:index]
            found.append({
                "start_job": start,
                "end_job": index - 1,
                "length_jobs": index - start,
                "max_response_ns": max(segment),
                "sum_response_ns": sum(segment),
            })
            start = None
    return found


def write_rows(path: Path, rows: list[dict[str, int]], fields: list[str]) -> None:
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--shock-threshold-ns", required=True, type=int)
    args = parser.parse_args()
    run_dir = args.run_dir
    meta = read_env(run_dir / "metadata.env")
    mode = meta["ARCHITECTURE"]
    period = int(meta["PERIOD_NS"])
    deadline = int(meta["DEADLINE_NS"])
    expected_jobs = int(meta["JOBS"])
    expected_cpu = int(meta["CPU_RT"])

    with (run_dir / "samples.csv").open(newline="") as stream:
        rows = [{key: int(value) for key, value in row.items()} for row in csv.DictReader(stream)]
    if len(rows) != expected_jobs:
        raise SystemExit(f"jobs={len(rows)}, expected={expected_jobs}")
    if [row["job"] for row in rows] != list(range(expected_jobs)):
        raise SystemExit("job IDs are not contiguous and ordered")

    first_release = rows[0]["release_ns"]
    accepted_ids: list[int] = []
    for index, row in enumerate(rows):
        if row["schema_version"] != 2:
            raise SystemExit("unexpected schema")
        if row["release_ns"] != first_release + index * period:
            raise SystemExit(f"release arithmetic failed at job {index}")
        if not (row["release_ns"] <= row["start_ns"] <= row["compute_finish_ns"] == row["finish_ns"]):
            raise SystemExit(f"basic timestamp order failed at job {index}")
        if row["execution_ns"] != row["compute_finish_ns"] - row["start_ns"]:
            raise SystemExit(f"execution identity failed at job {index}")
        if row["wakeup_delay_ns"] != row["start_ns"] - row["release_ns"]:
            raise SystemExit(f"wakeup identity failed at job {index}")
        if row["response_ns"] != row["compute_finish_ns"] - row["release_ns"]:
            raise SystemExit(f"response identity failed at job {index}")
        if row["lateness_ns"] != row["response_ns"] - deadline or row["miss"] != int(row["response_ns"] > deadline):
            raise SystemExit(f"deadline identity failed at job {index}")
        if row["cpu"] != expected_cpu:
            raise SystemExit(f"job {index} observed on CPU {row['cpu']}, expected {expected_cpu}")
        if not (row["compute_finish_ns"] <= row["output_start_ns"] <= row["output_finish_ns"]):
            raise SystemExit(f"output timestamp order failed at job {index}")
        if row["accepted"] + row["dropped"] != 1:
            raise SystemExit(f"accept/drop accounting failed at job {index}")
        if row["accepted"]:
            accepted_ids.append(index)
            if row["delivery_errno"] != 0:
                raise SystemExit(f"delivery error at job {index}")
            if not (row["delivery_start_ns"] >= row["compute_finish_ns"] and row["delivery_finish_ns"] >= row["delivery_start_ns"]):
                raise SystemExit(f"delivery timestamp order failed at job {index}")
            if mode == "inline" and not (
                row["output_start_ns"] <= row["delivery_start_ns"] <= row["delivery_finish_ns"] <= row["output_finish_ns"]
            ):
                raise SystemExit(f"inline delivery is outside output interval at job {index}")
        elif any(row[key] for key in ("delivery_start_ns", "delivery_finish_ns", "delivery_errno")):
            raise SystemExit(f"dropped job {index} has delivery fields")

    if mode in ("deferred", "inline") and len(accepted_ids) != expected_jobs:
        raise SystemExit(f"{mode} must deliver every offered record")
    if mode == "deferred" and min(row["delivery_start_ns"] for row in rows) < max(row["compute_finish_ns"] for row in rows):
        raise SystemExit("deferred delivery began before the loop ended")

    payload = (run_dir / "functional.bin").read_bytes()
    if len(payload) != len(accepted_ids) * 64:
        raise SystemExit("functional output size does not match accepted records")
    for offset, job in enumerate(accepted_ids):
        record = payload[offset * 64:(offset + 1) * 64]
        if int.from_bytes(record[:8], "little") != job or record[8:] != b"T" * 56:
            raise SystemExit(f"functional record mismatch at delivered offset {offset}")

    log = (run_dir / "benchmark.log").read_text(errors="replace")
    config_line = next((line for line in log.splitlines() if line.startswith("schema=2 ")), "")
    config = dict(token.split("=", 1) for token in config_line.split() if "=" in token)
    expected_config = {
        "schema": "2",
        "mode": mode,
        "jobs": str(expected_jobs),
        "period": str(period),
        "deadline": str(deadline),
        "iters": meta["BENCH_ITERS"],
        "policy": "1",
        "priority": meta["RT_PRIORITY"],
        "cpu": str(expected_cpu),
        "logger_cpu": meta["LOGGER_CPU"],
        "queue": meta["ASYNC_QUEUE_CAPACITY"],
        "record_bytes": "64",
        "minimal": "0",
        "mlock": "1",
    }
    for key, expected in expected_config.items():
        if config.get(key) != expected:
            raise SystemExit(f"benchmark config {key}={config.get(key)!r}, expected {expected!r}")
    final = re.search(
        r"loop_end_ns=(\d+) drain_end_ns=(\d+) accepted=(\d+) dropped=(\d+) "
        r"delivery_errors=(\d+) queue_high_water=(\d+)", log
    )
    if not final:
        raise SystemExit("benchmark final accounting is missing")
    loop_end, drain_end, log_accepted, log_dropped, delivery_errors, high_water = map(int, final.groups())
    dropped = expected_jobs - len(accepted_ids)
    if (log_accepted, log_dropped, delivery_errors) != (len(accepted_ids), dropped, 0):
        raise SystemExit("benchmark log and CSV accounting differ")
    queue_capacity = int(meta["ASYNC_QUEUE_CAPACITY"])
    if high_water > queue_capacity:
        raise SystemExit("queue high-water exceeds configured capacity")

    response = [row["response_ns"] for row in rows]
    execution = [row["execution_ns"] for row in rows]
    wakeup = [row["wakeup_delay_ns"] for row in rows]
    miss_flags = [bool(row["miss"]) for row in rows]
    high_flags = [value >= args.shock_threshold_ns for value in response]
    miss_episodes = episodes(miss_flags, response)
    high_episodes = episodes(high_flags, response)
    shock_rows = [
        {
            "job": row["job"],
            "delivery_duration_ns": row["delivery_finish_ns"] - row["delivery_start_ns"],
            "response_ns": row["response_ns"],
        }
        for row in rows
        if row["accepted"] and row["delivery_finish_ns"] - row["delivery_start_ns"] >= args.shock_threshold_ns
    ]
    local_response = [row["output_finish_ns"] - row["release_ns"] for row in rows if row["accepted"]]
    delivery_response = [row["delivery_finish_ns"] - row["release_ns"] for row in rows if row["accepted"]]
    delivery_duration = [row["delivery_finish_ns"] - row["delivery_start_ns"] for row in rows if row["accepted"]]
    queue_wait = [row["delivery_start_ns"] - row["output_start_ns"] for row in rows if mode == "async" and row["accepted"]]

    summary = {
        "run_id": meta["RUN_ID"],
        "architecture": mode,
        "scenario": meta["SCENARIO"],
        "substrate": meta["SUBSTRATE"],
        "block": int(meta["BLOCK"]),
        "replication": int(meta["REPLICATION"]),
        "jobs": expected_jobs,
        "nominal_exposure_ns": expected_jobs * period,
        "actual_loop_interval_ns": loop_end - first_release,
        "drain_ns": drain_end - loop_end,
        "accepted": len(accepted_ids),
        "dropped": dropped,
        "drop_rate": dropped / expected_jobs,
        "delivery_errors": 0,
        "queue_high_water": high_water,
        "misses": sum(miss_flags),
        "miss_episodes": len(miss_episodes),
        "max_miss_episode_jobs": max((item["length_jobs"] for item in miss_episodes), default=0),
        "activations_ge_threshold": sum(high_flags),
        "episodes_ge_threshold": len(high_episodes),
        "delivery_shocks_ge_threshold": len(shock_rows),
        "shock_threshold_ns": args.shock_threshold_ns,
        "median_response_ns": int(statistics.median(response)),
        "p99_response_ns": quantile(response, 0.99),
        "p999_response_ns": quantile(response, 0.999),
        "max_response_ns": max(response),
        "median_execution_ns": int(statistics.median(execution)),
        "max_execution_ns": max(execution),
        "max_wakeup_delay_ns": max(wakeup),
        "median_local_response_ns": int(statistics.median(local_response)),
        "p99_local_response_ns": quantile(local_response, 0.99),
        "max_local_response_ns": max(local_response),
        "median_delivery_response_ns": int(statistics.median(delivery_response)),
        "p99_delivery_response_ns": quantile(delivery_response, 0.99),
        "max_delivery_response_ns": max(delivery_response),
        "median_delivery_duration_ns": int(statistics.median(delivery_duration)),
        "max_delivery_duration_ns": max(delivery_duration),
        "median_async_queue_wait_ns": int(statistics.median(queue_wait)) if queue_wait else None,
        "p99_async_queue_wait_ns": quantile(queue_wait, 0.99) if queue_wait else None,
        "max_async_queue_wait_ns": max(queue_wait) if queue_wait else None,
    }
    episode_fields = ["start_job", "end_job", "length_jobs", "max_response_ns", "sum_response_ns"]
    write_rows(run_dir / "miss_episodes.csv", miss_episodes, episode_fields)
    write_rows(run_dir / "high_response_episodes.csv", high_episodes, episode_fields)
    write_rows(run_dir / "delivery_shocks.csv", shock_rows, ["job", "delivery_duration_ns", "response_ns"])
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    with (run_dir / "summary.txt").open("w") as stream:
        for key, value in summary.items():
            stream.write(f"{key}={value}\n")
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
