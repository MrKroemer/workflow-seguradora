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
                resolved=False,
            ),
            CalendarCommitment(
                id="agenda-3",
                title="Acompanhamento de sinistro - Bruna Rocha",
                color="CINZA",
                due_date=day,
                resolved=False,
            ),
            CalendarCommitment(
                id="agenda-4",
                title="Tratativa diversa - Ana Silva",
                color="VERDE",
                due_date=day,
                resolved=False,
            ),
        ]


class StubTodoGateway:
    def __init__(self) -> None:
        self._tasks: list[TodoTask] = []

    def fetch_open_tasks(self) -> list[TodoTask]:
        if not self._tasks:
            today = date.today()
            self._tasks.append(
                TodoTask(
                    id="todo-1",
                    title="Conferir comissao de renovacoes",
                    due_date=today - timedelta(days=1),
                    completed=False,
                    list_name="Principal",
                )
            )
        return [item for item in self._tasks if not item.completed]

    def create_task(
        self,
        *,
        title: str,
        due_date: date | None = None,
        notes: str | None = None,
    ) -> str | None:
        _ = notes
        task_id = f"todo-{len(self._tasks) + 1}"
        self._tasks.append(
            TodoTask(
                id=task_id,
                title=title,
                due_date=due_date,
                completed=False,
                list_name="Principal",
            )
        )
        return task_id

    def update_task(
        self,
        *,
        task_id: str,
        title: str | None = None,
        due_date: date | None = None,
        notes: str | None = None,
    ) -> bool:
        _ = notes
        for idx, task in enumerate(self._tasks):
            if task.id != task_id:
                continue
            self._tasks[idx] = TodoTask(
                id=task.id,
                title=title if title is not None else task.title,
                due_date=due_date if due_date is not None else task.due_date,
                completed=task.completed,
                list_name=task.list_name,
                external_ref=task.external_ref,
            )
            return True
        return False

    def complete_task(self, *, task_id: str) -> bool:
        for idx, task in enumerate(self._tasks):
            if task.id != task_id:
                continue
            self._tasks[idx] = TodoTask(
                id=task.id,
                title=task.title,
                due_date=task.due_date,
                completed=True,
                list_name=task.list_name,
                external_ref=task.external_ref,
            )
            return True
        return False


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
        self._expense_entries: list[ExpenseEntry] = []

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

    def append_expense_entries(self, entries: list[ExpenseEntry]) -> None:
        self._expense_entries.extend(entries)

    def validate_expense_summary(self, year: int, month: int) -> list[str]:
        _ = (year, month)
        return []


class StubSegfyGateway:
    def __init__(self) -> None:
        self.registered_payments: list[dict[str, str]] = []

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

    def register_payment(self, *, commitment_id: str, description: str) -> bool:
        self.registered_payments.append({"commitment_id": commitment_id, "description": description})
        print(f"[Segfy] Baixa registrada (stub): {commitment_id} -> {description}")
        return True


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

    def check_claim_status(self, *, commitment_id: str, description: str) -> str | None:
        print(f"[Portal] Consulta de sinistro (stub): {commitment_id} -> {description}")
        return "EM_ANALISE"


class ConsoleWhatsAppGateway:
    def send_message(self, phone: str, content: str) -> None:
        print(f"[WhatsApp] -> {phone}: {content[:90]}...")


class ConsoleEmailSenderGateway:
    def send_email(
        self,
        recipient: str,
        subject: str,
        content: str,
        attachments: list[str] | None = None,
    ) -> None:
        total_attachments = len(attachments or [])
        print(f"[Email] -> {recipient} | {subject} | {content[:80]}... | anexos={total_attachments}")
