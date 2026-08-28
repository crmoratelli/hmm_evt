#!/usr/bin/env python3
"""Triagem reproduzível de subcenários candidatos à modelagem por HMM.

Não ajusta HMMs. Resume, por condição/ambiente/subcenário, se há evidência
praticamente relevante de persistência temporal, cauda e misses. O campo
``scenario`` é obtido de um manifesto quando disponível; caso contrário, é
inferido de forma explícita e auditável a partir do nome do arquivo.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from common import root_path


def scenario_from_name(name: str) -> str:
    """Heurística conservadora para nomes como docker_cpu3-interf_io-run1."""
    stem = Path(str(name)).stem.lower()
    stem = re.sub(r"(?:[_-]?run[_-]?\d+)$", "", stem)
    stem = re.sub(r"^(?:host|docker|container)(?:[_-]cpu\d+)?[_-]?", "", stem)
    return stem or "unspecified"


def markdown_table(frame: pd.DataFrame) -> str:
    headers = list(frame.columns)
    rows = frame.fillna("").astype(str).values.tolist()
    line = lambda cells: "| " + " | ".join(str(x).replace("|", "\\|") for x in cells) + " |"
    return "\n".join([line(headers), line(["---"] * len(headers)), *(line(row) for row in rows)])


def load_scenarios(index: pd.DataFrame, manifest_path: str | None) -> dict[str, str]:
    """Retorna cenário por caminho derivado; usa manifesto somente se completo."""
    index = index.copy()
    index["derived_key"] = index["derived_file"].map(lambda p: str(Path(p).resolve()))
    index["scenario"] = index["source_file"].map(scenario_from_name)
    if manifest_path:
        manifest = pd.read_csv(manifest_path)
        needed = {"file", "scenario"}
        missing = needed - set(manifest.columns)
        if missing:
            raise ValueError(f"Manifesto sem colunas necessárias: {sorted(missing)}")
        manifest = manifest[["file", "scenario"]].copy()
        manifest["file"] = manifest["file"].astype(str).str.replace("\\\\", "/", regex=False)
        index["source_relative"] = index["source_file"].map(lambda p: Path(p).as_posix().split("/data/", 1)[-1])
        index = index.merge(manifest, how="left", left_on="source_relative", right_on="file", suffixes=("", "_manifest"))
        index["scenario"] = index["scenario_manifest"].fillna(index["scenario"])
    return dict(zip(index["derived_key"], index["scenario"]))


def recommendation(row: pd.Series) -> str:
    temporal = row["mean_abs_acf_lag1"] >= 0.10 and row["fraction_significant_lag1"] >= 0.70
    tail_or_miss = row["tail_ratio_p99_median"] >= 1.50 or row["mean_miss_rate"] >= 0.001
    bursty = row["fraction_excess_high_runs"] >= 0.50
    if temporal and (tail_or_miss or bursty):
        return "HMM candidato"
    if temporal:
        return "comparar AR(1) e HMM"
    if row["mean_abs_acf_lag1"] >= 0.03:
        return "efeito temporal fraco: baseline AR(1)"
    return "sem regimes: baseline independente"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", default="results", help="diretório produzido pelas etapas 01–04")
    parser.add_argument("--output", default="results/candidates")
    parser.add_argument("--manifest", help="opcional; deve conter file e scenario")
    args = parser.parse_args()

    results, output = root_path(args.results), root_path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    summary = pd.read_csv(results / "descriptive/summary_by_run.csv")
    temporal = pd.read_csv(results / "temporal/temporal_by_run.csv")
    index = pd.read_csv(results / "derived/index.csv")
    scenario_map = load_scenarios(index, args.manifest)

    summary["derived_key"] = summary["file"].map(lambda p: str(Path(p).resolve()))
    summary["scenario"] = summary["derived_key"].map(scenario_map).fillna(summary["run"].map(scenario_from_name))
    temporal = temporal.loc[temporal["variable"] == "log_response_ns"].copy()
    temporal["derived_key"] = temporal["file"].map(lambda p: str(Path(p).resolve()))
    temporal["scenario"] = temporal["derived_key"].map(scenario_map).fillna(temporal["run"].map(scenario_from_name))

    keys = ["condition", "environment", "scenario"]
    descriptive = summary.groupby(keys, as_index=False).agg(
        runs=("run", "nunique"), median_response_ns=("median_ns", "median"), p99_response_ns=("p99_ns", "median"),
        mean_miss_rate=("miss_rate", "mean"), max_miss_rate=("miss_rate", "max"),
    )
    temporal_summary = temporal.groupby(keys, as_index=False).agg(
        temporal_runs=("run", "nunique"), mean_acf_lag1=("acf_lag1", "mean"),
        mean_abs_acf_lag1=("acf_lag1", lambda x: np.mean(np.abs(x))),
        fraction_significant_lag1=("lag1_outside_shuffle_95", "mean"),
        fraction_excess_high_runs=("high_run_mean", lambda x: np.mean(x > temporal.loc[x.index, "shuffle_high_run_mean_95"])),
        median_high_run_max=("high_run_max", "median"),
    )
    table = descriptive.merge(temporal_summary, on=keys, how="left")
    table["tail_ratio_p99_median"] = table["p99_response_ns"] / table["median_response_ns"]
    table["recommendation"] = table.apply(recommendation, axis=1)
    table = table.sort_values(["recommendation", "condition", "environment", "scenario"])
    table.to_csv(output / "hmm_candidate_screen.csv", index=False)

    show = table.copy()
    numeric = show.select_dtypes("number").columns
    show[numeric] = show[numeric].round(4)
    report = ["# Triagem de candidatos a HMM", "", "A recomendação é uma triagem, não uma seleção de modelo. HMM só deve ser comparado a modelos independentes e AR(1) em validação fora da amostra.", "", markdown_table(show), "", "## Regras", "", "- **HMM candidato**: persistência prática (|ACF(1)| ≥ 0,10), reproduzida em pelo menos 70% dos runs, e cauda/misses ou rajadas de alta latência.", "- **comparar AR(1) e HMM**: persistência forte sem evidência adicional de estados raros/degradação.", "- **efeito temporal fraco**: testar primeiro o ganho de um AR(1).", "- **sem regimes**: usar modelo marginal independente como referência."]
    (output / "hmm_candidate_screen.md").write_text("\n".join(report) + "\n", encoding="utf-8")

    fig, ax = plt.subplots(figsize=(9, 5))
    for label, group in table.groupby("recommendation"):
        ax.scatter(group["mean_abs_acf_lag1"], group["tail_ratio_p99_median"], s=55, label=label)
        for _, row in group.iterrows():
            ax.annotate(f"{row.condition}:{row.scenario}", (row.mean_abs_acf_lag1, row.tail_ratio_p99_median), fontsize=7, xytext=(3, 3), textcoords="offset points")
    ax.axvline(.10, color="grey", ls="--", lw=.8); ax.axhline(1.50, color="grey", ls="--", lw=.8)
    ax.set(xlabel="média de |ACF(1)| em log(response_ns)", ylabel="p99 / mediana", title="Triagem de candidatos a HMM")
    ax.legend(fontsize=8); fig.tight_layout(); fig.savefig(output / "candidate_screen.png", dpi=170); plt.close(fig)
    print(f"Triagem criada em {output}")


if __name__ == "__main__":
    main()
