# RPA Corretora de Seguros

Base inicial de implementacao do sistema RPA para operacao de corretora de seguros.

## O que esta pronto nesta versao

- Estrutura de projeto organizada por dominio.
- Orquestrador diario com fluxo unificado de agenda, tarefas, e-mails, planilhas, Segfy e portais.
- Regras principais do escopo implementadas em codigo:
  - Alerta de renovacao em `D-30` (renovacao interna) e `D-15` (novos).
  - Escalonamento inteligente da severidade de renovacao (ex.: `D-10` e abaixo como `CRITICA`).
  - Reforcos em `D-7` e `D-1` quando ainda houver pendencia.
  - Antecipacao para dia util anterior quando cair em fim de semana/feriado.
  - Comissao pendente (`STATUS PGTO` em branco).
  - Sinistro e endosso em aberto.
  - Divergencias entre acompanhamento e carteira com matching mais preciso de segurados (exato + fuzzy controlado).
  - Pendencias nao resolvidas da agenda e do Microsoft To Do.
- Dashboard diario com indicadores-chave.
- Adapters "stub" para evolucao incremental das integracoes reais.
- Gateway real para leitura/escrita das planilhas operacionais (`.xlsx`).
- OCR opcional do `SENHAS.pdf` para mapear servicos de credenciais.

## Estrutura

- `src/rpa_corretora/main.py`: entrada da aplicacao.
- `src/rpa_corretora/processing/orchestrator.py`: fluxo diario principal.
- `src/rpa_corretora/domain/rules.py`: regras de negocio.
- `src/rpa_corretora/integrations/interfaces.py`: contratos de integracao.
- `src/rpa_corretora/integrations/stub_adapters.py`: implementacoes de exemplo.
- `src/rpa_corretora/integrations/workbook_gateway.py`: integracao real com planilhas Excel.
- `src/rpa_corretora/integrations/credentials_pdf.py`: OCR e parsing de credenciais por PDF.
- `src/rpa_corretora/integrations/microsoft_todo_graph.py`: integracao Microsoft To Do via Graph API.
- `docs/especificacao_tecnica.md`: especificacao de implementacao.
- `docs/adendo_escopo_final_v1.md`: adendo formal do escopo final (nao regressivo).
- `docs/mapeamento_portais_wave1.md`: mapeamento dos 3 primeiros portais (Yelum, Porto, Mapfre).

## Execucao local

```bash
PYTHONPATH=src python3 -m rpa_corretora.main --dry-run
```

Por padrao, o projeto busca os arquivos operacionais em `arquivos/` na raiz do repositorio.

Para forcar planilhas stub:

```bash
PYTHONPATH=src python3 -m rpa_corretora.main --dry-run --use-stub-sheets
```

Para escanear servicos do arquivo de senhas (sem exibir senha):

```bash
PYTHONPATH=src python3 -m rpa_corretora.main --scan-credentials
```

Usando arquivo `.env` especifico:

```bash
PYTHONPATH=src python3 -m rpa_corretora.main --dry-run --env-file .env
```

Gerar dashboard visual HTML em caminho customizado:

```bash
PYTHONPATH=src python3 -m rpa_corretora.main --dry-run --dashboard-html-output outputs/dashboard_execucao.html
```

Desativar geracao do dashboard HTML:

```bash
PYTHONPATH=src python3 -m rpa_corretora.main --dry-run --no-dashboard-html
```

## Microsoft To Do (Graph)

Para ativar o modo real no To Do, configure no `.env`:

- `MICROSOFT_TODO_CLIENT_ID`
- `MICROSOFT_TODO_REFRESH_TOKEN` (recomendado) ou `MICROSOFT_TODO_USER` + `MICROSOFT_TODO_PASSWORD`
- `MICROSOFT_TODO_TENANT_ID` (opcional, padrao `common`)

## Microsoft To Do sem Client ID (fallback Windows)

Quando o `MICROSOFT_TODO_CLIENT_ID` nao estiver configurado, o projeto tenta automaticamente
o modo `WEB_AUTOMATION` no Windows usando login/senha da conta Microsoft.

Requisitos:

```bash
python -m pip install playwright
python -m playwright install chromium
```

Variaveis relevantes no `.env`:

- `MICROSOFT_TODO_USER`
- `MICROSOFT_TODO_PASSWORD`
- `MICROSOFT_TODO_WEB_HEADLESS` (`1` padrao; use `0` para abrir o navegador e depurar)

## Piloto de Portais (Wave 1)

Integracao piloto real com automacao web para os 3 primeiros portais (Yelum, Porto e Mapfre)
foi adicionada com fallback para `stub`.

Variaveis no `.env`:

- `YELUM_PORTAL_USER`
- `YELUM_PORTAL_PASSWORD`
- `YELUM_PORTAL_WEB_HEADLESS` (`1` padrao; use `0` para depurar)
- `PORTO_PORTAL_USER`
- `PORTO_PORTAL_PASSWORD`
- `PORTO_PORTAL_WEB_HEADLESS` (`1` padrao; use `0` para depurar)
- `MAPFRE_PORTAL_USER`
- `MAPFRE_PORTAL_PASSWORD`
- `MAPFRE_PORTAL_WEB_HEADLESS` (`1` padrao; use `0` para depurar)
- `PORTAL_USE_PDF_CREDENTIALS` (`1` para tentar ler credenciais Wave 1 via `SENHAS.pdf` quando env estiver vazio)

## Windows

Execucao direta no Windows (PowerShell/CMD):

```powershell
set PYTHONPATH=src
py -3 -m rpa_corretora.main --dry-run
```

Ou via script:

`scripts\\run_rpa_windows.bat --dry-run`

Preparacao inicial recomendada (uma vez):

`scripts\\setup_windows.bat`

Se seus arquivos operacionais estiverem em outra pasta no Windows, voce pode apontar tudo de uma vez:

`scripts\\run_rpa_windows.bat --dry-run --files-dir "C:\\RPA\\arquivos"`

## Testes

```bash
PYTHONPATH=src python3 -m pytest
```
