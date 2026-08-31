# TDPS causal tracing suite

This suite implements the narrowed paper design: causal characterization of
large latency shocks under **buffered I/O stress** and **container churn**, with
host/container controls. It uses `containerd + nerdctl + runc`, namespace
`tdps`, one independently restarted interference process per observation, a
seeded randomized schedule, synchronized circular ftrace capture, and
low-frequency system telemetry.

On `cylon`, managed NVMe MSI-X vectors 90, 107, 115, 123, and 131 cannot be
retargeted. A 30-second I/O stress probe produced zero interrupts on all five.
The validation gate therefore accepts them only while their cumulative counts
remain zero. Every observation stores before/after snapshots and is marked
`INVALID_IRQ_ACTIVITY` if any counter changes.

## Experimental unit

One observation is exactly one tuple:

`scenario × substrate × replication × tracing mode`

The interference is started, warmed up, measured for one substrate, and
stopped. It is never reused for the other substrate. Run numbers identify
replications; `sequence` records the randomized chronological order.

## Layout

- `config.sh`: canonical parameters.
- `setup_rt_environment.sh`: runtime RT configuration and hard prechecks.
- `validate_environment.sh`: reproducibility gate; writes environment evidence.
- `build_image.sh`: compiles one binary and embeds the same bytes in the image.
- `calibrate.sh`: seven calibration samples and one fixed median `BENCH_ITERS`.
- `run_campaign.py`: deterministic schedule, manifest, pilot/full execution.
- `analyze_pilot.py`: per-run aggregation for the instrumentation decision.
- `run_observation.sh`: isolated experimental unit and cleanup.
- `collect_trace.sh`: overwriting ftrace ring, frozen two seconds after first shock.
- `collect_telemetry.py`: PSI, VM, dirty/writeback, disk, frequency, temperature.
- `benchmark/periodic_bench.c`: in-memory sampling and shock notification.

## Prerequisites

The boot command line must contain:

```text
idle=poll processor.max_cstate=0 \
isolcpus=domain,managed_irq,3,11 nohz_full=3,11 rcu_nocbs=3,11 \
irqaffinity=0-2,4-10,12-15
```

The machine must be dedicated: `kubelet` inactive, no tasks in `k8s.io`, and
`containerd` active. Required packages include `stress-ng`, `trace-cmd`,
`linux-tools`, `gcc`, `make`, `python3`, `nerdctl`, and BuildKit for the build.
The setup also restricts global unbound workqueues to the housekeeping CPUs.

The IRQ exception list is machine-specific and defaults to
`MANAGED_DORMANT_IRQS=90,107,115,123,131`. Do not reuse it on another machine
without repeating the IRQ ownership and activity probe.

## Preparation

```bash
chmod +x *.sh *.py
sudo ./setup_rt_environment.sh
./build_image.sh
./calibrate.sh
```

Review `${RESULT_ROOT}/calibration.env`; do not recalibrate between conditions.

## Pilot first

The pilot quantifies instrumentation effects for I/O stress, separately for
host and container, with three replications of each mode:

```bash
./run_campaign.py --pilot --dry-run
./run_campaign.py --pilot
./analyze_pilot.py
```

Modes are no instrumentation, telemetry only, and full telemetry+tracing.
Proceed to the full campaign only if the pilot shows acceptable perturbation.

## Full campaign

```bash
./run_campaign.py --full --dry-run
./run_campaign.py --full
```

The default full design contains 60 randomized independent observations:
three scenarios (`control`, `io`, `churn`) × two substrates × ten replications.
Use `--resume` after an interruption; completed observations are never
overwritten.

## Trace semantics

The benchmark reports the first response time at or above 10 ms through a FIFO.
The host watcher adds a trace marker, waits two seconds, then freezes the
overwriting ring buffer. The resulting `trace.dat` therefore contains the
available history before the first qualifying shock and two seconds after it.
If no qualifying shock occurs, the buffer is frozen at observation end.

The trace is supporting causal evidence. The CSV remains authoritative for
latency, wakeup delay, execution time, deadline misses, and backlog recovery.

## Safe restoration after the campaign

The suite does not delete Kubernetes metadata or modify GRUB. To restore the
node after returning its normal kernel command line and rebooting:

```bash
sudo systemctl enable --now kubelet
sudo systemctl start irqbalance 2>/dev/null || true
```
