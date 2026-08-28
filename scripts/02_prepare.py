#!/usr/bin/env python3
"""Gera tabelas derivadas ordenadas por release_ns, sem modificar data/."""
from __future__ import annotations
import argparse
from pathlib import Path
import sys
import pandas as pd
sys.path.insert(0, str(Path(__file__).parent))
from common import REQUIRED, discover_csvs, load_manifest, output_run_path, read_run, root_path


def prepare(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values("release_ns", kind="stable").reset_index(drop=True).copy()
    df["response_us"] = df["response_ns"] / 1_000
    df["lateness_us"] = df["lateness_ns"] / 1_000
    df["inter_release_ns"] = df["release_ns"].diff()
    df["response_error_ns"] = df["response_ns"] - (df["finish_ns"] - df["release_ns"])
    df["deadline_ns"] = df["response_ns"] - df["lateness_ns"]
    df["miss_expected"] = (df["lateness_ns"] > 0).astype(int)
    return df


def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("--input", default="data"); ap.add_argument("--output", default="results/derived"); ap.add_argument("--manifest")
    args = ap.parse_args(); manifest = load_manifest(args.manifest); out = root_path(args.output)
    index = []
    for source, meta in discover_csvs(args.input, manifest):
        df = read_run(source)
        if set(REQUIRED) - set(df.columns):
            print(f"Ignorado (esquema inválido): {source}"); continue
        target = output_run_path(out, meta); target.parent.mkdir(parents=True, exist_ok=True)
        prepare(df).to_csv(target, index=False)
        index.append({"source_file": str(source), "derived_file": str(target), "rows": len(df), **meta})
    pd.DataFrame(index).to_csv(out / "index.csv", index=False)
    print(f"Gerados {len(index)} conjuntos derivados em {out}")

if __name__ == "__main__": main()
