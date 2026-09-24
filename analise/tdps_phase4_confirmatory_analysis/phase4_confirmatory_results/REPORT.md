# TDPS Phase 4 confirmatory analysis

## Scope

Phase 4A tests controlled blocking. Phase 4B tests whether the same recovery law explains natural ext4 write-path stalls under I/O stress. The confirmatory unit for Phase 4B is a contiguous deadline-miss episode.

## Evidence audit

Phase 4A contains 250 runs. Invalid or incomplete runs: 0. Its registered schedule hash matches the computed hash: `True`.
Phase 4B contains 60 valid runs and 6,000,000 jobs. Invalid or incomplete runs: 0. Its registered schedule hash matches the computed hash: `True`.

Phase 4B source SHA-256: `b9f64037c63540de421a8b39449a1f21fbf1043280ac8f12a3496511b4576cb2`. Binary SHA-256: `936b198629ee8520b1a9a7c52af4c70b956e5910a71eea00584e8a7ff8f5bd4e`. Git commit: `a346e3a40de8c933593dfbb10697d27167e2d2c5`.

## Phase 4A controlled validation

Across 250 controlled runs, 220 were exact and all were within one recovery job. For the 200 non-zero block runs, 170 were exact. The overall mean absolute error was 0.120 jobs.

| level | runs | exact_runs | within_1_runs | mae_jobs | observed_recovery_jobs | predicted_recovery_jobs |
| --- | --- | --- | --- | --- | --- | --- |
| c06 | 40 | 40 | 40 | 0 | 110 | 110 |
| c15 | 40 | 40 | 40 | 0 | 120 | 120 |
| c25 | 40 | 20 | 40 | 0.5 | 160 | 180 |
| c35 | 40 | 40 | 40 | 0 | 270 | 270 |
| c40 | 40 | 30 | 40 | 0.25 | 400 | 410 |

## Phase 4B natural validation

The median write duration remains near 3.6 microseconds in both control and I/O cells. I/O stress changes the extreme tail, not the distribution body. All three control cells have zero deadline misses.

| level | episodes | shocks | shocks_causing_miss | observed_miss_jobs | predicted_miss_jobs | mae_jobs | exact_fraction | within_1_fraction | max_abs_error_jobs |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| c06 | 72 | 105 | 72 | 1116 | 1115 | 0.01389 | 0.9861 | 1 | 1 |
| c25 | 92 | 112 | 95 | 2234 | 2229 | 0.05435 | 0.9457 | 1 | 1 |
| c40 | 119 | 121 | 121 | 7136 | 7081 | 0.4622 | 0.6218 | 0.9244 | 3 |

### Aggregate episode fit

| episodes | observed misses | predicted misses | difference | relative difference | MAE per episode | exact | within 1 job | maximum error |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 283 | 10486 | 10425 | 61 | 0.005817 | 0.2155 | 0.8198 | 0.9682 | 3 |

The natural episode law underpredicts by only 61 jobs out of 10,486 observed misses (0.58%). The mean absolute error is 0.216 job per episode. The maximum episode error is three jobs.

## Slack threshold

The measured control service times imply slack values of 4.394 ms (c06), 2.494 ms (c25), and 0.994 ms (c40). The largest non-miss shocks are 4.008 ms for c06 and 2.455 ms for c25. The smallest miss-causing shocks are 4.611 ms and 2.768 ms, respectively. Every registered c40 shock causes a miss because the minimum shock is 1.020 ms, already above its measured slack.

## Randomized-block inference

| family | test | contrast | estimate | ci_low | ci_high | statistic | p_value | p_value_holm |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| shock incidence | Friedman shock counts across load levels | c06,c25,c40 |  |  |  | 2 | 0.3679 | 0.3679 |
| paired t-tests | Paired t-test deadline misses by randomized block | c25-c06 | 111.8 | -8.916 | 232.5 | 2.095 | 0.06564 | 0.06564 |
| paired t-tests | Paired t-test deadline misses by randomized block | c40-c25 | 490.2 | 143 | 837.4 | 3.194 | 0.01093 | 0.02187 |
| paired t-tests | Paired t-test deadline misses by randomized block | c40-c06 | 602 | 278.8 | 925.2 | 4.214 | 0.002259 | 0.006778 |
| Wilcoxon tests | Wilcoxon signed-rank deadline misses by randomized block | c25-c06 | 109.5 |  |  | 10 | 0.08398 | 0.08398 |
| Wilcoxon tests | Wilcoxon signed-rank deadline misses by randomized block | c40-c25 | 292.5 |  |  | 0 | 0.001953 | 0.005859 |
| Wilcoxon tests | Wilcoxon signed-rank deadline misses by randomized block | c40-c06 | 499.5 |  |  | 0 | 0.001953 | 0.005859 |

Shock counts do not differ significantly across load levels (Friedman p = 0.368). Therefore, the increase in deadline misses is explained by amplification, not by a higher observed incidence of registered shocks. Paired block comparisons show clear amplification for c40 versus c25 and c06. The c25-c06 contrast remains uncertain at n=10 because natural shock magnitudes are highly variable.

## Scientific conclusion

A rare local blocking event becomes a temporally extended degradation episode when it exceeds the available slack. Each subsequent periodic activation removes approximately T-C from the accumulated backlog. Phase 4B therefore generalizes the controlled Phase 4A law to natural write-path stalls, with less than 1% aggregate prediction error.

The result supports a two-part interpretation: the external I/O process determines when and how large a shock is, while the periodic task slack determines how strongly that shock is amplified and how long recovery takes.

## Limitations

The recurrence replay based on measured per-job service demand is explanatory rather than independently predictive, so it is retained only as a diagnostic. The episode-level block/slack law is the primary confirmatory result. The benchmark records write completion at kernel acceptance and does not call fsync; the experiment does not establish storage durability latency. External validity is limited to the evaluated machine, kernel, ext4 configuration, workload, and scheduler setup.

## Figures

- `figures/recovery_law.png`: controlled and natural law fits.
- `figures/slack_threshold.png`: natural transition across the block/slack boundary.
- `figures/miss_amplification.png`: run-level deadline-miss amplification.
