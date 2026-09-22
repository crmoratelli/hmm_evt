#!/usr/bin/env python3
from __future__ import annotations
import argparse
from pathlib import Path
import pandas as pd

def metadata(path: Path) -> dict[str, str]:
    result = {}
    for line in path.read_text().splitlines():
        if "=" in line:
            key, value = line.split("=", 1); result[key] = value
    return result

def main() -> None:
    p = argparse.ArgumentParser(); p.add_argument("--run-dir", type=Path, required=True); a = p.parse_args()
    m = metadata(a.run_dir / "metadata.env")
    df = pd.read_csv(a.run_dir / "samples.csv")
    required = {"job", "release_ns", "start_ns", "compute_ns", "block_actual_ns", "response_ns", "miss", "cpu", "shock_requested_ns"}
    missing = required - set(df.columns)
    if missing: raise SystemExit(f"missing columns: {sorted(missing)}")
    jobs, shock_job, requested = int(m["JOBS"]), int(m["SHOCK_JOB"]), int(m["SHOCK_REQUESTED_NS"])
    if len(df) != jobs or not df.job.equals(pd.Series(range(jobs))): raise SystemExit("job sequence invalid")
    if (df.release_ns.diff().dropna() != int(m["PERIOD_NS"])).any(): raise SystemExit("release grid invalid")
    if set(df.cpu) != {int(m["CPU_RT"])}: raise SystemExit(f"wrong CPU values: {sorted(set(df.cpu))}")
    nonzero = df.index[df.shock_requested_ns != 0].tolist()
    expected = [] if requested == 0 else [shock_job]
    if nonzero != expected: raise SystemExit(f"shock location invalid: {nonzero} != {expected}")
    if requested and int(df.loc[shock_job, "block_actual_ns"]) < requested: raise SystemExit("actual block shorter than requested")
    if (df.compute_ns <= 0).any() or (df.response_ns < df.compute_ns).any(): raise SystemExit("timing invariant failed")
    print(f"RUN_VALID={m['RUN_ID']} jobs={jobs} misses={int(df.miss.sum())}")

if __name__ == "__main__": main()
