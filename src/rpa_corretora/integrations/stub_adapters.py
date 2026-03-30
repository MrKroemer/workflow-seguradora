from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from rpa_corretora.domain.models import (
    CalendarCommitment,
    CashflowEntry,
    EmailMessage,
    ExpenseEntry,
    FollowupRecord,
    PolicyRecord,
    PortalPolicyData,
    SegfyPolicyData,
    TodoTask,
)


class StubCalendarGateway:
    def fetch_daily_commitments(self, day: date) -> list[CalendarCommitment]:
        return [
            CalendarCommitment(
                id="agenda-1",
                title="Cobranca de parcela - Ana Silva",
                color="VERMELHO",
                due_date=day,
                resolved=False,
                client_name="Ana Silva",
                whatsapp_number="+5583999897477",
            ),
            CalendarCommitment(
                id="agenda-2",
                title="Baixa de parcela - Carlos Lima",
                color="AZUL",
                due_date=day,
                resolved=True,
            ),
        ]


class StubTodoGateway:
    def fetch_open_tasks(self) -> list[TodoTask]:
        today = date.today()
        return [
            TodoTask(
                id="todo-1",
                title="Conferir comissao de renovacoes",
                due_date=today - timedelta(days=1),
                completed=False,
            )
        ]


class StubGmailGateway:
    def fetch_unread_messages(self) -> list[EmailMessage]:
        now = datetime.now()
        return [
            EmailMessage(
                id="email-1",
                sender="extrato@nubank.com.br",
                subject="Fluxo de caixa R$ 1.245,90 - Seguradora: Porto Seguro",
                body="Data: 27/03/2026 | Referencia mensal",
                received_at=now,
            ),
            EmailMessage(
                id="email-2",
                sender="comunicado@portoseguro.com.br",
                subject="Aviso de comissao liberada",
                body="Processamento concluido.",
                received_at=now,
            ),
            EmailMessage(
                id="email-3",
                sender="renovacao@corretora.com.br",
                subject="Relatorio de renovacao - carteira",
                body="Arquivo em anexo.",
                received_at=now,
                attachments=["relatorio_renovacao.xlsx"],
            ),
        ]


class StubSpreadsheetGateway:
    def __init__(self) -> None:
        self._cashflow_entries: list[CashflowEntry] = []

    def load_policies(self) -> list[PolicyRecord]:
        today = date.today()
        return [
            PolicyRecord(
                policy_id="PB-1001",
                insured_name="Ana Silva",
                insurer="Porto Seguro",
                vig=today + timedelta(days=30),
                renewal_kind="RENOVACAO_INTERNA",
                renewal_started=False,
                status_pgto="",
                sinistro_open=False,
                endosso_open=False,
                premio_total=Decimal("2400.00"),
                comissao=Decimal("360.00"),
            ),
            PolicyRecord(
                policy_id="PB-1002",
                insured_name="Carlos Lima",
                insurer="Allianz",
                vig=today + timedelta(days=15),
                renewal_kind="NOVO",
                renewal_started=False,
                status_pgto="PAGO",
                sinistro_open=True,
                endosso_open=False,
                premio_total=Decimal("1800.00"),
                comissao=Decimal("270.00"),
            ),
            PolicyRecord(
                policy_id="PB-1003",
                insured_name="Bruna Rocha",
                insurer="Mapfre",
                vig=today + timedelta(days=7),
                renewal_kind="RENOVACAO_INTERNA",
                renewal_started=False,
                status_pgto="PAGO",
                sinistro_open=False,
                endosso_open=True,
                premio_total=Decimal("2100.00"),
                comissao=Decimal("315.00"),
            ),
        ]

    def load_followups(self, year: int) -> list[FollowupRecord]:
        _ = year
        return [
            FollowupRecord(
                insured_name="Ana Silva",
                month="MARCO",
                fase="Contato inicial",
                status="",
            ),
            FollowupRecord(
                insured_name="Carlos Lima",
                month="MARCO",
                fase="Cotacao",
                status="Concluido",
            ),
            FollowupRecord(
                insured_name="Segurado nao mapeado",
                month="MARCO",
                fase="Proposta",
                status="Em aberto",
            ),
        ]

    def load_expenses(self, year: int, month: int) -> list[ExpenseEntry]:
        _ = (year, month)
        today = date.today()
        return [
            ExpenseEntry(
                date=today,
                value=Decimal("350.00"),
                description="Combustivel",
                category="Transporte",
            ),
            ExpenseEntry(
                date=today,
                value=Decimal("120.00"),
                description="Mercado",
                category="Mercado",
            ),
        ]

    def append_cashflow_entries(self, entries: list[CashflowEntry]) -> None:
        self._cashflow_entries.extend(entries)


class StubSegfyGateway:
    def fetch_policy_data(self) -> list[SegfyPolicyData]:
        return [
            SegfyPolicyData(
                policy_id="PB-1001",
                premio_total=Decimal("2400.00"),
                comissao=Decimal("360.00"),
            ),
            SegfyPolicyData(
                policy_id="PB-1002",
                premio_total=Decimal("1800.00"),
                comissao=Decimal("270.00"),
            ),
        ]


class StubInsurerPortalGateway:
    def fetch_policy_data(self, policy_ids: list[str]) -> list[PortalPolicyData]:
        data = {
            "PB-1001": PortalPolicyData(
                policy_id="PB-1001",
                insurer="Porto Seguro",
                premio_total=Decimal("2400.00"),
                comissao=Decimal("355.00"),
            ),
            "PB-1002": PortalPolicyData(
                policy_id="PB-1002",
                insurer="Allianz",
                premio_total=Decimal("1800.00"),
                comissao=Decimal("270.00"),
            ),
        }
        return [data[p_id] for p_id in policy_ids if p_id in data]


class ConsoleWhatsAppGateway:
    def send_message(self, phone: str, content: str) -> None:
        print(f"[WhatsApp] -> {phone}: {content[:90]}...")


class ConsoleEmailSenderGateway:
    def send_email(self, recipient: str, subject: str, content: str) -> None:
        print(f"[Email] -> {recipient} | {subject} | {content[:80]}...")
