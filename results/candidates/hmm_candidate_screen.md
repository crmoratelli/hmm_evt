# Triagem de candidatos a HMM

A recomendação é uma triagem, não uma seleção de modelo. HMM só deve ser comparado a modelos independentes e AR(1) em validação fora da amostra.

| condition | environment | scenario | runs | median_response_ns | p99_response_ns | mean_miss_rate | max_miss_rate | temporal_runs | mean_acf_lag1 | mean_abs_acf_lag1 | fraction_significant_lag1 | fraction_excess_high_runs | median_high_run_max | tail_ratio_p99_median | recommendation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cfs_pinned | container | baseline_cfs | 10 | 997222.5 | 1295874.0 | 0.0 | 0.0 | 10 | 0.9717 | 0.9717 | 1.0 | 1.0 | 12.5 | 1.2995 | HMM candidato |
| cfs_pinned | host | baseline_cfs | 10 | 1055698.5 | 1370416.5 | 0.0 | 0.0 | 10 | 0.9713 | 0.9713 | 1.0 | 1.0 | 6.5 | 1.2981 | HMM candidato |
| container_churn | container | churn_runtime | 10 | 605448.5 | 607644.5 | 0.0006 | 0.0065 | 10 | 0.1127 | 0.1127 | 0.9 | 0.5 | 3.5 | 1.0036 | HMM candidato |
| interference | container | interf_io | 10 | 603144.5 | 250978484.0 | 0.0257 | 0.0518 | 10 | 0.859 | 0.859 | 1.0 | 0.8 | 381.0 | 416.1167 | HMM candidato |
| interference | host | interf_io | 10 | 603539.0 | 110500958.5 | 0.0183 | 0.0397 | 10 | 0.8907 | 0.8907 | 1.0 | 0.9 | 335.0 | 183.0883 | HMM candidato |
| shared_cpuset_contention | container | sharing_shared_pool_k12 | 10 | 650613.5 | 3027086.0 | 0.0344 | 0.085 | 10 | -0.1676 | 0.1676 | 1.0 | 0.1 | 2.0 | 4.6527 | HMM candidato |
| shared_cpuset_contention | container | sharing_shared_pool_k4 | 10 | 653733.0 | 657243.5 | 0.0 | 0.0 | 10 | 0.415 | 0.415 | 1.0 | 0.6 | 7.5 | 1.0054 | HMM candidato |
| shared_cpuset_contention | container | sharing_shared_pool_k6 | 10 | 651333.0 | 658318.5 | 0.0 | 0.0 | 10 | 0.9342 | 0.9342 | 1.0 | 0.7 | 23.5 | 1.0107 | HMM candidato |
| shared_cpuset_contention | container | sharing_shared_pool_k8 | 10 | 655071.0 | 657911.5 | 0.0 | 0.0 | 10 | 0.1624 | 0.1656 | 1.0 | 0.8 | 12.5 | 1.0043 | HMM candidato |
| cfs_quota | container | quota_13 | 10 | 654820.0 | 655026.0 | 0.0 | 0.0002 | 10 | 0.0743 | 0.1207 | 0.9 | 0.4 | 4.0 | 1.0003 | comparar AR(1) e HMM |
| container_churn | host | churn_runtime | 10 | 604931.5 | 607393.5 | 0.0 | 0.0003 | 10 | 0.1694 | 0.1694 | 0.9 | 0.4 | 3.5 | 1.0041 | comparar AR(1) e HMM |
| shared_cpuset_contention | container | sharing_shared_pool_k2 | 10 | 649431.0 | 651273.5 | 0.0 | 0.0 | 10 | 0.2271 | 0.2336 | 0.8 | 0.2 | 6.0 | 1.0028 | comparar AR(1) e HMM |
| cfs_quota | container | quota_17 | 10 | 655635.5 | 657369.0 | 0.0 | 0.0 | 10 | 0.0302 | 0.0595 | 0.8 | 0.2 | 2.0 | 1.0026 | efeito temporal fraco: baseline AR(1) |
| cpu_migration | container | migration_unpinned_nomask | 10 | 653182.0 | 653439.0 | 0.0 | 0.0 | 10 | -0.0021 | 0.0372 | 0.7 | 0.2 | 7.0 | 1.0004 | efeito temporal fraco: baseline AR(1) |
| interference | container | interf_docker_cross_core | 10 | 604877.0 | 607099.5 | 0.0 | 0.0 | 10 | 0.0354 | 0.0764 | 1.0 | 0.2 | 2.0 | 1.0037 | efeito temporal fraco: baseline AR(1) |
| interference | container | interf_memory | 10 | 604978.5 | 606673.5 | 0.0 | 0.0 | 10 | 0.0666 | 0.0666 | 1.0 | 0.5 | 6.5 | 1.0028 | efeito temporal fraco: baseline AR(1) |
| interference | host | interf_memory | 10 | 606728.0 | 610302.5 | 0.0 | 0.0 | 10 | 0.0783 | 0.0783 | 1.0 | 1.0 | 7.5 | 1.0059 | efeito temporal fraco: baseline AR(1) |
| shared_cpuset_contention | container | sharing_shared_pool_k0 | 10 | 649681.0 | 651528.0 | 0.0 | 0.0 | 10 | 0.0857 | 0.0883 | 0.9 | 0.2 | 5.0 | 1.0028 | efeito temporal fraco: baseline AR(1) |
| shared_cpuset_contention | container | sharing_shared_pool_k10 | 10 | 649435.0 | 2987917.5 | 0.0096 | 0.0518 | 10 | -0.089 | 0.089 | 1.0 | 0.0 | 2.0 | 4.6008 | efeito temporal fraco: baseline AR(1) |
| cfs_quota | container | quota_15 | 10 | 652587.0 | 653554.5 | 0.0 | 0.0 | 10 | -0.0252 | 0.0268 | 1.0 | 0.2 | 1.0 | 1.0015 | sem regimes: baseline independente |
| cpu_migration | container | migration_unpinned_pinned | 10 | 654905.5 | 655116.5 | 0.0 | 0.0 | 10 | -0.0149 | 0.0241 | 0.9 | 0.4 | 2.0 | 1.0003 | sem regimes: baseline independente |
| interference | container | interf_same_core | 10 | 605680.0 | 605967.5 | 0.0 | 0.0 | 10 | 0.0047 | 0.0191 | 0.6 | 1.0 | 6.0 | 1.0005 | sem regimes: baseline independente |
| interference | host | interf_host_cross_core | 10 | 603597.5 | 606208.0 | 0.0 | 0.0 | 10 | -0.0052 | 0.0116 | 0.7 | 0.0 | 3.0 | 1.0043 | sem regimes: baseline independente |
| interference | host | interf_same_core | 10 | 605635.0 | 607020.0 | 0.0 | 0.0 | 10 | 0.0016 | 0.0043 | 0.2 | 0.1 | 3.5 | 1.0023 | sem regimes: baseline independente |
| sched_fifo_isolated | container | rt_isolated | 10 | 603783.5 | 604730.5 | 0.0 | 0.0 | 10 | -0.0152 | 0.0232 | 0.9 | 0.2 | 2.5 | 1.0016 | sem regimes: baseline independente |
| sched_fifo_isolated | host | rt_isolated | 10 | 603382.0 | 605902.5 | 0.0 | 0.0 | 10 | -0.0084 | 0.0095 | 0.6 | 0.1 | 3.5 | 1.0042 | sem regimes: baseline independente |

## Regras

- **HMM candidato**: persistência prática (|ACF(1)| ≥ 0,10), reproduzida em pelo menos 70% dos runs, e cauda/misses ou rajadas de alta latência.
- **comparar AR(1) e HMM**: persistência forte sem evidência adicional de estados raros/degradação.
- **efeito temporal fraco**: testar primeiro o ganho de um AR(1).
- **sem regimes**: usar modelo marginal independente como referência.
