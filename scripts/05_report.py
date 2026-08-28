#!/usr/bin/env python3
"""Consolida o marco: distribuição marginal versus ordem temporal."""
from __future__ import annotations
import argparse
from pathlib import Path
import sys
import pandas as pd
sys.path.insert(0, str(Path(__file__).parent))
from common import root_path


def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("--results", default="results"); ap.add_argument("--output", default="results/report")
    args = ap.parse_args(); results = root_path(args.results); out = root_path(args.output); out.mkdir(parents=True, exist_ok=True)
    integrity = pd.read_csv(results / "integrity/integrity_by_file.csv") if (results / "integrity/integrity_by_file.csv").exists() else pd.DataFrame()
    summary = pd.read_csv(results / "descriptive/summary_by_run.csv") if (results / "descriptive/summary_by_run.csv").exists() else pd.DataFrame()
    temporal = pd.read_csv(results / "temporal/temporal_by_run.csv") if (results / "temporal/temporal_by_run.csv").exists() else pd.DataFrame()
    lines = ["# Relatório: estrutura temporal das latências", ""]
    if not integrity.empty:
        lines += ["## Integridade", f"- Arquivos analisados: {len(integrity)}.", f"- Estado dos arquivos: {integrity.status.value_counts().to_dict()}.", ""]
    if not summary.empty:
        lines += ["## Resumo por condição", "", summary.groupby(["condition", "environment"])[["n", "median_ns", "p99_ns", "miss_rate"]].mean().round(3).to_markdown(), ""]
    if not temporal.empty:
        t = temporal[temporal.variable == "log_response_ns"].copy()
        evidence = t.groupby(["condition", "environment"]).agg(runs=("run", "count"), significant_lag1=("lag1_outside_shuffle_95", "sum"), mean_lag1=("acf_lag1", "mean")).round(3)
        lines += ["## Ordem temporal versus embaralhamento", "", evidence.to_markdown(), "", "A coluna `significant_lag1` conta runs cujo ACF no primeiro lag ficou fora do intervalo empírico de 95% obtido por embaralhamento. Evidência consistente em vários runs indica que a ordem temporal contém informação além da distribuição marginal.", ""]
    lines += ["## Próxima decisão", "Ajustar HMM somente se os resultados acima mostrarem dependência temporal reproduzível. Começar comparando HMM gaussiano em `response_ns` e em `log(response_ns)`; manter `miss` apenas para avaliação posterior por estado."]
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Relatório criado em {out / 'report.md'}")

if __name__ == "__main__": main()
