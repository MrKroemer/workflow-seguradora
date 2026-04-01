# Especificacao Tecnica de Implementacao

## 1. Objetivo

Implementar um RPA operacional para corretora de seguros com execucao diaria automatizada, consolidando agenda, tarefas, e-mails, Segfy, portais de seguradoras, planilhas operacionais, alertas e dashboard.

## 2. Arquitetura

A solucao foi separada em camadas:

- `domain`: entidades e regras de negocio.
- `integrations`: contratos para APIs e portais externos.
- `processing`: orquestracao, conciliacao, dashboard e alertas.
- `templates`: modelos padrao de mensagens.
- `config`: parametros de operacao (URLs, prazos, dominio de seguradoras).

## 3. Fluxo Diario

1. Coletar compromissos no Google Agenda.
2. Coletar tarefas abertas no Microsoft To Do.
3. Ler e-mails no Gmail.
4. Processar:
   - e-mails de seguradoras (triagem),
   - extrato Nubank (entrada em `RENDIMENTO`),
   - relatorio de renovacao (dia 20).
5. Ler carteira e acompanhamento nas planilhas.
6. Ler dados do Segfy e comparar com dados dos portais das seguradoras.
7. Aplicar regras e gerar alertas.
8. Disparar notificacoes (WhatsApp/e-mail) conforme gatilhos.
9. Gerar snapshot de dashboard diario.

## 4. Regras Implementadas

### 4.1 Renovacao

- Renovacao interna: alerta em `D-30`.
- Novos: alerta em `D-15`.
- Reforcos: `D-7` e `D-1`.
- Se a data de alerta cair em fim de semana/feriado, antecipar para o dia util anterior.
- Encerrar alertas ao iniciar renovacao (`renewal_started = true`).

### 4.2 Comissoes

- `STATUS PGTO` em branco gera alerta de comissao pendente.

### 4.3 Sinistro e Endosso

- Registros com `SINISTRO` ou `ENDOSSO` em aberto geram alerta.

### 4.4 Divergencias de Acompanhamento

- Segurado presente em `ACOMPANHAMENTO_2026.xlsx` e ausente em `SEGUROS_PBSEG.xlsx` gera divergencia.
- `FASE` ou `STATUS` em branco gera pendencia.
- Acompanhamento em status conclusivo sem renovacao iniciada na carteira gera divergencia.

### 4.5 Agenda e To Do

- Compromisso/tarefa vencido(a) e sem resolucao gera alerta de pendencia operacional.

### 4.6 Segfy vs Portal

- Divergencia entre premio total e comissao informados no Segfy e no portal gera inconsistencia.

## 5. Dashboard Diario

Indicadores consolidados:

- total de apolices ativas por seguradora;
- comissoes pagas vs pendentes;
- renovacoes em aberto (por tipo);
- sinistros e endossos em aberto;
- fluxo de caixa (entradas vs saidas);
- total de alertas criticos do dia.

## 6. Roadmap de Evolucao

1. Trocar adapters `stub` por integracoes reais (Google, Microsoft Graph, Gmail API, Segfy, Playwright para portais).
2. Conectar leitura/escrita real das planilhas `.xlsx`.
3. Persistir auditoria de execucoes (banco + logs estruturados).
4. Publicar dashboard web (ex.: Streamlit/FastAPI + frontend).
5. Agendar execucao (cron, scheduler cloud ou fila).

## 7. Integracao de Arquivos Locais (Implementado)

- `SEGUROS PBSEG.xlsx`: leitura de carteira e campos operacionais (vigencia, segurado, seguradora, status pgto, sinistro, endosso, premio e comissao).
- `ACOMPANHAMENTO 2026.xlsx`: leitura mensal das trilhas de renovacoes internas e novos, com parser adaptavel a variacoes de layout entre abas.
- `FLUXO DE CAIXA.xlsx`: leitura de despesas em `Gastos Mensais` e escrita de entradas em `RENDIMENTO` nas colunas `DATA`, `VALOR`, `SEGURADORA`, `ESPECIFICACAO`.
- `SENHAS.pdf`: OCR opcional para identificar servicos de acesso e preparar integracao futura de credenciais (sem exibir senhas em saida padrao).

## 8. Ambiente Windows

- A execucao em Windows e suportada via `py -3 -m rpa_corretora.main`.
- Existe script auxiliar em `scripts/run_rpa_windows.bat`.
- Existe script de preparacao em `scripts/setup_windows.bat` para instalar dependencias e Playwright.
- Cargas de caminho de arquivo podem ser sobrescritas por variaveis de ambiente:
  - `SEGUROS_PBSEG_XLSX`
  - `ACOMPANHAMENTO_2026_XLSX`
  - `FLUXO_CAIXA_XLSX`
  - `SENHAS_PDF`
- Alternativamente, o parametro `--files-dir` define esses caminhos automaticamente.
- Credenciais do Microsoft To Do sao lidas de:
  - `MICROSOFT_TODO_CLIENT_ID`
  - `MICROSOFT_TODO_REFRESH_TOKEN`
  - `MICROSOFT_TODO_TENANT_ID` (opcional)
  - `MICROSOFT_TODO_USER`
  - `MICROSOFT_TODO_PASSWORD`
- Quando `MICROSOFT_TODO_CLIENT_ID` nao estiver disponivel, o sistema pode usar fallback
  `WEB_AUTOMATION` no Windows (Playwright), preservando `STUB` como contingencia final.
- Pilotos de portais implementados via automacao web (Playwright):
  - Wave 1: Yelum, Porto Seguro e Mapfre.
  - Wave 2: Bradesco, Allianz e Suhai.
  - Wave 3 (inicio): Tokio Marine, HDI e Azul.
- A cadeia de busca de dados por apolice e nao regressiva e usa fallback para `stub`
  quando nao houver retorno nos portais web.

## 9. Adendo de Escopo Final

- O escopo final consolidado foi registrado em:
  - `docs/adendo_escopo_final_v1.md`
- Este adendo e nao regressivo e nao altera o contrato de execucao atual.
- A regra pendente de antecedencia de renovacao esta fechada como:
  - `D-30` para renovacao interna
  - `D-15` para novos
