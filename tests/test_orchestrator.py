from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from rpa_corretora.config import AppSettings, MicrosoftTodoSettings, RenewalSettings
from rpa_corretora.domain.models import (
    CalendarCommitment,
    DashboardSnapshot,
    EmailMessage,
    PolicyRecord,
    TodoTask,
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


class _CalendarGatewayWithWriter(_CalendarGateway):
    def __init__(self) -> None:
        self.upserted_task_ids: list[str] = []

    def fetch_daily_commitments(self, day: date) -> list[CalendarCommitment]:
        return [
            CalendarCommitment(
                id="agenda-red",
                title="Cobranca de parcela - Ana Silva",
                color="VERMELHO",
                due_date=day,
                resolved=False,
                client_name="Ana Silva",
                whatsapp_number=None,
            )
        ]

    def upsert_todo_task_event(self, *, task: TodoTask) -> str | None:
        self.upserted_task_ids.append(task.id)
        return f"evt-{len(self.upserted_task_ids)}"


class _CalendarGatewayMessageRules:
    def fetch_daily_commitments(self, day: date) -> list[CalendarCommitment]:
        _ = day
        return [
            CalendarCommitment(
                id="renovacao-1",
                title="RENOVACAO - ANA SILVA",
                color="VERDE",
                due_date=date(2026, 4, 3),
                description="Cliente: Ana Silva\nVIG: 13/04/2026",
                resolved=False,
                client_name="Ana Silva",
                whatsapp_number="+5583999991111",
            ),
            CalendarCommitment(
                id="atraso-1",
                title="Parcela vencida",
                color="TANGERINA",
                due_date=date(2026, 3, 27),
                description="Boleto em atraso\nVENCIMENTO: 27/03/2026",
                resolved=False,
                client_name="Bruno Costa",
                whatsapp_number="+5583999992222",
            ),
            CalendarCommitment(
                id="banco-1",
                title="Liberacao cobranca em conta",
                color="AMARELO",
                due_date=date(2026, 4, 5),
                description="Liberacao de cobranca em conta corrente",
                resolved=False,
                client_name="Carla Souza",
                whatsapp_number="+5583999993333",
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


class _TodoGatewayWithLegacyAgendaTask(_TodoGateway):
    def fetch_open_tasks(self):
        # Simulates an old-format title already synchronized in the past.
        return [
            TodoTask(
                id="legacy-1",
                title="RPA-AGENDA:agenda-red | VERMELHO | Cobranca de parcela - Ana Silva",
                due_date=date(2026, 3, 30),
                completed=False,
                list_name="INATIVOS",
            )
        ]


class _TodoGatewayWithContacts(_TodoGateway):
    def fetch_open_tasks(self):
        return [
            TodoTask(
                id="todo-contact-ana",
                title="Ana Silva - cadastro cliente",
                due_date=date(2026, 3, 30),
                completed=False,
                list_name="INATIVOS",
                external_ref="Telefone: +55 (83) 99989-1111 | E-mail: ana.silva@pbseg.com",
                contact_phone="+5583999891111",
                contact_email="ana.silva@pbseg.com",
            ),
            TodoTask(
                id="todo-mirror-agenda",
                title="VERMELHO | Ana Silva | AG:ABCDE12345",
                due_date=date(2026, 3, 30),
                completed=False,
                list_name="INATIVOS",
            ),
            TodoTask(
                id="todo-legacy-mirror-no-marker",
                title="Ana Silva - tarefa antiga",
                due_date=date(2026, 3, 30),
                completed=False,
                list_name="INATIVOS",
                external_ref="Origem: Google Agenda\nCompromisso: agenda-red",
            ),
        ]


class _GmailGateway:
    def fetch_unread_messages(self):
        return []


class _GmailGatewayWithNubank:
    def fetch_unread_messages(self):
        return [
            EmailMessage(
                id="nubank-1",
                sender="noreply@nubank.com.br",
                subject="Recebimento de pagamento",
                body="Recebemos um pagamento no valor de R$ 120,50 em 03/04/2026",
                received_at=datetime(2026, 4, 3, 9, 30, 0),
            )
        ]


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


def test_dispatch_notifications_executes_all_agenda_colors(monkeypatch, tmp_path) -> None:
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
    monkeypatch.setenv("MESSAGE_DISPATCH_STATE_PATH", str(tmp_path / "dispatch_state.json"))
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

    # Novo formato: titulo legivel com marcador compacto (sem id longo no prefixo).
    assert any(title.startswith("VERMELHO | ") for title in todo.created)
    assert all("RPA-AGENDA:" not in title for title in todo.created)
    assert any("AG:" in title for title in todo.created)
    assert any("| Ana Silva |" in title for title in todo.created)


def test_sync_todo_keeps_compatibility_with_legacy_agenda_marker(monkeypatch, tmp_path) -> None:
    segfy = _SegfyGateway()
    portals = _PortalGateway()
    whatsapp = _WhatsAppGateway()
    email_sender = _EmailGateway()
    todo = _TodoGatewayWithLegacyAgendaTask()

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
    monkeypatch.setenv("MESSAGE_DISPATCH_STATE_PATH", str(tmp_path / "dispatch_state.json"))
    processor.run(today=date(2026, 3, 30), dry_run=False)

    # agenda-red already existed as legacy format, so it should be updated instead of re-created.
    assert len(todo.updated) == 1
    assert todo.updated[0] == "legacy-1"
    assert len(todo.created) == 3


def test_orchestrator_uses_todo_contacts_and_writes_calendar(monkeypatch, tmp_path) -> None:
    segfy = _SegfyGateway()
    portals = _PortalGateway()
    whatsapp = _WhatsAppGateway()
    email_sender = _EmailGateway()
    todo = _TodoGatewayWithContacts()
    calendar = _CalendarGatewayWithWriter()

    processor = DailyProcessor(
        settings=_settings(),
        calendar=calendar,
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
    monkeypatch.setenv("MESSAGE_DISPATCH_STATE_PATH", str(tmp_path / "dispatch_state.json"))
    processor.run(today=date(2026, 3, 30), dry_run=False)

    # WhatsApp number was absent in calendar and recovered from Microsoft To Do details.
    assert len(whatsapp.sent) == 1
    assert whatsapp.sent[0][0] == "+5583999891111"

    # Only non-mirrored To Do tasks are upserted into Google Calendar.
    assert calendar.upserted_task_ids == ["todo-contact-ana"]


def test_operational_message_rules_and_nubank_notification_are_dispatched_once(monkeypatch, tmp_path) -> None:
    segfy = _SegfyGateway()
    portals = _PortalGateway()
    whatsapp = _WhatsAppGateway()
    email_sender = _EmailGateway()
    todo = _TodoGateway()

    processor = DailyProcessor(
        settings=_settings(),
        calendar=_CalendarGatewayMessageRules(),
        todo=todo,
        gmail=_GmailGatewayWithNubank(),
        sheets=_SheetsGateway(),
        segfy=segfy,
        portals=portals,
        whatsapp=whatsapp,
        email_sender=email_sender,
        dashboard_builder=_DashboardBuilder(),
    )

    monkeypatch.setenv("MESSAGE_DISPATCH_STATE_PATH", str(tmp_path / "dispatch_state.json"))
    monkeypatch.setenv("CORRETORA_NOTIFY_EMAIL_TO", "corretora@pbseg.com")

    processor.run(today=date(2026, 4, 3), dry_run=False)
    assert len(whatsapp.sent) == 3
    assert len(email_sender.sent) == 1
    assert "Aviso Nubank" in email_sender.sent[0][1]

    # Segundo ciclo igual nao deve reenviar mensagens ja disparadas.
    processor.run(today=date(2026, 4, 3), dry_run=False)
    assert len(whatsapp.sent) == 3
    assert len(email_sender.sent) == 1
