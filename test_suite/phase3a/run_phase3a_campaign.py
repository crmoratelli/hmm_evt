#!/usr/bin/env python3
"""Generate and execute the seeded, paired Phase 3A schedule."""
from __future__ import annotations

import argparse
import csv
import os
import random
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path


HERE = Path(__file__).resolve().parent
OBSERVATION = HERE / "run_phase3a_observation.sh"


def schedule(repetitions: int, seed: int) -> list[dict[str, int | str]]:
    rng = random.Random(seed)
    rows: list[dict[str, int | str]] = []
    sequence = 1
    for block in range(1, repetitions + 1):
        sinks = ["ext4", "tmpfs"]
        rng.shuffle(sinks)
        for sink in sinks:
            rows.append({"sequence": sequence, "block": block, "replication": block, "sink": sink})
            sequence += 1
    return rows


def run_id(row: dict[str, int | str]) -> str:
    return f"{int(row['sequence']):04d}_io_host_inline_{row['sink']}_run{int(row['replication']):02d}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--replications", type=int, default=int(os.getenv("PHASE3A_REPLICATIONS", "5")))
    parser.add_argument("--seed", type=int, default=int(os.getenv("PHASE3A_SEED", "20260910")))
    args = parser.parse_args()
    if args.replications < 1:
        parser.error("--replications must be positive")

    rows = schedule(args.replications, args.seed)
    for row in rows:
        print(f"{row['sequence']:02d}: block={row['block']} sink={row['sink']} rep={row['replication']}", flush=True)
    if args.dry_run:
        return

    root = Path(os.getenv("PHASE3A_RESULT_ROOT", "/home/ghost/tdps_phase3a_results"))
    runs = root / "runs"
    failed = root / "failed_runs"
    root.mkdir(parents=True, exist_ok=True)
    runs.mkdir(exist_ok=True)
    failed.mkdir(exist_ok=True)
    manifest = root / "manifest.csv"
    if manifest.exists() and not args.resume:
        raise SystemExit(f"{manifest} exists; use --resume or choose a new PHASE3A_RESULT_ROOT")
    if not manifest.exists():
        with manifest.open("x", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=["sequence", "block", "replication", "sink"])
            writer.writeheader()
            writer.writerows(rows)
        (root / "campaign.env").write_text(
            f"PHASE3A_SEED={args.seed}\nPHASE3A_REPLICATIONS={args.replications}\nCREATED_AT={datetime.now(timezone.utc).isoformat()}\n"
        )
    else:
        with manifest.open(newline="") as stream:
            existing = list(csv.DictReader(stream))
        normalized = [{key: str(value) for key, value in row.items()} for row in rows]
        if existing != normalized:
            raise SystemExit("existing manifest differs from the requested seed/replications")

    for row in rows:
        target = runs / run_id(row)
        if (target / "COMPLETED").exists():
            print(f"skip completed: {target.name}", flush=True)
            continue
        if target.exists():
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            shutil.move(str(target), str(failed / f"{target.name}__{stamp}"))
        subprocess.run(
            [str(OBSERVATION), str(row["sink"]), str(row["replication"]), str(row["sequence"])],
            check=True,
        )


if __name__ == "__main__":
    main()
