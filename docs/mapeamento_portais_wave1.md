# Mapeamento Inicial de Portais (Wave 1)

Este documento registra o mapeamento dos 3 primeiros portais definidos a partir de:

- lista de sites: `arquivos/Documento sem nome.pdf`
- credenciais: `arquivos/SENHAS.pdf`

## Portais Prioritarios

1. Yelum
2. Porto Seguro
3. Mapfre

## URLs (ordem do documento)

1. `https://novomeuespacocorretor.yelumseguros.com.br/dashboard`
2. `https://corretor.portoseguro.com.br/novocol/homepage?code=5e121c14-81cb-41d4-9d0d-fea54bbe5558&state=rAnDoMtExT`
3. `https://negocios.mapfre.com.br/tela-principal`

## Variaveis de Ambiente

- `YELUM_PORTAL_USER`
- `YELUM_PORTAL_PASSWORD`
- `YELUM_PORTAL_WEB_HEADLESS`

- `PORTO_PORTAL_USER`
- `PORTO_PORTAL_PASSWORD`
- `PORTO_PORTAL_WEB_HEADLESS`

- `MAPFRE_PORTAL_USER`
- `MAPFRE_PORTAL_PASSWORD`
- `MAPFRE_PORTAL_WEB_HEADLESS`

## Observacao de Implementacao

- Wave 1 implementada com automacao web para:
  - Yelum
  - Porto Seguro
  - Mapfre
- O retorno segue com fallback por apolice para `stub`, preservando continuidade operacional.

## Yelum (menu mapeado)

Com base no mapeamento visual validado:

- Menu superior identificado:
  - `+Negocios`
  - `Consultas`
  - `Assistencia`
  - `Sinistros`
  - `Financeiro`
  - `Produtos`
  - `Cresca Corretor`
  - `Atendimento`
- Submenu `Consultas` identificado:
  - `Propostas`
  - `Apolice`
  - `Renovacao`
  - `Cancelamentos`
  - `Cotacao - NewSel`
  - `Easyway`
- Submenu `Sinistros` identificado:
  - `Avisar sinistro`
  - `Acompanhar sinistro`
  - `Encontrar oficinas`

Uso no bot:

- Navegacao preferencial para consulta de apolice: `Consultas -> Apolice`.
- Fallback adicional para atalho lateral `Consultar Apolice`.

## Porto Seguro (menu mapeado)

Com base no mapeamento visual validado:

- Menu superior identificado:
  - `Vistoria Previa`
  - `Comissoes`
  - `Cobranca`
  - `Sinistro`
  - `Meus Clientes`
  - `Minha Carteira`
  - `Link do Corretor`
  - `Campanhas`

Telas com filtros visiveis:

- `Meus Clientes`:
  - tabela com coluna `N da Apolice / Contrato`
  - busca por `Periodo` ou `Identificador`
  - filtros de `Status`, `Produto` e periodo rapido
- `Minha Carteira`:
  - cards de producao/comissao e bloco de parcelas com link para cobranca
- `Cobranca`:
  - `Gestao de parcelas` com busca `CPF ou CNPJ`
  - indicadores de vencimento e status de parcela
- `Sinistro`:
  - acompanhamento por produto com acao `Abrir`
- `Comissoes`:
  - tela de consulta com seletores de empresa, susep e periodo
- `Link do Corretor`:
  - lista de links e modal inicial `Entendi`

Uso no bot:

- Navegacao preferencial para busca de apolice:
  - `Meus Clientes` -> `Identificador` -> preencher busca -> enviar (`Enter`/`Pesquisar`)
- Fallback de navegacao:
  - barra global do topo (`Buscar por nome, CPF ou CNPJ`)
  - `Minha Carteira` -> barra global
  - `Cobranca` -> busca por `CPF ou CNPJ`
  - `Sinistro` -> barra global
- Tratamento de UI:
  - fechamento defensivo do modal inicial (`Entendi`) e banner de cookies.

## Mapfre (menu mapeado)

Com base no mapeamento visual validado:

- Menu superior identificado:
  - `Inicio`
  - `Carteira`
  - `Desempenho`
  - `Renovacoes`
  - `Vistoria Previa Auto`
  - `Parcelas`
  - `Propostas`
  - `Comissao`
  - `Para voce`
  - `Sinistros`

Telas com filtros visiveis:

- `Carteira de clientes`:
  - campos `Nome do Cliente`, `Numero do CPF/CNPJ`, `Numero da Apolice`, `Numero de Proposta`, `Periodo`
  - acao principal: `Pesquisar`
- `Gestao de Renovacoes`:
  - campos `Nome do Cliente`, `Numero do CPF/CNPJ`, `Numero da Apolice`, `Placa`, `Chassi`
  - acao principal: `Pesquisar`
- `Consulta e Gestao de Sinistros`:
  - campos `Numero do Sinistro`, `Nome do Cliente`, `Numero do CPF/CNPJ`, `Numero da Apolice`, `Placa`, `Chassi`
  - acao principal: `Pesquisar`
- `Propostas`:
  - campos `Numero Proposta`, `Protocolo`, `Periodo`, `Numero Chassi`, `Placa`, `Segurado`, `Numero CPF/CNPJ`
  - acao principal: `Pesquisar`
- `Comissao / Extrato de Comissoes`:
  - filtro por `Relatorio` e `Empresa`
  - acao principal: `Pesquisar`
- `Desempenho`:
  - cards com `Premios` e `Comissoes emitidas` (usado como fonte auxiliar de sinais financeiros)

Uso no bot:

- Navegacao preferencial para consulta por apolice:
  - `Carteira` -> preencher `Numero da Apolice` -> `Pesquisar`
- Fallback de navegacao:
  - `Renovacoes` -> preencher `Numero da Apolice` -> `Pesquisar`
  - `Sinistros` -> preencher `Numero da Apolice` -> `Pesquisar`
