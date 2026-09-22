# TDPS Phase 2B analysis

Reproducible causal analysis of Phase 2. It reconstructs inline deadline-miss
episodes, validates the recurrence with leave-one-run-out overheads, and
decomposes asynchronous end-to-end tail events into service/backlog and
consumer-dispatch delay.

## Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
./run_phase2b.sh /path/to/tdps_phase2_results
```

The output directory contains CSV tables, figures, and `REPORT.md`.

The 3 ms threshold is the experiment's local deadline. Applying it to
asynchronous delivery is an explicit diagnostic, not a claim that the original
experiment specified an end-to-end deadline.

