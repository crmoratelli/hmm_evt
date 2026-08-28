#!/usr/bin/env python3
"""Resume episódios degradados de interference/interf_io por run.

Usa a caracterização da etapa 08, sem novo ajuste. Um estado é classificado
como degradado quando P(miss=1 | estado) >= --miss-threshold. Um run é severo
quando a ocupação total desses estados é >= --severe-occupancy.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

import matplotlib.pyplot as plt
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from common import root_path


def markdown_table(frame: pd.DataFrame) -> str:
    headers = list(frame.columns)
    rows = frame.fillna("").astype(str).values.tolist()
    line = lambda values: "| " + " | ".join(str(v).replace("|", "\\|") for v in values) + " |"
    return "\n".join([line(headers), line(["---"] * len(headers)), *(line(row) for row in rows)])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="results/hmm_interf_io_characterization")
    parser.add_argument("--output", default="results/degradation_episodes")
    parser.add_argument("--miss-threshold", type=float, default=.50)
    parser.add_argument("--severe-occupancy", type=float, default=.01)
    args = parser.parse_args()
    source, output = root_path(args.input), root_path(args.output); output.mkdir(parents=True, exist_ok=True)
    states = pd.read_csv(source / "state_summary_by_run.csv")
    episodes = pd.read_csv(source / "dwell_episodes.csv")
    keys = ["condition", "environment", "run", "states", "state_by_mean"]
    states["is_degraded"] = states["miss_rate"] >= args.miss_threshold
    degraded_states = states.loc[states.is_degraded].copy()
    degraded_episodes = episodes.merge(degraded_states[keys + ["miss_rate", "mean_response_ns"]], on=keys, how="inner")
    run_keys = ["condition", "environment", "run", "states"]
    all_runs = states[run_keys + ["n", "median_inter_release_ns"]].drop_duplicates()
    state_metrics = degraded_states.groupby(run_keys, as_index=False).agg(
        degraded_occupancy=("occupancy", "sum"), degraded_states=("state_by_mean", "nunique"),
        worst_state_miss_rate=("miss_rate", "max"), worst_state_mean_response_ns=("mean_response_ns", "max"),
    )
    episode_metrics = degraded_episodes.groupby(run_keys, as_index=False).agg(
        degraded_episodes=("dwell_activations", "size"), median_episode_activations=("dwell_activations", "median"),
        p95_episode_activations=("dwell_activations", lambda x: x.quantile(.95)),
        max_episode_activations=("dwell_activations", "max"), median_episode_us=("dwell_us", "median"),
        p95_episode_us=("dwell_us", lambda x: x.quantile(.95)), max_episode_us=("dwell_us", "max"),
    )
    report = all_runs.merge(state_metrics, on=run_keys, how="left").merge(episode_metrics, on=run_keys, how="left")
    zeros = ["degraded_occupancy", "degraded_states", "degraded_episodes", "median_episode_activations", "p95_episode_activations", "max_episode_activations", "median_episode_us", "p95_episode_us", "max_episode_us"]
    report[zeros] = report[zeros].fillna(0)
    report["severity"] = "sem degradação material"
    report.loc[report.degraded_occupancy.gt(0), "severity"] = "degradação moderada"
    report.loc[report.degraded_occupancy.ge(args.severe_occupancy), "severity"] = "degradação severa"
    report = report.sort_values(["environment", "severity", "run"])
    report.to_csv(output / "degradation_by_run.csv", index=False)
    degraded_episodes.to_csv(output / "degraded_episodes.csv", index=False)
    aggregate = report.groupby(["environment", "severity"], as_index=False).agg(
        runs=("run", "nunique"), median_degraded_occupancy=("degraded_occupancy", "median"),
        median_episodes=("degraded_episodes", "median"), median_max_episode_us=("max_episode_us", "median"),
    )
    aggregate.to_csv(output / "degradation_by_environment.csv", index=False)
    display = report[["environment", "run", "severity", "degraded_occupancy", "degraded_episodes", "median_episode_us", "p95_episode_us", "max_episode_us", "worst_state_miss_rate", "worst_state_mean_response_ns"]].copy()
    for column in display.select_dtypes("number"):
        display[column] = display[column].round(4)
    text = ["# Episódios de degradação: interference/interf_io", "", f"Um estado é degradado quando a taxa de miss estimada é pelo menos {args.miss_threshold:.0%}. Um run é severo quando pelo menos {args.severe_occupancy:.0%} das ativações pertencem a estados degradados.", "", markdown_table(display), "", "## Agregado por ambiente", "", markdown_table(aggregate.round(4))]
    (output / "degradation_report.md").write_text("\n".join(text) + "\n", encoding="utf-8")
    fig, ax = plt.subplots(figsize=(10, 4.5))
    colors = {"sem degradação material": "#8c8c8c", "degradação moderada": "#f39c12", "degradação severa": "#c0392b"}
    for severity, group in report.groupby("severity"):
        ax.scatter(group.run, group.degraded_occupancy * 100, s=65, color=colors[severity], label=severity)
    ax.set_yscale("symlog", linthresh=.01)
    ax.set(
        ylabel="ativações em estados degradados (%)",
        xlabel="run",
        title="Severidade dos episódios de degradação",
    )    
    ax.tick_params(axis="x", rotation=60); ax.legend(fontsize=8); fig.tight_layout()
    fig.savefig(output / "degradation_by_run.png", dpi=170); plt.close(fig)
    print(f"Relatório de episódios criado em {output}")


if __name__ == "__main__": main()
