#!/usr/bin/env python3
"""Detecta choques de latencia e rampas de recuperacao em interference/interf_io.

A unidade de analise e um episodio contiguo de deadline misses. Para cada
episodio, o script mede o salto inicial, o pico, a duracao, a inclinacao apos
o pico e a compatibilidade dessa inclinacao com a drenagem de backlog
esperada: baseline_response_ns - period_ns.

Este script nao usa rotulos do HMM e nao atribui causalidade aos choques.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from common import root_path


def scenario_from_source(source: str) -> str:
    stem = Path(source).stem.lower()
    stem = re.sub(r"(?:[_-]?run[_-]?\d+)$", "", stem)
    return re.sub(r"^(?:host|docker|container)(?:[_-]cpu\d+)?[_-]?", "", stem)


def robust_mad(values: np.ndarray) -> float:
    median = float(np.median(values))
    return float(np.median(np.abs(values - median)))


def linear_slope(values: np.ndarray) -> tuple[float, float]:
    """Retorna slope por ativacao e R2 para values ~ indice."""
    if len(values) < 2:
        return np.nan, np.nan
    x = np.arange(len(values), dtype=float)
    slope, intercept = np.polyfit(x, values.astype(float), 1)
    fitted = intercept + slope * x
    residual = float(np.sum((values - fitted) ** 2))
    total = float(np.sum((values - np.mean(values)) ** 2))
    r2 = 1.0 - residual / total if total > 0 else np.nan
    return float(slope), float(r2)


def contiguous_true(mask: np.ndarray) -> list[tuple[int, int]]:
    """Intervalos inclusivos (inicio, fim) nos quais mask e verdadeiro."""
    padded = np.r_[False, mask, False].astype(np.int8)
    changes = np.diff(padded)
    starts = np.flatnonzero(changes == 1)
    ends = np.flatnonzero(changes == -1) - 1
    return list(zip(starts.tolist(), ends.tolist()))


def analyze_run(item: pd.Series, min_shock_ns: float, shock_mad_multiplier: float,
                slope_tolerance_ns: float) -> tuple[dict, list[dict], list[dict]]:
    data = pd.read_csv(item["derived_file"])
    response = data["response_ns"].to_numpy(float)
    valid = np.isfinite(response) & (response > 0)
    if not valid.all():
        raise ValueError(f"Valores invalidos em {item['derived_file']}")

    if "inter_release_ns" in data:
        period_ns = float(np.nanmedian(data["inter_release_ns"].iloc[1:]))
    else:
        period_ns = float(np.nanmedian(np.diff(data["release_ns"].to_numpy(float))))

    if "miss_expected" in data:
        misses = data["miss_expected"].to_numpy(int).astype(bool)
    elif "miss" in data:
        misses = data["miss"].to_numpy(int).astype(bool)
    else:
        deadline_ns = float(np.nanmedian(response - data["lateness_ns"].to_numpy(float)))
        misses = response > deadline_ns
    deadline_ns = float(np.nanmedian(response - data["lateness_ns"].to_numpy(float)))

    nonmiss = response[~misses]
    baseline_ns = float(np.median(nonmiss)) if len(nonmiss) else float(np.median(response))
    delta = np.diff(response)
    delta_mad_ns = robust_mad(delta)
    shock_threshold_ns = max(float(min_shock_ns), shock_mad_multiplier * delta_mad_ns)
    shock_indices = np.flatnonzero(delta >= shock_threshold_ns) + 1
    expected_slope_ns = baseline_ns - period_ns

    base = {
        "condition": item["condition"], "environment": item["environment"],
        "run": item["run"], "n": len(data), "period_ns": period_ns,
        "deadline_ns": deadline_ns, "baseline_response_ns": baseline_ns,
        "expected_recovery_slope_ns_per_activation": expected_slope_ns,
        "delta_mad_ns": delta_mad_ns, "shock_threshold_ns": shock_threshold_ns,
    }

    shocks: list[dict] = []
    for index in shock_indices:
        shocks.append({
            **base, "shock_job_index": int(index),
            "shock_release_ns": int(data.iloc[index]["release_ns"]),
            "response_before_ns": float(response[index - 1]),
            "response_after_ns": float(response[index]),
            "shock_amplitude_ns": float(delta[index - 1]),
            "is_deadline_miss_after_shock": bool(misses[index]),
        })

    episodes: list[dict] = []
    for episode_id, (start, end) in enumerate(contiguous_true(misses), 1):
        segment = response[start:end + 1]
        peak = start + int(np.argmax(segment))
        recovery = response[peak:end + 1]
        slope_ns, slope_r2 = linear_slope(recovery)
        recovery_delta = np.diff(recovery)
        near_expected = (
            np.mean(np.abs(recovery_delta - expected_slope_ns) <= slope_tolerance_ns)
            if len(recovery_delta) else np.nan
        )
        episode_shocks = shock_indices[(shock_indices >= start) & (shock_indices <= end)]
        area_ns = float(np.sum(np.maximum(segment - deadline_ns, 0.0)))
        episodes.append({
            **base, "episode_id": episode_id, "start_index": start,
            "end_index": end, "peak_index": peak,
            "start_release_ns": int(data.iloc[start]["release_ns"]),
            "end_release_ns": int(data.iloc[end]["release_ns"]),
            "activations": end - start + 1,
            "duration_us": (end - start + 1) * period_ns / 1_000.0,
            "peak_response_ns": float(response[peak]),
            "onset_jump_ns": float(response[start] - response[start - 1]) if start else np.nan,
            "shocks_inside_episode": int(len(episode_shocks)),
            "recovery_activations": end - peak + 1,
            "observed_recovery_slope_ns_per_activation": slope_ns,
            "recovery_slope_error_ns": slope_ns - expected_slope_ns,
            "recovery_r2": slope_r2,
            "fraction_recovery_steps_near_expected": near_expected,
            "excess_latency_area_ns": area_ns,
        })

    episode_frame = pd.DataFrame(episodes)
    summary = {
        **base, "misses": int(misses.sum()), "miss_rate": float(misses.mean()),
        "shocks": len(shocks), "miss_episodes": len(episodes),
        "max_response_ns": float(response.max()),
        "median_episode_activations": float(episode_frame["activations"].median()) if episodes else 0.0,
        "max_episode_activations": int(episode_frame["activations"].max()) if episodes else 0,
        "median_recovery_slope_ns_per_activation": float(episode_frame["observed_recovery_slope_ns_per_activation"].median()) if episodes else np.nan,
        "median_recovery_r2": float(episode_frame["recovery_r2"].median()) if episodes else np.nan,
        "median_fraction_steps_near_expected": float(episode_frame["fraction_recovery_steps_near_expected"].median()) if episodes else np.nan,
    }
    return summary, shocks, episodes


def markdown_table(frame: pd.DataFrame) -> str:
    headers = list(frame.columns)
    rows = frame.fillna("").astype(str).values.tolist()
    line = lambda cells: "| " + " | ".join(str(x).replace("|", "\\|") for x in cells) + " |"
    return "\n".join([line(headers), line(["---"] * len(headers)), *(line(row) for row in rows)])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", default="results")
    parser.add_argument("--output", default="results/shock_recovery")
    parser.add_argument("--condition", default="interference")
    parser.add_argument("--scenario", default="interf_io")
    parser.add_argument("--min-shock-us", type=float, default=1_000.0,
                        help="salto positivo minimo; padrao: 1000 us")
    parser.add_argument("--shock-mad-multiplier", type=float, default=20.0)
    parser.add_argument("--slope-tolerance-us", type=float, default=250.0,
                        help="tolerancia ao comparar passos com baseline-periodo; padrao: 250 us")
    args = parser.parse_args()

    results, output = root_path(args.results), root_path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    index = pd.read_csv(results / "derived/index.csv")
    index["scenario"] = index["source_file"].map(scenario_from_source)
    selected = index[(index["condition"] == args.condition) & (index["scenario"] == args.scenario)].copy()
    if selected.empty:
        raise ValueError(f"Nenhum run encontrado para {args.condition}/{args.scenario}")

    summaries: list[dict] = []
    shocks: list[dict] = []
    episodes: list[dict] = []
    for _, item in selected.iterrows():
        summary, run_shocks, run_episodes = analyze_run(
            item, args.min_shock_us * 1_000.0, args.shock_mad_multiplier,
            args.slope_tolerance_us * 1_000.0,
        )
        summaries.append(summary); shocks.extend(run_shocks); episodes.extend(run_episodes)
        print(f"Concluido: {item['environment']} / {item['run']}", flush=True)

    by_run = pd.DataFrame(summaries).sort_values(["environment", "run"])
    shock_frame = pd.DataFrame(shocks)
    episode_frame = pd.DataFrame(episodes)
    by_run.to_csv(output / "shock_recovery_by_run.csv", index=False)
    shock_frame.to_csv(output / "latency_shocks.csv", index=False)
    episode_frame.to_csv(output / "recovery_episodes.csv", index=False)

    aggregate = by_run.groupby("environment", as_index=False).agg(
        runs=("run", "nunique"), total_shocks=("shocks", "sum"),
        total_episodes=("miss_episodes", "sum"), median_miss_rate=("miss_rate", "median"),
        median_max_response_ns=("max_response_ns", "median"),
        median_expected_slope_ns=("expected_recovery_slope_ns_per_activation", "median"),
        median_observed_slope_ns=("median_recovery_slope_ns_per_activation", "median"),
        median_recovery_r2=("median_recovery_r2", "median"),
        median_fraction_near_expected=("median_fraction_steps_near_expected", "median"),
    )
    aggregate.to_csv(output / "shock_recovery_by_environment.csv", index=False)

    display = aggregate.copy()
    for column in display.select_dtypes("number"):
        display[column] = display[column].round(4)
    report = [
        "# Choques de latencia e recuperacao de backlog", "",
        "Episodios sao sequencias contiguas de deadline misses. Choques sao saltos positivos em response_ns acima do maior entre o limiar absoluto e o limiar robusto baseado em MAD.", "",
        markdown_table(display), "", "## Interpretacao", "",
        "Uma inclinacao observada proxima de baseline_response_ns - period_ns, com R2 elevado, e compativel com drenagem deterministica de backlog apos um bloqueio. Isso nao identifica, por si so, a causa do bloqueio.",
    ]
    (output / "shock_recovery_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"Analise criada em {output}")


if __name__ == "__main__":
    main()
