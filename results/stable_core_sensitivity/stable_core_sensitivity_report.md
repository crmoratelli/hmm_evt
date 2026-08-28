# Sensibilidade do nucleo estavel

A ordem de GMM e HMM foi escolhida pelo menor BIC no treino antes da
avaliacao no hold-out temporal. Quantis foram estimados somente no treino.

## Comparacao pareada HMM menos GMM

| sensitivity    | environment   |   runs |   hmm_wins |   median_hmm_minus_gmm |   wilcoxon_p |   positive_temporal_gain_runs |   median_temporal_gain_hmm |   median_kept_fraction |
|:---------------|:--------------|-------:|-----------:|-----------------------:|-------------:|------------------------------:|---------------------------:|-----------------------:|
| base_stable    | container     |     10 |          9 |              0.166182  |   0.0839844  |                            10 |                  0.511554  |               0.973285 |
| cap_1000us     | container     |     10 |          9 |              0.151429  |   0.0273438  |                            10 |                  0.510292  |               0.973275 |
| cap_1500us     | container     |     10 |         10 |              0.204907  |   0.00195312 |                            10 |                  0.510746  |               0.97328  |
| cap_2000us     | container     |     10 |         10 |              0.28405   |   0.00195312 |                            10 |                  0.595852  |               0.97328  |
| cap_2500us     | container     |     10 |         10 |              0.207718  |   0.00195312 |                            10 |                  0.512343  |               0.97328  |
| train_q_0.999  | container     |     10 |         10 |              0.301833  |   0.00195312 |                            10 |                  0.593353  |               0.96998  |
| train_q_0.9995 | container     |     10 |         10 |              0.309041  |   0.00195312 |                            10 |                  0.600796  |               0.97097  |
| train_q_0.9999 | container     |     10 |         10 |              0.189287  |   0.00195312 |                            10 |                  0.482094  |               0.972595 |
| base_stable    | host          |     10 |          7 |              0.0206368 |   0.160156   |                            10 |                  0.0491328 |               0.98041  |
| cap_1000us     | host          |     10 |          7 |              0.0264321 |   0.431641   |                            10 |                  0.0465696 |               0.980395 |
| cap_1500us     | host          |     10 |          7 |              0.0286807 |   0.492188   |                            10 |                  0.0466127 |               0.980395 |
| cap_2000us     | host          |     10 |          7 |              0.0286807 |   0.492188   |                            10 |                  0.0465244 |               0.980405 |
| cap_2500us     | host          |     10 |          7 |              0.0205464 |   0.160156   |                            10 |                  0.0493085 |               0.98041  |
| train_q_0.999  | host          |     10 |         10 |              0.0605379 |   0.00195312 |                            10 |                  0.0995604 |               0.97962  |
| train_q_0.9995 | host          |     10 |         10 |              0.0609023 |   0.00195312 |                            10 |                  0.102819  |               0.98001  |
| train_q_0.9999 | host          |     10 |          8 |              0.0405292 |   0.0644531  |                             9 |                  0.0594859 |               0.980335 |

## Retencao das mascaras

| sensitivity    | environment   |   median_kept_fraction |   min_kept_fraction |   max_kept_fraction |   median_cap_us |
|:---------------|:--------------|-----------------------:|--------------------:|--------------------:|----------------:|
| base_stable    | container     |               0.973285 |            0.944701 |             0.9997  |         nan     |
| base_stable    | host          |               0.98041  |            0.95699  |             0.99979 |         nan     |
| cap_1000us     | container     |               0.973275 |            0.944701 |             0.9996  |        1000     |
| cap_1000us     | host          |               0.980395 |            0.95699  |             0.99974 |        1000     |
| cap_1500us     | container     |               0.97328  |            0.944701 |             0.99964 |        1500     |
| cap_1500us     | host          |               0.980395 |            0.95699  |             0.99974 |        1500     |
| cap_2000us     | container     |               0.97328  |            0.944701 |             0.99967 |        2000     |
| cap_2000us     | host          |               0.980405 |            0.95699  |             0.99976 |        2000     |
| cap_2500us     | container     |               0.97328  |            0.944701 |             0.99969 |        2500     |
| cap_2500us     | host          |               0.98041  |            0.95699  |             0.99977 |        2500     |
| train_q_0.999  | container     |               0.96998  |            0.943911 |             0.99853 |         606.441 |
| train_q_0.999  | host          |               0.97962  |            0.95622  |             0.99878 |         610.188 |
| train_q_0.9995 | container     |               0.97097  |            0.944351 |             0.99915 |         607.464 |
| train_q_0.9995 | host          |               0.98001  |            0.95661  |             0.99934 |         611.69  |
| train_q_0.9999 | container     |               0.972595 |            0.944631 |             0.99956 |         636.426 |
| train_q_0.9999 | host          |               0.980335 |            0.95692  |             0.99968 |         666.794 |

## Ordens selecionadas pelo BIC de treino

| sensitivity    | environment   | model        |   order |   runs_selected |
|:---------------|:--------------|:-------------|--------:|----------------:|
| base_stable    | container     | gaussian_gmm |       4 |               4 |
| base_stable    | container     | gaussian_gmm |       5 |               6 |
| base_stable    | container     | gaussian_hmm |       4 |               2 |
| base_stable    | container     | gaussian_hmm |       5 |               8 |
| base_stable    | host          | gaussian_gmm |       4 |               2 |
| base_stable    | host          | gaussian_gmm |       5 |               8 |
| base_stable    | host          | gaussian_hmm |       4 |               1 |
| base_stable    | host          | gaussian_hmm |       5 |               9 |
| cap_1000us     | container     | gaussian_gmm |       4 |               2 |
| cap_1000us     | container     | gaussian_gmm |       5 |               8 |
| cap_1000us     | container     | gaussian_hmm |       5 |              10 |
| cap_1000us     | host          | gaussian_gmm |       4 |               1 |
| cap_1000us     | host          | gaussian_gmm |       5 |               9 |
| cap_1000us     | host          | gaussian_hmm |       4 |               3 |
| cap_1000us     | host          | gaussian_hmm |       5 |               7 |
| cap_1500us     | container     | gaussian_gmm |       4 |               2 |
| cap_1500us     | container     | gaussian_gmm |       5 |               8 |
| cap_1500us     | container     | gaussian_hmm |       4 |               1 |
| cap_1500us     | container     | gaussian_hmm |       5 |               9 |
| cap_1500us     | host          | gaussian_gmm |       4 |               2 |
| cap_1500us     | host          | gaussian_gmm |       5 |               8 |
| cap_1500us     | host          | gaussian_hmm |       4 |               3 |
| cap_1500us     | host          | gaussian_hmm |       5 |               7 |
| cap_2000us     | container     | gaussian_gmm |       4 |               1 |
| cap_2000us     | container     | gaussian_gmm |       5 |               9 |
| cap_2000us     | container     | gaussian_hmm |       5 |              10 |
| cap_2000us     | host          | gaussian_gmm |       4 |               3 |
| cap_2000us     | host          | gaussian_gmm |       5 |               7 |
| cap_2000us     | host          | gaussian_hmm |       4 |               3 |
| cap_2000us     | host          | gaussian_hmm |       5 |               7 |
| cap_2500us     | container     | gaussian_gmm |       4 |               4 |
| cap_2500us     | container     | gaussian_gmm |       5 |               6 |
| cap_2500us     | container     | gaussian_hmm |       5 |              10 |
| cap_2500us     | host          | gaussian_gmm |       4 |               2 |
| cap_2500us     | host          | gaussian_gmm |       5 |               8 |
| cap_2500us     | host          | gaussian_hmm |       4 |               1 |
| cap_2500us     | host          | gaussian_hmm |       5 |               9 |
| train_q_0.999  | container     | gaussian_gmm |       4 |               4 |
| train_q_0.999  | container     | gaussian_gmm |       5 |               6 |
| train_q_0.999  | container     | gaussian_hmm |       5 |              10 |
| train_q_0.999  | host          | gaussian_gmm |       5 |              10 |
| train_q_0.999  | host          | gaussian_hmm |       5 |              10 |
| train_q_0.9995 | container     | gaussian_gmm |       4 |               6 |
| train_q_0.9995 | container     | gaussian_gmm |       5 |               4 |
| train_q_0.9995 | container     | gaussian_hmm |       5 |              10 |
| train_q_0.9995 | host          | gaussian_gmm |       4 |               1 |
| train_q_0.9995 | host          | gaussian_gmm |       5 |               9 |
| train_q_0.9995 | host          | gaussian_hmm |       5 |              10 |
| train_q_0.9999 | container     | gaussian_gmm |       4 |               3 |
| train_q_0.9999 | container     | gaussian_gmm |       5 |               7 |
| train_q_0.9999 | container     | gaussian_hmm |       4 |               1 |
| train_q_0.9999 | container     | gaussian_hmm |       5 |               9 |
| train_q_0.9999 | host          | gaussian_gmm |       5 |              10 |
| train_q_0.9999 | host          | gaussian_hmm |       4 |               2 |
| train_q_0.9999 | host          | gaussian_hmm |       5 |               8 |

## Associacao com a ordem cronologica dos runs

| condition    | environment   | sensitivity    | metric                            |   runs |   spearman_rho_with_run_order |   spearman_p |
|:-------------|:--------------|:---------------|:----------------------------------|-------:|------------------------------:|-------------:|
| interference | container     | base_stable    | hmm_minus_gmm_test_loglik_per_obs |     10 |                     0.672727  |   0.0330412  |
| interference | container     | base_stable    | temporal_gain_per_obs_hmm         |     10 |                     0.6       |   0.066688   |
| interference | container     | cap_1000us     | hmm_minus_gmm_test_loglik_per_obs |     10 |                     0.781818  |   0.00754701 |
| interference | container     | cap_1000us     | temporal_gain_per_obs_hmm         |     10 |                     0.563636  |   0.089724   |
| interference | container     | cap_1500us     | hmm_minus_gmm_test_loglik_per_obs |     10 |                     0.587879  |   0.0738777  |
| interference | container     | cap_1500us     | temporal_gain_per_obs_hmm         |     10 |                     0.575758  |   0.0815528  |
| interference | container     | cap_2000us     | hmm_minus_gmm_test_loglik_per_obs |     10 |                     0.272727  |   0.445838   |
| interference | container     | cap_2000us     | temporal_gain_per_obs_hmm         |     10 |                     0.490909  |   0.149656   |
| interference | container     | cap_2500us     | hmm_minus_gmm_test_loglik_per_obs |     10 |                     0.490909  |   0.149656   |
| interference | container     | cap_2500us     | temporal_gain_per_obs_hmm         |     10 |                     0.563636  |   0.089724   |
| interference | container     | train_q_0.999  | hmm_minus_gmm_test_loglik_per_obs |     10 |                     0.2       |   0.579584   |
| interference | container     | train_q_0.999  | temporal_gain_per_obs_hmm         |     10 |                     0.345455  |   0.328227   |
| interference | container     | train_q_0.9995 | hmm_minus_gmm_test_loglik_per_obs |     10 |                     0.2       |   0.579584   |
| interference | container     | train_q_0.9995 | temporal_gain_per_obs_hmm         |     10 |                     0.357576  |   0.310376   |
| interference | container     | train_q_0.9999 | hmm_minus_gmm_test_loglik_per_obs |     10 |                     0.515152  |   0.127553   |
| interference | container     | train_q_0.9999 | temporal_gain_per_obs_hmm         |     10 |                     0.587879  |   0.0738777  |
| interference | host          | base_stable    | hmm_minus_gmm_test_loglik_per_obs |     10 |                    -0.151515  |   0.676065   |
| interference | host          | base_stable    | temporal_gain_per_obs_hmm         |     10 |                     0.0787879 |   0.828717   |
| interference | host          | cap_1000us     | hmm_minus_gmm_test_loglik_per_obs |     10 |                     0.0424242 |   0.907364   |
| interference | host          | cap_1000us     | temporal_gain_per_obs_hmm         |     10 |                     0.0545455 |   0.881036   |
| interference | host          | cap_1500us     | hmm_minus_gmm_test_loglik_per_obs |     10 |                     0.0424242 |   0.907364   |
| interference | host          | cap_1500us     | temporal_gain_per_obs_hmm         |     10 |                     0.0545455 |   0.881036   |
| interference | host          | cap_2000us     | hmm_minus_gmm_test_loglik_per_obs |     10 |                     0.0424242 |   0.907364   |
| interference | host          | cap_2000us     | temporal_gain_per_obs_hmm         |     10 |                     0.0545455 |   0.881036   |
| interference | host          | cap_2500us     | hmm_minus_gmm_test_loglik_per_obs |     10 |                    -0.151515  |   0.676065   |
| interference | host          | cap_2500us     | temporal_gain_per_obs_hmm         |     10 |                     0.0787879 |   0.828717   |
| interference | host          | train_q_0.999  | hmm_minus_gmm_test_loglik_per_obs |     10 |                    -0.115152  |   0.75142    |
| interference | host          | train_q_0.999  | temporal_gain_per_obs_hmm         |     10 |                    -0.236364  |   0.510885   |
| interference | host          | train_q_0.9995 | hmm_minus_gmm_test_loglik_per_obs |     10 |                    -0.0424242 |   0.907364   |
| interference | host          | train_q_0.9995 | temporal_gain_per_obs_hmm         |     10 |                    -0.0666667 |   0.854813   |
| interference | host          | train_q_0.9999 | hmm_minus_gmm_test_loglik_per_obs |     10 |                     0.260606  |   0.467089   |
| interference | host          | train_q_0.9999 | temporal_gain_per_obs_hmm         |     10 |                     0.236364  |   0.510885   |

## Criterio de robustez

A evidencia residual e robusta somente se o ganho HMM-GMM permanecer positivo
na maioria dos runs, tiver mediana materialmente positiva, teste pareado consistente
e ganho sobre o embaralhamento em varias definicoes do nucleo estavel.
