#!/usr/bin/env python3
import csv, statistics, subprocess
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
root = subprocess.check_output([
    'bash', '-c', f'source "{HERE}/config.sh"; printf %s "$RESULT_ROOT"'
], text=True)
runs = Path(root) / 'runs'
groups = defaultdict(list)

def quantile(values, p):
    values = sorted(values)
    return values[min(len(values)-1, int(p*(len(values)-1)))]

for directory in sorted(runs.glob('*_io_*')):
    meta_path, sample_path = directory/'metadata.env', directory/'samples.csv'
    if not meta_path.exists() or not sample_path.exists(): continue
    meta = dict(line.split('=', 1) for line in meta_path.read_text().splitlines() if '=' in line)
    if meta.get('TRACE_MODE') not in {'none','telemetry','full'}: continue
    with sample_path.open(newline='') as f: rows = list(csv.DictReader(f))
    response = [int(r['response_ns']) for r in rows]
    wakeup = [int(r['wakeup_delay_ns']) for r in rows]
    execution = [int(r['execution_ns']) for r in rows]
    groups[(meta['SUBSTRATE'], meta['TRACE_MODE'])].append({
        'p99': quantile(response, .99), 'p999': quantile(response, .999),
        'max': max(response), 'max_wakeup': max(wakeup),
        'median_execution': statistics.median(execution),
        'miss_rate': sum(int(r['miss']) for r in rows)/len(rows),
    })

out_dir = Path(root) / 'campaigns' / 'pilot_analysis'
out_dir.mkdir(parents=True, exist_ok=True)
fields = ['substrate','trace_mode','runs','median_p99_ns','median_p999_ns','median_max_ns',
          'median_max_wakeup_ns','median_execution_ns','median_miss_rate']
results = []
for key, records in sorted(groups.items()):
    substrate, mode = key
    median = lambda name: statistics.median(r[name] for r in records)
    results.append(dict(substrate=substrate, trace_mode=mode, runs=len(records),
        median_p99_ns=median('p99'), median_p999_ns=median('p999'),
        median_max_ns=median('max'), median_max_wakeup_ns=median('max_wakeup'),
        median_execution_ns=median('median_execution'), median_miss_rate=median('miss_rate')))

with (out_dir/'pilot_summary.csv').open('w', newline='') as f:
    writer=csv.DictWriter(f, fieldnames=fields); writer.writeheader(); writer.writerows(results)

with (out_dir/'pilot_report.md').open('w') as f:
    f.write('# Pilot instrumentation report\n\n')
    f.write('| Substrate | Mode | Runs | median p99 (µs) | median p99.9 (µs) | median max (µs) | median execution (µs) |\n')
    f.write('|---|---:|---:|---:|---:|---:|---:|\n')
    for r in results:
        f.write(f"| {r['substrate']} | {r['trace_mode']} | {r['runs']} | "
                f"{r['median_p99_ns']/1000:.3f} | {r['median_p999_ns']/1000:.3f} | "
                f"{r['median_max_ns']/1000:.3f} | {r['median_execution_ns']/1000:.3f} |\n")
print(out_dir/'pilot_report.md')
