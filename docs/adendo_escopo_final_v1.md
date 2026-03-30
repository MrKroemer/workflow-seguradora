# Adendo de Escopo Final (Nao Regressivo)

Este documento registra o escopo final do projeto como adendo oficial, sem alterar o
comportamento padrao do RPA e sem quebrar fluxos existentes.

## 1. Regra Pendente Resolvida

Prazo de antecedencia para alerta de renovacao definido como:

- `D-30` para renovacao interna
- `D-15` para novos

Status no projeto: aplicado em `config/settings.json` e nas regras de renovacao.

## 2. Escopo Final Consolidado

### 2.1 Gestao de compromissos diarios (Google Agenda)

- Leitura diaria de compromissos.
- Interpretacao por codigo de cor:
  - Vermelho: cobranca de parcelas, com notificacao via WhatsApp.
  - Azul: baixa de parcelas, com registro no Segfy.
  - Cinza: acompanhamento de sinistros, com consulta em portal.
  - Verde: tratativas diversas, com registro e monitoramento.

### 2.2 Integracao com Microsoft To Do

- Leitura de tarefas ativas para complementar pendencias operacionais do dia.

### 2.3 Processamento de e-mails (Gmail)

- Filtragem de e-mails de seguradoras cadastradas.
- Deteccao de extrato Nubank e alimentacao da aba `RENDIMENTO` em `FLUXO DE CAIXA.xlsx`.
- Deteccao de relatorio de renovacao no dia 20.
- Envio de e-mails para segurados quando o processo exigir dados da planilha.

### 2.4 Acesso e operacao no Segfy

- Importacao de documentos.
- Leitura e analise de dados com regras de negocio.
- Cruzamento com dados de portais para detectar inconsistencias.

### 2.5 Acesso aos portais das seguradoras

- Acesso por credenciais.
- Operacoes por necessidade de processo:
  - cotacao
  - consulta de apolice
  - download de documentos
  - verificacao de comissoes
- Portais previstos:
  - Yelum
  - Porto Seguro
  - Mapfre
  - Bradesco
  - Allianz
  - Suhai
  - Tokio Marine
  - HDI
  - Azul
  - Justos

### 2.6 Processamento de planilhas

- `SEGUROS_PBSEG.xlsx`
  - comissao pendente (`STATUS PGTO` em branco)
  - vigencia proxima sem renovacao iniciada
  - sinistro/endosso em aberto
- `ACOMPANHAMENTO_2026.xlsx`
  - FASE/STATUS em aberto
  - divergencias entre acompanhamento e carteira
- `FLUXO_DE_CAIXA.xlsx`
  - entradas em `RENDIMENTO`
  - saidas em `Gastos Mensais`
  - validacao consolidada em `Resumo De Gastos`

### 2.7 Geracao de alertas

- Comissao pendente.
- Vigencia proxima sem renovacao.
- Divergencia entre acompanhamento e carteira.
- Inconsistencia Segfy x portal.
- Pendencia de agenda ou To Do.

### 2.8 Notificacoes via WhatsApp

- Mensagens automatizadas por gatilho de processo.
- Modelo de proposta de seguro auto previsto no escopo.

### 2.9 Dashboard

- Apolices ativas por seguradora.
- Comissoes pagas vs pendentes.
- Renovacoes concluidas vs em aberto.
- Sinistros/endossos em aberto.
- Fluxo de caixa (entradas vs saidas).
- Alertas criticos do dia.

## 3. Matriz de Aderencia (Estado Atual)

- `Implementado`:
  - regras de renovacao, comissao, sinistro, endosso e divergencias.
  - camada de precisao em divergencias de acompanhamento:
    - matching exato por nome normalizado;
    - matching fuzzy com limiar e margem para reduzir falso positivo.
  - escalonamento de criticidade para renovacao proxima (`D-10` e abaixo como `CRITICA`).
  - processamento real das planilhas operacionais.
  - dashboard consolidado e dashboard HTML.
  - Microsoft To Do em Graph ou fallback web no Windows.
  - piloto de portal Porto com fallback controlado para stub.
- `Parcial / Em evolucao`:
  - Google Agenda real (hoje em stub).
  - Gmail real (hoje em stub para leitura operacional).
  - Segfy real (hoje em stub para cruzamento).
  - portais restantes alem da Porto (em roadmap por fases).

## 4. Garantia de Nao Regressao

Este adendo e documental e de governanca de escopo.

- Nao muda contrato publico de execucao.
- Nao remove comportamento existente.
- Mantem fallback para `stub` quando integracao real estiver indisponivel.
- Preserva compatibilidade com ambiente Windows.
