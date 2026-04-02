# Colaborador Virtual RPA (Projeto Simplificado)

Projeto paralelo focado em operação simples para a corretora, com rotina fixa diária.

## Objetivo

Atuar como colaborador virtual:

- Ler Google Agenda (cores), Microsoft To Do (app desktop), Gmail e planilhas.
- Executar tarefas repetitivas (cobrança WhatsApp, baixa/registro no Segfy, consultas em portais).
- Entregar evidências do ciclo (dashboard + relatório JSON/PDF).
- Rodar em modo estrito de produção (sem fallback).

## Fluxo diário fixo

1. Google Agenda (interpretação por cor)
2. Microsoft To Do (app desktop no Windows)
3. Gmail (filtros de seguradoras + Nubank + renovação)
4. Planilhas operacionais (leitura/escrita/cruzamentos)
5. Segfy (web/importação)
6. Portais mapeados
7. Notificações (WhatsApp + e-mail)
8. Dashboard + relatório final

## Setup (Windows)

Na raiz do repositório:

```bat
colaborador_virtual_rpa\scripts\setup_windows.bat
```

## Configuração

1. Copie o arquivo de exemplo:

```bat
copy colaborador_virtual_rpa\.env.example colaborador_virtual_rpa\.env
```

2. Preencha os campos necessários no `colaborador_virtual_rpa/.env`.
3. Mantenha `RPA_STRICT_PRODUCTION=1` para bloquear qualquer execução em modo fallback.

## Execução

Comando único diário:

```bat
colaborador_virtual_rpa\scripts\run_colaborador_windows.bat
```

## Execução sem lacunas (setup + auditoria + dry-run + real)

Comando único de conclusão:

```bat
colaborador_virtual_rpa\scripts\concluir_tudo_windows.bat
```

## Validação opcional

```bat
colaborador_virtual_rpa\scripts\run_colaborador_windows.bat --windows-audit-only
colaborador_virtual_rpa\scripts\run_colaborador_windows.bat --dry-run
```

## Saídas esperadas

- `outputs/dashboard_latest.html`
- `outputs/relatorio_execucao_YYYYMMDD_HHMMSS.json`
- `outputs/relatorio_execucao_YYYYMMDD_HHMMSS.pdf`
- `outputs/windows_runtime_report.json` (quando auditoria)

## Regras do modo estrito

- Não aceita `NOOP`, `STUB`, `QUEUE_ONLY`, `OUTBOX_FILE` nem combinações com fallback.
- Bloqueia execução se qualquer integração não estiver em modo real.
- Exige Microsoft To Do via app desktop (`DESKTOP_APP`).
- Exige Segfy em `API_ONLY` para baixa real sem fila local.
