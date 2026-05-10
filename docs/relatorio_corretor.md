# RPA PBSeg — O que o Robô Faz por Você

**Corretora:** PBSeg Seguros  
**Operadora:** Danielly Rodrigues  
**Versão:** Produção (Maio/2026)

---

## Resumo Executivo

O RPA PBSeg é um robô que executa automaticamente todas as tarefas operacionais da corretora — desde a leitura de planilhas até o envio de mensagens para clientes. Ele trabalha todos os dias, sem erro humano, sem esquecimento, sem atraso.

---

## O que ele faz diariamente

### 📋 Gestão da Carteira (442 apólices)
- Lê a planilha SEGUROS PBSEG automaticamente
- Identifica apólices com comissão pendente
- Detecta sinistros e endossos em aberto
- Cruza dados com os portais das seguradoras
- Registra tudo no Segfy (CRM)

### 🔄 Renovações Automáticas
- Identifica apólices vencendo nos próximos dias
- Envia mensagem via WhatsApp **exatamente 10 dias antes** da vigência
- Solicita dados ao cliente para atualização da cotação
- Registra a fase/status da renovação no Segfy
- Nunca envia mensagem duplicada

### 💰 Cobranças e Boletos
- Identifica parcelas com mais de 5 dias de atraso
- Lê o conteúdo completo do compromisso na agenda
- Envia lembrete via WhatsApp com dados do débito
- Extrai valor, parcela, seguradora e veículo automaticamente

### 🌐 Acesso aos 9 Portais de Seguradoras
O robô entra em cada portal, extrai dados reais e alimenta o sistema:

| Portal | O que extrai |
|--------|-------------|
| Yelum | Prêmio, comissão, sinistros, renovações |
| Porto Seguro | Prêmio, comissão, sinistros, renovações |
| Mapfre | Prêmio, comissão, sinistros, renovações |
| Bradesco | Prêmio, comissão, sinistros, renovações |
| Allianz | Prêmio, comissão, sinistros, renovações |
| Suhai | Prêmio, comissão, sinistros, renovações |
| Tokio Marine | Prêmio, comissão, sinistros, renovações |
| HDI | Prêmio, comissão, sinistros, renovações |
| Azul | Prêmio, comissão, sinistros, renovações |

### 📧 E-mails (Gmail)
- Lê e-mails não lidos automaticamente
- Identifica e-mails de seguradoras
- Extrai recebimentos do Nubank (valor, data, seguradora)
- Salva anexos (PDF/XLSX) para importação no Segfy
- Lança recebimentos na planilha de fluxo de caixa

### 📅 Google Agenda
- Lê todos os compromissos do dia
- Classifica automaticamente por tipo (renovação, cobrança, sinistro, etc.)
- Extrai nome do cliente, telefone, dados da apólice
- Executa a ação correspondente (WhatsApp, Segfy, e-mail)

### 🔄 Segfy (CRM)
O robô sincroniza **tudo** com o Segfy:
- Apólices da carteira
- Acompanhamentos e renovações
- Sinistros e endossos
- Comissões e pagamentos
- Lançamentos financeiros
- Importação de documentos

### 💬 WhatsApp
Envia mensagens automáticas para clientes:
- Renovação (10 dias antes da vigência)
- Boleto/parcela em atraso (>5 dias)
- Cobrança de parcela (agenda vermelha)
- Liberação bancária (2 dias antes)

### 📊 Dashboards e Relatórios
- **Dashboard Inteligente** — gráficos interativos, predições, exportação XLSX/PDF
- **Relatório de Execução** — JSON + PDF enviado por e-mail ao final de cada ciclo
- **Banco de Dados** — histórico completo para análise e BI

---

## Indicadores em Tempo Real

| Indicador | Valor Atual |
|-----------|-------------|
| Apólices na carteira | 442 |
| Seguradoras ativas | 17 |
| Comissões pendentes | 126 |
| Sinistros abertos | 5 |
| Endossos abertos | 46 |
| Acompanhamentos | 175 |

---

## O Agente Inteligente (Robô com Chat)

O robô tem uma janela flutuante onde você pode:

- **Perguntar** — "buscar Ana Silva", "relatório Porto", "comissões pendentes"
- **Executar** — "executar" roda o ciclo completo
- **Ver alertas** — "alertas" mostra pendências críticas
- **Ver vencimentos** — "vencendo" mostra apólices próximas do vencimento
- **Abrir ferramentas** — "dashboard", "segfy", "agenda"

Ele mostra alertas proativos ao abrir (apólices vencendo, sinistros, comissões).

---

## O que você ganha

| Antes (manual) | Agora (robô) |
|----------------|--------------|
| 4-6 horas/dia em tarefas repetitivas | Execução automática em minutos |
| Esquecimento de renovações | Disparo exato em D-10, sem falha |
| Dados desatualizados no Segfy | Sincronização diária completa |
| Planilhas isoladas | Banco de dados centralizado |
| Sem visão consolidada | Dashboard com gráficos e predições |
| Cobranças atrasadas | Lembrete automático via WhatsApp |
| Verificação manual de portais | Extração automática de 9 portais |

---

## Como Usar

1. **Abrir o robô:** duplo-clique em `scripts/abrir_agente.bat`
2. **Executar:** digite "executar" no chat
3. **Ver resultados:** digite "dashboard" ou "status"

O robô cuida do resto.

---

*Desenvolvido para PBSeg Seguros — Automação inteligente de corretora.*
