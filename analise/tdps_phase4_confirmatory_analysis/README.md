# TDPS Phase 4 confirmatory analysis

This package combines Phase 4A (controlled blocking) and Phase 4B (natural ext4 write-path stalls) into one reproducible confirmatory analysis.

## Inputs

- `tdps_phase4_results.zip`: complete Phase 4A evidence archive.
- `tdps_phase4b_results.zip`: complete Phase 4B evidence archive.

The script reads the ZIP archives directly. Extraction is not required.

## Run

```bash
python3 -m pip install -r requirements.txt

python3 run_analysis.py \
  --phase4a /path/to/tdps_phase4_results.zip \
  --phase4b /path/to/tdps_phase4b_results.zip \
  --out phase4_confirmatory_results
```

The output directory contains the integrity audit, run-level and episode-level tables, statistical tests, figures in PNG and PDF, a consolidated report, and a SHA-256 manifest.

## Confirmatory quantities

For Phase 4A, the controlled recovery prediction is:

```text
recovery_jobs = ceil(actual_block / measured_slack)
```

For Phase 4B, the predicted number of consecutive deadline misses in a natural episode is:

```text
miss_jobs = max(0, ceil(accumulated_block / measured_slack) - 1)
```

`accumulated_block` is the sum of write durations above the control median for registered shock jobs (`delivery_duration >= 1 ms`) inside a contiguous deadline-miss episode. The primary validation unit is the episode, not the individual job.

The benchmark records completion at kernel acceptance. It does not call `fsync`, so the experiment does not measure storage durability.

