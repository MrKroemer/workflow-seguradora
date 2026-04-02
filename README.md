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
- Relatorio de execucao obrigatorio ao final do ciclo (`JSON + PDF`), inclusive em falha critica.
- Adapters "stub" para evolucao incremental das integracoes reais.
- Gateway real para leitura/escrita das planilhas operacionais (`.xlsx`).
- Gateways operacionais para ambiente Windows:
  - Google Calendar (API por refresh token).
  - Gmail (IMAP).
  - Segfy (API configuravel + fallback por export `.xlsx` + fila local de contingencia).
  - WhatsApp (API HTTP com fallback em outbox local).
  - E-mail SMTP (com fallback em outbox local).
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
- `docs/mapeamento_portais_wave2.md`: mapeamento dos portais 4 a 6 (Bradesco, Allianz, Suhai).
- `docs/mapeamento_portais_wave3.md`: mapeamento inicial dos portais 7 a 9 (Tokio, HDI, Azul), com os tres portais detalhados.

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

Auditoria de ambiente Windows (detecao de SO, apps/dependencias e arquivos operacionais):

```bash
PYTHONPATH=src python3 -m rpa_corretora.main --windows-audit-only
```

Desativar geracao do dashboard HTML:

```bash
PYTHONPATH=src python3 -m rpa_corretora.main --dry-run --no-dashboard-html
```

Definir pasta de saida para os relatorios de execucao:

```bash
PYTHONPATH=src python3 -m rpa_corretora.main --execution-report-dir outputs/relatorios
```

## Microsoft To Do (Graph)

Para ativar o modo real no To Do, configure no `.env`:

- `MICROSOFT_TODO_CLIENT_ID`
- `MICROSOFT_TODO_REFRESH_TOKEN` (recomendado) ou `MICROSOFT_TODO_USER` + `MICROSOFT_TODO_PASSWORD`
- `MICROSOFT_TODO_TENANT_ID` (opcional, padrao `common`)
- `MICROSOFT_TODO_LIST_NAME` (opcional, ex.: `Principal`)

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

Com To Do configurado (`GRAPH` ou `WEB_AUTOMATION`), o bot consegue:

- ler tarefas abertas;
- criar tarefas operacionais;
- atualizar tarefas ja existentes;
- concluir tarefas sincronizadas da agenda.

## Integracoes Operacionais (Agenda, Gmail, Segfy, WhatsApp, SMTP)

Variaveis no `.env` para ativacao real:

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
  - `GMAIL_IMAP_HOST` (opcional, padrao `imap.gmail.com`)
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
  - ou `SEGFY_EXPORT_XLSX` para leitura via exportacao
- WhatsApp:
  - `WHATSAPP_PROVIDER_URL`
  - `WHATSAPP_PROVIDER_TOKEN`
- E-mail de notificacao:
  - `SMTP_HOST`
  - `SMTP_PORT`
  - `SMTP_USER` / `SMTP_PASSWORD` (quando necessario)
  - `SMTP_FROM_EMAIL` (opcional)
  - `INSURED_NOTIFY_EMAIL_TO` (destino para notificacoes do compromisso verde)
- Relatorio de execucao:
  - `EXECUTION_REPORT_EMAIL_TO` (destino do e-mail automatico ao final do ciclo)
  - `EXECUTION_REPORT_OUTPUT_DIR` (opcional, pasta de saida dos arquivos de relatorio)

Quando o SMTP estiver ativo e `EXECUTION_REPORT_EMAIL_TO` configurado,
o envio automatico inclui os anexos JSON e PDF do relatorio.

Quando uma integracao externa nao estiver configurada, o projeto nao injeta dados fake no fluxo:

- Agenda/Gmail: modo `NOOP` (sem leitura).
- WhatsApp/E-mail: grava em `outputs/whatsapp_outbox.jsonl` e `outputs/email_outbox.jsonl`.
- Segfy sem API/web/export: grava fila de baixa em `outputs/segfy_payment_queue.jsonl`.
- Em todas as execucoes, o diagnostico do runtime e salvo em `outputs/windows_runtime_report.json`
  (ou caminho definido por `--windows-audit-output`).
- Em todas as execucoes, tambem sao gerados:
  - `relatorio_execucao_YYYYMMDD_HHMMSS.json`
  - `relatorio_execucao_YYYYMMDD_HHMMSS.pdf`

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

## Piloto de Portais (Wave 2)

Integracao piloto real com automacao web para os portais Bradesco, Allianz e Suhai
foi adicionada no mesmo pipeline de fallback.

Variaveis no `.env`:

- `BRADESCO_PORTAL_USER`
- `BRADESCO_PORTAL_PASSWORD`
- `BRADESCO_PORTAL_WEB_HEADLESS` (`1` padrao; use `0` para depurar)
- `ALLIANZ_PORTAL_USER`
- `ALLIANZ_PORTAL_PASSWORD`
- `ALLIANZ_PORTAL_WEB_HEADLESS` (`1` padrao; use `0` para depurar)
- `SUHAI_PORTAL_USER`
- `SUHAI_PORTAL_PASSWORD`
- `SUHAI_PORTAL_WEB_HEADLESS` (`1` padrao; use `0` para depurar)

## Piloto de Portais (Wave 3 - inicio)

Integracao web inicial da Tokio Marine, HDI e Azul foi adicionada no mesmo pipeline `WEB_MULTI+STUB`,
com tratamento de modais/termo/cookies e fallback nao regressivo para `stub`.

Variaveis no `.env`:

- `TOKIO_PORTAL_USER`
- `TOKIO_PORTAL_PASSWORD`
- `TOKIO_PORTAL_WEB_HEADLESS` (`1` padrao; use `0` para depurar)
- `HDI_PORTAL_USER`
- `HDI_PORTAL_PASSWORD`
- `HDI_PORTAL_WEB_HEADLESS` (`1` padrao; use `0` para depurar)
- `AZUL_PORTAL_USER`
- `AZUL_PORTAL_PASSWORD`
- `AZUL_PORTAL_WEB_HEADLESS` (`1` padrao; use `0` para depurar)

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
