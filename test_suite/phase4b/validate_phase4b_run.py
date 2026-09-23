#!/usr/bin/env python3
import argparse
from pathlib import Path
import pandas as pd

p=argparse.ArgumentParser(); p.add_argument('--run-dir',type=Path,required=True); p.add_argument('--jobs',type=int,required=True); p.add_argument('--cpu',type=int,required=True); p.add_argument('--record-bytes',type=int,default=64); a=p.parse_args()
f=a.run_dir/'samples.csv'; s=a.run_dir/'functional.bin'
if not f.exists(): raise SystemExit('missing samples.csv')
d=pd.read_csv(f)
required={'job','release_ns','start_ns','compute_finish_ns','output_start_ns','output_finish_ns','accepted','dropped','delivery_start_ns','delivery_finish_ns','delivery_errno','cpu'}
missing=required-set(d.columns)
if missing: raise SystemExit(f'missing columns: {sorted(missing)}')
assert len(d)==a.jobs, (len(d),a.jobs)
assert d.job.tolist()==list(range(a.jobs))
assert (d.cpu==a.cpu).all(), 'benchmark migrated from isolated CPU'
assert (d.accepted==1).all() and (d.dropped==0).all() and (d.delivery_errno==0).all()
assert (d.output_finish_ns>=d.output_start_ns).all()
assert (d.delivery_finish_ns>=d.delivery_start_ns).all()
assert s.stat().st_size==a.jobs*a.record_bytes, (s.stat().st_size,a.jobs*a.record_bytes)
local=d.output_finish_ns-d.release_ns
misses=int((local>5_000_000).sum())
print(f'RUN_VALID={a.run_dir.name} jobs={len(d)} local_misses={misses} max_write_ns={int((d.delivery_finish_ns-d.delivery_start_ns).max())}')

