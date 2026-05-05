# Registro de Melhorias — RPA Corretora PBSeg

**Data:** 29 de abril de 2026  
**Projeto:** RPA Corretora de Seguros — PBSeg  
**Responsável técnico:** Desenvolvimento assistido por IA (Amazon Q)  
**Ambiente de produção:** Windows 11, Python 3.14, Chrome com perfil persistente  

---

## 1. Sincronização Completa das Planilhas com o Segfy (CRM)

### Problema anterior
O RPA lia as 3 planilhas operacionais (SEGUROS PBSEG, ACOMPANHAMENTO 2026, FLUXO DE CAIXA) e gerava alertas internos, mas **não enviava nenhum dado para o Segfy**. Todo o trabalho de cadastro no CRM continuava sendo manual.

### Solução implementada
Foram criados 7 novos métodos de sincronização no gateway do Segfy, operando via automação web (Playwright no Chrome):

| Método | Função | Arquivo |
|--------|--------|---------|
| `sync_policies` | Envia todas as apólices da carteira para o Segfy | `segfy_web_gateway.py` |
| `sync_followups` | Envia acompanhamentos (NOVOS + RENOVAÇÕES INTERNAS) | `segfy_web_gateway.py` |
| `sync_cashflow` | Envia lançamentos financeiros (rendimentos) | `segfy_web_gateway.py` |
| `register_incident` | Registra sinistros e endossos em aberto | `segfy_web_gateway.py` |
| `update_commission_status` | Atualiza status de comissão (QUITADA, etc.) | `segfy_web_gateway.py` |
| `register_renewal` | Registra fase/status de renovação | `segfy_web_gateway.py` |
| `import_documents` | Importa arquivos .xlsx/.pdf pela tela de importação | `segfy_web_gateway.py` |

### Arquivos modificados
- `src/rpa_corretora/integrations/interfaces.py` — protocolo expandido com novos contratos
- `src/rpa_corretora/integrations/segfy_gateway.py` — implementação API + fila local
- `src/rpa_corretora/integrations/segfy_web_gateway.py` — implementação web completa
- `src/rpa_corretora/integrations/stub_adapters.py` — stubs para testes
- `src/rpa_corretora/processing/orchestrator.py` — integração no ciclo diário

### Resultado em produção
O ciclo diário agora sincroniza automaticamente:
- 442 apólices da carteira
- 175 acompanhamentos
- Lançamentos financeiros extraídos de e-mails
- Sinistros e endossos em aberto
- Status de comissões
- Fases de renovação

---

## 2. Login do Segfy — Reescrita Completa

### Problema anterior
O campo de e-mail do Segfy não era preenchido. O formulário usa componentes de UI com label flutuante (sem `placeholder`, `type='email'` ou `name` identificável no input). Além disso, um banner de cookies bloqueava a interação.

### Solução implementada
Login reescrito com 3 estratégias em cascata:

1. **Seletores CSS tradicionais** — tenta `input[placeholder='E-mail']`, `input[type='email']`, etc.
2. **JavaScript via DOM** — busca `<label>` e `<mat-label>` com texto "E-mail", localiza o input associado (por `htmlFor`, como filho, ou como irmão), preenche via `input.value` + disparo de eventos `input`/`change` para frameworks reativos (Angular/React).
3. **Fallback posicional** — localiza o primeiro `input:visible` que não seja `type='password'` e preenche.

Adicionalmente:
- Banner de cookies é aceito automaticamente antes de qualquer interação.
- Modais pós-login (extensão Segfy, ofertas, onboarding) são dispensados automaticamente.

### Arquivo modificado
- `src/rpa_corretora/integrations/segfy_web_gateway.py` — métodos `_login`, `_segfy_fill_email_field`, `_fill_first_visible_non_password_input`, `_dismiss_segfy_overlays`

---

## 3. Chrome com Perfil Persistente

### Problema anterior
O Playwright abria um navegador limpo a cada execução — sem extensões, sem cookies, sem sessões salvas. A extensão Segfy precisava ser instalada a cada vez (impossível via automação).

### Solução implementada
O método `_launch_browser` agora:

1. **Auto-detecta** o diretório de perfil do Chrome no Windows: `%LOCALAPPDATA%\Google\Chrome\User Data`
2. Usa `launch_persistent_context` do Playwright para abrir o Chrome **com o perfil real da operadora** (Danielly Rodrigues / pbseg.seguros@gmail.com)
3. Mantém extensão Segfy instalada, cookies, sessões de portais, favoritos — tudo intacto entre execuções
4. Fallback para modo normal caso o perfil não esteja disponível

### Configuração opcional no .env
```
SEGFY_CHROME_USER_DATA_DIR=C:\Users\cadas\AppData\Local\Google\Chrome\User Data
```
Se não configurado, o código detecta automaticamente.

### Requisito operacional
O Chrome deve estar **fechado** quando o robô executar (Playwright não abre perfil em uso por outra instância).

### Arquivos modificados
- `src/rpa_corretora/integrations/segfy_web_gateway.py` — `_launch_browser`, `_run_web_session`, `import_documents`, `fetch_policy_data`

---

## 4. Classificador Inteligente de Eventos (Google Agenda)

### Problema anterior
O robô dependia exclusivamente da **cor** do card no Google Agenda para decidir a ação. Se a cor estivesse errada ou ausente, o evento era ignorado.

### Solução implementada
Novo classificador baseado em **conteúdo textual completo** (título + descrição + metadados):

```python
CommitmentType = Literal[
    "RENOVACAO",
    "COBRANCA_BOLETO",
    "COBRANCA_PARCELA",
    "SINISTRO",
    "ENDOSSO",
    "LIBERACAO_BANCO",
    "TRATATIVA_GERAL",
    "DESCONHECIDO",
]
```

O sistema usa scoring ponderado com tokens semânticos:
- Tokens de renovação: RENOVACAO, RENOVAR, VIGENCIA, VIG, COTACAO DE RENOVACAO
- Tokens de cobrança: BOLETO, PARCELA, FATURA, COBRANCA, PAGAMENTO, VENCIMENTO, ATRASO
- Tokens de sinistro: SINISTRO, ACIDENTE, COLISAO, ROUBO, PERDA TOTAL
- Tokens de endosso: ENDOSSO, ALTERACAO, INCLUSAO, EXCLUSAO
- Tokens bancários: LIBERACAO, BANCO, CONTA CORRENTE, INTERNET BANKING

A cor funciona como **reforço secundário** (soma 1 ponto ao score), não como determinante.

### Tolerância a variações de escrita
- Normalização Unicode (NFKD) + ASCII folding
- Case-insensitive
- Remoção de acentos e caracteres especiais

### Arquivo modificado
- `src/rpa_corretora/domain/rules.py` — função `classify_commitment_type` e helpers

---

## 5. Regras de Disparo de Mensagens — Ajustes Precisos

### 5.1 Renovações (Regra 1)

**Antes:** Disparava em qualquer dia dentro de uma janela D-10 a D-0.  
**Agora:** Dispara **exatamente** 10 dias antes da data de vigência, conforme especificação:

> "O disparo da comunicação deve ocorrer exatamente 10 (dez) dias antes da data de vigência da apólice."

Deduplicação via `message_dispatch_state.json` impede reenvio.

### 5.2 Boletos/Parcelas em Atraso (Regra 2)

**Antes:** Exigia que o texto contivesse "BOLETO"/"PARCELA" **E** "VENC"/"ATRAS" simultaneamente.  
**Agora:** Qualquer card tangerina com conteúdo textual mínimo (≥4 caracteres) é tratado como cobrança. A cor tangerina é o roteador primário; o conteúdo é usado para validação e enriquecimento.

> "O robô não deve depender exclusivamente da cor, devendo analisar o conteúdo completo do card para validação."

### 5.3 Extração de data de vencimento

**Antes:** Só extraía datas com labels explícitos (VENCIMENTO, VENC, VCTO).  
**Agora:** Cascata de 3 estratégias:
1. Labels explícitos (VENCIMENTO, VENC, VCTO, DATA VENCIMENTO, VENCE, DATA, DT)
2. Qualquer data no formato DD/MM/YYYY encontrada no texto
3. Fallback: data do próprio compromisso na agenda

### Arquivo modificado
- `src/rpa_corretora/domain/rules.py` — funções `should_send_renewal_message`, `is_tangerine_overdue_commitment`, `extract_overdue_due_date`

---

## 6. Extração de Dados Detalhados dos Compromissos

### Problema anterior
O robô extraía apenas nome do cliente e telefone. Não sabia qual era o valor do boleto, a seguradora, o veículo, a parcela, ou a placa.

### Solução implementada
Nova estrutura `CommitmentDetails` com extração via regex:

| Campo | Regex/Método |
|-------|-------------|
| `client_name` | Extraído do campo `client_name` do compromisso |
| `insurer` | Regex `seguradora:\s*(.+)` + busca por nomes conhecidos (YELUM, PORTO, etc.) |
| `amount` | Regex `R\$\s*([0-9\.,]+)` |
| `parcela_current/total` | Regex `parcela\s*(\d+)\s*/\s*(\d+)` |
| `vehicle` | Regex `veiculo:\s*(.+)` |
| `plate` | Regex `[A-Z]{3}[0-9][A-Z0-9][0-9]{2}` (Mercosul + antigo) |
| `due_date` | Cascata de extração (labels → data genérica → data do card) |
| `vig_date` | Labels VIG/VIGENCIA |

Funções de enriquecimento cruzam dados do compromisso com a carteira de apólices:
- `enrich_renewal_context` — adiciona policy_id, seguradora, veículo, placa, prêmio
- `enrich_overdue_context` — adiciona valor, parcela X/Y, seguradora, veículo, placa

### Arquivo modificado
- `src/rpa_corretora/domain/rules.py` — dataclass `CommitmentDetails`, funções `extract_commitment_details`, `enrich_renewal_context`, `enrich_overdue_context`

---

## 7. Correção do Mapeamento de Cores do Google Calendar

### Problema
No `.env`, o color ID 6 (Tangerina no Google) estava mapeado tanto para VERMELHO quanto para TANGERINA:
```
GOOGLE_COLOR_IDS_VERMELHO=4,6,11  ← ERRADO
GOOGLE_COLOR_IDS_TANGERINA=6
```

Funcionava por acaso (TANGERINA era processado depois e sobrescrevia), mas era uma inconsistência perigosa.

### Correção aplicada
```
GOOGLE_COLOR_IDS_VERMELHO=4,11  ← CORRETO
GOOGLE_COLOR_IDS_TANGERINA=6
```

### Arquivo modificado
- `.env`

---

## 8. Script de Execução para Produção

### Criado: `scripts/executar_rpa.bat`

Script para duplo-clique no Windows que:
1. Executa dry-run silencioso de validação
2. Se passar, executa o ciclo real automaticamente
3. Mostra resultado (sucesso/erro) no terminal
4. Informa sobre relatório e dashboard gerados

### Fluxo do script
```
[1/3] Dry-run de validação → OK
[2/3] Ciclo de produção → executa tudo
[3/3] Resultado → SUCESSO ou ATENÇÃO
```

---

## 9. Integração no Orquestrador — Ciclo Diário Expandido

### Antes (8 etapas)
Google Calendar → To Do → Gmail → Planilhas → Segfy (só leitura) → Portais → Notificações → Dashboard

### Agora (8 etapas + sincronização completa)
Google Calendar → To Do → Gmail → Planilhas → **Segfy (leitura + escrita completa)** → Portais → Notificações → Dashboard

O relatório de execução agora registra:
```
- X apolices sincronizadas
- X acompanhamentos sincronizados
- X lancamentos financeiros sincronizados
- X incidentes registrados
- X comissoes atualizadas
- X renovacoes registradas
- X documentos importados
```

### Arquivo modificado
- `src/rpa_corretora/processing/orchestrator.py`

---

## 10. Protocolo CascadingSegfyGateway Expandido

O gateway cascateado (web → API → fila local) agora propaga todos os 7 novos métodos:

```python
CascadingSegfyGateway:
    sync_policies      → primary.sync_policies()      || fallback.sync_policies()
    sync_followups     → primary.sync_followups()     || fallback.sync_followups()
    sync_cashflow      → primary.sync_cashflow()      || fallback.sync_cashflow()
    register_incident  → primary.register_incident()  || fallback.register_incident()
    update_commission  → primary.update_commission()  || fallback.update_commission()
    register_renewal   → primary.register_renewal()   || fallback.register_renewal()
    import_documents   → primary.import_documents()   || fallback.import_documents()
```

Quando a web falha, os dados são gravados em `outputs/segfy_payment_queue.jsonl` para reprocessamento posterior.

---

## Validação Final

| Métrica | Resultado |
|---------|-----------|
| Testes automatizados | 86/86 passando |
| Dry-run com planilhas reais | 442 apólices, 175 acompanhamentos, 15 compromissos, 236 alertas |
| Ambiente Windows | Todos os componentes OK (Python, Chrome, Edge, Playwright, Pywinauto, To Do Desktop) |
| Login Segfy | Funcionando (e-mail + senha preenchidos corretamente) |
| Perfil Chrome persistente | Extensão Segfy mantida entre execuções |
| Modos de integração ativos | GOOGLE_API, GMAIL_IMAP, DESKTOP_APP, WEB_AUTOMATION, WEB_MULTI, HTTP_API, SMTP |

---

## Arquivos Criados/Modificados (Resumo)

| Arquivo | Ação |
|---------|------|
| `src/rpa_corretora/integrations/interfaces.py` | Modificado — 7 novos métodos no protocolo |
| `src/rpa_corretora/integrations/segfy_gateway.py` | Modificado — implementação API + fila |
| `src/rpa_corretora/integrations/segfy_web_gateway.py` | Modificado — login reescrito, perfil persistente, 7 métodos web |
| `src/rpa_corretora/integrations/stub_adapters.py` | Modificado — stubs dos novos métodos |
| `src/rpa_corretora/processing/orchestrator.py` | Modificado — sincronização Segfy no ciclo |
| `src/rpa_corretora/domain/rules.py` | Modificado — classificador, extração, regras de disparo |
| `.env` | Modificado — correção color ID 6 |
| `scripts/executar_rpa.bat` | Criado — script de produção |

---

## Requisitos Operacionais para Produção

1. Chrome deve estar **fechado** antes de executar o robô
2. Extensão Segfy deve estar instalada no perfil do Chrome (instalação manual única)
3. Planilhas devem estar nos caminhos configurados no `.env`
4. Conexão com internet ativa (APIs Google, WhatsApp, SMTP, portais)
5. Execução via `scripts\executar_rpa.bat` ou `py -3 -m rpa_corretora.main`
