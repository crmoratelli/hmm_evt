# Pipeline: latência para regimes temporais

Os dados em `data/` são somente leitura. Os scripts geram todos os artefatos em
`results/` e podem ser executados a partir da raiz do projeto.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/01_validate.py
python scripts/02_prepare.py
python scripts/03_describe.py
python scripts/04_temporal_structure.py
python scripts/05_report.py
```

Os parâmetros de entrada e saída podem ser alterados com `--input` e `--output`.
Se os caminhos ou nomes dos CSVs não identificarem condição, ambiente e run,
crie um `manifest.csv` com as colunas `file`, `condition`, `environment` e
`run` e informe `--manifest manifest.csv` em cada etapa.

O leitor aceita as colunas obrigatórias `release_ns`, `finish_ns`,
`response_ns` e `lateness_ns`; `miss` é opcional. O identificador de condição
e ambiente é inferido de diretórios como `cfs_pinned/host_run01.csv`.
