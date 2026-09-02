#!/usr/bin/env python3
import argparse, csv, hashlib, os, random, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent

def bash_config():
    command = f'source "{HERE}/config.sh"; printf "%s\\0" "$RESULT_ROOT" "$REPLICATIONS" "$CAMPAIGN_SEED"'
    raw = subprocess.check_output(['bash', '-c', command])
    return raw.decode().split('\0')[:3]

def completed(run_dir):
    meta = run_dir / 'metadata.env'
    return meta.exists() and 'COMPLETED_AT=' in meta.read_text(errors='replace')

parser = argparse.ArgumentParser(description='Randomized TDPS causal campaign')
group = parser.add_mutually_exclusive_group(required=True)
group.add_argument('--pilot', action='store_true', help='I/O overhead pilot: none, telemetry, full; 3 reps')
group.add_argument('--full', action='store_true', help='control, I/O, churn; configured repetitions; full tracing')
parser.add_argument('--resume', action='store_true')
parser.add_argument('--dry-run', action='store_true')
parser.add_argument('--seed', type=int)
args = parser.parse_args()

result_root, configured_reps, configured_seed = bash_config()
seed = args.seed if args.seed is not None else int(configured_seed)
mode = 'pilot' if args.pilot else 'full'
campaign_dir = Path(result_root) / 'campaigns' / f'{mode}_seed{seed}'
campaign_dir.mkdir(parents=True, exist_ok=True)
schedule_path = campaign_dir / 'schedule.csv'

if schedule_path.exists():
    with schedule_path.open(newline='') as f: schedule = list(csv.DictReader(f))
else:
    rows = []
    if args.pilot:
        for rep in range(1, 4):
            for substrate in ('host', 'container'):
                for trace_mode in ('none', 'telemetry', 'full'):
                    rows.append({'scenario':'io','substrate':substrate,'replication':rep,'trace_mode':trace_mode})
    else:
        for rep in range(1, int(configured_reps) + 1):
            for scenario in ('control', 'io', 'churn'):
                for substrate in ('host', 'container'):
                    rows.append({'scenario':scenario,'substrate':substrate,'replication':rep,'trace_mode':'full'})
    random.Random(seed).shuffle(rows)
    schedule = []
    for sequence, row in enumerate(rows, 1):
        row = {'sequence':sequence, **row}
        row['run_id'] = f"{sequence:04d}_{row['scenario']}_{row['substrate']}_run{row['replication']:02d}_{row['trace_mode']}"
        schedule.append(row)
    with schedule_path.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=schedule[0].keys()); writer.writeheader(); writer.writerows(schedule)

schedule_hash = hashlib.sha256(schedule_path.read_bytes()).hexdigest()
with (campaign_dir / 'campaign.env').open('w') as f:
    f.write(f'MODE={mode}\nSEED={seed}\nSCHEDULE_SHA256={schedule_hash}\nSTARTED_AT={datetime.now(timezone.utc).isoformat()}\n')

if not args.dry_run:
    setup = [str(HERE/'setup_rt_environment.sh')]
    if os.geteuid() != 0: setup.insert(0, 'sudo')
    subprocess.run(setup, check=True)

manifest_path = campaign_dir / 'manifest.csv'
with manifest_path.open('a', newline='') as manifest:
    fields = ['timestamp','sequence','run_id','scenario','substrate','replication','trace_mode','status','exit_code']
    writer = csv.DictWriter(manifest, fieldnames=fields)
    if manifest.tell() == 0: writer.writeheader()
    for row in schedule:
        run_dir = Path(result_root) / 'runs' / row['run_id']
        if completed(run_dir):
            if args.resume: continue
            print(f"refusing to overwrite completed run: {run_dir}", file=sys.stderr); sys.exit(2)
        if run_dir.exists():
            if not args.resume:
                print(f"refusing to overwrite incomplete run: {run_dir}", file=sys.stderr); sys.exit(2)
            failed_root = Path(result_root) / 'failed_runs'
            stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
            archived = failed_root / f"{row['run_id']}__{stamp}"
            suffix = 1
            while archived.exists():
                archived = failed_root / f"{row['run_id']}__{stamp}_{suffix}"
                suffix += 1
            if args.dry_run:
                print(f"would archive incomplete run: {run_dir} -> {archived}", flush=True)
            else:
                failed_root.mkdir(parents=True, exist_ok=True)
                run_dir.rename(archived)
                print(f"archived incomplete run: {run_dir} -> {archived}", flush=True)
        command = [str(HERE/'run_observation.sh'), row['scenario'], row['substrate'],
                   str(row['replication']), row['trace_mode'], str(row['sequence'])]
        print('+', ' '.join(command), flush=True)
        if args.dry_run: continue
        started = datetime.now(timezone.utc).isoformat()
        rc = subprocess.run(command).returncode
        writer.writerow({'timestamp':started, **row, 'status':'completed' if rc == 0 else 'failed', 'exit_code':rc})
        manifest.flush()
        if rc != 0: sys.exit(rc)
