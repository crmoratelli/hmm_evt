# TDPS Phase 4B — natural recovery under ext4 I/O stress

Phase 4B tests whether the recovery mechanism confirmed with controlled blocks in Phase 4A also explains naturally occurring synchronous-write stalls. It deliberately fixes the architecture to **inline**, the substrate to **host**, and `T=D=5 ms`.

## Registered design

- execution levels: `c06`, `c25`, `c40`;
- scenarios: `control`, `io`;
- I/O load: `stress-ng --io 4 --hdd 2 --hdd-bytes 10G` on the same ext4 filesystem as the 64-byte functional sink;
- 10 randomized blocks (60 observations), 500 s per observation;
- benchmark on isolated CPU 3 with `SCHED_FIFO/80`; samples and telemetry staged on tmpfs;
- primary deadline response: `output_finish_ns - release_ns` (includes the inline write);
- natural shock: synchronous delivery duration at least 1 ms;
- mechanistic check: work-conserving recurrence replay with measured per-job service demand.

The full measurement time is 8 h 20 min. Warm-up and mandatory spacing add at least 25 min, so reserve about **9–10 hours**.

## Install and preflight

From `test_suite`:

```bash
python3 -m pip install -r phase4b/requirements.txt
phase4b/preflight_phase4b.sh
```

The preflight requires the common files already used by earlier phases (`lib.sh`, `collect_telemetry.py`, `validate_environment.sh`) and `phase1/periodic_v2.c`. The results path and stress temporary path must be on the same ext4 filesystem; staging must be tmpfs.

## Smoke and full campaign

```bash
phase4b/run_phase4b_campaign.py --smoke
cat ~/tdps_phase4b_smoke/REPORT.md

phase4b/run_phase4b_campaign.py --full
```

Resume safely after interruption:

```bash
phase4b/run_phase4b_campaign.py --full --resume
```

Run one registered block (six observations), useful for overnight partitions:

```bash
phase4b/run_phase4b_campaign.py --full --block 1
phase4b/run_phase4b_campaign.py --full --block 2 --resume
```

Outputs include `schedule.csv`, immutable schedule hash in `campaign.env`, per-run evidence under `runs/`, and `run_summary.csv`, `cell_summary.csv`, and `REPORT.md`.
