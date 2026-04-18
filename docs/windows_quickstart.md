# Windows Quickstart - RPA Corretora

Guia rapido para preparar e executar o bot em ambiente Windows.

## 1) Pre-requisitos

- Windows 10/11
- Python 3.11+ instalado (`py -3 --version`)
- Google Chrome ou Microsoft Edge instalado
- Internet para integracoes (Google, Microsoft, Gmail, portais, APIs)

## 2) Preparar ambiente (uma vez)

No CMD ou PowerShell, na raiz do projeto:

```bat
scripts\setup_windows.bat
```

Esse script:

- cria `.venv`
- instala dependencias do projeto
- instala `playwright`
- instala browser Chromium do Playwright

## 3) Configurar `.env`

Use `.env.example` como base e preencha as variaveis do seu ambiente.

Blocos principais:

- Producao estrita (sem fallback):
  - `RPA_STRICT_PRODUCTION=1`
  - `MICROSOFT_TODO_REQUIRE_DESKTOP=1`
  - com isso, o bot bloqueia execucao se qualquer modulo cair em `NOOP/STUB/QUEUE/OUTBOX`.

- Microsoft To Do:
  - `MICROSOFT_TODO_DESKTOP_ENABLED=1` (modo prioritario: app nativo no Windows)
  - `MICROSOFT_TODO_CLIENT_ID` + `MICROSOFT_TODO_REFRESH_TOKEN` (modo Graph opcional)
  - ou `MICROSOFT_TODO_USER` + `MICROSOFT_TODO_PASSWORD` (fallback web no Windows)
  - opcional: `MICROSOFT_TODO_LIST_NAME=Principal`
  - opcional: `MICROSOFT_TODO_DESKTOP_TIMEOUT_SECONDS=40`
  - para modo desktop, instale `pywinauto`: `py -3 -m pip install pywinauto`
  - com To Do configurado, o bot sincroniza tarefas da agenda (cria, atualiza e conclui tarefas automaticamente).
- Agenda Google: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN`
- Cores da Agenda Google (opcional, mas recomendado para sua regra):
  - `GOOGLE_COLOR_IDS_VERMELHO`
  - `GOOGLE_COLOR_IDS_AZUL`
  - `GOOGLE_COLOR_IDS_CINZA`
  - `GOOGLE_COLOR_IDS_VERDE`
- Gmail IMAP: `GMAIL_IMAP_USER`, `GMAIL_IMAP_PASSWORD`
- Segfy:
  - API: `SEGFY_API_BASE_URL` + token/login
  - ou Web no Chrome: `SEGFY_WEB_ENABLED=1`, `SEGFY_WEB_BASE_URL`, `SEGFY_WEB_BROWSER_CHANNEL=chrome`
  - para importacao no Segfy Web: `SEGFY_WEB_IMPORT_ENABLED=1` + `SEGFY_IMPORT_SOURCE_DIR`
  - para importar so arquivos novos desde a ultima execucao: `SEGFY_IMPORT_STATE_PATH`
  - para baixa de pagamentos no Segfy Web: `SEGFY_WEB_PAYMENT_ENABLED=1` (opcionalmente `SEGFY_WEB_PAYMENT_URL`)
  - ou exportacao: `SEGFY_EXPORT_XLSX`
  - em producao estrita, o Segfy e aceito em `API_ONLY` ou `WEB_AUTOMATION_ONLY`
- Portais: usuarios e senhas de cada seguradora
- WhatsApp API: `WHATSAPP_PROVIDER_URL`, `WHATSAPP_PROVIDER_TOKEN`
- SMTP: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL`
- Relatorio por e-mail: `EXECUTION_REPORT_EMAIL_TO`

## 4) Definir pasta dos arquivos operacionais

Opcao A (padrao do projeto):

- usar a pasta `arquivos` na raiz

Opcao B (pasta externa no Windows):

```bat
scripts\run_rpa_windows.bat --dry-run --files-dir "C:\RPA\arquivos"
```

## 5) Validar runtime Windows

```bat
scripts\run_rpa_windows.bat --windows-audit-only
```

Arquivo gerado:

- `outputs/windows_runtime_report.json`

## 6) Teste seguro (dry-run)

```bat
scripts\run_rpa_windows.bat --dry-run
```

No dry-run, o bot processa leitura/regras/dashboard/relatorios, mas nao envia integracoes externas.

## 7) Execucao real

```bat
scripts\run_rpa_windows.bat --strict-production
```

## 8) Evidencias esperadas

Depois da execucao:

- `outputs/dashboard_latest.html`
- `outputs/windows_runtime_report.json`
- `outputs/relatorio_execucao_YYYYMMDD_HHMMSS.json`
- `outputs/relatorio_execucao_YYYYMMDD_HHMMSS.pdf`

## 9) Agendamento no Task Scheduler (opcional)

Comando sugerido no agendador:

```bat
cmd /c "cd /d C:\caminho\do\projeto && scripts\run_rpa_windows.bat"
```

## 10) Solucao rapida de problemas

- `Playwright nao encontrado`: rode `scripts\setup_windows.bat` novamente.
- `No module named pip` durante setup: o `setup_windows.bat` agora tenta reparar/recriar `.venv` automaticamente.
  Se ainda falhar, apague `.venv` manualmente e rode `scripts\setup_windows.bat`.
- `To Do sem dados`: confirmar `MICROSOFT_TODO_*` e validar se entrou em `DESKTOP_APP`, `GRAPH` ou `WEB_AUTOMATION`.
- `Portais sem consulta`: conferir credenciais no `.env` e se Edge/Playwright estao OK.
- `Sem envio de e-mail`: revisar bloco SMTP e `EXECUTION_REPORT_EMAIL_TO`.
- `Sem envio WhatsApp`: revisar `WHATSAPP_PROVIDER_URL` e `WHATSAPP_PROVIDER_TOKEN`.
