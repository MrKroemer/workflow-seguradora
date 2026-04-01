# Matriz de Aderencia - Regras de Negocio do RPA

Data de referencia: 01/04/2026

## Legenda

- Aderente: implementado e operacional no fluxo atual.
- Parcial: existe implementacao, mas com restricoes relevantes.
- Pendente: ainda nao implementado no fluxo atual.

## Matriz Consolidada

| Pilar | Regra de Negocio | Status | Situacao Atual |
|---|---|---|---|
| 1. Google Calendar | Leitura diaria de compromissos | Aderente | Leitura via API Google ativa quando credenciais estao configuradas. |
| 1. Google Calendar | Interpretacao por cores (Vermelho/Azul/Cinza/Verde) | Aderente | Cores sao mapeadas para acoes operacionais no orquestrador. |
| 1. Google Calendar | Criacao automatica de eventos | Parcial | Fluxo atual registra como nao executado; rotina de escrita ainda nao implementada. |
| 2. Microsoft To Do | Leitura de tarefas abertas | Aderente | Disponivel via Graph e fallback web (Windows + Playwright). |
| 2. Microsoft To Do | Incorporar pendencias ao processamento diario | Aderente | Tarefas alimentam regras de alerta no ciclo. |
| 2. Microsoft To Do | Criacao/atualizacao automatica de tarefas | Parcial | Fluxo atual e somente leitura. |
| 3. Gmail | Leitura de e-mails nao lidos | Aderente | Via IMAP quando credenciais estao presentes. |
| 3. Gmail | Classificacao de e-mails de seguradoras | Aderente | Classificacao por dominios configurados. |
| 3. Gmail | Extrato Nubank para RENDIMENTO | Aderente | Extracao e gravacao suportadas (fora de dry-run). |
| 3. Gmail | Relatorio de renovacao no dia 20 | Aderente | Deteccao implementada com alerta dedicado. |
| 3. Gmail | Envio de notificacao com segurado + modelo + placa | Aderente | Implementado no gatilho de agenda verde, com dados da carteira. |
| 3. Gmail | Respostas automáticas amplas de e-mail por processo | Parcial | Existe envio operacional, mas nao ha motor amplo de reply por cenarios complexos. |
| 4. Segfy | Consulta de dados de apolices | Aderente | Via API quando configurada, com fallback por exportacao XLSX. |
| 4. Segfy | Registro de baixa de parcela | Aderente | Agenda azul executa `register_payment`; se API falhar, envia para fila local. |
| 4. Segfy | Cruzamento Segfy x portais | Aderente | Regras de inconsistencia por premio/comissao estao ativas. |
| 4. Segfy | Importacao de documentos conforme fluxo operacional | Parcial | Nucleo de consulta/baixa existe; rotina dedicada de importacao documental ainda nao foi detalhada. |
| 5. Portais seguradoras | Login e consulta de apolice | Aderente | Cobertura web ativa em Windows com Playwright e credenciais por .env/PDF. |
| 5. Portais seguradoras | Consulta de status de sinistro | Aderente | Gatilho da agenda cinza chama consulta de sinistro nos gateways de portal. |
| 5. Portais seguradoras | Download documental e operacoes avancadas por portal | Parcial | Base de navegacao e pesquisa implementada; operacoes especificas completas dependem de mapeamento final por portal. |
| 5. Portais seguradoras | Cobertura Yelum | Aderente | Fluxo mapeado com menu/atalhos de consulta. |
| 5. Portais seguradoras | Cobertura Porto | Aderente | Fluxo mapeado em menus principais e barra global. |
| 5. Portais seguradoras | Cobertura Mapfre | Aderente | Fluxo mapeado para Carteira/Renovacoes/Sinistros. |
| 5. Portais seguradoras | Cobertura Suhai | Aderente | Fluxo mapeado para Apolice/Relatorios/Sinistros. |
| 5. Portais seguradoras | Cobertura HDI | Aderente | Fluxo mapeado com tratamento de overlays/modais. |
| 5. Portais seguradoras | Cobertura Azul | Aderente | Fluxo mapeado para dashboard, menus e consulta de sinistro. |
| 5. Portais seguradoras | Cobertura Tokio Marine | Parcial | Fluxo de consulta mapeado; consulta dedicada de sinistro ainda segue caminho generico. |
| 5. Portais seguradoras | Cobertura Bradesco | Parcial | Gateway funcional, ainda mais generico (sem mapeamento detalhado de menus/telas). |
| 5. Portais seguradoras | Cobertura Allianz | Parcial | Gateway funcional, ainda mais generico (sem mapeamento detalhado de menus/telas). |
| 5. Portais seguradoras | Cobertura Justos | Pendente | Em espera por etapa de confirmacao de e-mail no ambiente Windows. |
| 6. Planilhas | Leitura de carteira SEGUROS PBSEG | Aderente | Leitura de campos-chave, sinistro/endosso, comissao e vigencia. |
| 6. Planilhas | Leitura de acompanhamento ACOMPANHAMENTO 2026 | Aderente | Leitura de renovacoes internas e novos por mes. |
| 6. Planilhas | Cruzamento carteira x acompanhamento | Aderente | Divergencias detectadas com matching exato e fuzzy. |
| 6. Planilhas | Escrita em RENDIMENTO | Aderente | Append na aba RENDIMENTO implementado. |
| 6. Planilhas | Escrita em Gastos Mensais | Aderente | Append na aba Gastos Mensais implementado. |
| 6. Planilhas | Validacao Resumo De Gastos | Aderente | Validacao por categoria com alerta de divergencia. |
| 7. Alertas | Comissao pendente | Aderente | Regra ativa (`STATUS PGTO` em branco). |
| 7. Alertas | Vigencia proxima sem renovacao iniciada | Aderente | Regras D-30 interno, D-15 novos + lembretes D-7/D-1. |
| 7. Alertas | Divergencia acompanhamento x carteira | Aderente | Regras com severidade e contexto para tratamento operacional. |
| 7. Alertas | Inconsistencia Segfy x portal | Aderente | Alertas criticos quando diferencas superam tolerancia. |
| 7. Alertas | Pendencias agenda/To Do sem resolucao | Aderente | Alertas para agenda, To Do vencido/hoje e To Do sem prazo. |
| 8. WhatsApp | Envio automatizado por gatilho | Aderente | Vermelho envia cobranca via API HTTP ou outbox fallback. |
| 8. WhatsApp | Modelos adicionais (renovacao/sinistro etc.) | Parcial | Modelo de cobranca pronto; biblioteca de modelos completos ainda em expansao. |
| 9. Dashboard | Apolices ativas por seguradora | Aderente | KPI consolidado no snapshot e HTML. |
| 9. Dashboard | Comissoes pagas vs pendentes | Aderente | KPI consolidado no snapshot e HTML. |
| 9. Dashboard | Renovacoes concluidas vs abertas por mes | Aderente | Tabela de renovacoes mensais implementada. |
| 9. Dashboard | Sinistros e endossos em aberto | Aderente | KPI consolidado no snapshot e HTML. |
| 9. Dashboard | Fluxo de caixa entradas vs saidas por categoria | Aderente | Tabela por categoria com `cash_in`, `cash_out`, `net`. |
| 9. Dashboard | Alertas criticos do dia | Aderente | KPI e painel visual de criticidade implementados. |
| 10. Relatorio de execucao | JSON + PDF ao final de todo ciclo | Aderente | Geracao obrigatoria inclusive em falha critica. |
| 10. Relatorio de execucao | Cabecalho, resumo, etapas, itens nao executados, log de erros | Aderente | Estrutura completa implementada no coletor de execucao. |
| 10. Relatorio de execucao | Envio automatico por e-mail ao corretor | Parcial | Ativo quando `EXECUTION_REPORT_EMAIL_TO` e SMTP estao configurados e sem dry-run. |
| 11. Ambiente Windows | Diagnostico de prontidao do ambiente | Aderente | Auditoria de componentes e arquivos operacionais com JSON de saida. |
| 11. Ambiente Windows | Reconhecimento de apps/recursos necessarios | Aderente | Verifica Edge, Playwright, Chromium, PowerShell e Task Scheduler. |

## Pontos de Controle para Homologacao

1. Executar em Windows real sem `--dry-run` com todos os `.env` preenchidos.
2. Confirmar no relatorio final que as etapas nao estao em `IGNORADO`.
3. Concluir mapeamento final de Bradesco/Allianz/Tokio (sinistro dedicado) e ativacao Justos.
4. Validar envio real de WhatsApp API e SMTP em ambiente produtivo.
