# Fluxo Diário (Fixo)

Este projeto paralelo segue sempre a mesma ordem de execução:

1. Agenda Google por cores
2. Microsoft To Do (app desktop)
3. Gmail (filtragem e processamento)
4. Planilhas operacionais
5. Segfy
6. Portais das seguradoras
7. WhatsApp/e-mail
8. Dashboard + relatório final

## Regra operacional

- Execução em modo estrito: se houver fallback em qualquer integração, o ciclo é bloqueado antes de iniciar.
- Falhas de execução viram pendências no relatório final.
- O ciclo sempre entrega evidência (`dashboard_latest.html` + relatório JSON/PDF).
