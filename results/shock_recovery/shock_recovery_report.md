# Choques de latencia e recuperacao de backlog

Episodios sao sequencias contiguas de deadline misses. Choques sao saltos positivos em response_ns acima do maior entre o limiar absoluto e o limiar robusto baseado em MAD.

| environment | runs | total_shocks | total_episodes | median_miss_rate | median_max_response_ns | median_expected_slope_ns | median_observed_slope_ns | median_recovery_r2 | median_fraction_near_expected |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| container | 10 | 420 | 391 | 0.0237 | 1681586891.5 | -4396859.0 | -4391832.3338 | 1.0 | 1.0 |
| host | 10 | 376 | 356 | 0.0171 | 1468996166.5 | -4396511.5 | -4391351.2955 | 1.0 | 1.0 |

## Interpretacao

Uma inclinacao observada proxima de baseline_response_ns - period_ns, com R2 elevado, e compativel com drenagem deterministica de backlog apos um bloqueio. Isso nao identifica, por si so, a causa do bloqueio.
