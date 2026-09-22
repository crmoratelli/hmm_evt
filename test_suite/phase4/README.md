# TDPS Phase 4 - lei de recuperação

## Hipótese

Para período `T`, execução observada `C` e bloqueio controlado `B`, a folga é
`S=T-C`. O comprimento total do episódio, incluindo o job que recebe o choque,
é previsto por `L=ceil(B/S)`. Com `D=T`, o número de deadline misses não é a
mesma quantidade e é relatado separadamente.

## Desenho confirmatório (Fase 4A)

- host, `SCHED_FIFO/80`, CPU 3 isolada;
- `T=D=5 ms`, 300 jobs, choque no job 100;
- cinco níveis fixos de iterações, aproximadamente `C={0.6,1.5,2.5,3.5,4.0} ms`;
- `B={0,2,5,10,20} ms`;
- 10 blocos; cada bloco contém as 25 células em ordem aleatória reprodutível;
- 250 runs e exatamente um choque por run;
- `C`, `S` e `B` usados na análise são sempre os valores observados.

Os controles `B=0` verificam se cada carga permanece estável sem impulso. A
unidade de replicação é o run, nunca o job. Esta etapa usa bloqueio temporizado,
não I/O real: seu propósito é testar o mecanismo. A Fase 4B posterior validará
uma seleção de folgas sob ext4/I/O real.

## Instalação

Copie a pasta `phase4` para `~/hmm_evt/test_suite/phase4`. No ambiente Python
já usado pelas análises:

```bash
pip install -r test_suite/phase4/requirements.txt
cd ~/hmm_evt/test_suite
chmod +x phase4/*.sh phase4/*.py
phase4/preflight_phase4.sh
```

O pacote inclui também `test_suite/validate_environment.sh` com suporte ao gate
`TDPS_REQUIRE_TRACING=0`. A alteração apenas pula verificações de tracing nas
fases que explicitamente não coletam trace; os demais gates permanecem ativos.

## Sequência obrigatória

```bash
phase4/run_phase4_campaign.py --dry-run
phase4/run_phase4_campaign.py --smoke
```

Audite `~/tdps_phase4_smoke/REPORT.md`, `run_summary.csv` e `cell_summary.csv`.
Não execute a campanha completa antes dessa auditoria. Após aprovação:

```bash
phase4/run_phase4_campaign.py --full --block 1
phase4/run_phase4_campaign.py --full --block 2 --resume
```

Continue até o bloco 10. Para todos os blocos pendentes, omita `--block`.

## Critérios antes da campanha completa

- todos os quatro smoke runs válidos e na CPU 3;
- controles com zero misses;
- `measured_c_ns < 5 ms` em ambos os níveis;
- bloqueio efetivo nunca menor que o solicitado;
- sinais corretos da lei: choque maior e folga menor não reduzem a recuperação;
- ausência de atividade nos IRQs gerenciados durante cada janela.
