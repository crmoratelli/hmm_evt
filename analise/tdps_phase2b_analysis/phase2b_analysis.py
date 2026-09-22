#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def episode_ranges(mask: np.ndarray):
    start = None
    for i, value in enumerate(np.asarray(mask, dtype=bool)):
        if value and start is None:
            start = i
        elif not value and start is not None:
            yield start, i - 1
            start = None
    if start is not None:
        yield start, len(mask) - 1


def episode_count(mask: np.ndarray) -> int:
    return sum(1 for _ in episode_ranges(mask))


def metadata(run: Path) -> dict[str, str]:
    result = {}
    for line in (run / "metadata.env").read_text().splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            result[key] = value
    return result


def load_runs(root: Path):
    result = []
    for run in sorted((root / "runs").iterdir()):
        if not run.is_dir() or not (run / "samples.csv").exists():
            continue
        meta = metadata(run)
        result.append((run, meta, pd.read_csv(run / "samples.csv")))
    if len(result) != 120:
        raise SystemExit(f"expected 120 runs, found {len(result)}")
    return result


def inline_analysis(runs, output: Path):
    selected = [(p, m, d) for p, m, d in runs if m["ARCHITECTURE"] == "inline" and m["SCENARIO"] == "io"]
    calibrations, episode_rows = [], []
    for path, meta, df in selected:
        release = df.release_ns.to_numpy(np.int64)
        start = df.start_ns.to_numpy(np.int64)
        finish = df.output_finish_ns.to_numpy(np.int64)
        reference = np.maximum(release[1:], finish[:-1])
        handoff = start[1:] - reference
        slept = finish[:-1] <= release[1:]
        calibrations.append({"run": path.name, "sleep": int(np.median(handoff[slept])), "catchup": int(np.median(handoff[~slept]))})

        deadline = int(df.response_ns.iloc[0] - df.lateness_ns.iloc[0])
        period = int(release[1] - release[0])
        for begin, end in episode_ranges(df.miss.to_numpy(bool)):
            previous, first = df.iloc[begin - 1], df.iloc[begin]
            spill = max(0, int(previous.output_finish_ns - first.release_ns))
            segment = df.iloc[begin:end + 1]
            recovery = period - float(segment.execution_ns.median())
            predicted_length = max(1, int(np.ceil(max(0, first.response_ns - deadline) / recovery)))
            episode_rows.append({
                "run": path.name, "substrate": meta["SUBSTRATE"], "start_job": begin, "end_job": end,
                "length_jobs": end - begin + 1, "predicted_simple_length": predicted_length,
                "precursor_job": begin - 1,
                "precursor_delivery_ns": int(previous.delivery_finish_ns - previous.delivery_start_ns),
                "spill_into_release_ns": spill, "first_response_ns": int(first.response_ns),
                "overlap_predicts_miss": spill + int(first.execution_ns) > deadline,
            })

    cal = pd.DataFrame(calibrations)
    episodes = pd.DataFrame(episode_rows)
    loo_rows = []
    for path, meta, df in selected:
        training = cal.loc[cal.run != path.name]
        hs, hc = int(np.median(training.sleep)), int(np.median(training.catchup))
        release = df.release_ns.to_numpy(np.int64)
        start = df.start_ns.to_numpy(np.int64)
        execution = df.execution_ns.to_numpy(np.int64)
        service = (df.output_finish_ns - df.compute_finish_ns).to_numpy(np.int64)
        deadline = int(df.response_ns.iloc[0] - df.lateness_ns.iloc[0])
        predicted_start = np.empty(len(df), np.int64); predicted_start[0] = start[0]
        for j in range(1, len(df)):
            prior_finish = predicted_start[j-1] + execution[j-1] + service[j-1]
            predicted_start[j] = release[j] + hs if prior_finish <= release[j] else prior_finish + hc
        predicted_response = predicted_start - release + execution
        observed = df.miss.to_numpy(bool); predicted = predicted_response > deadline
        loo_rows.append({
            "run": path.name, "substrate": meta["SUBSTRATE"], "sleep_overhead_ns": hs, "catchup_overhead_ns": hc,
            "observed_misses": int(observed.sum()), "predicted_misses": int(predicted.sum()),
            "observed_episodes": episode_count(observed), "predicted_episodes": episode_count(predicted),
            "tp": int(np.sum(observed & predicted)), "fp": int(np.sum(~observed & predicted)), "fn": int(np.sum(observed & ~predicted)),
            "mae_ns": float(np.mean(np.abs(df.response_ns.to_numpy(np.int64) - predicted_response))),
        })
    loo = pd.DataFrame(loo_rows)
    episodes.to_csv(output / "inline_episode_mapping.csv", index=False)
    loo.to_csv(output / "inline_loo_validation.csv", index=False)
    return episodes, loo


def async_analysis(runs, output: Path):
    selected = [(p, m, d) for p, m, d in runs if m["ARCHITECTURE"] == "async"]
    cal = []
    for path, meta, df in selected:
        arrival = df.output_start_ns.to_numpy(np.int64); start = df.delivery_start_ns.to_numpy(np.int64); finish = df.delivery_finish_ns.to_numpy(np.int64)
        idle = finish[:-1] <= arrival[1:]
        cal.append({"run": path.name, "idle": int(np.median(start[1:][idle] - arrival[1:][idle])), "busy": int(np.median(start[1:][~idle] - finish[:-1][~idle])) if np.any(~idle) else np.nan})
    cal = pd.DataFrame(cal)
    idle_overhead = int(np.median(cal.idle)); busy_overhead = int(np.nanmedian(cal.busy))
    summary_rows, event_rows = [], []
    for path, meta, df in selected:
        release = df.release_ns.to_numpy(np.int64); arrival = df.output_start_ns.to_numpy(np.int64)
        start = df.delivery_start_ns.to_numpy(np.int64); finish = df.delivery_finish_ns.to_numpy(np.int64)
        service = finish - start; previous = np.r_[finish[0], finish[:-1]]
        idle = previous <= arrival; reference = np.maximum(arrival, previous)
        dispatch = start - reference; normal = np.where(idle, idle_overhead, busy_overhead)
        deadline = int(df.response_ns.iloc[0] - df.lateness_ns.iloc[0])
        local = df.output_finish_ns.to_numpy(np.int64) - release; e2e = finish - release
        over = e2e > deadline; counterfactual = reference + normal + service - release
        backlog = over & (counterfactual > deadline); dispatch_excess = over & ~backlog
        run_summary = json.loads((path / "summary.json").read_text())
        summary_rows.append({
            "run": path.name, "scenario": meta["SCENARIO"], "substrate": meta["SUBSTRATE"], "jobs": len(df),
            "queue_high_water": run_summary["queue_high_water"], "drops": int(df.dropped.sum()),
            "local_over_3ms": int(np.sum(local > deadline)), "e2e_over_3ms": int(over.sum()), "e2e_episodes": episode_count(over),
            "service_backlog_jobs": int(backlog.sum()), "dispatch_excess_jobs": int(dispatch_excess.sum()),
            "dispatch_excess_episodes": episode_count(dispatch_excess), "e2e_p999_ns": int(np.quantile(e2e, .999)), "e2e_max_ns": int(e2e.max()),
        })
        for job in np.flatnonzero(dispatch_excess):
            event_rows.append({"run": path.name, "scenario": meta["SCENARIO"], "substrate": meta["SUBSTRATE"], "job": int(job), "idle": bool(idle[job]), "e2e_ns": int(e2e[job]), "counterfactual_e2e_ns": int(counterfactual[job]), "dispatch_delay_ns": int(dispatch[job]), "service_ns": int(service[job])})
    summary, events = pd.DataFrame(summary_rows), pd.DataFrame(event_rows)
    summary.to_csv(output / "async_end_to_end_summary.csv", index=False)
    events.to_csv(output / "async_dispatch_excess_events.csv", index=False)
    return summary, events, idle_overhead, busy_overhead


def figures(episodes, inline_loo, async_summary, output: Path):
    figdir = output / "figures"; figdir.mkdir()
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.scatter(episodes.length_jobs, episodes.first_response_ns / 1e6, alpha=.7)
    ax.set(xlabel="Episode length (jobs)", ylabel="First response (ms)", title="Inline backlog determines episode length")
    fig.tight_layout(); fig.savefig(figdir / "inline_episode_length.png", dpi=180); plt.close(fig)

    io = async_summary.loc[async_summary.scenario == "io"].groupby("substrate")[["service_backlog_jobs", "dispatch_excess_jobs"]].sum()
    fig, ax = plt.subplots(figsize=(7, 4.5)); io.plot.bar(stacked=True, ax=ax)
    ax.set(xlabel="Substrate", ylabel="Jobs over 3 ms", title="Async end-to-end tail decomposition")
    ax.legend(["Service/backlog", "Dispatch delay"]); ax.tick_params(axis="x", rotation=0)
    fig.tight_layout(); fig.savefig(figdir / "async_tail_decomposition.png", dpi=180); plt.close(fig)


def report(episodes, loo, async_summary, events, idle_h, busy_h, output: Path):
    io = async_summary.loc[async_summary.scenario == "io"]
    control = async_summary.loc[async_summary.scenario == "control"]
    tp, fp, fn = int(loo.tp.sum()), int(loo.fp.sum()), int(loo.fn.sum())
    text = f"""# TDPS Phase 2B report

## Inline causal reconstruction

- Runs: {loo.run.nunique()}
- Observed misses: {int(loo.observed_misses.sum())}
- Episodes: {len(episodes)}
- Episodes preceded by causal overlap: {int(episodes.overlap_predicts_miss.sum())}/{len(episodes)}
- Leave-one-run-out: TP={tp}, FP={fp}, FN={fn}
- Mean reconstruction MAE: {loo.mae_ns.mean():.3f} ns

The inline path converts a blocking write into producer backlog. Fixed releases
then produce consecutive misses until the backlog is recovered.

## Async local and end-to-end behavior

- I/O jobs: {int(io.jobs.sum())}
- Local jobs over 3 ms: {int(io.local_over_3ms.sum())}
- End-to-end jobs over 3 ms (diagnostic): {int(io.e2e_over_3ms.sum())}
- End-to-end episodes: {int(io.e2e_episodes.sum())}
- Service/backlog jobs: {int(io.service_backlog_jobs.sum())}
- Dispatch-excess jobs: {int(io.dispatch_excess_jobs.sum())}
- Drops: {int(io.drops.sum())}
- Maximum queue high-water: {int(io.queue_high_water.max())}/1024
- Control end-to-end jobs over 3 ms: {int(control.e2e_over_3ms.sum())}
- Idle overhead used: {idle_h} ns
- Busy handoff used: {busy_h} ns

The async path protects the periodic producer, but relocates tail latency to
the consumer. Its end-to-end tail contains two observed mechanisms: I/O
service/backlog and exceptional consumer dispatch delay.

## Scope

The 3 ms threshold is the original local deadline. Its use for completed
delivery is a diagnostic counterfactual, not a claim that the original
experiment specified an end-to-end deadline. The recurrence is a causal replay
conditioned on observed service times; it is not a forecast of future I/O.
"""
    (output / "REPORT.md").write_text(text)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--root", type=Path, required=True); ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args(); args.output.mkdir(parents=True, exist_ok=True)
    runs = load_runs(args.root)
    episodes, loo = inline_analysis(runs, args.output)
    async_summary, events, idle_h, busy_h = async_analysis(runs, args.output)
    figures(episodes, loo, async_summary, args.output)
    report(episodes, loo, async_summary, events, idle_h, busy_h, args.output)
    print(f"PHASE2B_COMPLETE={args.output.resolve()}")


if __name__ == "__main__":
    main()
