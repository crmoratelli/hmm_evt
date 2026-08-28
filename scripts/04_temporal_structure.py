#!/usr/bin/env python3
"""ACF, sequências de extremos e teste contra embaralhamento por run."""
from __future__ import annotations
import argparse
from pathlib import Path
import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
sys.path.insert(0, str(Path(__file__).parent))
from common import derived_files, root_path


def acf(x: np.ndarray, max_lag: int) -> np.ndarray:
    x = x[np.isfinite(x)]
    if len(x) < 3: return np.array([])
    x = x - x.mean(); denom = np.dot(x, x)
    return np.array([np.dot(x[:-lag], x[lag:]) / denom for lag in range(1, min(max_lag, len(x)-1)+1)])


def run_lengths(mask: np.ndarray) -> list[int]:
    values, count, result = [], 0, []
    for value in mask:
        if value: count += 1
        elif count: result.append(count); count = 0
    if count: result.append(count)
    return result


def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("--input", default="results/derived"); ap.add_argument("--output", default="results/temporal"); ap.add_argument("--max-lag", type=int, default=100); ap.add_argument("--shuffles", type=int, default=200); ap.add_argument("--seed", type=int, default=20260827)
    args = ap.parse_args(); out = root_path(args.output); figs = out / "figures"; figs.mkdir(parents=True, exist_ok=True); rng = np.random.default_rng(args.seed)
    records, lengths = [], []
    for path, meta in derived_files(args.input):
        df = pd.read_csv(path); raw = df.response_ns.to_numpy(float); logged = np.log(raw, where=raw > 0, out=np.full_like(raw, np.nan))
        for variable, x in (("response_ns", raw), ("log_response_ns", logged)):
            observed = acf(x, args.max_lag)
            if not len(observed): continue
            shuffled_lag1 = np.array([acf(rng.permutation(x), 1)[0] for _ in range(args.shuffles)])
            ci_low, ci_high = np.quantile(shuffled_lag1, [.025, .975])
            records.append({**meta, "file": str(path), "variable": variable, "n": int(np.isfinite(x).sum()), "acf_lag1": observed[0], "shuffle_lag1_low": ci_low, "shuffle_lag1_high": ci_high, "lag1_outside_shuffle_95": bool(observed[0] < ci_low or observed[0] > ci_high)})
            fig, ax = plt.subplots(figsize=(8, 3.4)); ax.stem(np.arange(1, len(observed)+1), observed, basefmt=" "); ax.axhline(0, color="black", lw=.6); ax.axhspan(ci_low, ci_high, color="gray", alpha=.18, label="95% embaralhado (lag 1)")
            ax.set(title=f"ACF — {meta['condition']} / {meta['environment']} / {meta['run']} — {variable}", xlabel="lag", ylabel="ACF"); fig.tight_layout(); fig.savefig(figs / f"acf_{meta['condition']}_{meta['environment']}_{meta['run']}_{variable}.png", dpi=160); plt.close(fig)
        threshold = np.nanquantile(raw, .95); observed_lengths = run_lengths(raw >= threshold)
        shuffled_means = [np.mean(run_lengths(rng.permutation(raw) >= threshold) or [0]) for _ in range(args.shuffles)]
        records[-1].update({"high_threshold_ns": threshold, "high_run_count": len(observed_lengths), "high_run_max": max(observed_lengths, default=0), "high_run_mean": np.mean(observed_lengths) if observed_lengths else 0, "shuffle_high_run_mean_95": np.quantile(shuffled_means, .95)})
        lengths.extend([{**meta, "threshold_quantile": .95, "run_length": v} for v in observed_lengths])
    pd.DataFrame(records).to_csv(out / "temporal_by_run.csv", index=False)
    pd.DataFrame(lengths).to_csv(out / "high_latency_run_lengths.csv", index=False)
    print(f"Estrutura temporal calculada para {len(records)//2} runs em {out}")

if __name__ == "__main__": main()
