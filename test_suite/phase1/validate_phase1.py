#!/usr/bin/env python3
"""Functional gate only: no stress, no tracing, no environment mutation."""
import argparse, csv, hashlib, json, os, platform, random, re, resource, signal, statistics, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
p = argparse.ArgumentParser()
p.add_argument('--output', type=Path, required=True)
p.add_argument('--iters', type=int, required=True)
p.add_argument('--cpu', type=int, default=min(os.sched_getaffinity(0)))
p.add_argument('--logger-cpu', type=int)
p.add_argument('--rt', action='store_true', help='SCHED_FIFO 80 + mlock; requires privileges')
p.add_argument('--backend', choices=['host','container'], default='host')
p.add_argument('--runtime', default='nerdctl')
p.add_argument('--namespace', default='tdps')
p.add_argument('--image', default='localhost/tdps/periodic-bench:phase1-v2')
a = p.parse_args()
if a.iters <= 0: p.error('--iters must be positive')
if a.logger_cpu is None:
    a.logger_cpu = next((c for c in sorted(os.sched_getaffinity(0)) if c != a.cpu), a.cpu)
if a.logger_cpu == a.cpu: p.error('logger needs a separate logical CPU; choose a housekeeping CPU')
a.output = a.output.resolve(); a.output.mkdir(parents=True, exist_ok=False)
# Capture the execution environment before the first test; never tune it here.
for src,name in [('/proc/cmdline','cmdline.txt'),('/proc/interrupts','interrupts_before.txt')]:
    (a.output/name).write_text(Path(src).read_text())
siblings=Path(f'/sys/devices/system/cpu/cpu{a.cpu}/topology/thread_siblings_list').read_text().strip()
sibling_set=set()
for part in siblings.split(','):
    bounds=list(map(int,part.split('-')))
    sibling_set.update(range(bounds[0],bounds[-1]+1))
if a.rt and a.logger_cpu in sibling_set: raise RuntimeError('logger must not share the RT physical core')
freq=[]
for directory in sorted(Path('/sys/devices/system/cpu').glob('cpu[0-9]*/cpufreq')):
    entry={key:(directory/key).read_text().strip() for key in ['scaling_governor','scaling_min_freq','scaling_max_freq']}
    entry['cpu']=directory.parent.name;freq.append(entry)
if a.rt:
    if not freq or any(x['scaling_governor']!='performance' or x['scaling_min_freq']!='3800000' or x['scaling_max_freq']!='3800000' for x in freq):
        raise RuntimeError('RT gate requires performance and min=max=3800000 on all cpufreq CPUs')
    boost=Path('/sys/devices/system/cpu/cpufreq/boost')
    if not boost.exists() or boost.read_text().strip()!='0': raise RuntimeError('RT gate requires boost=0')
report = {'cpufreq':freq,'rt_cpu_siblings':siblings,'platform':platform.platform(), 'python':sys.version, 'backend':a.backend,
          'rt':a.rt, 'cpu':a.cpu,'logger_cpu':a.logger_cpu,'iters':a.iters,
          'source_sha256':hashlib.sha256((HERE/'periodic_v2.c').read_bytes()).hexdigest(),
          'binary_sha256':hashlib.sha256((HERE/'periodic_v2').read_bytes()).hexdigest(),
          'tests':[], 'limitations':['Functional validation, not a cylon latency campaign.',
          'CPU frequency, isolation, IRQ routing and physical-core separation require independent verification.']}
if a.backend == 'container':
    rt = [a.runtime] + (['--namespace',a.namespace] if a.runtime == 'nerdctl' else [])
    info = subprocess.check_output(rt+['image','inspect',a.image], text=True)
    (a.output/'image_inspect.json').write_text(info)
    # Require exact identity of the copied host executable in the container.
    embedded = subprocess.check_output(rt+['run','--rm','--net','none','--entrypoint','/usr/bin/sha256sum',a.image,
                                      '/usr/local/bin/periodic_v2'],text=True).split()[0]
    if embedded != report['binary_sha256']: raise RuntimeError('container binary differs from host')


def run(name, mode='deferred', extra=(), expected=0, period=1000000, jobs=100):
    folder=a.output/name; folder.mkdir()
    sample=folder/'samples.csv'; sink=folder/'functional.bin'
    paths = ('/out/samples.csv','/out/functional.bin') if a.backend=='container' else (str(sample),str(sink))
    args=['--mode',mode,'--iters',str(a.iters),'--jobs',str(jobs),'--period',str(period),
          '--deadline',str(period),'--out',paths[0],'--sink',paths[1],
          '--logger-cpu',str(a.logger_cpu),*extra]
    if a.rt: args+=['--mlock']
    if a.backend=='host':
        cmd=(['chrt','-f','80'] if a.rt else [])+['taskset','-c',str(a.cpu),str(HERE/'periodic_v2'),*args]
    else:
        cmd=rt+['run','--rm','--net','none','--cpuset-cpus',f'{a.cpu},{a.logger_cpu}',
                '--volume',f'{folder}:/out','--entrypoint','/usr/bin/taskset']
        if a.rt: cmd+=['--cap-add','SYS_NICE','--cap-add','IPC_LOCK','--ulimit','rtprio=99','--ulimit','memlock=-1']
        cmd += [a.image,'-c',str(a.cpu)]+(['chrt','-f','80'] if a.rt else [])+['/usr/local/bin/periodic_v2',*args]
    (folder/'command.json').write_text(json.dumps(cmd,indent=2))
    r=subprocess.run(cmd,capture_output=True,text=True,timeout=120)
    (folder/'benchmark.log').write_text(r.stderr+r.stdout)
    if a.rt and expected==0: assert re.search(r'policy=1 priority=80 ', r.stderr) and 'mlock=1' in r.stderr
    if r.returncode != expected: raise AssertionError(f'{name}: exit {r.returncode}, expected {expected}: {r.stderr}')
    rows=[]
    if expected==0:
        with sample.open() as f: rows=[{k:int(v) for k,v in row.items()} for row in csv.DictReader(f)]
        assert len(rows)==jobs
        ids=[]; minimal='--minimal' in extra
        for j,s in enumerate(rows):
            assert s['job']==j and s['schema_version']==2
            assert s['release_ns']==rows[0]['release_ns']+j*period
            assert s['release_ns']<=s['start_ns']<=s['compute_finish_ns']==s['finish_ns']
            assert s['execution_ns']==s['finish_ns']-s['start_ns']
            assert s['wakeup_delay_ns']==s['start_ns']-s['release_ns']
            assert s['response_ns']==s['finish_ns']-s['release_ns']
            assert s['lateness_ns']==s['response_ns']-period
            assert s['miss']==int(s['lateness_ns']>0)
            assert s['accepted']+s['dropped']==1 and s['delivery_errno']==0
            if not minimal: assert s['compute_finish_ns']<=s['output_start_ns']<=s['output_finish_ns'] and s['cpu']==a.cpu
            if s['accepted']:
                assert s['delivery_start_ns']>=s['compute_finish_ns']
                assert s['delivery_finish_ns']>=s['delivery_start_ns']
                if mode=='deferred': assert s['delivery_start_ns']>=rows[-1]['compute_finish_ns']
                if mode=='inline': assert s['output_start_ns']<=s['delivery_start_ns']<=s['delivery_finish_ns']<=s['output_finish_ns']
                ids.append(j)
            else: assert s['delivery_start_ns']==s['delivery_finish_ns']==0
        data=sink.read_bytes()
        assert len(data)==64*len(ids)
        for offset,j in enumerate(ids):
            record=data[offset*64:(offset+1)*64]
            assert int.from_bytes(record[:8],'little')==j and record[8:]==b'T'*56
        if name=='queue_full': assert sum(s['dropped'] for s in rows)>0
        if name=='shock':
            assert rows[10]['output_finish_ns']-rows[10]['output_start_ns']>=20000000
            assert rows[11]['wakeup_delay_ns']>=10000000
        result={'name':name,'passed':True,'jobs':jobs,'accepted':len(ids),'dropped':jobs-len(ids),
                'misses':sum(s['miss'] for s in rows),
                'median_execution_ns':statistics.median(s['execution_ns'] for s in rows),
                'median_response_ns':statistics.median(s['response_ns'] for s in rows),
                'max_response_ns':max(s['response_ns'] for s in rows),
                'median_postcompute_instrumented_ns':None if minimal else statistics.median(s['output_finish_ns']-s['compute_finish_ns'] for s in rows)}
    else: result={'name':name,'passed':True,'expected_exit':expected}
    report['tests'].append(result)
    print(json.dumps(result),flush=True)
    return rows

try:
    for mode in ('deferred','inline','async'): run(mode,mode)
    run('queue_full','async',['--queue','1','--test-logger-delay-ns','5000000'],period=100000,jobs=200)
    run('shock','inline',['--test-shock-job','10','--test-shock-ns','20000000'])
    run('legacy_rejected','stream',expected=2)
    # Local host failure injection uses /dev/full without touching any user's sink.
    if a.backend=='host':
        folder=a.output/'io_error';folder.mkdir();(folder/'functional.bin').symlink_to('/dev/full')
        # O_EXCL must reject an existing path, including a symlink; never follows it.
        r=subprocess.run([str(HERE/'periodic_v2'),'--mode','inline','--iters',str(a.iters),
                          '--jobs','1','--out',str(folder/'samples.csv'),'--sink',str(folder/'functional.bin')],capture_output=True,text=True)
        assert r.returncode==1 and 'open sink' in r.stderr
        report['tests'].append({'name':'existing_sink_rejected','passed':True})
        # Real write failure: ignore SIGXFSZ and cap child file sizes at 64 bytes.
        # The second functional record must fail with EFBIG; CSV export can fail too.
        faildir=a.output/'write_error'; faildir.mkdir()
        def file_limit():
            signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
            resource.setrlimit(resource.RLIMIT_FSIZE,(64,64))
        r=subprocess.run([str(HERE/'periodic_v2'),'--mode','inline','--iters',str(a.iters),
                          '--jobs','3','--out',str(faildir/'samples.csv'),'--sink',str(faildir/'functional.bin')],
                         capture_output=True,text=True,preexec_fn=file_limit)
        (faildir/'benchmark.log').write_text(r.stderr)
        assert r.returncode==1 and 'delivery_errors=2' in r.stderr
        report['tests'].append({'name':'real_write_error_propagated','passed':True})
    rng=random.Random(20260909)
    for block in range(5):
        variants=['minimal','instrumented'];rng.shuffle(variants)
        for variant in variants:
            run(f'overhead_{block}_{variant}',extra=['--minimal'] if variant=='minimal' else [],jobs=200)
    (a.output/'interrupts_after.txt').write_text(Path('/proc/interrupts').read_text())
    report['status']='passed'
except Exception as exc:
    report['status']='failed';report['error']=repr(exc)
    raise
finally:
    (a.output/'validation.json').write_text(json.dumps(report,indent=2)+'\n')
