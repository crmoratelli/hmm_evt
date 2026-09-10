# TDPS Phase 3A — paired causal pilot

This launcher runs only the pre-registered short intervention placed between
phases 1 and 2: host, SCHED_FIFO, inline functional output, and identical I/O
stress, comparing an ext4 sink with a tmpfs sink.

The default schedule has five paired blocks (ten independent observations),
500 seconds per observation. The order inside each block is randomized with a
fixed seed. Every observation restarts the interference, performs warm-up,
captures low-frequency telemetry, checks the audited managed IRQ counters, and
waits for dirty/writeback recovery. Heavy tracing is deliberately excluded
from this first paired contrast because periodic_v2 has no synchronized shock
notification yet.

The host is the only substrate in Phase 3A. Therefore neither Docker nor
nerdctl launches the benchmark here; nerdctl remains the canonical runtime for
the later container experiments.

```bash
chmod +x phase3a/*.sh phase3a/*.py
phase3a/preflight_phase3a.sh
phase3a/run_phase3a_campaign.py --dry-run
phase3a/run_phase3a_campaign.py
```

Resume an interrupted campaign with `--resume`. Completed observations are
never overwritten; incomplete directories are moved to `failed_runs/`.
