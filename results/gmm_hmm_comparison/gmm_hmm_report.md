# Comparacao GMM versus HMM

Modelos ajustados em log(response_ns), com normalizacao definida somente no treino.
`raw` usa a serie completa; `stable` remove misses e guardas em torno da degradacao.

## Retencao dos trechos estaveis

| environment   |   median |      min |     max |
|:--------------|---------:|---------:|--------:|
| container     | 0.973285 | 0.944701 | 0.9997  |
| host          | 0.98041  | 0.95699  | 0.99979 |

## Vencedores por run (hold-out temporal)

| view   | environment   | model        |   order |   run_wins |
|:-------|:--------------|:-------------|--------:|-----------:|
| raw    | container     | gaussian_hmm |       4 |          1 |
| raw    | container     | gaussian_hmm |       5 |          9 |
| raw    | host          | gaussian_gmm |       5 |          1 |
| raw    | host          | gaussian_hmm |       5 |          9 |
| stable | container     | gaussian_hmm |       4 |          1 |
| stable | container     | gaussian_hmm |       5 |          8 |
| stable | container     | iid_gaussian |       1 |          1 |
| stable | host          | gaussian_gmm |       4 |          1 |
| stable | host          | gaussian_gmm |       5 |          2 |
| stable | host          | gaussian_hmm |       5 |          7 |

## Resultado agregado

| view   | environment   | model        |   order |   runs |   total_test_observations |   mean_test_loglik_per_obs |   median_test_loglik_per_obs |   median_train_bic |   mean_temporal_gain_per_obs |   median_temporal_gain_per_obs |
|:-------|:--------------|:-------------|--------:|-------:|--------------------------:|---------------------------:|-----------------------------:|-------------------:|-----------------------------:|-------------------------------:|
| raw    | container     | gaussian_hmm |       5 |     10 |                    300010 |                4.8957      |                    5.76646   |         -798240    |                    0.465598  |                    0.411646    |
| raw    | container     | gaussian_hmm |       4 |     10 |                    300010 |                4.88073     |                    5.74778   |         -795851    |                    0.396674  |                    0.367044    |
| raw    | container     | gaussian_hmm |       3 |     10 |                    300010 |                4.79527     |                    5.5189    |         -784759    |                    0.325589  |                    0.273728    |
| raw    | container     | gaussian_hmm |       2 |     10 |                    300010 |                4.74028     |                    5.49144   |         -780137    |                    0.288617  |                    0.248609    |
| raw    | container     | gaussian_gmm |       5 |     10 |                    300010 |                4.37561     |                    5.13284   |         -723651    |                    0         |                    0           |
| raw    | container     | gaussian_gmm |       4 |     10 |                    300010 |                4.37505     |                    5.13215   |         -723548    |                    0         |                    0           |
| raw    | container     | gaussian_gmm |       3 |     10 |                    300010 |                4.37302     |                    5.13171   |         -723409    |                    0         |                    0           |
| raw    | container     | gaussian_gmm |       2 |     10 |                    300010 |                4.34963     |                    5.12603   |         -722167    |                    0         |                    0           |
| raw    | container     | ar1_gaussian |       1 |     10 |                    300000 |                0.0680919   |                    0.393076  |             nan    |                  nan         |                  nan           |
| raw    | container     | iid_gaussian |       1 |     10 |                    300010 |               -1.64188     |                   -1.53173   |          198673    |                    0         |                    0           |
| raw    | host          | gaussian_hmm |       5 |     10 |                    299906 |                4.29136     |                    4.92793   |         -680993    |                    0.298811  |                    0.220148    |
| raw    | host          | gaussian_hmm |       4 |     10 |                    299906 |                4.21509     |                    4.75022   |         -664325    |                    0.251717  |                    0.151594    |
| raw    | host          | gaussian_hmm |       3 |     10 |                    299906 |                4.16819     |                    4.68255   |         -660471    |                    0.22893   |                    0.134604    |
| raw    | host          | gaussian_hmm |       2 |     10 |                    299906 |                4.15167     |                    4.66431   |         -658895    |                    0.203454  |                    0.109713    |
| raw    | host          | gaussian_gmm |       5 |     10 |                    299906 |                4.03365     |                    4.49768   |         -645468    |                    0         |                    0           |
| raw    | host          | gaussian_gmm |       4 |     10 |                    299906 |                4.02738     |                    4.4975    |         -645472    |                    0         |                    0           |
| raw    | host          | gaussian_gmm |       3 |     10 |                    299906 |                4.0268      |                    4.4958    |         -645366    |                    0         |                    0           |
| raw    | host          | gaussian_gmm |       2 |     10 |                    299906 |                4.02257     |                    4.49153   |         -645139    |                    0         |                    0           |
| raw    | host          | ar1_gaussian |       1 |     10 |                    299896 |                0.167348    |                    0.444986  |             nan    |                  nan         |                  nan           |
| raw    | host          | iid_gaussian |       1 |     10 |                    299906 |               -1.56778     |                   -1.36849   |          198673    |                    0         |                    0           |
| stable | container     | gaussian_gmm |       3 |     10 |                    290470 |               -1.82332     |                    0.775691  |         -121216    |                    0         |                    0           |
| stable | container     | ar1_gaussian |       1 |     10 |                    290348 |               -2.07871     |                   -1.12515   |             nan    |                  nan         |                  nan           |
| stable | container     | iid_gaussian |       1 |     10 |                    290470 |               -2.08239     |                   -1.1332    |          192858    |                    0         |                    0           |
| stable | container     | gaussian_gmm |       5 |     10 |                    290470 |              -19.4843      |                    0.802161  |         -126908    |                    0         |                    0           |
| stable | container     | gaussian_hmm |       5 |     10 |                    290470 |              -19.5914      |                    0.849375  |         -150622    |                    0.501479  |                    0.512668    |
| stable | container     | gaussian_gmm |       4 |     10 |                    290470 |              -23.6591      |                    0.799215  |         -126282    |                    0         |                    0           |
| stable | container     | gaussian_hmm |       4 |     10 |                    290470 |              -28.9797      |                    0.907298  |         -145678    |                    0.40457   |                    0.332992    |
| stable | container     | gaussian_hmm |       2 |     10 |                    290470 |              -29.0916      |                    0.273239  |          -49483.1  |                   -0.0113742 |                   -1.04013e-15 |
| stable | container     | gaussian_gmm |       2 |     10 |                    290470 |              -29.1866      |                    0.54502   |          -74303.8  |                    0         |                    0           |
| stable | container     | gaussian_hmm |       3 |     10 |                    290470 |              -32.9854      |                    0.78745   |         -109869    |                   -0.13319   |                    0.078881    |
| stable | host          | gaussian_gmm |       4 |     10 |                    293076 |                0.00100818  |                    0.260362  |          -25044.2  |                    0         |                    0           |
| stable | host          | gaussian_hmm |       5 |     10 |                    293076 |               -0.000665014 |                    0.301165  |          -40387.2  |                    0.0609704 |                    0.0491711   |
| stable | host          | gaussian_gmm |       5 |     10 |                    293076 |               -0.000831087 |                    0.285737  |          -25073.4  |                    0         |                    0           |
| stable | host          | gaussian_hmm |       4 |     10 |                    293076 |               -0.0666141   |                    0.215391  |          -31429.9  |                    0.051175  |                    0.033172    |
| stable | host          | gaussian_gmm |       3 |     10 |                    293076 |               -0.14174     |                    0.228154  |          -21344.5  |                    0         |                    0           |
| stable | host          | gaussian_hmm |       3 |     10 |                    293076 |               -0.152634    |                    0.177562  |          -16791.5  |                    0.03023   |                    0.00390584  |
| stable | host          | gaussian_gmm |       2 |     10 |                    293076 |               -0.320453    |                    0.0719177 |            4146.99 |                    0         |                    0           |
| stable | host          | gaussian_hmm |       2 |     10 |                    293076 |               -0.360326    |                   -0.0151985 |           12497.9  |                   -0.0242465 |                    1.16765e-05 |
| stable | host          | iid_gaussian |       1 |     10 |                    293076 |               -1.58211     |                   -1.22825   |          194803    |                    0         |                    0           |
| stable | host          | ar1_gaussian |       1 |     10 |                    292960 |               -1.58989     |                   -1.22755   |             nan    |                  nan         |                  nan           |

## Leitura

Para HMM, `temporal_gain_per_obs > 0` indica vantagem da ordem original sobre testes embaralhados.
A evidencia mais forte de regimes exige simultaneamente: HMM superior a GMM no hold-out,
ganho temporal positivo e repeticao do resultado entre runs, sobretudo na visao `stable`.
