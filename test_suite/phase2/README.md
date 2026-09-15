# TDPS Phase 2 — matriz principal

Estado: launcher preparado; campanha principal bloqueada até preflight, dry-run,
smoke de 12 células e autorização explícita do pesquisador.

## Desenho confirmatório

A matriz principal mantém as 12 células:

`deferred | inline | async` × `control | io` × `host | container`

As 12 células são o fatorial mínimo para estimar os efeitos de arquitetura,
pressão de I/O e substrato e, principalmente, suas interações. `deferred` mede
o periódico sem I/O funcional durante o loop; `inline` mede o acoplamento
direto; `async` mede o desacoplamento e seus custos. As células de controle não
são descartadas porque identificam overheads e diferenças de substrato que não
dependem do stress.

Cada bloco contém uma observação de cada célula em ordem aleatória determinada
por `PHASE2_SEED=20260915`. A campanha tem 10 blocos, 500 s por observação e
100.000 jobs por run. Isso corresponde a 60.000 s (16 h 40 min) de exposição
nominal. Warm-up de 10 s e intervalo mínimo de 15 s acrescentam pelo menos 50
min; recovery, drain e validações aumentam o total. Um bloco dura pelo menos
105 min e pode ser executado separadamente.

## Contrato funcional

Todos os modos oferecem 100.000 registros de 64 bytes, com ID do job e payload
fixos. O sink funcional fica no ext4 compartilhado com o stress; `samples.csv`,
telemetria e logs ficam em tmpfs durante a janela e são persistidos depois.
`write(2)` completo significa aceitação pelo kernel, não durabilidade.

| Modo | Marco no produtor | Entrega | Saturação |
|---|---|---|---|
| deferred | retenção em memória | depois do loop, ainda sob a condição experimental | não descarta |
| inline | retorno do `write` | dentro do job, após computação | bloqueia o periódico |
| async | publicação SPSC | logger separado em CPU 0, `SCHED_OTHER/0` | fila 1024, `drop-newest`, sem backpressure |

No modo async, `accepted=1` significa que o registro entrou na fila;
`delivery_finish_ns` significa que o logger concluiu o `write`; `dropped=1`
significa rejeição quando `head−tail=1024`. O produtor nunca espera espaço:
não há backpressure e a política de fila cheia é `drop-newest`. Drops são
resultados válidos e devem ser reportados. Erro de escrita, arquivo funcional
inconsistente, quebra de invariantes, CPU incorreta, timeout, término prematuro
do stress/telemetria ou atividade nos IRQs gerenciados tornam o run inválido.
Deferred e inline exigem entrega completa.

## Ambiente e validade

- período 5 ms; deadline 3 ms; `BENCH_ITERS=151994`;
- CPU RT 3, sibling isolado 11, `SCHED_FIFO/80`;
- logger async na CPU 0, housekeeping, `SCHED_OTHER/0`;
- releases absolutos, catch-up e número fixo de jobs;
- frequência 3,8 GHz fixa e boost desativado;
- I/O: `stress-ng --io 4 --hdd 2 --hdd-bytes 10G` nos housekeeping CPUs;
- telemetria leve em todas as células; sem tracing pesado;
- o preflight desativa somente os gates de eventos/`trace_marker` da validação
  comum; todas as verificações de isolamento, frequência, runtime e IRQ continuam;
- snapshots dos IRQs gerenciados delimitam benchmark e drain;
- recuperação exige `sync` e Dirty+Writeback ≤ 65536 kB;
- runs incompletos são preservados e movidos para `failed_runs/` no resume.

Métricas são produzidas por run, choque de entrega e episódio contíguo de
misses/respostas ≥10 ms. A unidade de replicação é o run, nunca o job. O resumo
de campanha preserva também runs sem eventos e tempo total de exposição.

## Sequência obrigatória

O preflight compila `phase2/periodic_v2` sem tocar no binário não rastreado da
Fase 1, constrói uma imagem própria e verifica a identidade SHA256 host/container.

```bash
cd /home/ghost/hmm_evt/test_suite
chmod +x phase2/*.sh phase2/*.py
phase2/preflight_phase2.sh
```

Depois, apenas inspecione a agenda completa:

```bash
phase2/run_phase2_campaign.py --dry-run
```

O smoke executa as 12 células por 10 s cada em raiz separada:

```bash
phase2/run_phase2_campaign.py --smoke
```

Somente após revisar `tdps_phase2_smoke/cell_summary.csv` e obter autorização
explícita, execute a campanha. É possível fazê-la bloco a bloco:

```bash
phase2/run_phase2_campaign.py --full --block 1
phase2/run_phase2_campaign.py --full --block 2 --resume
```

Sem `--block`, `--full` executa todos os blocos pendentes. Nunca reutilize uma
raiz com agenda diferente; o hash e o conteúdo de `schedule.csv` são validados.
