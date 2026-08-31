#!/usr/bin/env python3
import argparse, json, os, signal, time
from pathlib import Path

running = True
def stop(*_):
    global running
    running = False

signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)

def read_text(path):
    try: return Path(path).read_text().strip()
    except OSError: return None

def key_values(path, wanted=None):
    result = {}
    text = read_text(path)
    if text is None: return result
    for line in text.splitlines():
        parts = line.replace(':', '').split()
        if len(parts) >= 2 and (wanted is None or parts[0] in wanted):
            try: result[parts[0]] = int(parts[1])
            except ValueError: pass
    return result

def pressure(kind):
    text = read_text(f"/proc/pressure/{kind}")
    result = {}
    if not text: return result
    for line in text.splitlines():
        parts = line.split()
        row = {}
        for item in parts[1:]:
            key, value = item.split('=', 1)
            row[key] = float(value) if key != 'total' else int(value)
        result[parts[0]] = row
    return result

def frequencies():
    result = {}
    for path in Path('/sys/devices/system/cpu').glob('cpu[0-9]*/cpufreq/scaling_cur_freq'):
        value = read_text(path)
        if value: result[path.parts[-3]] = int(value)
    return result

def temperatures():
    result = {}
    for path in Path('/sys/class/thermal').glob('thermal_zone*/temp'):
        value = read_text(path)
        if value:
            label = read_text(path.parent / 'type') or path.parent.name
            result[label] = int(value)
    return result

def diskstats():
    text = read_text('/proc/diskstats') or ''
    rows = {}
    for line in text.splitlines():
        p = line.split()
        if len(p) >= 14 and not p[2].startswith(('loop', 'ram')):
            rows[p[2]] = [int(x) for x in p[3:14]]
    return rows

parser = argparse.ArgumentParser()
parser.add_argument('--out', required=True)
parser.add_argument('--interval', type=float, default=0.25)
args = parser.parse_args()

vm_keys = {'pgpgin','pgpgout','pswpin','pswpout','pgfault','pgmajfault',
           'nr_dirty','nr_writeback','nr_dirtied','nr_written',
           'compact_stall','allocstall_normal','allocstall_movable'}
mem_keys = {'Dirty','Writeback','WritebackTmp','MemAvailable','Cached','Buffers'}

with open(args.out, 'w', buffering=1) as out:
    deadline = time.monotonic()
    while running:
        record = {
            'monotonic_ns': time.monotonic_ns(), 'realtime_ns': time.time_ns(),
            'loadavg': os.getloadavg(),
            'pressure': {k: pressure(k) for k in ('cpu','io','memory')},
            'meminfo_kb': key_values('/proc/meminfo', mem_keys),
            'vmstat': key_values('/proc/vmstat', vm_keys),
            'diskstats': diskstats(), 'frequency_khz': frequencies(),
            'temperature_millic': temperatures(),
        }
        out.write(json.dumps(record, separators=(',', ':')) + '\n')
        deadline += args.interval
        time.sleep(max(0.0, deadline - time.monotonic()))
