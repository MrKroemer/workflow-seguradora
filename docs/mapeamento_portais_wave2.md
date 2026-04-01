# Mapeamento Inicial de Portais (Wave 2)

Este documento registra o mapeamento dos portais 4 a 6 definidos a partir de:

- lista de sites: `arquivos/Documento sem nome.pdf`
- credenciais: `arquivos/SENHAS.pdf`

## Portais Prioritarios (Wave 2)

4. Bradesco
5. Allianz
6. Suhai

## URLs (ordem do documento)

4. `https://wwwn.bradescoseguros.com.br`
5. `https://www.allianznet.com.br`
6. `https://suhaiseguradoracotacao.com.br/login`

## Variaveis de Ambiente

- `BRADESCO_PORTAL_USER`
- `BRADESCO_PORTAL_PASSWORD`
- `BRADESCO_PORTAL_WEB_HEADLESS`

- `ALLIANZ_PORTAL_USER`
- `ALLIANZ_PORTAL_PASSWORD`
- `ALLIANZ_PORTAL_WEB_HEADLESS`

- `SUHAI_PORTAL_USER`
- `SUHAI_PORTAL_PASSWORD`
- `SUHAI_PORTAL_WEB_HEADLESS`

## Observacao de Implementacao

- Wave 2 implementada com automacao web para:
  - Bradesco
  - Allianz
  - Suhai
- A cadeia de portais permanece nao regressiva com fallback por apolice para `stub`.
- Proximo bloco de mapeamento (Wave 3) registrado em `docs/mapeamento_portais_wave3.md`.

## Suhai (menu mapeado)

Mapeamento visual consolidado com base nos prints enviados em `2026-04-01`:

- Menu superior identificado:
  - `Cadastro`
  - `Apolice`
  - `Relatorios`
  - `Sinistros`
  - `Geral`
- Submenus identificados:
  - `Cadastro`:
    - `Meus Dados`
  - `Apolice`:
    - `Consulta de Apolice`
  - `Relatorios`:
    - `Impressao de 2 Via`
    - `Seg Canc Inadimplencia`
    - `Apolices a Renovar`
    - `Seguros Emitidos`
  - `Sinistros`:
    - `Processo de Sinistro`
  - `Geral`:
    - `Alterar Senha`

Navegacao preferencial adicionada no gateway:

- Consulta de apolice:
  - `Apolice` -> `Consulta de Apolice` -> preencher campo de busca por apolice -> `Pesquisar/Buscar/Consultar`.
- Consulta de sinistro por compromisso:
  - `Sinistros` -> `Processo de Sinistro` -> preencher busca por sinistro/apolice/protocolo -> `Pesquisar/Buscar/Consultar`.
- Fallback:
  - Mantido fallback generico da `BasePortalWebGateway` para preservar nao regressao quando o menu nao for localizado.
