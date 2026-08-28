#!/usr/bin/env python3
"""Compara IID, AR(1) e HMMs gaussianos para interference/interf_io.

Cada CSV é uma sequência independente. Todos os ajustes usam os primeiros
``--train-fraction`` pontos; a escolha do modelo usa somente o trecho final.
As emissões são gaussianas em log(response_ns). ``miss`` não é entrada do HMM.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import os
from pathlib import Path
import re
import sys

# Um processo por run; evita multiplicar threads BLAS dentro de cada processo.
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

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


def iid_fit_score(train: np.ndarray, test: np.ndarray) -> tuple[float, float, float]:
    mean, sd = float(np.mean(train)), float(np.std(train, ddof=1))
    sd = max(sd, 1e-9)
    return float(norm.logpdf(test, mean, sd).sum()), mean, sd


def ar1_fit_score(train: np.ndarray, test: np.ndarray) -> tuple[float, float, float, float]:
    # y_t = intercept + phi*y_(t-1) + epsilon; avaliação condicional no teste.
    design = np.column_stack([np.ones(len(train) - 1), train[:-1]])
    intercept, phi = np.linalg.lstsq(design, train[1:], rcond=None)[0]
    residual = train[1:] - (intercept + phi * train[:-1])
    sd = max(float(np.std(residual, ddof=2)), 1e-9)
    previous = np.r_[train[-1], test[:-1]]
    ll = norm.logpdf(test, intercept + phi * previous, sd).sum()
    return float(ll), float(intercept), float(phi), sd


def best_hmm(train: np.ndarray, test: np.ndarray, states: int, seeds: int) -> tuple[GaussianHMM, float, float]:
    """Seleciona a melhor inicialização apenas pela verossimilhança de treino."""
    best_model, best_train_score = None, -np.inf
    values = train.reshape(-1, 1)
    for seed in range(seeds):
        model = GaussianHMM(n_components=states, covariance_type="diag", n_iter=250,
                            tol=1e-4, min_covar=1e-6, random_state=seed)
        model.fit(values)
        score = model.score(values)
        if score > best_train_score:
            best_model, best_train_score = model, score
    assert best_model is not None
    return best_model, float(best_train_score), float(best_model.score(test.reshape(-1, 1)))


def hmm_parameter_count(states: int) -> int:
    # start probabilities + transições + uma média e variância por estado.
    return (states - 1) + states * (states - 1) + 2 * states


def fit_one_run(item: dict, train_fraction: float, states_to_try: list[int], seeds: int) -> tuple[list[dict], list[dict]]:
    """Unidade de paralelismo: um run inteiro, sem misturar sequências."""
    data = pd.read_csv(item["derived_file"])
    response = data["response_ns"].to_numpy(float)
    keep = np.isfinite(response) & (response > 0)
    y = np.log(response[keep])
    misses = data.loc[keep, "miss_expected"].to_numpy(int)
    split = int(len(y) * train_fraction)
    train, test, test_miss = y[:split], y[split:], misses[split:]
    common = {"condition": item["condition"], "environment": item["environment"], "run": item["run"],
              "n_train": len(train), "n_test": len(test)}
    metrics, state_rows = [], []
    iid_ll, iid_mean, iid_sd = iid_fit_score(train, test)
    metrics.append({**common, "model": "iid_gaussian", "states": 1, "test_loglik": iid_ll,
                    "test_loglik_per_obs": iid_ll / len(test), "train_bic": np.nan,
                    "parameters": f"mean={iid_mean:.6f};sd={iid_sd:.6f}"})
    ar_ll, intercept, phi, ar_sd = ar1_fit_score(train, test)
    metrics.append({**common, "model": "ar1_gaussian", "states": 1, "test_loglik": ar_ll,
                    "test_loglik_per_obs": ar_ll / len(test), "train_bic": np.nan,
                    "parameters": f"intercept={intercept:.6f};phi={phi:.6f};sd={ar_sd:.6f}"})
    for states in states_to_try:
        model, train_ll, test_ll = best_hmm(train, test, states, seeds)
        bic = -2 * train_ll + hmm_parameter_count(states) * np.log(len(train))
        means = model.means_.ravel(); order = np.argsort(means)
        labels = model.predict(test.reshape(-1, 1))
        remap = np.empty(states, dtype=int); remap[order] = np.arange(states)
        labels = remap[labels]
        metrics.append({**common, "model": "gaussian_hmm", "states": states, "test_loglik": test_ll,
                        "test_loglik_per_obs": test_ll / len(test), "train_bic": bic,
                        "parameters": ";".join(f"state_{i}_mean_log_ns={means[s]:.6f}" for i, s in enumerate(order))})
        for state in range(states):
            mask = labels == state
            state_rows.append({**common, "states": states, "state_by_mean": state,
                               "test_observations": int(mask.sum()), "occupancy": float(mask.mean()),
                               "miss_rate": float(test_miss[mask].mean()) if mask.any() else np.nan,
                               "mean_response_ns": float(np.exp(test[mask]).mean()) if mask.any() else np.nan})
    return metrics, state_rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", default="results")
    parser.add_argument("--output", default="results/hmm_interf_io")
    parser.add_argument("--train-fraction", type=float, default=.70)
    parser.add_argument("--states", type=int, nargs="+", default=[2, 3, 4, 5])
    parser.add_argument("--seeds", type=int, default=5, help="reinicializações de cada HMM")
    parser.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 1) - 1),
                        help="runs processados simultaneamente; por padrão, deixa um núcleo livre")
    args = parser.parse_args()
    if not .5 <= args.train_fraction < 1:
        raise ValueError("--train-fraction deve estar em [0.5, 1)")

    results, output = root_path(args.results), root_path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    index = pd.read_csv(results / "derived/index.csv")
    index["scenario"] = index["source_file"].map(scenario_from_source)
    selected = index.loc[(index["condition"] == "interference") & (index["scenario"] == "interf_io")].copy()
    if selected.empty:
        raise ValueError("Nenhum run interference/interf_io encontrado em results/derived/index.csv")

    if args.jobs < 1:
        raise ValueError("--jobs deve ser pelo menos 1")
    work = selected.to_dict("records")
    metrics, state_rows = [], []
    print(f"Ajustando {len(work)} runs com {args.jobs} processo(s)...", flush=True)
    with ProcessPoolExecutor(max_workers=args.jobs) as executor:
        futures = [executor.submit(fit_one_run, item, args.train_fraction, args.states, args.seeds) for item in work]
        for completed, future in enumerate(as_completed(futures), start=1):
            run_metrics, run_states = future.result()
            metrics.extend(run_metrics); state_rows.extend(run_states)
            print(f"Concluído {completed}/{len(work)}: {run_metrics[0]['environment']} / {run_metrics[0]['run']}", flush=True)

    per_run = pd.DataFrame(metrics)
    per_run.to_csv(output / "model_comparison_by_run.csv", index=False)
    state_table = pd.DataFrame(state_rows)
    state_table.to_csv(output / "state_miss_characterization.csv", index=False)
    aggregate = per_run.groupby(["environment", "model", "states"], as_index=False).agg(
        runs=("run", "nunique"), total_test_loglik=("test_loglik", "sum"),
        mean_test_loglik_per_obs=("test_loglik_per_obs", "mean"), median_test_loglik_per_obs=("test_loglik_per_obs", "median"),
    ).sort_values(["environment", "mean_test_loglik_per_obs"], ascending=[True, False])
    aggregate.to_csv(output / "model_comparison_aggregate.csv", index=False)
    print(f"Comparação concluída para {len(selected)} runs em {output}")


if __name__ == "__main__":
    main()
