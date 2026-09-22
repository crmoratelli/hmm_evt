#!/usr/bin/env python3
from __future__ import annotations
import argparse, csv, hashlib, os, random, shutil, subprocess
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
OBS = HERE / "run_phase4_observation.sh"
PREFLIGHT = HERE / "preflight_phase4.sh"

def env_int(name: str, default: int) -> int: return int(os.getenv(name, default))
def levels() -> list[tuple[str, int]]:
    value = os.getenv("PHASE4_LEVELS", "c06:151994,c15:379985,c25:633308,c35:886632,c40:1013293")
    return [(name, int(iters)) for name, iters in (item.split(":", 1) for item in value.split(","))]
def shocks() -> list[int]: return [int(x) for x in os.getenv("PHASE4_SHOCKS_NS", "0,2000000,5000000,10000000,20000000").split(",")]

def schedule(reps: int, seed: int, smoke: bool) -> list[dict[str, int | str]]:
    cells = [(n, i, b) for n, i in levels() for b in shocks()]
    if smoke: cells = [(levels()[0][0], levels()[0][1], 0), (levels()[0][0], levels()[0][1], 10000000), (levels()[-1][0], levels()[-1][1], 0), (levels()[-1][0], levels()[-1][1], 10000000)]
    rng = random.Random(seed); rows = []; seq = 1
    for block in range(1, reps + 1):
        order = cells.copy(); rng.shuffle(order)
        for name, iters, shock in order:
            rows.append(dict(sequence=seq, block=block, replication=block, level=name, iters=iters, shock_ns=shock)); seq += 1
    return rows

def run_id(r): return f"{int(r['sequence']):04d}_{r['level']}_b{int(r['shock_ns']):08d}ns_run{int(r['replication']):02d}"

def main() -> None:
    p = argparse.ArgumentParser(description="TDPS Phase 4 controlled recovery campaign")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true"); g.add_argument("--smoke", action="store_true"); g.add_argument("--full", action="store_true")
    p.add_argument("--resume", action="store_true"); p.add_argument("--block", type=int)
    p.add_argument("--seed", type=int, default=env_int("PHASE4_SEED", 20260922)); p.add_argument("--replications", type=int, default=env_int("PHASE4_REPLICATIONS", 10))
    a = p.parse_args(); reps = 1 if a.smoke else a.replications
    default_root = Path.home() / ("tdps_phase4_smoke" if a.smoke else "tdps_phase4_results")
    root = Path(os.getenv("PHASE4_SMOKE_ROOT" if a.smoke else "PHASE4_RESULT_ROOT", str(default_root)))
    rows = schedule(reps, a.seed, a.smoke); selected = [r for r in rows if a.block is None or r["block"] == a.block]
    if a.block is not None and not selected: p.error(f"block outside 1..{reps}")
    for r in selected: print(f"{r['sequence']:03d}: block={r['block']} level={r['level']} iters={r['iters']} shock_ns={r['shock_ns']}")
    print(f"runs={len(selected)} cells_per_block={len(rows)//reps}")
    if a.dry_run: return
    root.mkdir(parents=True, exist_ok=True); (root / "runs").mkdir(exist_ok=True); (root / "failed_runs").mkdir(exist_ok=True)
    path = root / "schedule.csv"; fields = ["sequence", "block", "replication", "level", "iters", "shock_ns"]
    normalized = [{k: str(v) for k, v in r.items()} for r in rows]
    if not path.exists():
        with path.open("x", newline="") as f: w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)
        (root / "campaign.env").write_text(f"SEED={a.seed}\nREPLICATIONS={reps}\nSCHEDULE_SHA256={hashlib.sha256(path.read_bytes()).hexdigest()}\nCREATED_AT={datetime.now(timezone.utc).isoformat()}\n")
    else:
        with path.open(newline="") as f: existing = list(csv.DictReader(f))
        if existing != normalized: raise SystemExit("existing schedule differs")
        if not a.resume: raise SystemExit("schedule exists; use --resume")
    subprocess.run([str(PREFLIGHT), "--check-only"], check=True, env={**os.environ, "PHASE4_RESULT_ROOT": str(root)})
    for r in selected:
        target = root / "runs" / run_id(r)
        if (target / "COMPLETED").exists() and a.resume: print(f"skip completed: {target.name}"); continue
        if target.exists():
            if not a.resume: raise SystemExit(f"refusing to overwrite {target}")
            archived = root / "failed_runs" / f"{target.name}__{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"; shutil.move(str(target), str(archived))
        cmd = [str(OBS), str(r["level"]), str(r["iters"]), str(r["shock_ns"]), str(r["replication"]), str(r["block"]), str(r["sequence"])]
        print("+", " ".join(cmd), flush=True)
        rc = subprocess.run(cmd, env={**os.environ, "PHASE4_ACTIVE_ROOT": str(root), "PHASE4_PROFILE": "smoke" if a.smoke else "full"}).returncode
        if rc: raise SystemExit(rc)
    subprocess.run(["python3", str(HERE / "analyze_phase4.py"), "--root", str(root)], check=True)

if __name__ == "__main__": main()
