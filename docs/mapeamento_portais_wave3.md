# Mapeamento Inicial de Portais (Wave 3)

Este documento registra o mapeamento dos proximos portais a partir de:

- lista de sites: `arquivos/Documento sem nome.pdf`
- credenciais: `arquivos/SENHAS.pdf`

## Portais Prioritarios (Wave 3)

7. Tokio Marine
8. HDI
9. Azul

## URLs (ordem do documento)

7. `https://www.tokiomarine.com.br/corretores`
8. `https://www.hdi.com.br/hdidigital`
9. `https://www.azulseguros.com.br/area-restrita`

## Variaveis de Ambiente (Tokio)

- `TOKIO_PORTAL_USER`
- `TOKIO_PORTAL_PASSWORD`
- `TOKIO_PORTAL_WEB_HEADLESS`

## Variaveis de Ambiente (HDI)

- `HDI_PORTAL_USER`
- `HDI_PORTAL_PASSWORD`
- `HDI_PORTAL_WEB_HEADLESS`

## Variaveis de Ambiente (Azul)

- `AZUL_PORTAL_USER`
- `AZUL_PORTAL_PASSWORD`
- `AZUL_PORTAL_WEB_HEADLESS`

## Tokio Marine (menu mapeado)

Com base no mapeamento visual validado:

- Entradas de acesso identificadas:
  - pagina publica `Corretores` com link para `Portal do Corretor`
  - seletor de portal com card `Corretor`
- Menu superior identificado no portal:
  - `Produtos`
  - `Renovacoes`
  - `Consultas`
  - `Financeiro`
  - `Sinistros`
  - `Assistencias`
  - `Eu, Corretor!`
  - `Brokertech`

Submenus observados:

- `Consultas`:
  - `Visao Geral do Cliente - PIX, 2a Via de Boleto, Apolice ou Endosso`
  - `Acompanhar Emissoes`
  - `Acompanhamento de Propostas e Endossos`
- `Financeiro`:
  - `Acompanhar Emissoes`
  - `Extrato Comissao`
  - `Consulta Saldo/Extrato`
  - `Clientes inadimplentes`
- `Sinistros`:
  - `Sinistro Automovel`
  - `Acompanhar Sinistro Auto Segurado`
  - `Acompanhar Sinistro Auto Terceiro`
  - `Consultar SMS`
- `Assistencias`:
  - `Solicitar Guincho e Assistencia 24 horas`
  - `Consultar Servicos (Vidros e Carro Reserva)`

Pontos de atencao de UI:

- Modais de campanha podem abrir ao entrar (com `x` para fechar).
- Modal de `Termo de Aceite` pode exigir checkbox (`Li e aceito`) e botao `Aceitar`.
- Banner de cookies na base da tela pode bloquear cliques.

Uso no bot:

- Navegacao preferencial para consulta por apolice:
  - `Consultas` -> `Visao Geral do Cliente ... Apolice ou Endosso` -> preencher busca -> `Pesquisar/Buscar`
- Fallback de navegacao:
  - `Financeiro` -> `Extrato Comissao` (quando aplicavel)
  - `Sinistros` -> `Acompanhar Sinistro ...`
  - busca global por `CPF/apolice` quando campo estiver presente
- Tratamento defensivo:
  - fechamento automatico de modal/cookies antes de clicar em menus e filtros.

## Observacao de Implementacao

- Wave 3 iniciado com automacao web para Tokio Marine.
- Mapeamento de menus HDI registrado e conectado ao gateway dedicado.
- Mapeamento de menus Azul registrado e conectado ao gateway dedicado.
- A cadeia de portais permanece nao regressiva com fallback por apolice para `stub`.

## HDI (menu mapeado)

Com base no mapeamento visual validado:

- URL de trabalho:
  - `https://www.hdi.com.br/hdidigital`
- Menu superior identificado:
  - `Home`
  - `Cotacao`
  - `Proposta`
  - `Vistoria`
  - `Apolice`
  - `Rastreador`
  - `Parcela`
  - `Renovacao`
  - `Sinistro`
  - `Ajuda`
  - `Adm`

Submenus observados:

- `Cotacao`:
  - `Nova Cotacao`
  - `Buscar Cotacao`
  - `Endosso`
  - `Carta Verde`
  - `Patrimonial`
  - `Rural`
- `Proposta`:
  - `Buscar Proposta`
  - `Exclusao de Proposta`
- `Vistoria`:
  - `Buscar Vistoria`
  - `Agendar Vistoria`
- `Apolice`:
  - `Buscar Apolices`
- `Renovacao`:
  - `Renovacoes`
  - `Renovacao Patrimonial`
  - `Relatorio Renovacoes`
- `Ajuda`:
  - `Por categoria`
  - `Por palavra-chave`
  - `Por mais acessadas`

Pontos de atencao de UI:

- Modal de campanha/comissao pode abrir no carregamento (`Novo Programa de Comissao Especial`).
- Botao de fechar pode aparecer como `X`, icone ou texto (`Fechar`).
- Banner de cookies pode bloquear cliques no rodape.
- Caixa lateral de pesquisa (`COTACOES`, `PROPOSTAS`, `APOLICES`, `SINISTROS`) pode ser usada como fallback.

Uso no bot:

- Navegacao preferencial para consulta por apolice:
  - `Apolice` -> `Buscar Apolices` -> preencher campo -> `Pesquisar/Buscar/Continuar`
- Fallbacks:
  - `Proposta` -> `Buscar Proposta`
  - `Renovacao` -> `Renovacoes`
  - caixa lateral (`APOLICES`) com campo `CPF/CNPJ`
- Consulta de sinistro:
  - abertura de `Sinistro` e busca por sinistro/apolice/protocolo/CPF-CNPJ
- Tratamento defensivo:
  - fechamento automatico de modais/cookies antes e depois de navegacoes.

## Azul (menu mapeado)

Com base no mapeamento visual validado:

- URLs de trabalho:
  - `https://www.azulseguros.com.br/area-restrita`
  - `https://dashboard.azulseguros.com.br/#/home`
- Menu principal identificado no dashboard:
  - `Meus Negocios`
  - `Cadastro`
  - `Propostas`
  - `Biblioteca`
  - `Sinistros`
  - `Financeiro`
  - `Tributos`
  - `Atendimento`

Submenus observados:

- `Meus Negocios`:
  - `Apolice`
  - `Azul por Assinatura`
  - `Endosso`
  - `Renovacao`
  - `Solicitar Kit Apolice`
- `Cadastro`:
  - `Alterar Dados`
  - `Alterar Senha`
  - `Termo de Confirmacao Eletronica`
- `Propostas`:
  - `Consultar Cota Premio`
  - `Consultar Propostas`
  - `Gestao de Pendencias`
- `Biblioteca`:
  - `Arquivos`
  - `Comparativo Assistencia 24h`
  - `Guia Rapido Produto Auto`
- `Sinistros`:
  - `Acompanhamento de Sinistros`
  - `Aviso de Ocorrencia`
  - `Codigo de Postagem (Sedex)`
  - `Documentacao de Sinistros`
  - `Envio de Documentos Online`
  - `Relatorio Sinistros Avisados`
- `Financeiro`:
  - `2a via boleto debito nao autorizado`
  - `Consultar Parcelas`
  - `Extrato de Comissoes`
  - `Orientacoes debito em conta`
- `Tributos`:
  - `Emissao de Nota Fiscal Corretor`
  - `Informe de Rendimentos`
- `Atendimento`:
  - `Agendamento de Vistoria Previa`
  - `Chat`
  - `Enviar Email`
  - `Mensagens`
  - `Solicitar Kit Apolice`

Pontos de atencao de UI:

- Login por modal de `Area restrita` com aba `Corretor` (codigo + senha).
- Modal de aviso de privacidade pode abrir apos login (botao `Fechar` e `X`).
- Banner de cookies com `Aceitar todos os cookies`/`Dispensar` pode bloquear cliques.

Uso no bot:

- Navegacao preferencial para consulta por apolice:
  - `Meus Negocios` -> `Apolice` -> busca superior (`CPF/CNPJ/placa/segurado`)
- Fallbacks:
  - `Propostas` -> `Consultar Cota Premio`
  - `Financeiro` -> `Extrato de Comissoes` ou `Consultar Parcelas`
  - campo de busca superior com botao `Buscar Segurado`
- Consulta de sinistro:
  - `Sinistros` -> `Acompanhamento de Sinistros` -> busca por sinistro/apolice/protocolo/CPF-CNPJ/placa
- Tratamento defensivo:
  - fechamento automatico de popup de aviso e cookies antes/depois de navegacoes.
