# TDPS — Novo foco científico e registro das cinco fases

Data da decisão: 09/09/2026. Versão inicial do registro.
Periódico-alvo: Journal of Systems Architecture (JSA).
Estado: fase 1 iniciada em 09/09/2026; especificação e implementação local disponíveis; validação RT no cylon pendente.

## 1. Como usar este documento

Este é o documento de continuidade para os próximos prompts. Registra a decisão científica, suas evidências, o plano e o histórico de resultados. Complementa e, quanto ao foco e às prioridades, substitui o plano anterior em `02-principal.txt`; não apaga o histórico anterior.

Ao concluir cada fase, atualizar a seção correspondente neste mesmo documento com resultados efetivamente obtidos, evidências, limitações e decisões. Não preencher resultados esperados como se fossem observados. Preservar runs, versões do código e dados brutos anteriores.

Autorização atual: fase 1 solicitada em novo prompt e suite mais recente recebida. Nova sonda implementada em diretório separado; código e evidências históricos preservados. Campanha principal não iniciada.

## 2. Novo foco aprovado

Investigar como bloqueios raros, especialmente no caminho de I/O inline, se propagam pela dinâmica de uma tarefa periódica e produzem episódios de degradação e deadline misses. Separar o processo que gera o choque da dinâmica de acumulação e recuperação do atraso.

Tese de trabalho, a ser testada:

> Em workloads periódicos, a latência extrema não é apenas uma coleção de amostras raras. Um choque de bloqueio pode criar backlog temporal e gerar um episódio estruturado de deadline misses. A arquitetura de I/O influencia a ocorrência dos choques; a semântica periódica determina sua propagação e recuperação.

O estudo terá natureza experimental e mecanística, com modelagem probabilística e avaliação de intervenções arquiteturais. Host versus container permanece como fator experimental, não como explicação presumida. HMM, HSMM e EVT são ferramentas candidatas, não contribuições garantidas nem resultados a serem forçados.

Contribuições pretendidas:

1. Separar interferência externa, efeito do observador e I/O funcional da aplicação.
2. Explicar quantitativamente a transformação de choques em episódios de misses.
3. Avaliar se modelos de choques/regimes e recuperação melhoram a estimação de risco por episódio frente a baselines.
4. Avaliar mitigação por desacoplamento da saída, explicitando custos e garantias de entrega.

Título provisório, não definitivo: *From Tail Samples to Deadline-Miss Episodes: In-Band I/O and Regime Dynamics in Periodic Real-Time Containers*.

## 3. Por que mudamos de rumo

### 3.1 Foco anterior

O plano anterior partia da hipótese de regimes temporais latentes em séries de latência: validar dependência, comparar IID/AR(1)/HMM, caracterizar estados e eventualmente aplicar EVT por estado. O trabalho anterior, `Where Temporal Determinism Is Lost: An Experimental Analysis of Cloud Execution Layers`, motivava a investigação com grandes caudas sob I/O.

O novo diagnóstico revelou uma variável metodológica decisiva: a saída incremental do próprio benchmark. A série pode conter dependência não porque o sistema permaneceu em vários modos latentes, mas porque um bloqueio isolado atrasou diversas ativações sucessivas. Um HMM pode segmentar os degraus da recuperação sem descobrir mecanismos físicos distintos.

### 3.2 Evidências preliminares que motivaram a decisão

Origem: saídas de terminal e trechos de código fornecidos pelo pesquisador nesta conversa. Os CSVs completos e traces dessas campanhas estão na máquina `cylon`; não foram reanalisados integralmente para produzir este registro. Resultados de campanhas distintas não constituem, sozinhos, um contraste causal randomizado definitivo.

Configuração reportada: período 5 ms; deadline 3 ms; computação aproximadamente 600 µs; BENCH_ITERS=151994; SCHED_FIFO prioridade 80; CPU RT 3; sibling 11; interferência nos CPUs de housekeeping. O comando efetivamente mostrado nas campanhas era `stress-ng --io 4 --hdd 2 --hdd-bytes 10G`, apesar de outras variáveis de stress presentes no config. Registrar sempre o comando efetivo, não apenas defaults.

| Evidência | Resultado reportado | Interpretação limitada aos dados disponíveis |
|---|---|---|
| Piloto deferred, I/O, 18 runs de 500 s: host/container × none/telemetry/full × 3 | 1.800.018 jobs, zero misses; maior máximo entre runs 772.383 ns | Não houve violação observada nessa amostra com saída pós-loop em tmpfs; não prova ausência de risco |
| Stream host/full, 60 s, run 0001 | 12.001 jobs, zero misses; máximo 653.061 ns; nenhum choque | Um smoke test curto não revelou o evento raro |
| Stream host/full, 500 s, run 0002 | 100.001 jobs; 132 misses; máximo 199.793.975 ns; p99 609.778 ns; p99.9 26.690.342 ns | Centro quase inalterado coexistiu com cauda e violações relevantes |
| Mesmo run 0002 | mediana de execução 603.210 ns; máximo de atraso release-to-start 199.190.325 ns; CPU observado 3 | O atraso de início domina o máximo, mas essa métrica não isola latência do scheduler |
| IRQs monitorados 90,107,115,123,131 | Todos os deltas iguais a zero | Exclui atividade desses vetores no intervalo; não exclui todo efeito de kernel/IRQ |
| Trace do primeiro choque | Saída em estado D às 336686.075290 s; wakeup às 336686.110401 s | Aproximadamente 35,111 ms entre bloqueio e wakeup, após a computação do job anterior |
| Atividade concomitante | Completions NVMe em outros CPUs; 44 block_rq_complete na janela filtrada | Evidência de atividade de armazenamento, não identificação da causa interna da espera |

No run 0002, o primeiro choque foi o job 43946: release=336686079677899 ns, start=336686110417386 ns, finish=336686111021576 ns e response=31343677 ns. O job 43945 havia terminado a computação em 336686075285324 ns.

Respostas dos jobs 43946–43953, em ms: 31,343677; 26,960747; 22,573316; 18,181986; 13,794806; 9,407046; 5,016296; 0,628285. Foram sete misses consecutivos, seguidos de recuperação. A queda é aproximadamente T−C=4,4 ms por ativação, compatível com escoamento de backlog sob releases absolutos sem descarte de jobs.

O caminho de saída é a principal hipótese para o bloqueio, pela posição temporal e pelo contraste deferred/stream. O trace mostrado confirma estado D, mas não identifica a syscall/stack responsável. Não registrar dirty throttling, writeback ou journal como causa comprovada. Atribuição exata requer instrumentação dirigida e intervenções.

### 3.3 Limites e cautelas que acompanham o achado

- A saída de medição original e a saída funcional de uma aplicação devem ser distinguidas. Alterar a primeira muda o observador; alterar a segunda muda o workload.
- `finish_ns` anterior à escrita exclui a saída do job atual, mas o bloqueio pode atrasar os jobs seguintes.
- `wakeup_delay_ns=start−release` inclui atraso acumulado antes de chamar o sono periódico; não é uma medida pura de latência de wakeup/escalonamento.
- Retorno de `fprintf`, `write` ou `fflush` não equivale a persistência durável. Especificar o contrato: aceitação em buffer, entrega ao kernel, enqueue assíncrono ou durabilidade.
- O valor reportado `minimum_history=505.255_s` não demonstra 505 s de eventos úteis preservados. Com congelamento após choque, `now−oldest` pode incluir tempo sem gravação. Validar cobertura pelos timestamps dos eventos, marcadores e contadores antes da extração.
- Perdas anteriores por eventos ext4 de alta frequência motivaram redução de tracing; preservar a lista efetivamente habilitada por run. Ausência de evento também pode significar falta de cobertura.
- Mensagens `Killed` não demonstram OOM. Há encerramento explícito do grupo de stress após medição; verificar função de cleanup/logs se necessário.
- Não reclassificar retroativamente todas as conclusões do artigo anterior como falsas: a seção de I/O exige qualificação e investigação, e outros cenários precisam de evidências próprias.

### 3.4 Localização dos artefatos históricos no cylon

- Projeto: `/home/ghost/hmm_evt/test_suite`.
- Piloto deferred: `/home/ghost/tdps_causal_results_buffered_v1`.
- Relatório do piloto: `campaigns/pilot_analysis/pilot_report.md` dentro da raiz anterior.
- Smoke stream: `/home/ghost/tdps_causal_results_stream_smoke`.
- Episódio principal: `runs/0002_io_host_run02_full` dentro da raiz stream.
- Evidências: `samples.csv`, `summary.txt`, `metadata.env`, `benchmark.log`, `first_shock.txt`, `trace.dat`, `trace_buffer_stats.txt`, `trace_events_enabled.txt`, `managed_irq_delta.csv`.
- `/home/ghost` e `/tmp` foram reportados no mesmo volume ext4 `/dev/mapper/ubuntu--vg-ubuntu--lv`. A saída deferred estava em `/dev/shm` durante a medição.

Esses caminhos são referências da máquina do pesquisador, não confirmação de acesso a ela por este assistente.

## 4. Modelo conceitual e perguntas de pesquisa

Modelo simplificado candidato, não resultado novo já validado:

`W[k+1] = max(0, W[k] + C[k] + L[k] - T)`

Aqui W é atraso acumulado de início, C é computação e L é saída inline após a computação. Supõe releases absolutos, execução sequencial e ausência de descarte; overheads adicionais e jitter devem ser modelados ou medidos. Para essa semântica, resposta computacional é W+C; resposta até completar a operação de saída é W+C+L. A relação é associada à dinâmica clássica de backlog/filas, não reivindicada como invenção.

Perguntas:

1. Quando a arquitetura de saída abre um canal de interferência temporal sob pressão de I/O?
2. Quanto dos misses corresponde a choques distintos e quanto corresponde à recuperação de um mesmo choque?
3. Um modelo que separa choque e recuperação prevê risco por episódio melhor que modelos puramente descritivos?
4. Host/container altera frequência, intensidade ou recuperação após controlar a semântica do workload?
5. Qual compromisso entre latência do periódico, perdas de registros, atraso de entrega e durabilidade resulta do desacoplamento da saída?

Não assumir que logging assíncrono elimina risco: fila finita pode saturar e exigir descarte ou backpressure. Não comparar durabilidade síncrona com enqueue assíncrono como se fossem serviços equivalentes.

## 5. Plano aprovado: cinco fases

| Fase | Objetivo | Entrega e critério de passagem | Status |
|---|---|---|---|
| 1 — Semântica do workload | Separar computação, saída e observação; definir deferred/inline/async | Especificação temporal e de entrega; implementação revisada; testes funcionais e de consistência; overhead documentado | Em andamento; gate cylon pendente |
| 2 — Matriz principal | Comparar arquiteturas × controle/I/O × host/container | Campanha randomizada reproduzível; métricas por run e episódio; incerteza e número de choques reportados | Não iniciada |
| 3 — Intervenções causais | Testar dependência do caminho compartilhado | Contrastes mesmo armazenamento/tmpfs/outro dispositivo quando disponível; batching/desacoplamento e eventual limitação de I/O | Não iniciada |
| 4 — Lei de recuperação | Testar previsão quantitativa da dinâmica periódica | Variação controlada de T−C; comparação entre trajetória e número de misses previstos/observados; análise dos desvios | Não iniciada |
| 5 — Generalização | Testar transferibilidade além da sonda e plataforma inicial | Segunda plataforma/configuração e/ou aplicação de controle real; limites de validade explícitos | Não iniciada |

As fases são frentes metodológicas, não uma exigência de executar toda a matriz antes de verificar causalidade. Após a fase 1, fazer um subconjunto curto da fase 3 para validar o desenho antes da campanha extensa da fase 2. Registrar qualquer mudança de ordem.

### Fase 1 — Especificação de início para o próximo prompt

Primeiro inspecionar o código atual na máquina/repositório correto, incluindo `periodic_bench.c`, config, launcher, build da imagem e scripts de resumo. Os trechos anteriores não garantem o estado atual. Não presumir que o ZIP original contém as modificações recentes.

Estado previamente reportado:

- Binário host compilou e reconheceu `--stream-output`.
- Config contém `BENCH_OUTPUT_MODE`, default `deferred`.
- Launcher aceita `deferred|stream`, usa caminho em tmpfs para deferred e caminho direto em run_dir para stream; há montagem correspondente no ramo container.
- Não há confirmação nesta conversa de rebuild da imagem container com o código stream, nem de implementação async.

Decisões que precisam ser fechadas na fase 1:

1. Distinguir registro experimental de saída funcional; manter a instrumentação de referência em memória previamente alocada.
2. Definir tamanho/conteúdo da saída funcional, buffering, flushing, fechamento e requisito de durabilidade; controlar seu volume entre condições.
3. Definir timestamps: release, start, compute_finish, output_start, output_finish; no async, distinguir enqueue de entrega/persistência pelo logger, vinculados por job ID.
4. Definir métricas: computação, atraso release-to-start, tempo de saída, resposta computacional, resposta até o marco funcional escolhido; manter compatibilidade explícita com CSVs antigos.
5. Definir modo deferred, inline e async. Não renomear `stream` silenciosamente: registrar mapeamento e versão do esquema.
6. Definir política de overruns: catch-up sem descarte como referência do experimento atual; documentar qualquer variante com skip/coalescing.
7. Para async, especificar capacidade da fila, afinidade/prioridade do logger, política de fila cheia, perdas, atraso e backlog de registros; prealocar os recursos pertinentes.
8. Validar contabilização de jobs, unidades, timestamps monotônicos, relações entre métricas e erros de saída; comparar funcionalmente modos com e sem I/O.
9. Registrar commit, binários/imagem, configuração efetiva e teste de equivalência host/container; não recalibrar silenciosamente entre condições.
10. Quantificar overhead de medição e preservar campanhas anteriores em diretórios separados.

Critério de encerramento: especificação inequívoca + implementação testada + evidências de consistência + limitações registradas. A fase 1 não exige demonstrar misses raros nem ajustar HMM/EVT.

### Fase 2 — Matriz e análise

Matriz planejada: 3 arquiteturas (deferred, inline, async) × 2 condições (controle e I/O) × 2 substratos (host e container) = 12 células. Referência inicial: 500 s/run e 10 repetições/célula, a revisar antes da campanha conforme a frequência de episódios observada e recursos disponíveis. Não prolongar seletivamente apenas condições com resultados desejados.

Randomizar por blocos; manter configuração e comando de stress efetivos, warm-up e recuperação; tratar run como unidade de replicação e respeitar dependência entre jobs. Usar campanhas principais sem tracing pesado, acompanhadas por subset diagnóstico para efeito do observador. Reportar tempo total de exposição, inclusive runs sem eventos. Não confundir 132 misses com 132 choques independentes.

### Fase 3 — Intervenções

Priorizar host/inline: sink no armazenamento compartilhado versus tmpfs; dispositivo separado se disponível; desacoplamento e batching com contratos explícitos. Investigar syscall/stack de bloqueio. Usar `io.max` apenas como intervenção adicional justificada e registrar limites efetivamente aplicados. Tracing fornece evidência mecanística; comparação controlada/intervenção sustenta atribuição causal.

### Fase 4 — Recuperação e modelagem

Variar C ou T em subconjunto controlado; testar a inclinação de recuperação e misses por choque. Comparar IID, AR(1), HMM e modelo de backlog; considerar HSMM/regimes e EVT somente com dados suficientes. Separar treino/teste por runs ou blocos temporais sem vazamento. Avaliar frequência, duração, máximo e misses por episódio, risco em janelas e calibração fora da amostra. Se o modelo simples bastar, não forçar estados latentes adicionais.

EVT exige diagnóstico de limiar, dependência, misturas e volume de excedências/episódios. Considerar extremos de choques ou clusters com declustering e análise de sensibilidade; não aplicar automaticamente GPD a estados inferidos da mesma variável como se a seleção não afetasse a cauda. Não alegar pWCET seguro ou garantia determinística a partir de máximos empíricos.

### Fase 5 — Generalização

Escolher e justificar uma segunda máquina/storage stack/kernel e/ou workload de controle real. O busy-loop é uma sonda mecanística, não prova de impacto sobre estabilidade de controle. Alegações de benefício para controle precisam de métricas e aplicação próprias. O objetivo é identificar o que se transfere e sob quais condições, não apenas reproduzir um valor máximo.

## 6. Registro cumulativo dos resultados por fase

Os experimentos anteriores são evidências exploratórias pré-pivô (seção 3), não resultados das novas fases.

### Fase 1 — Resultados

- Status: em andamento. Suite atual auditada; especificação e implementação local concluídas; gate RT host/container no cylon pendente.
- Data: 09/09/2026. Fonte recebida: test_suite.zip, SHA256 7b19b3721bb30d76711720e4a432cb7e084bbc31b2bffb66ef7fd591c4c88ff0. Todos os 16 arquivos históricos preservados byte a byte.
- Implementação: phase1/periodic_v2.c, esquema 2, SHA256 b9f64037c63540de421a8b39449a1f21fbf1043280ac8f12a3496511b4576cb2; sem commit atribuído. Novo executável separado; stream continua legado, não alias de inline.
- Semântica: observação em memória prealocada/tocada; saída funcional de 64 bytes por job; deferred pós-loop, inline write, async fila finita drop-newest; sem promessa de durabilidade. CLOCK_MONOTONIC, catch-up e número fixo de jobs explícito, diferente do encerramento legado por finish. Timestamps computacionais, aceitação local e entrega separados.
- Auditoria: versão recebida já respeita --iters; o problema de recalibração do ZIP original não se aplica a ela. Persistem escrita CSV pós-finish no stream, ausência de saída funcional separada e de async. Launcher usa nerdctl. Configs de stress não representam o comando executado; validade de IRQ é ambígua no ramo io; resolver antes da fase 2.
- Testes locais: compilação sem warnings; 18 casos/verificações passaram, incluindo integridade temporal/binária, fila saturada, choque artificial, proteção contra sobrescrita, erro real de write e cinco pares de overhead parcial. Ambiente SCHED_OTHER, iters=1000, sem mlock, não cylon.
- Resultados quantitativos: três modos entregaram 100/100 registros cada; saturação artificial entregou 4/200 e descartou 196; choque artificial de 20 ms produziu 20 misses computacionais nesta execução local. Não são eventos naturais nem resultados da campanha científica.
- Overhead: diferenças pareadas de mediana de response_ns: [418.0, -2468.0, -43.0, -1289.5, 4008.5] ns; mediana -43.0 ns, sem conclusão causal. Intervalo parcial pós-computação deferred mediano 50 ns, que não representa overhead total. Validação na configuração científica permanece pendente.
- Artefatos: TDPS_fase1_suite_v2.zip, contendo a suite histórica, phase1/README.md, RESULTADOS_LOCAIS.md, sonda, gate de validação e local_validation/. Hash do binário e comandos registrados nos resultados. Evidências exploratórias pré-pivô permanecem na seção 3.
- Limitações: imagem/container não executados localmente; não houve acesso remoto ao cylon; tracing histórico preservado, não integrado à nova sonda. Overhead completo, equivalência funcional RT host/container e ambiente alvo ainda precisam de validação.
- Critério de passagem: não atendido. Próximo passo: executar o gate host e container no cylon com iters fixos, retornar os resultados, medir overhead em T=5 ms/D=3 ms e fechar fase 1 antes da intervenção causal curta. Não iniciar campanha principal automaticamente.

### Fase 2 — Resultados

- Status: não iniciada.
- Runs, configurações, tempo de exposição e episódios: pendentes.
- Resultados por célula e incerteza entre runs: pendentes.
- Integridade, exclusões justificadas e evidências: pendentes.
- Conclusões/limitações e critério de passagem: pendentes.

### Fase 3 — Resultados

- Status: não iniciada.
- Intervenções e controles executados: pendentes.
- Evidência de syscall/stack e efeitos quantitativos: pendentes.
- Hipóteses confirmadas/refutadas/não resolvidas: pendentes.
- Evidências, limitações e decisões: pendentes.

### Fase 4 — Resultados

- Status: não iniciada.
- Parâmetros T, C, saída e política de overrun: pendentes.
- Acurácia da recuperação e baselines: pendentes.
- Validação fora da amostra, risco e EVT (se aplicável): pendentes.
- Evidências, limitações e decisões: pendentes.

### Fase 5 — Resultados

- Status: não iniciada.
- Plataforma/aplicação adicional: pendente.
- Resultados de transferência e divergências: pendentes.
- Limites de generalização e contribuição final sustentada: pendentes.
- Evidências e decisões: pendentes.

## 7. Protocolo de atualização e continuidade

Ao encerrar cada fase, preencher: data; objetivo; versão do código/imagem; configuração; runs e exposição; quantidade de episódios; resultados com unidades e incerteza; evidências; hipóteses sustentadas ou rejeitadas; limitações; decisão de passagem; próximo passo. Manter a evidência exploratória original separada dos resultados confirmatórios.

Changelog:

- 09/09/2026, fase 1: recebida suite atual, preservado histórico, entregue sonda v2 e validação local; aguardando gate no cylon.

- 09/09/2026: pesquisador aprovou a mudança de foco e as cinco fases. Criado este registro; não foram executadas as fases. Próximo prompt inicia fase 1.

Prompt sugerido para continuidade:

> Leia TDPS_novo_foco_e_registro_das_fases.md e inicie a fase 1. Preserve as evidências pré-pivô. Primeiro verifique o estado atual do benchmark e dos scripts, depois feche a semântica de saída e medição antes de modificar o código. Ao terminar, atualize os resultados da fase 1 neste mesmo registro. Não inicie a campanha principal automaticamente.

## 8. Referências de posicionamento já discutidas

Lista de apoio da discussão anterior, não revisão sistemática exaustiva nem comprovação de novidade:

- JSA, escopo: https://www.sciencedirect.com/journal/journal-of-systems-architecture
- Najafi et al., Systems Research is Running out of Time, HotOS 2021: https://sigops.org/s/conferences/hotos/2021/papers/hotos21-s04-najafi.pdf
- Guet et al., dependência e tarefas multimodais, WCET 2017: https://drops.dagstuhl.de/entities/document/10.4230/OASIcs.WCET.2017.3
- Davis e Cucu-Grosjean, survey de análise probabilística de tempo, 2019: https://drops.dagstuhl.de/entities/document/10.4230/LITES-v006-i001-a003
- Friebe et al., probabilidades de miss de tarefas Markov, 2024: https://link.springer.com/article/10.1007/s11241-024-09431-7
- Manau et al., TailID e misturas raras nas caudas, ECRTS 2025: https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.ECRTS.2025.20
- Queiroz et al., revisão de containers industriais de tempo real: https://dl.acm.org/doi/full/10.1145/3617591

O novo estudo deve demonstrar novidade pela combinação validada de mecanismo, propagação, risco e intervenção, não pela mera utilização de técnicas conhecidas.
