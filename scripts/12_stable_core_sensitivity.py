#!/usr/bin/env python3
"""Teste de sensibilidade da evidencia HMM nos trechos estaveis.

Reutiliza as rotinas de ajuste de ``11_compare_gmm_hmm.py`` e repete a
comparacao sob mascaras progressivamente mais estritas. As ordens de GMM e HMM
sao escolhidas separadamente pelo menor BIC no treino; o hold-out temporal nao
participa da escolha. Limiares quantilicos tambem sao definidos somente pelo
treino, evitando vazamento de informacao.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import importlib.util
import os
from pathlib import Path
import sys

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

import numpy as np
import pandas as pd
from scipy.stats import spearmanr, wilcoxon

sys.path.insert(0, str(Path(__file__).parent))
from common import root_path


def load_step11():
    path = Path(__file__).with_name("11_compare_gmm_hmm.py")
    if not path.exists():
        raise FileNotFoundError(
            f"Dependencia ausente: {path}. Coloque os scripts 11 e 12 na mesma pasta.")
    spec = importlib.util.spec_from_file_location("step11_compare", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Nao foi possivel carregar {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


STEP11 = load_step11()


def build_masks(response: np.ndarray, miss: np.ndarray, args: dict
                ) -> tuple[list[tuple[str, np.ndarray, str, float]], float, float]:
    """Cria mascaras; cada tupla contem nome, mascara, tipo e limiar em ns."""
    base, mad, shock_threshold = STEP11.robust_shock_mask(
        response, miss, args["min_shock_us"] * 1_000.0,
        args["shock_mad_multiplier"], args["guard_before"], args["guard_after"])
    masks: list[tuple[str, np.ndarray, str, float]] = [
        ("base_stable", base, "base", np.nan)
    ]
    for cap_us in args["fixed_caps_us"]:
        cap_ns = float(cap_us) * 1_000.0
        label = f"cap_{cap_us:g}us"
        masks.append((label, base & (response <= cap_ns), "fixed_cap", cap_ns))

    split = int(len(response) * args["train_fraction"])
    train_base = response[:split][base[:split]]
    if len(train_base) == 0:
        raise ValueError("Mascara base eliminou todo o trecho de treino")
    for quantile in args["train_quantiles"]:
        cap_ns = float(np.quantile(train_base, quantile))
        label = f"train_q_{quantile:.5f}".rstrip("0").rstrip(".")
        masks.append((label, base & (response <= cap_ns), "train_quantile", cap_ns))
    return masks, mad, shock_threshold


def fit_one_run(item: dict, args: dict) -> tuple[list[dict], list[dict]]:
    data = pd.read_csv(item["derived_file"])
    response = data["response_ns"].to_numpy(float)
    miss_column = "miss_expected" if "miss_expected" in data else "miss"
    miss = data[miss_column].to_numpy(int).astype(bool)
    finite = np.isfinite(response) & (response > 0)
    response = response[finite]; miss = miss[finite]

    masks, mad, shock_threshold = build_masks(response, miss, args)
    rows: list[dict] = []; audits: list[dict] = []
    split = int(len(response) * args["train_fraction"])
    for label, keep, mask_type, cap_ns in masks:
        result = STEP11.analyze_view(item, response, miss, keep, label, args)
        rows.extend(result)
        audits.append({
            "condition": item["condition"], "environment": item["environment"],
            "run": item["run"], "sensitivity": label, "mask_type": mask_type,
            "cap_response_ns": cap_ns, "cap_response_us": cap_ns / 1_000.0,
            "observations": len(response), "kept": int(keep.sum()),
            "kept_fraction": float(keep.mean()),
            "train_kept": int(keep[:split].sum()),
            "test_kept": int(keep[split:].sum()), "misses": int(miss.sum()),
            "delta_mad_ns": mad, "shock_threshold_ns": shock_threshold,
        })
    return rows, audits


def select_by_training_bic(per_run: pd.DataFrame) -> pd.DataFrame:
    candidates = per_run.loc[
        per_run["model"].isin(["gaussian_gmm", "gaussian_hmm"])
        & np.isfinite(per_run["train_bic"])
    ].copy()
    keys = ["condition", "environment", "run", "view", "model"]
    selected = (candidates.sort_values("train_bic", kind="stable")
                .groupby(keys, as_index=False).first())
    return selected.rename(columns={"view": "sensitivity"})


def paired_summary(selected: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    index = ["condition", "environment", "run", "sensitivity"]
    wide = selected.pivot(index=index, columns="model", values=[
        "order", "train_bic", "test_loglik_per_obs", "temporal_gain_per_obs",
        "n_train", "n_test", "kept_fraction"])
    wide.columns = [f"{metric}_{model.replace('gaussian_', '')}"
                    for metric, model in wide.columns]
    wide = wide.reset_index()
    wide["run_number"] = wide["run"].str.extract(r"run(\d+)$")[0].astype(int)
    wide["hmm_minus_gmm_test_loglik_per_obs"] = (
        wide["test_loglik_per_obs_hmm"] - wide["test_loglik_per_obs_gmm"])
    wide["hmm_wins"] = wide["hmm_minus_gmm_test_loglik_per_obs"] > 0

    summaries: list[dict] = []
    for (condition, environment, sensitivity), group in wide.groupby(
            ["condition", "environment", "sensitivity"], sort=False):
        delta = group["hmm_minus_gmm_test_loglik_per_obs"].dropna().to_numpy(float)
        if len(delta) and np.any(delta != 0):
            try:
                p_value = float(wilcoxon(delta).pvalue)
            except ValueError:
                p_value = np.nan
        else:
            p_value = np.nan
        summaries.append({
            "condition": condition, "environment": environment,
            "sensitivity": sensitivity, "runs": len(group),
            "hmm_wins": int(group["hmm_wins"].sum()),
            "gmm_wins_or_ties": int((~group["hmm_wins"]).sum()),
            "mean_hmm_minus_gmm": float(np.mean(delta)),
            "median_hmm_minus_gmm": float(np.median(delta)),
            "min_hmm_minus_gmm": float(np.min(delta)),
            "max_hmm_minus_gmm": float(np.max(delta)),
            "wilcoxon_p": p_value,
            "positive_temporal_gain_runs": int((group["temporal_gain_per_obs_hmm"] > 0).sum()),
            "median_temporal_gain_hmm": float(group["temporal_gain_per_obs_hmm"].median()),
            "median_kept_fraction": float(group["kept_fraction_hmm"].median()),
        })
    return wide, pd.DataFrame(summaries)


def chronology_summary(paired: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    metrics = ["hmm_minus_gmm_test_loglik_per_obs", "temporal_gain_per_obs_hmm",
               "test_loglik_per_obs_hmm", "test_loglik_per_obs_gmm"]
    for (condition, environment, sensitivity), group in paired.groupby(
            ["condition", "environment", "sensitivity"], sort=False):
        for metric in metrics:
            valid = group[["run_number", metric]].dropna()
            if len(valid) >= 3 and valid[metric].nunique() > 1:
                rho, p_value = spearmanr(valid["run_number"], valid[metric])
            else:
                rho, p_value = np.nan, np.nan
            rows.append({"condition": condition, "environment": environment,
                         "sensitivity": sensitivity, "metric": metric,
                         "runs": len(valid), "spearman_rho_with_run_order": rho,
                         "spearman_p": p_value})
    return pd.DataFrame(rows)


def order_counts(selected: pd.DataFrame) -> pd.DataFrame:
    return (selected.groupby(["sensitivity", "environment", "model", "order"],
                             as_index=False).size()
            .rename(columns={"size": "runs_selected"}))


def write_report(summary: pd.DataFrame, orders: pd.DataFrame,
                 chronology: pd.DataFrame, audit: pd.DataFrame, output: Path) -> None:
    compact = summary[["sensitivity", "environment", "runs", "hmm_wins",
                       "median_hmm_minus_gmm", "wilcoxon_p",
                       "positive_temporal_gain_runs", "median_temporal_gain_hmm",
                       "median_kept_fraction"]].copy()
    retention = (audit.groupby(["sensitivity", "environment"], as_index=False)
                 .agg(median_kept_fraction=("kept_fraction", "median"),
                      min_kept_fraction=("kept_fraction", "min"),
                      max_kept_fraction=("kept_fraction", "max"),
                      median_cap_us=("cap_response_us", "median")))
    chronology_compact = chronology.loc[
        chronology["metric"].isin(["hmm_minus_gmm_test_loglik_per_obs",
                                    "temporal_gain_per_obs_hmm"])]
    lines = [
        "# Sensibilidade do nucleo estavel", "",
        "A ordem de GMM e HMM foi escolhida pelo menor BIC no treino antes da",
        "avaliacao no hold-out temporal. Quantis foram estimados somente no treino.", "",
        "## Comparacao pareada HMM menos GMM", "", compact.to_markdown(index=False), "",
        "## Retencao das mascaras", "", retention.to_markdown(index=False), "",
        "## Ordens selecionadas pelo BIC de treino", "", orders.to_markdown(index=False), "",
        "## Associacao com a ordem cronologica dos runs", "",
        chronology_compact.to_markdown(index=False), "",
        "## Criterio de robustez", "",
        "A evidencia residual e robusta somente se o ganho HMM-GMM permanecer positivo",
        "na maioria dos runs, tiver mediana materialmente positiva, teste pareado consistente",
        "e ganho sobre o embaralhamento em varias definicoes do nucleo estavel.", "",
    ]
    (output / "stable_core_sensitivity_report.md").write_text(
        "\n".join(lines), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--results", default="results")
    ap.add_argument("--output", default="results/stable_core_sensitivity")
    ap.add_argument("--train-fraction", type=float, default=.70)
    ap.add_argument("--orders", type=int, nargs="+", default=[2, 3, 4, 5])
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--shuffle-repeats", type=int, default=10)
    ap.add_argument("--random-seed", type=int, default=20260828)
    ap.add_argument("--fixed-caps-us", type=float, nargs="+",
                    default=[2500, 2000, 1500, 1000])
    ap.add_argument("--train-quantiles", type=float, nargs="+",
                    default=[.999, .9995, .9999])
    ap.add_argument("--min-shock-us", type=float, default=1000.0)
    ap.add_argument("--shock-mad-multiplier", type=float, default=20.0)
    ap.add_argument("--guard-before", type=int, default=1)
    ap.add_argument("--guard-after", type=int, default=5)
    ap.add_argument("--min-observations", type=int, default=500)
    ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 1) - 1))
    args = ap.parse_args()
    if not .5 <= args.train_fraction < 1:
        raise ValueError("--train-fraction deve estar em [0.5, 1)")
    if any(order < 2 for order in args.orders):
        raise ValueError("--orders aceita somente valores >= 2")
    if any(not 0 < q < 1 for q in args.train_quantiles):
        raise ValueError("--train-quantiles deve conter valores entre 0 e 1")
    if any(cap <= 0 for cap in args.fixed_caps_us):
        raise ValueError("--fixed-caps-us deve conter valores positivos")
    if min(args.seeds, args.shuffle_repeats, args.jobs) < 1:
        raise ValueError("--seeds, --shuffle-repeats e --jobs devem ser >= 1")

    results, output = root_path(args.results), root_path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    index = pd.read_csv(results / "derived/index.csv")
    index["scenario"] = index["source_file"].map(STEP11.scenario_from_source)
    selected_runs = index.loc[(index["condition"] == "interference") &
                              (index["scenario"] == "interf_io")].copy()
    if selected_runs.empty:
        raise ValueError("Nenhum run interference/interf_io encontrado")

    config = vars(args).copy()
    all_rows: list[dict] = []; all_audits: list[dict] = []
    work = selected_runs.to_dict("records")
    print(f"Executando sensibilidade em {len(work)} runs com {args.jobs} processo(s)...",
          flush=True)
    with ProcessPoolExecutor(max_workers=args.jobs) as executor:
        futures = [executor.submit(fit_one_run, item, config) for item in work]
        for completed, future in enumerate(as_completed(futures), 1):
            rows, audits = future.result()
            all_rows.extend(rows); all_audits.extend(audits)
            print(f"Concluido {completed}/{len(work)}: "
                  f"{audits[0]['environment']} / {audits[0]['run']}", flush=True)

    per_run = pd.DataFrame(all_rows)
    audit = pd.DataFrame(all_audits)
    selected = select_by_training_bic(per_run)
    paired, summary = paired_summary(selected)
    orders = order_counts(selected)
    chronology = chronology_summary(paired)

    per_run.to_csv(output / "sensitivity_models_by_run.csv", index=False)
    audit.to_csv(output / "sensitivity_mask_audit.csv", index=False)
    selected.to_csv(output / "sensitivity_selected_by_bic.csv", index=False)
    paired.to_csv(output / "sensitivity_paired_by_run.csv", index=False)
    summary.to_csv(output / "sensitivity_summary.csv", index=False)
    orders.to_csv(output / "sensitivity_order_counts.csv", index=False)
    chronology.to_csv(output / "sensitivity_chronology.csv", index=False)
    write_report(summary, orders, chronology, audit, output)
    print(f"Resultados gravados em {output}")


if __name__ == "__main__":
    main()
