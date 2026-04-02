# Execucao sem lacunas (Windows)

Este documento fecha o ciclo completo do Colaborador Virtual com o minimo de intervencao manual.

## Comando unico

Na raiz do projeto:

```bat
colaborador_virtual_rpa\scripts\concluir_tudo_windows.bat
```

## O que o script faz

1. Garante que `colaborador_virtual_rpa/.env` exista
2. Faz setup do ambiente com `venv`
3. Executa auditoria de runtime Windows
4. Executa `dry-run` para validar fluxo
5. Executa ciclo real

> O `run_colaborador_windows.bat` já roda com `--strict-production`.
> Se alguma integração estiver em fallback, a execução é bloqueada com lista de pendências.

## Resultado esperado

Ao final, o ciclo gera:

- `outputs/dashboard_latest.html`
- `outputs/relatorio_execucao_YYYYMMDD_HHMMSS.json`
- `outputs/relatorio_execucao_YYYYMMDD_HHMMSS.pdf`

## Observacoes

- Se `colaborador_virtual_rpa/.env` nao existir e houver `.env` na raiz, ele e sincronizado automaticamente.
- Se falhar em alguma etapa, o script encerra com codigo de erro e informa o ponto da falha.
