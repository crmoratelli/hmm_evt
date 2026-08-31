# Changelog

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
