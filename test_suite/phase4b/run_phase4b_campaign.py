#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,hashlib,os,random,shutil,subprocess
from datetime import datetime,timezone
from pathlib import Path
HERE=Path(__file__).resolve().parent
LEVELS={'c06':151994,'c25':633308,'c40':1013293}; SCENARIOS=('control','io')
def ei(n,d): return int(os.getenv(n,str(d)))
def schedule(reps,seed):
 r=random.Random(seed); out=[]; seq=1
 for block in range(1,reps+1):
  cells=[(l,s) for l in LEVELS for s in SCENARIOS]; r.shuffle(cells)
  for level,scenario in cells: out.append({'sequence':seq,'block':block,'replication':block,'level':level,'iters':LEVELS[level],'scenario':scenario}); seq+=1
 return out
def rid(x): return f"{int(x['sequence']):04d}_{x['level']}_{x['scenario']}_run{int(x['replication']):02d}"
def main():
 p=argparse.ArgumentParser(); g=p.add_mutually_exclusive_group(required=True); g.add_argument('--dry-run',action='store_true'); g.add_argument('--smoke',action='store_true'); g.add_argument('--full',action='store_true'); p.add_argument('--resume',action='store_true'); p.add_argument('--block',type=int); p.add_argument('--seed',type=int,default=ei('PHASE4B_SEED',20260922)); p.add_argument('--replications',type=int,default=ei('PHASE4B_REPLICATIONS',10)); a=p.parse_args()
 reps=1 if a.smoke else a.replications; duration=ei('PHASE4B_SMOKE_DURATION_S',30) if a.smoke else ei('PHASE4B_DURATION_S',500); profile='smoke' if a.smoke else 'full'; root=Path(os.getenv('PHASE4B_SMOKE_ROOT' if a.smoke else 'PHASE4B_RESULT_ROOT',str(Path.home()/f'tdps_phase4b_{profile}')))
 rows=schedule(reps,a.seed); selected=[x for x in rows if a.block is None or x['block']==a.block]
 if not selected: p.error('block outside schedule')
 overhead=ei('PHASE4B_WARMUP_S',10)+ei('PHASE4B_BETWEEN_S',15)
 for x in selected: print(f"{x['sequence']:03}: block={x['block']} {x['level']} {x['scenario']}")
 print(f"runs={len(selected)} nominal_seconds={len(selected)*duration} minimum_planned_seconds={len(selected)*(duration+overhead)}")
 if a.dry_run:return
 (root/'runs').mkdir(parents=True,exist_ok=True); (root/'failed_runs').mkdir(exist_ok=True); fields=['sequence','block','replication','level','iters','scenario']; sp=root/'schedule.csv'
 normalized=[{k:str(v) for k,v in x.items()} for x in rows]
 if not sp.exists():
  with sp.open('x',newline='') as f: w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)
  (root/'campaign.env').write_text(f"PROFILE={profile}\nSEED={a.seed}\nREPLICATIONS={reps}\nDURATION_S={duration}\nSCHEDULE_SHA256={hashlib.sha256(sp.read_bytes()).hexdigest()}\nCREATED_AT={datetime.now(timezone.utc).isoformat()}\n")
 else:
  with sp.open(newline='') as f: old=list(csv.DictReader(f))
  if old!=normalized: raise SystemExit('existing schedule differs from requested campaign')
  if not a.resume: raise SystemExit('schedule exists; use --resume')
 env={**os.environ,'PHASE4B_RESULT_ROOT':str(root)}; subprocess.run([str(HERE/'preflight_phase4b.sh'),'--check-only'],check=True,env=env)
 ap=root/'attempts.csv'
 with ap.open('a',newline='') as f:
  af=fields+['run_id','started_at','status','exit_code']; w=csv.DictWriter(f,fieldnames=af)
  if f.tell()==0:w.writeheader()
  for x in selected:
   target=root/'runs'/rid(x)
   if (target/'COMPLETED').exists():
    if a.resume: print('skip completed:',target.name); continue
    raise SystemExit(f'refusing overwrite: {target}')
   if target.exists():
    if not a.resume: raise SystemExit(f'incomplete run exists: {target}')
    shutil.move(str(target),str(root/'failed_runs'/f"{target.name}__{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"))
   cmd=[str(HERE/'run_phase4b_observation.sh'),x['level'],str(x['iters']),x['scenario'],str(x['replication']),str(x['block']),str(x['sequence'])]; print('+',' '.join(cmd),flush=True)
   rc=subprocess.run(cmd,env={**os.environ,'PHASE4B_ACTIVE_ROOT':str(root),'PHASE4B_ACTIVE_DURATION_S':str(duration),'PHASE4B_PROFILE':profile}).returncode
   w.writerow({**x,'run_id':rid(x),'started_at':datetime.now(timezone.utc).isoformat(),'status':'completed' if rc==0 else 'failed','exit_code':rc}); f.flush()
   if rc: raise SystemExit(rc)
 subprocess.run(['python3',str(HERE/'analyze_phase4b.py'),'--root',str(root)],check=True)
if __name__=='__main__':main()

