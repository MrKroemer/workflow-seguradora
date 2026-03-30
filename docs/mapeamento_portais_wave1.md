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
