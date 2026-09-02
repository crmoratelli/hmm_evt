# Changelog

## 1.0.5

- Enables the ftrace ring before writing `TDPS_TRACE_START`, avoiding `EBADF`
  from `trace_marker` on Linux 6.8.
- Adds an enable/write/disable `trace_marker` preflight to environment validation.
- Makes `--resume` archive incomplete runs under `failed_runs/` and repeat only
  the interrupted observation while preserving completed runs.

## 1.0.4

- Stages samples, logs, telemetry, churn records, and trace output in `/dev/shm`.
- Measures managed IRQ deltas strictly across the timed benchmark window.
- Persists observer artifacts only after closing the IRQ interval.
- Accepts nonzero cumulative counters for audited IRQs after earlier runs;
  validity depends on the per-observation delta.

## 1.0.3

- Converts the housekeeping CPU list to the hexadecimal mask required by the
  global workqueue sysfs interface (`0-2,4-10,12-15` becomes `f7f7`).
- Validates the workqueue mask as hexadecimal instead of as a CPU-list string.

## 1.0.2

- Accepts only the five audited, zero-count managed NVMe IRQs on isolated CPUs.
- Captures managed IRQ counters before and after every observation.
- Automatically invalidates an observation if an audited IRQ fires.
- Restricts global unbound workqueues to the housekeeping CPU set.

## 1.0.1

- Removed `eval` from strict environment validation.
- CPU isolation is now validated by parsing the kernel CPU-list format.
- SMT topology accepts either ordering of the sibling pair.

## 1.0.0

- Initial causal tracing campaign for control, I/O stress, and container churn.
