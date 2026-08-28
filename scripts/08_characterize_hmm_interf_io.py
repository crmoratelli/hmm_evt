#!/usr/bin/env python3
"""Caracteriza HMMs de 4 estados para interference/interf_io após seleção.

Refaz o ajuste em cada run completo exclusivamente para descrição: transições,
tempos de permanência, ocupação e P(miss=1 | estado). Não use estes ajustes
para escolher o modelo; essa decisão já foi feita na etapa 07 com hold-out.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import os
from pathlib import Path
import re
import sys

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from hmmlearn.hmm import GaussianHMM
from scipy.stats import norm

sys.path.insert(0, str(Path(__file__).parent))
from common import root_path


def scenario_from_source(source: str) -> str:
    stem = Path(source).stem.lower()
    stem = re.sub(r"(?:[_-]?run[_-]?\d+)$", "", stem)
    return re.sub(r"^(?:host|docker|container)(?:[_-]cpu\d+)?[_-]?", "", stem)


def wilson(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total == 0: return np.nan, np.nan
    p = successes / total; denom = 1 + z*z/total
    centre = (p + z*z/(2*total)) / denom
    radius = z * np.sqrt(p*(1-p)/total + z*z/(4*total*total)) / denom
    return centre - radius, centre + radius


def fit_run(item: dict, states: int, seeds: int) -> tuple[list[dict], list[dict], list[dict]]:
    data = pd.read_csv(item["derived_file"])
    valid = data["response_ns"].notna() & (data["response_ns"] > 0)
    response = data.loc[valid, "response_ns"].to_numpy(float)
    values = np.log(response).reshape(-1, 1)
    misses = data.loc[valid, "miss_expected"].to_numpy(int)
    inter = data.loc[valid, "inter_release_ns"].to_numpy(float)
    best, best_score = None, -np.inf
    for seed in range(seeds):
        model = GaussianHMM(n_components=states, covariance_type="diag", n_iter=300,
                            tol=1e-4, min_covar=1e-6, random_state=seed).fit(values)
        score = model.score(values)
        if score > best_score: best, best_score = model, score
    assert best is not None
    means = best.means_.ravel(); order = np.argsort(means)
    remap = np.empty(states, dtype=int); remap[order] = np.arange(states)
    labels = remap[best.predict(values)]
    base = {"condition": item["condition"], "environment": item["environment"], "run": item["run"], "states": states,
            "n": len(labels), "median_inter_release_ns": float(np.nanmedian(inter))}
    summaries, transitions, dwells = [], [], []
    for state in range(states):
        mask = labels == state; n = int(mask.sum()); n_miss = int(misses[mask].sum())
        low, high = wilson(n_miss, n)
        summaries.append({**base, "state_by_mean": state, "occupancy": n / len(labels), "observations": n,
                          "misses": n_miss, "miss_rate": n_miss / n if n else np.nan,
                          "miss_rate_ci_low": low, "miss_rate_ci_high": high,
                          "mean_response_ns": float(response[mask].mean()) if n else np.nan,
                          "median_response_ns": float(np.median(response[mask])) if n else np.nan,
                          "p95_response_ns": float(np.quantile(response[mask], .95)) if n else np.nan,
                          "emission_mean_log_ns": float(means[order[state]]),
                          "emission_sd_log_ns": float(np.sqrt(best.covars_[order[state], 0, 0]))})
    counts = np.zeros((states, states), dtype=int)
    for left, right in zip(labels[:-1], labels[1:]): counts[left, right] += 1
    for left in range(states):
        total = counts[left].sum()
        for right in range(states):
            transitions.append({**base, "from_state": left, "to_state": right, "count": int(counts[left, right]),
                                "observed_probability": counts[left, right] / total if total else np.nan,
                                "model_probability": float(best.transmat_[order[left], order[right]])})
    start = 0
    for index in range(1, len(labels) + 1):
        if index == len(labels) or labels[index] != labels[start]:
            length = index - start; state = int(labels[start])
            dwells.append({**base, "state_by_mean": state, "dwell_activations": length,
                           "dwell_us": length * base["median_inter_release_ns"] / 1_000})
            start = index
    return summaries, transitions, dwells


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", default="results")
    parser.add_argument("--output", default="results/hmm_interf_io_characterization")
    parser.add_argument("--states", type=int, default=4)
    parser.add_argument("--seeds", type=int, default=10)
    parser.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 1) - 1))
    args = parser.parse_args()
    results, output = root_path(args.results), root_path(args.output); output.mkdir(parents=True, exist_ok=True)
    index = pd.read_csv(results / "derived/index.csv")
    index["scenario"] = index.source_file.map(scenario_from_source)
    chosen = index.loc[(index.condition == "interference") & (index.scenario == "interf_io")].to_dict("records")
    if not chosen: raise ValueError("Nenhum run interference/interf_io encontrado")
    summaries, transitions, dwells = [], [], []
    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        futures = [pool.submit(fit_run, item, args.states, args.seeds) for item in chosen]
        for i, future in enumerate(as_completed(futures), 1):
            a, b, c = future.result(); summaries.extend(a); transitions.extend(b); dwells.extend(c)
            print(f"Concluído {i}/{len(chosen)}: {a[0]['environment']} / {a[0]['run']}", flush=True)
    pd.DataFrame(summaries).to_csv(output / "state_summary_by_run.csv", index=False)
    pd.DataFrame(transitions).to_csv(output / "transitions_by_run.csv", index=False)
    dwell_frame = pd.DataFrame(dwells); dwell_frame.to_csv(output / "dwell_episodes.csv", index=False)
    dwell_summary = dwell_frame.groupby(["environment", "state_by_mean"], as_index=False).agg(
        episodes=("dwell_activations", "size"), median_dwell_activations=("dwell_activations", "median"),
        p95_dwell_activations=("dwell_activations", lambda x: x.quantile(.95)), median_dwell_us=("dwell_us", "median"))
    dwell_summary.to_csv(output / "dwell_summary.csv", index=False)
    print(f"Caracterização criada em {output}")


if __name__ == "__main__": main()
