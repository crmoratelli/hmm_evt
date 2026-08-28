#!/usr/bin/env python3
"""Resumo por run e figuras distribucionais/temporais descritivas."""
from __future__ import annotations
import argparse
from pathlib import Path
import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
sys.path.insert(0, str(Path(__file__).parent))
from common import derived_files, root_path


def condition_label(meta: dict) -> str:
    return f"{meta['condition']} / {meta['environment']}"


def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("--input", default="results/derived"); ap.add_argument("--output", default="results/descriptive"); ap.add_argument("--max-series-points", type=int, default=5000)
    args = ap.parse_args(); out = root_path(args.output); figures = out / "figures"; figures.mkdir(parents=True, exist_ok=True)
    summaries, combined = [], []
    for path, meta in derived_files(args.input):
        df = pd.read_csv(path); response = df["response_ns"].dropna()
        if response.empty: continue
        q = response.quantile([.5, .9, .95, .99]).to_dict()
        summaries.append({**meta, "file": str(path), "n": len(response), "mean_ns": response.mean(), "std_ns": response.std(), "min_ns": response.min(), "median_ns": q[.5], "p90_ns": q[.9], "p95_ns": q[.95], "p99_ns": q[.99], "max_ns": response.max(), "miss_rate": df.get("miss_expected", pd.Series(dtype=float)).mean(), "inter_release_median_ns": df["inter_release_ns"].median()})
        combined.append(pd.DataFrame({"response_ns": response, "group": condition_label(meta)}))
        n = min(len(df), args.max_series_points)
        fig, ax = plt.subplots(figsize=(10, 3.5)); ax.plot(np.arange(n), df["response_us"].iloc[:n], lw=.65)
        ax.set(title=f"Série temporal — {condition_label(meta)} — {meta['run']}", xlabel="ativação (ordenada por release)", ylabel="resposta (µs)"); fig.tight_layout()
        fig.savefig(figures / f"series_{meta['condition']}_{meta['environment']}_{meta['run']}.png", dpi=160); plt.close(fig)
    summary = pd.DataFrame(summaries); summary.to_csv(out / "summary_by_run.csv", index=False)
    if combined:
        all_data = pd.concat(combined, ignore_index=True)
        fig, ax = plt.subplots(figsize=(9, 5))
        for label, group in all_data.groupby("group"):
            ax.hist(group.response_ns / 1_000, bins=80, density=True, histtype="step", lw=1.3, label=label)
        ax.set(xlabel="resposta (µs)", ylabel="densidade", title="Distribuição de latências por condição"); ax.legend(fontsize=8); fig.tight_layout()
        fig.savefig(figures / "response_distribution.png", dpi=160); plt.close(fig)
    print(f"Resumo de {len(summary)} runs em {out}")

if __name__ == "__main__": main()
