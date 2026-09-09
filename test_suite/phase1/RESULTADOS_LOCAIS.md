# Fase 1 — resultados locais e pendências

Data: 09/09/2026. Status: em andamento, gate no cylon pendente.

A especificação e os comandos estão em phase1/README.md. A suite histórica foi preservada byte a byte; a nova sonda é independente, esquema 2. Não há commit Git desta entrega: fonte identificada por SHA256.

- ZIP recebido SHA256: 7b19b3721bb30d76711720e4a432cb7e084bbc31b2bffb66ef7fd591c4c88ff0
- periodic_v2.c SHA256: b9f64037c63540de421a8b39449a1f21fbf1043280ac8f12a3496511b4576cb2
- Binário testado SHA256: 9d0901bed2e7f91ba93f1fbdd8be5f05afc71d00c03f3d8553c6e904cc34db83
- Ambiente: Linux-6.18.35-x86_64-with-glibc2.39; SCHED_OTHER, sem --mlock, CPU 0, logger 1; iters=1000. Não é cylon.
- Compilação: cc -O2 -Wall -Wextra -Wpedantic -std=c11 -pthread, sem warnings.
- Gate: 18 verificações/casos passaram, incluindo cinco pares de overhead; CSVs, logs, comandos e metadados em local_validation/.

| Caso | Jobs | Entregues | Descartados | Misses computacionais |
|---|---:|---:|---:|---:|
| deferred | 100 | 100 | 0 | 0 |
| inline | 100 | 100 | 0 | 1 |
| async | 100 | 100 | 0 | 0 |
| queue_full | 200 | 4 | 196 | 8 |
| shock | 100 | 100 | 0 | 20 |

Os três modos entregaram todos os registros sem erro nos testes básicos. Os números de misses da tabela são somente diagnósticos funcionais locais, com T=D=1 ms (fila saturada: 0,1 ms). Não são estimativas para a plataforma-alvo.

Fila saturada: capacidade 1 e atraso artificial do logger de 5 ms; contagem e IDs dos descartes/entregas conferidos. Choque: espera artificial de 20 ms no caminho de saída do job 10; o job seguinte apresentou atraso >=10 ms. Isso verifica a semântica de propagação, não confirma uma causa de I/O no kernel. Proteção contra sobrescrita e erro real EFBIG foram testados; write errors propagaram exit 1.

Overhead parcial: cinco pares minimal/instrumented com seed 20260909, 200 jobs por run, T=D=1 ms. Diferenças das medianas de resposta (instrumented−minimal), em ns: [418.0, -2468.0, -43.0, -1289.5, 4008.5]. Mediana das diferenças: -43.0 ns. Os sinais mistos mostram que este ensaio curto local não resolve o efeito sobre resposta. No deferred instrumentado, a mediana de output_finish−compute_finish foi 50 ns em cada par; esse intervalo não inclui toda a instrumentação (por exemplo sched_getcpu, gravação de timestamp final, clocks básicos, exportação e efeitos de memória). Não declarar overhead total de 50 ns nem overhead desprezível.

Resultados anteriores stream/deferred e traces não foram reanalisados. Não houve build/execução de container neste ambiente nem qualquer execução remota. O caminho de validação de container está implementado, mas ainda não validado em runtime. O gate no cylon deverá confirmar ABI, permissões RT/mlock, expansão da afinidade do logger dentro do cpuset e identidade do executável da imagem.

Critério de passagem: ainda não atendido. Faltam gate RT host/container, overhead na configuração científica T=5 ms/D=3 ms, ambiente auditado e registro da imagem no cylon. A campanha principal e a integração do tracing dirigido ficam para os próximos passos; nenhuma evidência artificial conta como choque natural.
