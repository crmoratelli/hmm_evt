#!/usr/bin/env python3
from __future__ import annotations
import argparse, math
from pathlib import Path
import pandas as pd

def markdown_table(df: pd.DataFrame) -> str:
    values = [[str(x) for x in df.columns]] + [[str(x) for x in row] for row in df.itertuples(index=False, name=None)]
    widths = [max(len(row[i]) for row in values) for i in range(len(values[0]))]
    line = lambda row: "| " + " | ".join(value.ljust(widths[i]) for i, value in enumerate(row)) + " |"
    return "\n".join([line(values[0]), "| " + " | ".join("-" * w for w in widths) + " |", *[line(row) for row in values[1:]]])

def meta(path: Path) -> dict[str, str]:
    d = {}
    for line in path.read_text().splitlines():
        if "=" in line: k, v = line.split("=", 1); d[k] = v
    return d

def main() -> None:
    p = argparse.ArgumentParser(); p.add_argument("--root", type=Path, required=True); a = p.parse_args()
    rows = []
    for run in sorted((a.root / "runs").iterdir()):
        if not (run / "COMPLETED").exists(): continue
        m = meta(run / "metadata.env"); df = pd.read_csv(run / "samples.csv"); j = int(m["SHOCK_JOB"])
        pre = df.iloc[max(0, j - 80):j]
        c = float(pre.compute_ns.median()); wake = float(pre.wakeup_delay_ns.median()); period = int(m["PERIOD_NS"])
        slack = period - c; block = float(df.loc[j, "block_actual_ns"]); predicted = 0 if int(m["SHOCK_REQUESTED_NS"]) == 0 else math.ceil(block / slack)
        tolerance = max(50000.0, float(pre.wakeup_delay_ns.quantile(.999)) - wake)
        post = df.iloc[j:]
        affected = (post.response_ns > c + wake + tolerance)
        observed = 0
        for flag in affected:
            if not flag: break
            observed += 1
        rows.append(dict(run=run.name, level=m["EXECUTION_LEVEL"], replication=int(m["REPLICATION"]), requested_block_ns=int(m["SHOCK_REQUESTED_NS"]), actual_block_ns=block, measured_c_ns=c, measured_slack_ns=slack, predicted_recovery_jobs=predicted, observed_recovery_jobs=observed, recovery_error_jobs=observed-predicted, deadline_misses=int(df.miss.sum()), baseline_wakeup_ns=wake, tolerance_ns=tolerance))
    out = pd.DataFrame(rows); out.to_csv(a.root / "run_summary.csv", index=False)
    cells = out.groupby(["level", "requested_block_ns"], as_index=False).agg(runs=("run", "size"), measured_c_ns=("measured_c_ns", "median"), measured_slack_ns=("measured_slack_ns", "median"), predicted_recovery_jobs=("predicted_recovery_jobs", "median"), observed_recovery_jobs=("observed_recovery_jobs", "median"), mean_abs_error_jobs=("recovery_error_jobs", lambda x: x.abs().mean()), deadline_misses=("deadline_misses", "sum"))
    cells.to_csv(a.root / "cell_summary.csv", index=False)
    if (out.measured_slack_ns <= 0).any(): raise SystemExit("invalid cell: measured C >= T")
    report = ["# TDPS Phase 4 - controlled recovery", "", f"Valid runs: {len(out)}", "", "The confirmatory quantity is recovery_error_jobs = observed - ceil(actual_block / measured_slack).", "", markdown_table(cells), ""]
    (a.root / "REPORT.md").write_text("\n".join(report))
    print(f"PHASE4_ANALYSIS_COMPLETE={a.root} runs={len(out)} cells={len(cells)}")

if __name__ == "__main__": main()
