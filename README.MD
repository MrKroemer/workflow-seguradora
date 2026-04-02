# RPA Corretora de Seguros

Automacao operacional para corretora de seguros com processamento diario de agenda, tarefas, e-mails, planilhas, regras de alerta e consolidacao em dashboard.

## Status atual

- Orquestracao diaria funcional (`dry-run` e modo normal).
- Processamento real de planilhas `.xlsx`:
  - `SEGUROS PBSEG.xlsx`
  - `ACOMPANHAMENTO 2026.xlsx`
  - `FLUXO DE CAIXA.xlsx`
- OCR opcional de `SENHAS.pdf` para catalogar servicos de credenciais.
- Integracao Microsoft To Do via Microsoft Graph pronta (com fallback web para Windows),
  incluindo leitura + criacao + atualizacao + conclusao de tarefas.
- Integracoes operacionais ja plugadas no fluxo principal:
  - Google Calendar (API);
  - Gmail (IMAP);
  - Segfy (API/config + fallback exportacao e fila local);
  - WhatsApp (API HTTP + outbox local);
  - SMTP (envio real + outbox local).
- Camada de precisao de regras:
  - matching de segurados por nome com estrategia exata + fuzzy controlada;
  - renovacoes `D-10` e abaixo com severidade `CRITICA`.
- Dashboard com indicadores operacionais e financeiros.
- Relatorio de execucao obrigatorio ao fim do ciclo (`JSON + PDF`), inclusive em falha critica.

## Estrutura principal

- `src/rpa_corretora/main.py`: entrada do sistema.
- `src/rpa_corretora/processing/orchestrator.py`: fluxo diario.
- `src/rpa_corretora/processing/dashboard.py`: consolidacao de KPIs.
- `src/rpa_corretora/domain/rules.py`: regras de negocio e alertas.
- `src/rpa_corretora/integrations/workbook_gateway.py`: leitura/escrita real de Excel.
- `src/rpa_corretora/integrations/microsoft_todo_graph.py`: leitura e manipulacao de tarefas do Microsoft To Do via Graph.
- `src/rpa_corretora/integrations/credentials_pdf.py`: OCR do PDF de senhas.
- `docs/adendo_escopo_final_v1.md`: adendo oficial do escopo final (sem regressao).
- `docs/mapeamento_portais_wave1.md`: mapeamento dos 3 primeiros portais (Yelum, Porto, Mapfre).
- `docs/mapeamento_portais_wave2.md`: mapeamento dos portais 4 a 6 (Bradesco, Allianz, Suhai).
- `docs/mapeamento_portais_wave3.md`: mapeamento inicial dos portais 7 a 9 (Tokio, HDI, Azul), com os tres portais detalhados.

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
MICROSOFT_TODO_LIST_NAME=Principal
MICROSOFT_TODO_USER=cadastro.segurados@hotmail.com
MICROSOFT_TODO_PASSWORD=******
```

Observacoes:

- Para ativar To Do real (`GRAPH`), e necessario ao menos:
  - `MICROSOFT_TODO_CLIENT_ID`
  - `MICROSOFT_TODO_REFRESH_TOKEN` (recomendado)
- Opcional: `MICROSOFT_TODO_LIST_NAME` para escolher a lista-alvo de escrita
  (criacao/atualizacao/conclusao) pelo bot.
- Sem esses valores, no Windows o sistema tenta `WEB_AUTOMATION` com login/senha.
- No modo `WEB_AUTOMATION`, o bot usa o Microsoft To Do na web (Edge/Playwright) com a mesma conta do To Do local instalado no Windows.
  Atualmente, nao ha leitura direta da aplicacao desktop nativa.
- Se Graph e automacao web nao estiverem disponiveis, o sistema entra em `NOOP` (sem dados ficticios).

### 1.1) Integracoes operacionais (agenda, e-mail, Segfy, WhatsApp)

Variaveis no `.env`:

- Agenda Google:
  - `GOOGLE_CLIENT_ID`
  - `GOOGLE_CLIENT_SECRET`
  - `GOOGLE_REFRESH_TOKEN`
  - `GOOGLE_CALENDAR_ID` (opcional, padrao `primary`)
  - `GOOGLE_COLOR_IDS_VERMELHO` (padrao `4,11`)
  - `GOOGLE_COLOR_IDS_AZUL` (padrao `9`)
  - `GOOGLE_COLOR_IDS_CINZA` (padrao `8`)
  - `GOOGLE_COLOR_IDS_VERDE` (padrao `10`)
- Gmail:
  - `GMAIL_IMAP_USER`
  - `GMAIL_IMAP_PASSWORD`
  - `GMAIL_IMAP_HOST` (opcional)
  - `GMAIL_IMAP_MAILBOX` (opcional)
- Segfy:
  - `SEGFY_API_BASE_URL` + (`SEGFY_API_TOKEN` ou `SEGFY_USER` + `SEGFY_PASSWORD`)
  - ou automacao web no Windows:
    - `SEGFY_WEB_ENABLED=1`
    - `SEGFY_WEB_BASE_URL` (ex.: `https://app.segfy.com`)
    - `SEGFY_WEB_BROWSER_CHANNEL=chrome`
    - `SEGFY_WEB_HEADLESS` (`1` padrao; use `0` para depurar)
    - `SEGFY_WEB_IMPORT_ENABLED=1` (importa documentos na tela "Importar PDF/Excel")
    - `SEGFY_IMPORT_SOURCE_DIR` (pasta local dos arquivos a importar)
    - `SEGFY_WEB_IMPORT_URL` (opcional, se quiser forcar URL exata da tela)
    - `SEGFY_IMPORT_STATE_PATH` (controle da ultima execucao para importar apenas arquivos novos)
  - ou `SEGFY_EXPORT_XLSX`
- WhatsApp:
  - `WHATSAPP_PROVIDER_URL`
  - `WHATSAPP_PROVIDER_TOKEN`
- SMTP:
  - `SMTP_HOST`
  - `SMTP_PORT`
  - `SMTP_USER`
  - `SMTP_PASSWORD`
  - `SMTP_FROM_EMAIL`
  - `INSURED_NOTIFY_EMAIL_TO`
- Relatorio de execucao:
  - `EXECUTION_REPORT_EMAIL_TO`
  - `EXECUTION_REPORT_OUTPUT_DIR` (opcional)

Com SMTP ativo e `EXECUTION_REPORT_EMAIL_TO` definido,
o sistema envia o relatorio com anexos JSON e PDF.

### 1.2) Fallback Windows sem Client ID

Para usar To Do sem `MICROSOFT_TODO_CLIENT_ID` no Windows:

```bash
python -m pip install playwright
python -m playwright install chromium
```

Variavel opcional:

- `MICROSOFT_TODO_WEB_HEADLESS=1` (padrao). Use `0` para abrir navegador e depurar.

### 1.3) Piloto de Portais (Wave 1)

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

### 1.4) Piloto de Portais (Wave 2)

Variaveis no `.env`:

- `BRADESCO_PORTAL_USER`
- `BRADESCO_PORTAL_PASSWORD`
- `BRADESCO_PORTAL_WEB_HEADLESS=1` (padrao). Use `0` para depurar.
- `ALLIANZ_PORTAL_USER`
- `ALLIANZ_PORTAL_PASSWORD`
- `ALLIANZ_PORTAL_WEB_HEADLESS=1` (padrao). Use `0` para depurar.
- `SUHAI_PORTAL_USER`
- `SUHAI_PORTAL_PASSWORD`
- `SUHAI_PORTAL_WEB_HEADLESS=1` (padrao). Use `0` para depurar.

### 1.5) Piloto de Portais (Wave 3 - inicio)

Integracao web inicial da Tokio Marine, HDI e Azul foi adicionada no pipeline `WEB_MULTI+STUB`,
com tratamento de modais/termo/cookies e fallback nao regressivo para `stub`.

Variaveis no `.env`:

- `TOKIO_PORTAL_USER`
- `TOKIO_PORTAL_PASSWORD`
- `TOKIO_PORTAL_WEB_HEADLESS=1` (padrao). Use `0` para depurar.
- `HDI_PORTAL_USER`
- `HDI_PORTAL_PASSWORD`
- `HDI_PORTAL_WEB_HEADLESS=1` (padrao). Use `0` para depurar.
- `AZUL_PORTAL_USER`
- `AZUL_PORTAL_PASSWORD`
- `AZUL_PORTAL_WEB_HEADLESS=1` (padrao). Use `0` para depurar.

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

Auditoria de ambiente Windows (detecao do SO + apps/dependencias + arquivos):

```bash
PYTHONPATH=src python3 -m rpa_corretora.main --windows-audit-only
```

Desativar geracao de HTML:

```bash
PYTHONPATH=src python3 -m rpa_corretora.main --dry-run --no-dashboard-html
```

Salvar relatorios em pasta customizada:

```bash
PYTHONPATH=src python3 -m rpa_corretora.main --execution-report-dir outputs/relatorios
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
- modo de integracao da agenda (`GOOGLE_API` ou `NOOP`)
- modo de integracao do Gmail (`GMAIL_IMAP` ou `NOOP`)
- modo de integracao do Segfy (`API_OR_QUEUE`, `WEB_AUTOMATION_OR_QUEUE`, `WEB_AUTOMATION_OR_EXPORT_OR_QUEUE`, `EXPORT_XLSX_OR_QUEUE` ou `QUEUE_ONLY`)
- modo de integracao do WhatsApp (`HTTP_API` ou `OUTBOX_FILE`)
- modo de integracao de e-mail (`SMTP` ou `OUTBOX_FILE`)
- modo de integracao do To Do (`GRAPH`, `WEB_AUTOMATION` ou `NOOP`)
- modo de integracao dos portais (`WEB_MULTI+STUB` ou `STUB`)
- auditoria de runtime Windows em JSON (`outputs/windows_runtime_report.json`)
- relatorio de execucao em JSON/PDF (`relatorio_execucao_YYYYMMDD_HHMMSS.{json,pdf}`)
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
3. Avancar no mapeamento detalhado dos portais restantes (unica frente ainda parcial).
