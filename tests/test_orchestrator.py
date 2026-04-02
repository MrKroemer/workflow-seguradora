from __future__ import annotations

from datetime import date
from decimal import Decimal

from rpa_corretora.config import AppSettings, MicrosoftTodoSettings, RenewalSettings
from rpa_corretora.domain.models import (
    CalendarCommitment,
    DashboardSnapshot,
    PolicyRecord,
)
from rpa_corretora.processing.orchestrator import DailyProcessor


class _CalendarGateway:
    def fetch_daily_commitments(self, day: date) -> list[CalendarCommitment]:
        return [
            CalendarCommitment(
                id="agenda-red",
                title="Cobranca de parcela - Ana Silva",
                color="VERMELHO",
                due_date=day,
                resolved=False,
                client_name="Ana Silva",
                whatsapp_number="+5583999990000",
            ),
            CalendarCommitment(
                id="agenda-blue",
                title="Baixa de parcela - Ana Silva",
                color="AZUL",
                due_date=day,
                resolved=False,
                client_name="Ana Silva",
            ),
            CalendarCommitment(
                id="agenda-gray",
                title="Sinistro - Ana Silva",
                color="CINZA",
                due_date=day,
                resolved=False,
                client_name="Ana Silva",
            ),
            CalendarCommitment(
                id="agenda-green",
                title="Tratativa diversa - Ana Silva",
                color="VERDE",
                due_date=day,
                resolved=False,
                client_name="Ana Silva",
            ),
        ]


class _TodoGateway:
    def __init__(self) -> None:
        self.created: list[str] = []
        self.updated: list[str] = []
        self.completed: list[str] = []

    def fetch_open_tasks(self):
        return []

    def create_task(self, *, title: str, due_date=None, notes=None):
        _ = (due_date, notes)
        self.created.append(title)
        return f"todo-{len(self.created)}"

    def update_task(self, *, task_id: str, title=None, due_date=None, notes=None):
        _ = (title, due_date, notes)
        self.updated.append(task_id)
        return True

    def complete_task(self, *, task_id: str):
        self.completed.append(task_id)
        return True


class _GmailGateway:
    def fetch_unread_messages(self):
        return []


class _SheetsGateway:
    def load_policies(self):
        return [
            PolicyRecord(
                policy_id="PB-ORQ-1",
                insured_name="Ana Silva",
                insurer="Porto Seguro",
                vig=date(2026, 4, 30),
                status_pgto="PAGO",
                premio_total=Decimal("1000.00"),
                comissao=Decimal("100.00"),
                vehicle_item="ONIX QWE1A23",
                vehicle_model="ONIX",
                vehicle_plate="QWE1A23",
            )
        ]

    def load_followups(self, year: int):
        _ = year
        return []

    def load_expenses(self, year: int, month: int):
        _ = (year, month)
        return []

    def append_cashflow_entries(self, entries):
        _ = entries

    def append_expense_entries(self, entries):
        _ = entries

    def validate_expense_summary(self, year: int, month: int):
        _ = (year, month)
        return []


class _SegfyGateway:
    def __init__(self) -> None:
        self.payments: list[tuple[str, str]] = []

    def fetch_policy_data(self):
        return []

    def register_payment(self, *, commitment_id: str, description: str) -> bool:
        self.payments.append((commitment_id, description))
        return True


class _PortalGateway:
    def __init__(self) -> None:
        self.claim_checks: list[tuple[str, str]] = []

    def fetch_policy_data(self, policy_ids):
        _ = policy_ids
        return []

    def check_claim_status(self, *, commitment_id: str, description: str) -> str | None:
        self.claim_checks.append((commitment_id, description))
        return "EM_ANDAMENTO"


class _WhatsAppGateway:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def send_message(self, phone: str, content: str) -> None:
        self.sent.append((phone, content))


class _EmailGateway:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []

    def send_email(self, recipient: str, subject: str, content: str) -> None:
        self.sent.append((recipient, subject, content))


class _DashboardBuilder:
    def build(self, policies, alerts, cashflow_entries, expenses, followups=None):
        _ = (policies, alerts, cashflow_entries, expenses, followups)
        return DashboardSnapshot(
            active_policies_by_insurer={},
            commissions={"paid": 0, "pending": 0},
            open_renewals={"RENOVACAO_INTERNA": 0, "NOVO": 0},
            open_incidents={"SINISTRO": 0, "ENDOSSO": 0},
            cashflow={"cash_in": "0.00", "cash_out": "0.00", "net": "0.00"},
            critical_alerts=0,
        )


def _settings() -> AppSettings:
    return AppSettings(
        timezone="America/Fortaleza",
        insurers={},
        insurer_domains=tuple(),
        renewal=RenewalSettings(
            internal_days=30,
            new_days=15,
            reminder_days=(20, 10, 7, 1),
            holidays=frozenset(),
        ),
        files=None,
        microsoft_todo=MicrosoftTodoSettings(username="user@example.com", password="Senha@123"),
    )


def test_dispatch_notifications_executes_all_agenda_colors(monkeypatch) -> None:
    segfy = _SegfyGateway()
    portals = _PortalGateway()
    whatsapp = _WhatsAppGateway()
    email_sender = _EmailGateway()
    todo = _TodoGateway()

    processor = DailyProcessor(
        settings=_settings(),
        calendar=_CalendarGateway(),
        todo=todo,
        gmail=_GmailGateway(),
        sheets=_SheetsGateway(),
        segfy=segfy,
        portals=portals,
        whatsapp=whatsapp,
        email_sender=email_sender,
        dashboard_builder=_DashboardBuilder(),
    )

    monkeypatch.setenv("INSURED_NOTIFY_EMAIL_TO", "operacional@pbseg.com")
    processor.run(today=date(2026, 3, 30), dry_run=False)

    assert len(whatsapp.sent) == 1
    assert whatsapp.sent[0][0] == "+5583999990000"

    assert segfy.payments == [("agenda-blue", "Baixa de parcela - Ana Silva")]
    assert portals.claim_checks == [("agenda-gray", "Sinistro - Ana Silva")]

    assert len(email_sender.sent) == 1
    recipient, subject, content = email_sender.sent[0]
    assert recipient == "operacional@pbseg.com"
    assert "Ana Silva" in subject
    assert "Modelo: ONIX" in content
    assert "Placa: QWE1A23" in content

    # Cada compromisso pendente da agenda vira tarefa operacional no To Do.
    assert len(todo.created) == 4
