"""Funções compartilhadas do pipeline; os CSVs originais nunca são alterados."""
from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Iterable

import pandas as pd

REQUIRED = ("release_ns", "finish_ns", "response_ns", "lateness_ns")
NUMERIC = (*REQUIRED, "miss")

def root_path(value: str | Path) -> Path:
    return Path(value).expanduser().resolve()


def load_manifest(path: str | Path | None) -> pd.DataFrame | None:
    if not path:
        return None
    frame = pd.read_csv(path)
    required = {"file", "condition", "environment", "run"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Manifesto sem colunas: {sorted(missing)}")
    frame["file"] = frame["file"].astype(str).str.replace("\\\\", "/", regex=False)
    return frame


def infer_metadata(path: Path, data_root: Path, manifest: pd.DataFrame | None) -> dict:
    relative = path.relative_to(data_root).as_posix()
    if manifest is not None:
        row = manifest.loc[manifest["file"] == relative]
        if len(row) == 1:
            return row.iloc[0][["condition", "environment", "run"]].to_dict()
        if len(row) > 1:
            raise ValueError(f"Mais de uma linha no manifesto para {relative}")
    condition = path.parent.name
    name = path.stem.lower()
    environment = "host" if "host" in name else "container" if ("container" in name or "docker" in name or "quota" in name or "migration" in name) else "unknown"
    match = re.search(r"run[_-]?(\\d+)", name)
    run = f"run{int(match.group(1)):02d}" if match else path.stem
    return {"condition": condition, "environment": environment, "run": run}


def discover_csvs(data_root: str | Path, manifest: pd.DataFrame | None = None) -> list[tuple[Path, dict]]:
    data_root = root_path(data_root)
    files = sorted(data_root.rglob("*.csv"))
    return [(path, infer_metadata(path, data_root, manifest)) for path in files]


def read_run(path: str | Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = [str(c).strip().lower() for c in df.columns]
    for col in NUMERIC:
        if col in df:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def output_run_path(output_root: Path, metadata: dict) -> Path:
    return output_root / str(metadata["condition"]) / str(metadata["environment"]) / f"{metadata['run']}.csv"


def save_json(value: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def metadata_from_derived(path: Path, derived_root: Path) -> dict:
    relative = path.relative_to(derived_root)
    if len(relative.parts) < 3:
        raise ValueError(f"Caminho derivado inválido: {path}")
    return {"condition": relative.parts[0], "environment": relative.parts[1], "run": path.stem}


def derived_files(derived_root: str | Path) -> Iterable[tuple[Path, dict]]:
    root = root_path(derived_root)
    for path in sorted(root.rglob("*.csv")):
        if path.name != "index.csv":
            yield path, metadata_from_derived(path, root)
