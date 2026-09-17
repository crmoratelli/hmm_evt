# TDPS — fase 1, esquema 2

Estado histórico desta entrega: implementação e validação funcional local em 09/09/2026. Os gates RT host/container e de overhead foram concluídos em 10/09/2026; consulte `TDPS_novo_foco_e_registro_das_fases.md`. A campanha principal continua separada em `../phase2/`.

## Auditoria e preservação

Todos os arquivos recebidos em test_suite.zip foram preservados byte a byte. A nova implementação está somente em phase1/. O executável antigo continua sendo a referência histórica; o novo chama-se periodic_v2.

A versão recebida já exige --iters, não recalibra durante medição, aloca samples com calloc e implementa deferred/stream. Contudo, calloc sozinho não demonstra prefault de todas as páginas. No stream, fprintf do CSV vem depois de finish e usa buffering da libc; não há timestamp da escrita ou contrato de saída funcional separado. wakeup_delay é start−release, incluindo backlog. O benchmark antigo encerra pelo finish observado; o número de jobs não é fixo sob atraso.

O launcher atual usa nerdctl/containerd, não Docker Engine. O build testa chrt --version, mas não prova identidade/funcionalidade do benchmark na imagem. O comando real de stress é --io 4 --hdd 2 --hdd-bytes 10G; os defaults IOMIX/HDD do config não controlam esse comando. IRQs não nulas geram VALID=0 mesmo quando o ramo io permite conclusão: há ambiguidade de validade a resolver antes da fase 2. O modo none ainda usa notificação FIFO; não é ausência total de observador. A cobertura temporal do trace precisa ser validada por eventos, não pelo tempo desde o evento mais antigo até a extração. Essas características históricas não foram alteradas nesta entrega.

## Contrato fechado para a sonda v2

Decisões de implementação iniciais, sujeitas a sensibilidade posterior; não são resultados científicos.

- Payload computacional idêntico ao loop C recebido; --iters obrigatório, sem calibração automática. Não misturar resultados com calibração diferente.
- N jobs explícitos (--jobs). Releases absolutos CLOCK_MONOTONIC: r[j]=r[0]+j*T, com catch-up sem skip/coalescing. Todos os N jobs terminam, mesmo que o tempo de parede exceda N*T. Para exposição nominal 500 s e T=5 ms, N=100000. Difere explicitamente do encerramento antigo por finish. Reportar exposição nominal, intervalo real e drain separadamente.
- Registro funcional sintético de 64 bytes: ID uint64 little-endian e 56 bytes ASCII T, pré-construído antes do loop. É uma sonda de transporte de saída, não demonstra fidelidade a dados de sensores nem estabilidade de controle.
- Observação em array previamente alocado e tocado; exportação CSV apenas após loop e drain. --mlock requerido nos testes RT. Alocação/touch de fila, abertura de arquivos, criação do logger e preparação dos registros precedem o loop. O primeiro uso de bibliotecas/cache ainda pode produzir efeitos de inicialização; o gate não os trata como ausência garantida de jitter.
- Sink aberto sem O_DIRECT/O_SYNC, com criação exclusiva. Escritas de 64 bytes via write, sem stdio buffering, sem fsync/fdatasync. Trata EINTR e short write. Aceitação pelo kernel não implica persistência em disco. Erros de escrita/close/export resultam em exit != 0; descartar um run com erro como comparação de serviço completo.
- O tamanho oferecido é N*64 em todos os modos; async pode entregar menos se descartar. Os arquivos contêm os IDs entregues em ordem. Registros parciais podem existir em runs com erro; não são runs válidos.

| Modo | Marco local | Entrega ao kernel | Saturação e custo |
|---|---|---|---|
| deferred | retenção em RAM prealocada | após todos os jobs | memória O(N), sem entrega durante o loop |
| inline | retorno de write completo | durante o job, após computação | bloqueio afeta o job e os subsequentes |
| async | publicação em fila SPSC finita | logger separado | drop-newest, sem backpressure no produtor |

Deferred é um controle sem I/O funcional durante o loop; não oferece o mesmo prazo de entrega que inline. Async não garante serviço completo quando há perdas. Não comparar apenas response_ns como prova de equivalência funcional.

Async: fila default 1024 registros, incluindo a escrita em voo; índices atômicos lock-free verificados em startup; logger SCHED_OTHER prioridade 0 em CPU housekeeping explícita, fora do core físico RT. Polling de 100 us quando vazia; esse atraso faz parte da arquitetura. Capacidade default representa aproximadamente 5,12 s de produção a T=5 ms, mas não garante ausência de saturação. Contador de high-water usa observação do produtor (limite superior amostrado), não medição contínua exata. O logger publica tail só depois de terminar a escrita. Drain espera toda saída aceita, sem timeout interno; bloqueio permanente exige encerramento externo e invalida o run. Drop e erro são eventos distintos.

## Timestamps e métricas

Todos os timestamps são CLOCK_MONOTONIC em ns. Para cada job:

- release_ns, start_ns e compute_finish_ns; finish_ns é alias explícito de compute_finish_ns para leitores antigos.
- execution_ns = compute_finish − start; tempo decorrido do payload, incluindo preempção, não tempo de CPU puro.
- response_ns = compute_finish − release; lateness_ns = response − D; miss = response > D.
- wakeup_delay_ns = start − release: alias legado de atraso de início acumulado, não latência pura de scheduler.
- output_start_ns/output_finish_ns delimitam tentativa local de saída. Em deferred, delimitam retenção; em async, enqueue ou rejeição; em inline, escrita. accepted/dropped qualificam o marco.
- delivery_start_ns/delivery_finish_ns delimitam write pelo produtor/logger/batch; delivery_errno indica erro. Zero nos descartados.
- Resposta local: output_finish−release apenas quando accepted=1. Resposta de entrega: delivery_finish−release apenas quando accepted=1 e delivery_errno=0. Calcular misses desses marcos separadamente; não substituir miss computacional.
- Atraso de entrega após computação: delivery_finish−compute_finish. Latência da fila pode ser aproximada por delivery_start−output_start; inclui a operação de enqueue e não é tempo exato só de espera.
- Em async, o consumidor pode entregar antes de o produtor registrar output_finish; não exigir delivery_finish >= output_finish. O timestamp de publicação exato não é observado.
- --minimal, somente deferred, omite os dois timestamps de saída e sched_getcpu; mantém as medidas básicas. Campos de saída ficam zero e cpu=-1. Serve para comparação parcial de overhead, não como observador de custo zero.

A recorrência W[j+1]=max(0,W[j]+C[j]+L[j]−T) é aproximada: há trabalho entre compute_finish e output_start, instrumentação após output_finish e custo de sleep/reinício. Avaliar resíduo em vez de atribuir tudo ao L medido. Não ajustar HMM/EVT nesta fase.

## Validação e execução no cylon

Extraia a entrega em diretório separado do histórico. Entre em test_suite/phase1. Não use run_campaign.py para esta fase. Os comandos abaixo não alteram governor, IRQ, kubelet ou tracing; pressupõem a preparação RT previamente feita no cylon.

```bash
make clean all
./periodic_v2 --version
sudo python3 validate_phase1.py --output /home/ghost/tdps_phase1_host_v2 \
  --iters 151994 --cpu 3 --logger-cpu 0 --rt
```

151994 é a calibração reportada no registro; conferir com o calibration.env da última execução antes de usar. Não recalibrar entre host/container. O gate --rt exige performance, min=max=3800000 e boost=0; verifica que logger não usa sibling do periódico. Não substitui auditoria completa de IRQs, isolamento, workloads externos e kernel. Salva cmdline, cpufreq, topologia, snapshots de IRQs, hashes, comandos e logs. Use CPU 0 apenas se confirmado como housekeeping no cylon.

Para testar a mesma imagem no container (BuildKit deve estar disponível):

```bash
sudo nerdctl --namespace tdps build -t localhost/tdps/periodic-bench:phase1-v2 .
sudo python3 validate_phase1.py --output /home/ghost/tdps_phase1_container_v2 \
  --iters 151994 --cpu 3 --logger-cpu 0 --rt --backend container
```

O teste compara SHA256 do executável host com o copiado para a imagem antes de rodar. O container recebe cpuset 3,0; o periódico é fixado em 3 e o logger em 0. O contrato muda o cpuset de uma CPU da suite antiga de forma explícita, necessária ao logger. A imagem é nova, sem sobrescrever causal-v1. Não se presume que compilar localmente aqui produz ABI compatível com Ubuntu do cylon: recompile lá antes do build.

Os diretórios de saída devem ser novos; o teste recusa sobrescrita. Testes são curtos, sem stress/tracing, com períodos 1 ms e 0,1 ms, e deadline=T para invariantes; não são a configuração científica T=5 ms/D=3 ms. Valida 3 modos, conteúdo binário por ID, perdas sob fila 1 com logger atrasado, choque artificial de 20 ms, rejeição de stream, proteção de destino existente e erro real de write no host. Executa também 5 pares minimal/instrumented, com ordem aleatória fixa. Não usar os choques artificiais como evidência de mecanismo de kernel.

Retornar os dois diretórios de validação, incluindo validation.json, logs e CSVs. Depois avaliar consistência host/container, overhead a T=5 ms/D=3 ms e iters fixos, condições do ambiente e decidir encerramento. O teste atual mede apenas uma parte da instrumentação e não permite declarar overhead total desprezível.

## Pendências para encerrar a fase 1

1. Gate funcional RT host/container no cylon e identidade da imagem.
2. Medição de overhead na configuração científica, com repetição suficiente e análise por run; registrar custo/memória do logger e drain.
3. Revisão dos contratos de prazo de saída em conjunto com os resultados. Nenhum deles promete durabilidade.
4. Antes da fase 2: launcher versionado para nova matriz, identificação de arquitetura no run ID, semântica de validade de IRQ, registro do stress efetivo e instrumentação diagnóstica dirigida a syscall/stack.

O tracing histórico foi preservado, mas não conectado à sonda v2. A validação causal curta prevista entre fases 1/2 dependerá dessa integração dirigida. Nenhuma campanha nova foi executada no cylon por esta entrega.
