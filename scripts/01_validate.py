#!/usr/bin/env python3
"""Valida esquema e coerência interna dos CSVs brutos."""
from __future__ import annotations
import argparse
from pathlib import Path
import sys
import pandas as pd
sys.path.insert(0, str(Path(__file__).parent))
from common import REQUIRED, discover_csvs, load_manifest, read_run, root_path, save_json


def assess(path: Path, meta: dict) -> dict:
    row = {"file": str(path), **meta}
    try:
        df = read_run(path)
        missing = [c for c in REQUIRED if c not in df.columns]
        row.update(rows=len(df), missing_columns=";".join(missing))
        if missing:
            row.update(status="invalid", null_required="", release_nonmonotonic="", response_mismatch="", miss_mismatch="")
            return row
        nulls = int(df[list(REQUIRED)].isna().sum().sum())
        release_bad = int((df["release_ns"].diff().dropna() < 0).sum())
        expected_response = df["finish_ns"] - df["release_ns"]
        response_bad = int((df["response_ns"] - expected_response).abs().gt(1).sum())
        miss_bad = ""
        if "miss" in df:
            miss_bad = int((df["miss"].fillna(-1).astype(int) != (df["lateness_ns"] > 0).astype(int)).sum())
        row.update(status="ok" if not (nulls or release_bad) else "warning", null_required=nulls,
                   release_nonmonotonic=release_bad, response_mismatch=response_bad, miss_mismatch=miss_bad)
    except Exception as exc:
        row.update(status="unreadable", rows="", missing_columns="", null_required="", release_nonmonotonic="", response_mismatch="", miss_mismatch="", error=str(exc))
    return row


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="data")
    ap.add_argument("--output", default="results/integrity")
    ap.add_argument("--manifest")
    args = ap.parse_args()
    manifest = load_manifest(args.manifest)
    rows = [assess(path, meta) for path, meta in discover_csvs(args.input, manifest)]
    out = root_path(args.output); out.mkdir(parents=True, exist_ok=True)
    columns = ["file", "condition", "environment", "run", "status", "rows", "missing_columns", "null_required", "release_nonmonotonic", "response_mismatch", "miss_mismatch", "error"]
    report = pd.DataFrame(rows).reindex(columns=columns)
    report.to_csv(out / "integrity_by_file.csv", index=False)
    status = report["status"].value_counts().to_dict() if len(report) else {}
    save_json({"files": len(report), "status_counts": status, "required_columns": list(REQUIRED)}, out / "integrity_summary.json")
    print(f"Validados {len(report)} CSVs; relatório em {out}")

if __name__ == "__main__": main()
