# Relatório: estrutura temporal das latências

## Integridade
- Arquivos analisados: 260.
- Estado dos arquivos: {'ok': 260}.

## Resumo por condição

|                                           |        n |        median_ns |           p99_ns |   miss_rate |
|:------------------------------------------|---------:|-----------------:|-----------------:|------------:|
| ('cfs_pinned', 'container')               | 100001   |      1.03018e+06 |      1.29824e+06 |       0     |
| ('cfs_pinned', 'host')                    | 100001   |      1.01691e+06 |      1.31791e+06 |       0     |
| ('cfs_quota', 'container')                | 100001   | 654196           | 655532           |       0     |
| ('container_churn', 'container')          | 100001   | 604764           | 606434           |       0.001 |
| ('container_churn', 'host')               | 100001   | 605126           | 607654           |       0     |
| ('cpu_migration', 'container')            | 100001   | 651003           | 652289           |       0     |
| ('interference', 'container')             | 100001   | 604257           |      1.48716e+08 |       0.006 |
| ('interference', 'host')                  |  99992.4 | 602428           |      1.02193e+08 |       0.005 |
| ('sched_fifo_isolated', 'container')      | 100001   | 604230           | 605169           |       0     |
| ('sched_fifo_isolated', 'host')           | 100001   | 601982           | 604291           |       0     |
| ('shared_cpuset_contention', 'container') | 100001   | 649948           |      1.36636e+06 |       0.006 |

## Ordem temporal versus embaralhamento

|                                           |   runs |   significant_lag1 |   mean_lag1 |
|:------------------------------------------|-------:|-------------------:|------------:|
| ('cfs_pinned', 'container')               |     10 |                 10 |       0.972 |
| ('cfs_pinned', 'host')                    |     10 |                 10 |       0.971 |
| ('cfs_quota', 'container')                |     30 |                 27 |       0.026 |
| ('container_churn', 'container')          |     10 |                  9 |       0.113 |
| ('container_churn', 'host')               |     10 |                  9 |       0.169 |
| ('cpu_migration', 'container')            |     20 |                 16 |      -0.009 |
| ('interference', 'container')             |     40 |                 36 |       0.241 |
| ('interference', 'host')                  |     40 |                 29 |       0.241 |
| ('sched_fifo_isolated', 'container')      |     10 |                  9 |      -0.015 |
| ('sched_fifo_isolated', 'host')           |     10 |                  6 |      -0.008 |
| ('shared_cpuset_contention', 'container') |     70 |                 67 |       0.224 |

A coluna `significant_lag1` conta runs cujo ACF no primeiro lag ficou fora do intervalo empírico de 95% obtido por embaralhamento. Evidência consistente em vários runs indica que a ordem temporal contém informação além da distribuição marginal.

## Próxima decisão
Ajustar HMM somente se os resultados acima mostrarem dependência temporal reproduzível. Começar comparando HMM gaussiano em `response_ns` e em `log(response_ns)`; manter `miss` apenas para avaliação posterior por estado.
