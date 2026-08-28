#!/usr/bin/env python3
"""Compara IID, AR(1), GMM e HMM em interference/interf_io.

Para cada run, os modelos sao avaliados em hold-out temporal sobre
log(response_ns), em duas visoes:

* raw: serie completa;
* stable: remove deadline misses, choques que iniciam degradacao e uma guarda.

Os HMMs tambem pontuam copias embaralhadas do teste. A diferenca entre a
verossimilhanca da sequencia original e a embaralhada mede quanto o modelo se
beneficia da ordem temporal, alem da distribuicao marginal.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import os
from pathlib import Path
import re
import sys
import warnings

# Um processo por run; evita oversubscription das bibliotecas numericas.
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

import numpy as np
import pandas as pd
from hmmlearn.hmm import GaussianHMM
from scipy.stats import norm
from sklearn.mixture import GaussianMixture

sys.path.insert(0, str(Path(__file__).parent))
from common import root_path


def scenario_from_source(source: str) -> str:
    stem = Path(source).stem.lower()
    stem = re.sub(r"(?:[_-]?run[_-]?\d+)$", "", stem)
    return re.sub(r"^(?:host|docker|container)(?:[_-]cpu\d+)?[_-]?", "", stem)


def robust_shock_mask(response: np.ndarray, miss: np.ndarray, absolute_ns: float,
                      mad_multiplier: float, guard_before: int,
                      guard_after: int) -> tuple[np.ndarray, float, float]:
    """Retorna pontos estaveis e os parametros do detector de choques."""
    delta = np.diff(response, prepend=response[0])
    finite_delta = delta[np.isfinite(delta)]
    center = float(np.median(finite_delta))
    mad = float(np.median(np.abs(finite_delta - center)))
    threshold = max(float(absolute_ns), float(mad_multiplier * mad))

    # Choques relevantes: salto robusto que desemboca em deadline miss.
    shock = (delta >= threshold) & miss
    remove = miss.copy() | shock
    event_indices = np.flatnonzero(remove)
    for idx in event_indices:
        lo = max(0, idx - guard_before)
        hi = min(len(remove), idx + guard_after + 1)
        remove[lo:hi] = True
    return ~remove, mad, threshold


def contiguous_lengths(indices: np.ndarray) -> list[int]:
    if len(indices) == 0:
        return []
    cuts = np.flatnonzero(np.diff(indices) != 1) + 1
    return [len(x) for x in np.split(indices, cuts) if len(x)]


def iid_score(train: np.ndarray, test: np.ndarray) -> tuple[float, int, str]:
    mean = float(np.mean(train)); sd = max(float(np.std(train, ddof=1)), 1e-9)
    ll = float(norm.logpdf(test, mean, sd).sum())
    return ll, 2, f"mean={mean:.8g};sd={sd:.8g}"


def ar1_score(train: np.ndarray, train_idx: np.ndarray, test: np.ndarray,
              test_idx: np.ndarray) -> tuple[float, int, str, int]:
    train_adj = np.flatnonzero(np.diff(train_idx) == 1)
    test_adj = np.flatnonzero(np.diff(test_idx) == 1)
    if len(train_adj) < 3 or len(test_adj) < 1:
        return np.nan, 3, "insufficient_adjacent_pairs", len(test_adj)
    x = train[train_adj]; target = train[train_adj + 1]
    design = np.column_stack([np.ones(len(x)), x])
    intercept, phi = np.linalg.lstsq(design, target, rcond=None)[0]
    residual = target - (intercept + phi * x)
    sd = max(float(np.std(residual, ddof=2)), 1e-9)
    predicted = intercept + phi * test[test_adj]
    ll = float(norm.logpdf(test[test_adj + 1], predicted, sd).sum())
    params = f"intercept={intercept:.8g};phi={phi:.8g};sd={sd:.8g}"
    return ll, 3, params, len(test_adj)


def fit_gmm(train: np.ndarray, test: np.ndarray, components: int,
            seeds: int) -> tuple[float, float, int, str]:
    model = GaussianMixture(n_components=components, covariance_type="diag",
                            n_init=seeds, max_iter=300, tol=1e-4,
                            reg_covar=1e-6, random_state=0)
    model.fit(train.reshape(-1, 1))
    train_ll = float(model.score(train.reshape(-1, 1)) * len(train))
    test_ll = float(model.score(test.reshape(-1, 1)) * len(test))
    order = np.argsort(model.means_.ravel())
    means = model.means_.ravel()[order]
    weights = model.weights_.ravel()[order]
    params = ";".join(
        f"component_{i}_mean={means[i]:.8g},weight={weights[i]:.8g}"
        for i in range(components)
    )
    return train_ll, test_ll, 3 * components - 1, params


def fit_hmm(train: np.ndarray, train_lengths: list[int], test: np.ndarray,
            test_lengths: list[int], states: int, seeds: int,
            shuffle_repeats: int, random_seed: int
            ) -> tuple[float, float, int, str, float, float]:
    values = train.reshape(-1, 1)
    best_model = None; best_ll = -np.inf
    failures: list[str] = []
    for seed in range(seeds):
        model = GaussianHMM(n_components=states, covariance_type="diag",
                            n_iter=300, tol=1e-4, min_covar=1e-6,
                            random_state=seed)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                model.fit(values, lengths=train_lengths)
            ll = float(model.score(values, lengths=train_lengths))
            if np.isfinite(ll) and ll > best_ll:
                best_model, best_ll = model, ll
        except (ValueError, FloatingPointError, np.linalg.LinAlgError) as exc:
            failures.append(f"seed={seed}:{type(exc).__name__}")
    if best_model is None:
        detail = ", ".join(failures) if failures else "scores nao finitos"
        raise RuntimeError(f"HMM({states}) falhou em todas as seeds: {detail}")
    test_values = test.reshape(-1, 1)
    test_ll = float(best_model.score(test_values, lengths=test_lengths))

    rng = np.random.default_rng(random_seed)
    shuffled_ll = []
    for _ in range(shuffle_repeats):
        shuffled = rng.permutation(test).reshape(-1, 1)
        shuffled_ll.append(float(best_model.score(shuffled, lengths=test_lengths)))
    shuffle_mean = float(np.mean(shuffled_ll))
    shuffle_sd = float(np.std(shuffled_ll, ddof=1)) if len(shuffled_ll) > 1 else 0.0

    means = best_model.means_.ravel(); order = np.argsort(means)
    params = ";".join(
        f"state_{i}_mean={means[s]:.8g}" for i, s in enumerate(order)
    )
    parameter_count = states * states + 2 * states - 1
    return best_ll, test_ll, parameter_count, params, shuffle_mean, shuffle_sd


def analyze_view(item: dict, response: np.ndarray, miss: np.ndarray,
                 keep: np.ndarray, view: str, args: dict) -> list[dict]:
    n_total = len(response)
    split_position = int(n_total * args["train_fraction"])
    original_idx = np.arange(n_total)
    train_idx = original_idx[keep & (original_idx < split_position)]
    test_idx = original_idx[keep & (original_idx >= split_position)]
    if len(train_idx) < args["min_observations"] or len(test_idx) < args["min_observations"]:
        return [{"condition": item["condition"], "environment": item["environment"],
                 "run": item["run"], "view": view, "model": "skipped", "order": 0,
                 "n_total": n_total, "n_kept": int(keep.sum()),
                 "n_train": len(train_idx), "n_test": len(test_idx),
                 "reason": "insufficient_observations"}]

    # Padronizacao calculada somente no treino; melhora a estabilidade numerica.
    log_response = np.log(response)
    center = float(np.mean(log_response[train_idx]))
    scale = max(float(np.std(log_response[train_idx], ddof=1)), 1e-9)
    y = (log_response - center) / scale
    train, test = y[train_idx], y[test_idx]
    train_lengths = contiguous_lengths(train_idx)
    test_lengths = contiguous_lengths(test_idx)
    common = {
        "condition": item["condition"], "environment": item["environment"],
        "run": item["run"], "view": view, "n_total": n_total,
        "n_kept": int(keep.sum()), "kept_fraction": float(keep.mean()),
        "n_train": len(train), "n_test": len(test),
        "train_segments": len(train_lengths), "test_segments": len(test_lengths),
        "standardization_center_log_ns": center,
        "standardization_scale_log_ns": scale, "reason": "",
    }
    rows: list[dict] = []

    iid_ll, iid_k, iid_params = iid_score(train, test)
    iid_train_ll, _, _ = iid_score(train, train)
    rows.append({**common, "model": "iid_gaussian", "order": 1,
                 "train_loglik": iid_train_ll, "test_loglik": iid_ll,
                 "scored_test_observations": len(test), "parameters_count": iid_k,
                 "train_bic": -2 * iid_train_ll + iid_k * np.log(len(train)),
                 "test_loglik_per_obs": iid_ll / len(test),
                 "shuffled_test_loglik_mean": iid_ll,
                 "shuffled_test_loglik_sd": 0.0, "temporal_gain_per_obs": 0.0,
                 "parameters": iid_params})

    ar_ll, ar_k, ar_params, ar_n = ar1_score(train, train_idx, test, test_idx)
    rows.append({**common, "model": "ar1_gaussian", "order": 1,
                 "train_loglik": np.nan, "test_loglik": ar_ll,
                 "scored_test_observations": ar_n, "parameters_count": ar_k,
                 "train_bic": np.nan,
                 "test_loglik_per_obs": ar_ll / ar_n if ar_n else np.nan,
                 "shuffled_test_loglik_mean": np.nan,
                 "shuffled_test_loglik_sd": np.nan,
                 "temporal_gain_per_obs": np.nan, "parameters": ar_params})

    for components in args["orders"]:
        train_ll, test_ll, k, params = fit_gmm(
            train, test, components, args["seeds"])
        rows.append({**common, "model": "gaussian_gmm", "order": components,
                     "train_loglik": train_ll, "test_loglik": test_ll,
                     "scored_test_observations": len(test), "parameters_count": k,
                     "train_bic": -2 * train_ll + k * np.log(len(train)),
                     "test_loglik_per_obs": test_ll / len(test),
                     "shuffled_test_loglik_mean": test_ll,
                     "shuffled_test_loglik_sd": 0.0,
                     "temporal_gain_per_obs": 0.0, "parameters": params})

        seed_material = sum(ord(c) for c in f'{item["run"]}:{view}:{components}')
        train_ll, test_ll, k, params, shuffled_mean, shuffled_sd = fit_hmm(
            train, train_lengths, test, test_lengths, components, args["seeds"],
            args["shuffle_repeats"], args["random_seed"] + seed_material)
        rows.append({**common, "model": "gaussian_hmm", "order": components,
                     "train_loglik": train_ll, "test_loglik": test_ll,
                     "scored_test_observations": len(test), "parameters_count": k,
                     "train_bic": -2 * train_ll + k * np.log(len(train)),
                     "test_loglik_per_obs": test_ll / len(test),
                     "shuffled_test_loglik_mean": shuffled_mean,
                     "shuffled_test_loglik_sd": shuffled_sd,
                     "temporal_gain_per_obs": (test_ll - shuffled_mean) / len(test),
                     "parameters": params})
    return rows


def fit_one_run(item: dict, args: dict) -> tuple[list[dict], dict]:
    data = pd.read_csv(item["derived_file"])
    response = data["response_ns"].to_numpy(float)
    miss_column = "miss_expected" if "miss_expected" in data else "miss"
    miss = data[miss_column].to_numpy(int).astype(bool)
    finite = np.isfinite(response) & (response > 0)
    response = response[finite]; miss = miss[finite]

    stable, mad, threshold = robust_shock_mask(
        response, miss, args["min_shock_us"] * 1_000.0,
        args["shock_mad_multiplier"], args["guard_before"], args["guard_after"])
    rows = analyze_view(item, response, miss, np.ones(len(response), dtype=bool),
                        "raw", args)
    rows += analyze_view(item, response, miss, stable, "stable", args)
    audit = {"condition": item["condition"], "environment": item["environment"],
             "run": item["run"], "observations": len(response),
             "misses": int(miss.sum()), "stable_observations": int(stable.sum()),
             "stable_fraction": float(stable.mean()), "delta_mad_ns": mad,
             "shock_threshold_ns": threshold,
             "guard_before": args["guard_before"], "guard_after": args["guard_after"]}
    return rows, audit


def aggregate_results(per_run: pd.DataFrame) -> pd.DataFrame:
    valid = per_run.loc[per_run["model"] != "skipped"].copy()
    return (valid.groupby(["view", "environment", "model", "order"], as_index=False)
            .agg(runs=("run", "nunique"),
                 total_test_observations=("scored_test_observations", "sum"),
                 mean_test_loglik_per_obs=("test_loglik_per_obs", "mean"),
                 median_test_loglik_per_obs=("test_loglik_per_obs", "median"),
                 median_train_bic=("train_bic", "median"),
                 mean_temporal_gain_per_obs=("temporal_gain_per_obs", "mean"),
                 median_temporal_gain_per_obs=("temporal_gain_per_obs", "median"))
            .sort_values(["view", "environment", "mean_test_loglik_per_obs"],
                         ascending=[True, True, False]))


def write_report(per_run: pd.DataFrame, aggregate: pd.DataFrame, audit: pd.DataFrame,
                 output: Path) -> None:
    valid = per_run.loc[per_run["model"] != "skipped"].copy()
    winners = (valid.sort_values("test_loglik_per_obs", ascending=False)
               .groupby(["view", "environment", "run"], as_index=False).first())
    win_counts = (winners.groupby(["view", "environment", "model", "order"], as_index=False)
                  .size().rename(columns={"size": "run_wins"}))
    win_counts.to_csv(output / "model_wins_by_run.csv", index=False)

    lines = ["# Comparacao GMM versus HMM", "",
             "Modelos ajustados em log(response_ns), com normalizacao definida somente no treino.",
             "`raw` usa a serie completa; `stable` remove misses e guardas em torno da degradacao.", "",
             "## Retencao dos trechos estaveis", "",
             audit.groupby("environment")["stable_fraction"].agg(["median", "min", "max"]).to_markdown(),
             "", "## Vencedores por run (hold-out temporal)", "", win_counts.to_markdown(index=False),
             "", "## Resultado agregado", "", aggregate.to_markdown(index=False), "",
             "## Leitura", "",
             "Para HMM, `temporal_gain_per_obs > 0` indica vantagem da ordem original sobre testes embaralhados.",
             "A evidencia mais forte de regimes exige simultaneamente: HMM superior a GMM no hold-out,",
             "ganho temporal positivo e repeticao do resultado entre runs, sobretudo na visao `stable`.", ""]
    (output / "gmm_hmm_report.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--results", default="results")
    ap.add_argument("--output", default="results/gmm_hmm_comparison")
    ap.add_argument("--train-fraction", type=float, default=.70)
    ap.add_argument("--orders", type=int, nargs="+", default=[2, 3, 4, 5])
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--shuffle-repeats", type=int, default=10)
    ap.add_argument("--random-seed", type=int, default=20260828)
    ap.add_argument("--min-shock-us", type=float, default=1000.0)
    ap.add_argument("--shock-mad-multiplier", type=float, default=20.0)
    ap.add_argument("--guard-before", type=int, default=1)
    ap.add_argument("--guard-after", type=int, default=5)
    ap.add_argument("--min-observations", type=int, default=500)
    ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 1) - 1))
    args = ap.parse_args()
    if not .5 <= args.train_fraction < 1:
        raise ValueError("--train-fraction deve estar em [0.5, 1)")
    if any(x < 2 for x in args.orders):
        raise ValueError("--orders aceita somente valores >= 2")
    if args.seeds < 1 or args.shuffle_repeats < 1 or args.jobs < 1:
        raise ValueError("--seeds, --shuffle-repeats e --jobs devem ser >= 1")

    results, output = root_path(args.results), root_path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    index = pd.read_csv(results / "derived/index.csv")
    index["scenario"] = index["source_file"].map(scenario_from_source)
    selected = index.loc[(index["condition"] == "interference") &
                         (index["scenario"] == "interf_io")].copy()
    if selected.empty:
        raise ValueError("Nenhum run interference/interf_io encontrado")

    config = vars(args).copy()
    work = selected.to_dict("records")
    all_rows: list[dict] = []; audits: list[dict] = []
    print(f"Comparando modelos em {len(work)} runs com {args.jobs} processo(s)...", flush=True)
    with ProcessPoolExecutor(max_workers=args.jobs) as executor:
        futures = [executor.submit(fit_one_run, item, config) for item in work]
        for completed, future in enumerate(as_completed(futures), 1):
            rows, audit = future.result()
            all_rows.extend(rows); audits.append(audit)
            print(f"Concluido {completed}/{len(work)}: {audit['environment']} / {audit['run']}", flush=True)

    per_run = pd.DataFrame(all_rows)
    audit = pd.DataFrame(audits)
    aggregate = aggregate_results(per_run)
    per_run.to_csv(output / "model_comparison_by_run.csv", index=False)
    aggregate.to_csv(output / "model_comparison_aggregate.csv", index=False)
    audit.to_csv(output / "stable_mask_audit.csv", index=False)
    write_report(per_run, aggregate, audit, output)
    print(f"Resultados gravados em {output}")


if __name__ == "__main__":
    main()
