#!/usr/bin/env python3
from __future__ import annotations
import argparse,math
from pathlib import Path
import pandas as pd
def markdown_table(frame):
 cols=list(frame.columns)
 def clean(value): return str(value).replace('|','\\|').replace('\n',' ')
 lines=['| '+' | '.join(map(clean,cols))+' |','| '+' | '.join('---' for _ in cols)+' |']
 lines.extend('| '+' | '.join(clean(value) for value in row)+' |' for row in frame.itertuples(index=False,name=None))
 return '\n'.join(lines)
def meta(path):
 out={}
 for line in path.read_text().splitlines():
  if '=' in line:
   k,v=line.split('=',1); out[k]=v
 return out
def episodes(mask):
 ids=[]; cur=-1; prev=False
 for hit in mask:
  if hit and not prev: cur+=1
  ids.append(cur if hit else -1); prev=bool(hit)
 return ids,cur+1
def one(run,threshold):
 m=meta(run/'metadata.env'); d=pd.read_csv(run/'samples.csv'); service=d.output_finish_ns-d.start_ns; write=d.delivery_finish_ns-d.delivery_start_ns; response=d.output_finish_ns-d.release_ns; miss=response>int(m['DEADLINE_NS']); shock=write>=threshold; ep,n_ep=episodes(miss.tolist())
 # Work-conserving recurrence driven by the measured per-job service demand.
 idle=(d.start_ns-d.release_ns)[pd.concat([pd.Series([True]),d.output_finish_ns.iloc[:-1].reset_index(drop=True)<=d.release_ns.iloc[1:].reset_index(drop=True)],ignore_index=True)]
 idle_over=int(idle.median()) if len(idle) else int((d.start_ns-d.release_ns).median()); pred=[]; finish=0
 for i,row in d.iterrows():
  start=int(row.release_ns)+idle_over if i==0 or finish<=int(row.release_ns) else finish
  finish=start+int(service.iloc[i]); pred.append(finish-int(row.release_ns)>int(m['DEADLINE_NS']))
 pred=pd.Series(pred); exact=float((pred.values==miss.values).mean())
 return {'run':run.name,'level':m['LEVEL'],'scenario':m['SCENARIO'],'replication':int(m['REPLICATION']),'jobs':len(d),'median_compute_ns':float((d.compute_finish_ns-d.start_ns).median()),'median_write_ns':float(write.median()),'p99_write_ns':float(write.quantile(.99)),'max_write_ns':int(write.max()),'shock_jobs':int(shock.sum()),'local_deadline_misses':int(miss.sum()),'miss_episodes':n_ep,'longest_miss_episode_jobs':max(pd.Series(ep)[pd.Series(ep)>=0].value_counts().max() if n_ep else 0,0),'max_local_response_ns':int(response.max()),'recurrence_accuracy':exact,'recurrence_fp':int((pred&~miss).sum()),'recurrence_fn':int((~pred&miss).sum())}
def main():
 p=argparse.ArgumentParser(); p.add_argument('--root',type=Path,required=True); p.add_argument('--shock-threshold-ns',type=int,default=1_000_000); a=p.parse_args(); runs=[]
 for r in sorted((a.root/'runs').iterdir()):
  if (r/'COMPLETED').exists(): runs.append(one(r,a.shock_threshold_ns))
 if not runs: raise SystemExit('no completed runs')
 df=pd.DataFrame(runs); df.to_csv(a.root/'run_summary.csv',index=False)
 cell=df.groupby(['level','scenario'],as_index=False).agg(runs=('run','count'),jobs=('jobs','sum'),median_write_ns=('median_write_ns','median'),p99_write_ns=('p99_write_ns','median'),max_write_ns=('max_write_ns','max'),shock_jobs=('shock_jobs','sum'),local_deadline_misses=('local_deadline_misses','sum'),miss_episodes=('miss_episodes','sum'),mean_recurrence_accuracy=('recurrence_accuracy','mean'),recurrence_fp=('recurrence_fp','sum'),recurrence_fn=('recurrence_fn','sum')); cell.to_csv(a.root/'cell_summary.csv',index=False)
 report=['# TDPS Phase 4B - natural ext4 I/O shocks','',f'Valid runs: {len(df)}',f'Jobs: {int(df.jobs.sum())}',f'Shock threshold: {a.shock_threshold_ns} ns','', 'The deadline quantity is local completion: `output_finish_ns - release_ns`.','The recurrence model replays measured per-job inline service demand under a work-conserving periodic server.','',markdown_table(cell),'']
 (a.root/'REPORT.md').write_text('\n'.join(report)); print(f'PHASE4B_ANALYSIS_COMPLETE={a.root} runs={len(df)} cells={len(cell)}')
if __name__=='__main__':main()
