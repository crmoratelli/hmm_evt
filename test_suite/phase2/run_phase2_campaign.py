#!/usr/bin/env python3
"""Create and execute the blocked, seeded Phase 2 schedule."""
from __future__ import annotations

import argparse
import csv
import hashlib
import os
import random
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
OBSERVATION = HERE / "run_phase2_observation.sh"
PREFLIGHT = HERE / "preflight_phase2.sh"
SUMMARIZE = HERE / "summarize_phase2_campaign.py"

ARCHITECTURES = ("deferred", "inline", "async")
SCENARIOS = ("control", "io")
SUBSTRATES = ("host", "container")


def env_int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def make_schedule(repetitions: int, seed: int) -> list[dict[str, int | str]]:
    rng = random.Random(seed)
    rows: list[dict[str, int | str]] = []
    sequence = 1
    cells = [(a, s, u) for a in ARCHITECTURES for s in SCENARIOS for u in SUBSTRATES]
    for block in range(1, repetitions + 1):
        order = cells.copy()
        rng.shuffle(order)
        for architecture, scenario, substrate in order:
            rows.append({
                "sequence": sequence,
                "block": block,
                "replication": block,
                "architecture": architecture,
                "scenario": scenario,
                "substrate": substrate,
            })
            sequence += 1
    return rows


def run_id(row: dict[str, int | str]) -> str:
    return (
        f"{int(row['sequence']):04d}_{row['scenario']}_{row['substrate']}_"
        f"{row['architecture']}_run{int(row['replication']):02d}"
    )


def normalized(rows: list[dict[str, int | str]]) -> list[dict[str, str]]:
    return [{key: str(value) for key, value in row.items()} for row in rows]


def main() -> None:
    parser = argparse.ArgumentParser(description="TDPS Phase 2 factorial campaign")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--dry-run", action="store_true", help="print the full schedule; write nothing")
    action.add_argument("--smoke", action="store_true", help="execute one 12-cell short block")
    action.add_argument("--full", action="store_true", help="execute the confirmatory campaign")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--block", type=int, help="execute one pre-registered block")
    parser.add_argument("--seed", type=int, default=env_int("PHASE2_SEED", 20260915))
    parser.add_argument("--replications", type=int, default=env_int("PHASE2_REPLICATIONS", 10))
    args = parser.parse_args()
    if args.replications < 1:
        parser.error("--replications must be positive")
    if args.smoke and args.block not in (None, 1):
        parser.error("smoke has only block 1")

    if args.smoke:
        profile = "smoke"
        repetitions = 1
        duration = env_int("PHASE2_SMOKE_DURATION_S", 10)
        root = Path(os.getenv("PHASE2_SMOKE_ROOT", "/home/ghost/tdps_phase2_smoke"))
    else:
        profile = "full"
        repetitions = args.replications
        duration = env_int("PHASE2_DURATION_S", 500)
        root = Path(os.getenv("PHASE2_RESULT_ROOT", "/home/ghost/tdps_phase2_results"))

    rows = make_schedule(repetitions, args.seed)
    selected = [row for row in rows if args.block is None or row["block"] == args.block]
    if args.block is not None and not selected:
        parser.error(f"block {args.block} is outside 1..{repetitions}")
    for row in selected:
        print(
            f"{int(row['sequence']):03d}: block={row['block']} {row['architecture']} "
            f"{row['scenario']} {row['substrate']}",
            flush=True,
        )
    run_count = len(selected)
    minimum = run_count * (duration + env_int("INTERFERENCE_WARMUP_S", 10) + env_int("BETWEEN_OBSERVATIONS_S", 15))
    print(f"runs={run_count} nominal_seconds={run_count * duration} minimum_planned_seconds={minimum}")
    if args.dry_run:
        return

    root.mkdir(parents=True, exist_ok=True)
    runs = root / "runs"
    failed = root / "failed_runs"
    runs.mkdir(exist_ok=True)
    failed.mkdir(exist_ok=True)
    schedule_path = root / "schedule.csv"
    fields = ["sequence", "block", "replication", "architecture", "scenario", "substrate"]
    if not schedule_path.exists():
        with schedule_path.open("x", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        schedule_hash = hashlib.sha256(schedule_path.read_bytes()).hexdigest()
        (root / "campaign.env").write_text(
            f"PROFILE={profile}\nSEED={args.seed}\nREPLICATIONS={repetitions}\n"
            f"DURATION_S={duration}\nSCHEDULE_SHA256={schedule_hash}\n"
            f"CREATED_AT={datetime.now(timezone.utc).isoformat()}\n"
        )
    else:
        with schedule_path.open(newline="") as stream:
            existing = list(csv.DictReader(stream))
        if existing != normalized(rows):
            raise SystemExit("existing schedule differs from requested profile/seed/replications")
        if not args.resume:
            raise SystemExit(f"{schedule_path} exists; use --resume or choose a new result root")

    subprocess.run([str(PREFLIGHT), "--check-only"], check=True, env={**os.environ, "PHASE2_RESULT_ROOT": str(root)})
    attempts_path = root / "attempts.csv"
    with attempts_path.open("a", newline="") as stream:
        attempt_fields = fields + ["run_id", "started_at", "status", "exit_code"]
        writer = csv.DictWriter(stream, fieldnames=attempt_fields)
        if stream.tell() == 0:
            writer.writeheader()
        for row in selected:
            target = runs / run_id(row)
            if (target / "COMPLETED").exists():
                if args.resume:
                    print(f"skip completed: {target.name}", flush=True)
                    continue
                raise SystemExit(f"refusing to overwrite completed run: {target}")
            if target.exists():
                if not args.resume:
                    raise SystemExit(f"refusing to overwrite incomplete run: {target}")
                stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                archived = failed / f"{target.name}__{stamp}"
                suffix = 1
                while archived.exists():
                    archived = failed / f"{target.name}__{stamp}_{suffix}"
                    suffix += 1
                shutil.move(str(target), str(archived))
                print(f"archived incomplete run: {target.name} -> {archived.name}", flush=True)

            command = [
                str(OBSERVATION), str(row["architecture"]), str(row["scenario"]),
                str(row["substrate"]), str(row["replication"]), str(row["block"]),
                str(row["sequence"]),
            ]
            print("+", " ".join(command), flush=True)
            run_env = {
                **os.environ,
                "PHASE2_ACTIVE_ROOT": str(root),
                "PHASE2_ACTIVE_DURATION_S": str(duration),
                "PHASE2_PROFILE": profile,
            }
            started = datetime.now(timezone.utc).isoformat()
            rc = subprocess.run(command, env=run_env).returncode
            writer.writerow({
                **row,
                "run_id": run_id(row),
                "started_at": started,
                "status": "completed" if rc == 0 else "failed",
                "exit_code": rc,
            })
            stream.flush()
            if rc != 0:
                raise SystemExit(rc)

    subprocess.run(["python3", str(SUMMARIZE), "--root", str(root)], check=True)


if __name__ == "__main__":
    main()

