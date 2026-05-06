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

## 2. Login do Segfy — Reescrita Completa com Detecção de Sessão

### Problema anterior
O campo de e-mail do Segfy não era preenchido. O formulário usa componentes de UI com label flutuante (sem `placeholder`, `type='email'` ou `name` identificável no input). Além disso, um banner de cookies bloqueava a interação.

### Solução implementada

#### Detecção de sessão ativa
Antes de tentar login, o robô verifica se já está autenticado (perfil persistente com sessão ativa). Indicadores:
- Presença de menu lateral (Home, Segurados, Financeiro, HFy)
- Ausência de campo de senha visível
- Palavras-chave do dashboard no corpo da página

Se detectar sessão ativa: `[Segfy] Sessao ativa detectada, login nao necessario.`

#### Login com 3 estratégias de preenchimento do e-mail

1. **Seletores CSS tradicionais** — tenta `input[placeholder='E-mail']`, `input[type='email']`, etc.
2. **JavaScript via DOM** — busca `<label>` e `<mat-label>` com texto "E-mail", localiza o input associado (por `htmlFor`, como filho, ou como irmão), preenche via `input.value` + disparo de eventos `input`/`change` para frameworks reativos (Angular/React).
3. **Fallback posicional** — localiza o primeiro `input:visible` que não seja `type='password'` e preenche.

#### Submissão do formulário
O botão "Entrar" é clicado via seletores. Se nenhum seletor encontrar o botão, o robô pressiona **Enter** no teclado como fallback (submete o formulário).

#### Tratamento pós-login
Modais pós-login (extensão Segfy, ofertas, onboarding) são dispensados automaticamente via `_dismiss_segfy_overlays`.

### Arquivo modificado
- `src/rpa_corretora/integrations/segfy_web_gateway.py` — métodos `_login`, `_is_already_logged_in`, `_segfy_fill_email_field`, `_fill_first_visible_non_password_input`, `_dismiss_segfy_overlays`

---

## 3. Chrome com Perfil Persistente e Conexão CDP

### Problema anterior
O Playwright abria um navegador limpo a cada execução — sem extensões, sem cookies, sem sessões salvas. A extensão Segfy precisava ser instalada a cada vez (impossível via automação). Além disso, abrir o Chrome com perfil persistente falhava quando o Chrome já estava em uso.

### Solução implementada
O método `_launch_browser` agora opera com 3 estratégias em cascata:

1. **Conexão CDP (Chrome DevTools Protocol)** — conecta ao Chrome que já está aberto e logado na máquina da operadora. Não abre instância nova. Usa a sessão ativa com extensão Segfy, cookies, perfil Google — tudo intacto.
2. **Perfil persistente** — se CDP não estiver disponível, abre Chrome com `User Data` real (auto-detectado no Windows).
3. **Modo normal** — último recurso, abre Chrome limpo.

### Configuração no atalho do Chrome (barra de tarefas)
O atalho do Chrome foi configurado com a flag de debug remoto:
```
"C:\Program Files\Google\Chrome\Application\chrome.exe" --profile-directory="Profile 1" --remote-debugging-port=9222
```

Isso permite que o Playwright conecte ao Chrome existente sem abrir nova instância.

### Configuração no .env
```
SEGFY_CHROME_CDP_URL=http://localhost:9222
```

### Resultado
- O robô conecta ao Chrome que a operadora já usa no dia a dia
- Extensão Segfy permanece instalada e ativa
- Sessões de portais e Google mantidas
- Não precisa fechar o Chrome para rodar o robô

### Arquivo modificado
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

## 12. Banco de Dados Operacional Centralizado (SQLite)

### Problema anterior
Os dados ficavam dispersos entre planilhas, Segfy, portais e relatórios JSON. Não havia cruzamento automático de informações nem histórico consolidado de execuções. Impossível gerar dashboards inteligentes sem reprocessar tudo.

### Solução implementada
Banco de dados SQLite local (`outputs/rpa_corretora.db`) alimentado automaticamente por **todas** as fontes de dados a cada ciclo de execução.

### Tabelas criadas

| Tabela | Conteúdo | Fonte |
|--------|----------|-------|
| `policies` | 443 apólices com prêmio, comissão, sinistro, endosso, veículo, placa | Planilha + Portais |
| `followups` | 172 acompanhamentos com fase/status por mês | Planilha |
| `cashflow` | Lançamentos financeiros (recebimentos) | Gmail (Nubank) + Planilha |
| `expenses` | Despesas categorizadas | Gmail + Planilha |
| `portal_data` | Dados brutos extraídos dos 9 portais (prêmio, comissão, sinistro, endosso, renovação) | Portais |
| `alerts` | Todos os alertas gerados por execução | Regras de negócio |
| `commitments` | Compromissos da agenda com classificação inteligente | Google Calendar |
| `emails` | E-mails processados (seguradoras identificadas) | Gmail IMAP |
| `run_history` | Histórico de execuções com métricas consolidadas | Orquestrador |

### Queries prontas para dashboards

```python
db = OperationalDatabase()
db.query_policies_by_insurer()       # Apólices por seguradora
db.query_commissions_summary()       # Comissões pagas vs pendentes
db.query_open_incidents()            # Sinistros/endossos abertos
db.query_cashflow_month(2026, 4)     # Fluxo de caixa abril/2026
db.query_alerts_by_severity(today)   # Alertas por severidade
db.query_renewals_by_month()         # Renovações concluídas vs abertas
db.query_portal_divergences()        # Divergências planilha × portal
db.query_run_history(limit=30)       # Últimas 30 execuções
```

### Características técnicas
- **SQLite WAL mode** — permite leitura concorrente enquanto o robô escreve
- **UPSERT** — apólices e followups são atualizados sem duplicar
- **Índices** — consultas otimizadas por seguradora, data, severidade
- **Arquivo único** — `outputs/rpa_corretora.db` (portável, abrível por Power BI, Metabase, DBeaver, Excel)
- **Não-bloqueante** — se o banco falhar, o fluxo principal continua normalmente

### Integração com ferramentas de BI
O banco pode ser conectado diretamente a:
- **Power BI** (via conector SQLite/ODBC)
- **Metabase** (open source, auto-hospedado)
- **Google Data Studio** (via exportação CSV)
- **Excel** (via ODBC ou Power Query)
- **Qualquer aplicação Python** (import sqlite3)

### Arquivo criado
- `src/rpa_corretora/core/__init__.py` — classe `OperationalDatabase` com schema, upserts e queries

### Arquivo modificado
- `src/rpa_corretora/processing/orchestrator.py` — persistência automática ao final de cada ciclo

---

## 13. Extração Completa de Dados dos Portais (Sinistros, Endossos, Renovações)

### Problema anterior
Os portais das seguradoras só extraíam prêmio e comissão. Sinistros, endossos e status de renovação eram ignorados — o robô não sabia o que estava acontecendo nas seguradoras além dos valores financeiros.

### Solução implementada
O modelo `PortalPolicyData` foi expandido com campos adicionais:

```python
@dataclass
class PortalPolicyData:
    policy_id: str
    insurer: str
    premio_total: Decimal
    comissao: Decimal
    sinistro_status: str      # "EM ANDAMENTO", "FINALIZADO", etc.
    endosso_status: str       # "ABERTO", "EMITIDO", etc.
    renewal_status: str       # "RENOVADO", "NAO RENOVADO", etc.
    parcelas_pendentes: int   # Quantidade de parcelas em aberto
    documento_url: str        # URL do documento no portal
```

O parser genérico (`parse_policy_data_from_text_generic`) agora extrai status de sinistro, endosso e renovação do texto da página usando busca por labels:

| Tipo | Labels de busca | Status detectados |
|------|----------------|-------------------|
| Sinistro | "sinistro", "acidente", "indenizacao" | EM ANDAMENTO, PENDENTE, FINALIZADO, ENCERRADO |
| Endosso | "endosso", "alteracao", "inclusao" | ABERTO, EMITIDO, CONCLUIDO, CANCELADO |
| Renovação | "renovacao", "renovar", "vigencia" | RENOVADO, NAO RENOVADO, EM ANALISE |

### Fluxo de dados completo (após correção)

```
Portal da seguradora
    → extrai prêmio, comissão, sinistro, endosso, renovação
    → atualiza PolicyRecord (flags sinistro_open/endosso_open)
    → registra sinistros/endossos abertos no Segfy
    → registra renovações no Segfy
    → sincroniza apólices atualizadas no Segfy
    → persiste tudo no banco SQLite
    → gera alertas de divergência Segfy × Portal
```

### Arquivos modificados
- `src/rpa_corretora/domain/models.py` — `PortalPolicyData` expandido
- `src/rpa_corretora/integrations/insurer_portal_wave1.py` — `_extract_status_near_labels`, `parse_policy_data_from_text_generic`
- `src/rpa_corretora/processing/orchestrator.py` — sincronização portal → Segfy com sinistros/endossos/renovações

---

## 14. Importação Inteligente de Documentos (Anexos de E-mails)

### Problema anterior
A importação de documentos no Segfy monitorava apenas uma pasta fixa (`SEGFY_IMPORT_SOURCE_DIR`). Anexos de e-mails de seguradoras e apólices baixadas dos portais não eram importados automaticamente.

### Solução implementada
O `GmailImapGateway` agora salva automaticamente anexos de e-mails de seguradoras:

1. Identifica e-mails de seguradoras pelo domínio do remetente
2. Extrai anexos com extensões permitidas: `.pdf`, `.xlsx`, `.xls`, `.csv`, `.doc`, `.docx`
3. Salva em `outputs/email_attachments/` com nome único (evita duplicatas)
4. O Segfy importa da pasta monitorada + anexos salvos

### Fluxo
```
Gmail IMAP
    → lê e-mails não lidos
    → identifica seguradoras (yelum, portoseguro, mapfre, etc.)
    → salva anexos PDF/XLSX em outputs/email_attachments/
    → Segfy importa automaticamente
```

### Arquivo modificado
- `src/rpa_corretora/integrations/gmail_imap_gateway.py` — método `save_insurer_attachments`
- `src/rpa_corretora/processing/orchestrator.py` — integração no estágio Gmail

---

## 15. Compatibilidade com Frameworks Reativos (Angular/React)

### Problema anterior
O Segfy utiliza Angular com componentes reativos. O Playwright preenchia campos via `fill()`, mas o framework não detectava a mudança — os formulários ficavam "preenchidos visualmente" porém sem disparar validação, busca ou submissão.

### Solução implementada
Toda interação com campos do Segfy agora dispara eventos reativos via JavaScript após o preenchimento:

```javascript
input.dispatchEvent(new Event('input', {bubbles: true}));
input.dispatchEvent(new Event('change', {bubbles: true}));
input.dispatchEvent(new Event('blur', {bubbles: true}));
input.dispatchEvent(new KeyboardEvent('keyup', {bubbles: true, key: 'Enter', keyCode: 13}));
input.dispatchEvent(new KeyboardEvent('keydown', {bubbles: true, key: 'Enter', keyCode: 13}));
```

### Arquivo modificado
- `src/rpa_corretora/integrations/segfy_web_gateway.py` — `_search_and_open_record`, `_fill_form_field`
 — os formulários ficavam "preenchidos visualmente" porém sem disparar validação, busca ou submissão.

Sintomas observados:
- Campo de busca preenchido mas sem executar a pesquisa
- Formulários preenchidos mas botão "Salvar" permanecia desabilitado
- Login com e-mail preenchido mas sem efeito no estado interno do app

### Solução implementada
Toda interação com campos do Segfy agora dispara eventos reativos via JavaScript após o preenchimento:

```javascript
input.dispatchEvent(new Event('input', {bubbles: true}));
input.dispatchEvent(new Event('change', {bubbles: true}));
input.dispatchEvent(new Event('blur', {bubbles: true}));
input.dispatchEvent(new KeyboardEvent('keyup', {bubbles: true, key: 'Enter', keyCode: 13}));
input.dispatchEvent(new KeyboardEvent('keydown', {bubbles: true, key: 'Enter', keyCode: 13}));
```

Isso garante que:
- Angular/React detectam a mudança de valor (`input` + `change`)
- Validações de campo são disparadas (`blur`)
- Buscas são executadas (`keyup`/`keydown` com Enter)
- O estado interno do framework fica sincronizado com o DOM

### Métodos corrigidos
- `_search_and_open_record` — busca de segurados/apólices
- `_fill_form_field` — preenchimento de qualquer campo de formulário
- `_segfy_fill_email_field` — campo de e-mail no login

### Fluxo de busca completo (após correção)
1. Preenche o campo via Playwright `fill()`
2. Dispara eventos reativos via `page.evaluate()` (JavaScript)
3. Pressiona Enter no teclado (fallback físico)
4. Clica no botão "Pesquisar"/"Buscar" se existir
5. Aguarda resultado e tenta abrir o primeiro registro encontrado

### Arquivo modificado
- `src/rpa_corretora/integrations/segfy_web_gateway.py` — `_search_and_open_record`, `_fill_form_field`

---

| Métrica | Resultado |
|---------|-----------|
| Testes automatizados | 86/86 passando |
| Dry-run com planilhas reais | 442 apólices, 175 acompanhamentos, 15 compromissos, 236 alertas |
| Ambiente Windows | Todos os componentes OK (Python, Chrome, Edge, Playwright, Pywinauto, To Do Desktop) |
| Login Segfy | Funcionando (detecção de sessão + preenchimento + Enter) |
| Busca no Segfy | Funcionando (eventos reativos + Enter + botão Pesquisar) |
| Perfil Chrome persistente | Conexão CDP ao Chrome existente (extensão Segfy mantida) |
| Modos de integração ativos | GOOGLE_API, GMAIL_IMAP, DESKTOP_APP, WEB_AUTOMATION, WEB_MULTI, HTTP_API, SMTP |

---

## Arquivos Criados/Modificados (Resumo)

| Arquivo | Ação |
|---------|------|
| `src/rpa_corretora/core/__init__.py` | **Criado** — banco de dados operacional SQLite |
| `src/rpa_corretora/integrations/interfaces.py` | Modificado — 7 novos métodos no protocolo |
| `src/rpa_corretora/integrations/segfy_gateway.py` | Modificado — implementação API + fila |
| `src/rpa_corretora/integrations/segfy_web_gateway.py` | Modificado — login, CDP, perfil persistente, 7 métodos web, eventos reativos |
| `src/rpa_corretora/integrations/stub_adapters.py` | Modificado — stubs dos novos métodos |
| `src/rpa_corretora/integrations/gmail_imap_gateway.py` | Modificado — salvamento de anexos de seguradoras |
| `src/rpa_corretora/integrations/insurer_portal_wave1.py` | Modificado — extração de sinistros/endossos/renovações |
| `src/rpa_corretora/processing/orchestrator.py` | Modificado — sincronização Segfy, portais→Segfy, banco de dados |
| `src/rpa_corretora/domain/models.py` | Modificado — PortalPolicyData expandido |
| `src/rpa_corretora/domain/rules.py` | Modificado — classificador, extração, regras de disparo |
| `.env` | Modificado — correção color ID 6, adição SEGFY_CHROME_CDP_URL |
| `scripts/executar_rpa.bat` | **Criado** — script de produção |
| `docs/registro_melhorias_v2.md` | **Criado** — este documento |

---

## Requisitos Operacionais para Produção

1. Chrome deve estar aberto com a flag `--remote-debugging-port=9222` no atalho da barra de tarefas
2. Extensão Segfy deve estar instalada no perfil do Chrome (instalação manual única)
3. `.env` deve conter `SEGFY_CHROME_CDP_URL=http://localhost:9222`
4. Planilhas devem estar nos caminhos configurados no `.env`
5. Conexão com internet ativa (APIs Google, WhatsApp, SMTP, portais)
6. Execução via `scripts\executar_rpa.bat` ou `py -3 -m rpa_corretora.main`
7. O Chrome **não precisa** ser fechado — o robô conecta à instância existente via CDP
