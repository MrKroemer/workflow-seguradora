# RPA Corretora de Seguros

Automacao operacional para corretora de seguros com processamento diario de agenda, tarefas, e-mails, planilhas, regras de alerta e consolidacao em dashboard.

## Status atual

- Orquestracao diaria funcional (`dry-run` e modo normal).
- Processamento real de planilhas `.xlsx`:
  - `SEGUROS PBSEG.xlsx`
  - `ACOMPANHAMENTO 2026.xlsx`
  - `FLUXO DE CAIXA.xlsx`
- OCR opcional de `SENHAS.pdf` para catalogar servicos de credenciais.
- Integracao Microsoft To Do via Microsoft Graph pronta (com fallback web para Windows e fallback `stub`).
- Camada de precisao de regras:
  - matching de segurados por nome com estrategia exata + fuzzy controlada;
  - renovacoes `D-10` e abaixo com severidade `CRITICA`.
- Dashboard com indicadores operacionais e financeiros.

## Estrutura principal

- `src/rpa_corretora/main.py`: entrada do sistema.
- `src/rpa_corretora/processing/orchestrator.py`: fluxo diario.
- `src/rpa_corretora/processing/dashboard.py`: consolidacao de KPIs.
- `src/rpa_corretora/domain/rules.py`: regras de negocio e alertas.
- `src/rpa_corretora/integrations/workbook_gateway.py`: leitura/escrita real de Excel.
- `src/rpa_corretora/integrations/microsoft_todo_graph.py`: leitura de tarefas do Microsoft To Do via Graph.
- `src/rpa_corretora/integrations/credentials_pdf.py`: OCR do PDF de senhas.
- `docs/adendo_escopo_final_v1.md`: adendo oficial do escopo final (sem regressao).
- `docs/mapeamento_portais_wave1.md`: mapeamento dos 3 primeiros portais (Yelum, Porto, Mapfre).

## Requisitos

- Python `3.11+`
- Dependencias no `pyproject.toml`

## Configuracao

### 1) Arquivo `.env`

Exemplo minimo para o estado atual:

```env
MICROSOFT_TODO_CLIENT_ID=
MICROSOFT_TODO_REFRESH_TOKEN=
MICROSOFT_TODO_TENANT_ID=common
MICROSOFT_TODO_USER=cadastro.segurados@hotmail.com
MICROSOFT_TODO_PASSWORD=******
```

Observacoes:

- Para ativar To Do real (`GRAPH`), e necessario ao menos:
  - `MICROSOFT_TODO_CLIENT_ID`
  - `MICROSOFT_TODO_REFRESH_TOKEN` (recomendado)
- Sem esses valores, no Windows o sistema tenta `WEB_AUTOMATION` com login/senha.
- Se Graph e automacao web nao estiverem disponiveis, o sistema entra em `STUB`.

### 1.1) Fallback Windows sem Client ID

Para usar To Do sem `MICROSOFT_TODO_CLIENT_ID` no Windows:

```bash
python -m pip install playwright
python -m playwright install chromium
```

Variavel opcional:

- `MICROSOFT_TODO_WEB_HEADLESS=1` (padrao). Use `0` para abrir navegador e depurar.

### 1.2) Piloto de Portais (Wave 1)

Variaveis no `.env`:

- `YELUM_PORTAL_USER`
- `YELUM_PORTAL_PASSWORD`
- `YELUM_PORTAL_WEB_HEADLESS=1` (padrao). Use `0` para depurar.
- `PORTO_PORTAL_USER`
- `PORTO_PORTAL_PASSWORD`
- `PORTO_PORTAL_WEB_HEADLESS=1` (padrao). Use `0` para depurar.
- `MAPFRE_PORTAL_USER`
- `MAPFRE_PORTAL_PASSWORD`
- `MAPFRE_PORTAL_WEB_HEADLESS=1` (padrao). Use `0` para depurar.
- `PORTAL_USE_PDF_CREDENTIALS=1` para buscar credenciais Wave 1 no `SENHAS.pdf` quando env estiver vazio.

### 2) Arquivos operacionais

Os caminhos sao lidos de `config/settings.json` e podem ser sobrescritos por ambiente:

- `SEGUROS_PBSEG_XLSX`
- `ACOMPANHAMENTO_2026_XLSX`
- `FLUXO_CAIXA_XLSX`
- `SENHAS_PDF`

## Execucao

### Linux/macOS

```bash
PYTHONPATH=src python3 -m rpa_corretora.main --dry-run
```

Por padrao, o projeto busca os arquivos operacionais em `arquivos/` na raiz do repositorio.

Gerar dashboard visual HTML em caminho customizado:

```bash
PYTHONPATH=src python3 -m rpa_corretora.main --dry-run --dashboard-html-output outputs/dashboard_execucao.html
```

Desativar geracao de HTML:

```bash
PYTHONPATH=src python3 -m rpa_corretora.main --dry-run --no-dashboard-html
```

### Windows (PowerShell/CMD)

```powershell
set PYTHONPATH=src
py -3 -m rpa_corretora.main --dry-run
```

Ou:

```bat
scripts\run_rpa_windows.bat --dry-run
```

Preparacao inicial recomendada (uma vez):

```bat
scripts\setup_windows.bat
```

Se seus arquivos operacionais estiverem em outra pasta no Windows, voce pode apontar tudo de uma vez:

```bat
scripts\run_rpa_windows.bat --dry-run --files-dir "C:\RPA\arquivos"
```

## Modos uteis

### Forcar planilhas `stub`

```bash
PYTHONPATH=src python3 -m rpa_corretora.main --dry-run --use-stub-sheets
```

### Escanear servicos no `SENHAS.pdf` (sem exibir senha)

```bash
PYTHONPATH=src python3 -m rpa_corretora.main --scan-credentials
```

## Evidencias de execucao

Ao rodar, o sistema imprime:

- total de alertas
- e-mails de seguradoras triados
- lancamentos de caixa detectados
- modo de integracao do To Do (`GRAPH`, `WEB_AUTOMATION` ou `STUB`)
- modo de integracao dos portais (`WEB_WAVE1+STUB` ou `STUB`)
- snapshot do dashboard

Exemplo de linha esperada para To Do real:

```text
Microsoft To Do modo: GRAPH
```

## Testes

```bash
PYTHONPATH=src python3 -m pytest
```

## Observacoes de seguranca

- Nao versionar `.env`.
- Nao imprimir tokens/senhas em logs.
- Preferir `refresh_token` para Microsoft Graph em vez de login por senha.

## Proximos passos recomendados

1. Escolher o modo do To Do:
   - `GRAPH`: preencher `MICROSOFT_TODO_CLIENT_ID` e `MICROSOFT_TODO_REFRESH_TOKEN`.
   - `WEB_AUTOMATION` (Windows): instalar Playwright e manter `MICROSOFT_TODO_USER` + `MICROSOFT_TODO_PASSWORD`.
2. Rodar `--dry-run` e confirmar `Microsoft To Do modo: GRAPH` ou `WEB_AUTOMATION`.
3. Avancar para integracao real de Gmail, Segfy e portais no mesmo padrao.
