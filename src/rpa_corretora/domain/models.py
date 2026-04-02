from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

CommitmentColor = Literal["VERMELHO", "AZUL", "CINZA", "VERDE"]
Severity = Literal["BAIXA", "MEDIA", "ALTA", "CRITICA"]


@dataclass(slots=True)
class CalendarCommitment:
    id: str
    title: str
    color: CommitmentColor
    due_date: date
    resolved: bool = False
    client_name: str | None = None
    whatsapp_number: str | None = None


@dataclass(slots=True)
class TodoTask:
    id: str
    title: str
    due_date: date | None = None
    completed: bool = False
    list_name: str | None = None
    external_ref: str | None = None
    contact_phone: str | None = None
    contact_email: str | None = None
    contact_address: str | None = None


@dataclass(slots=True)
class EmailMessage:
    id: str
    sender: str
    subject: str
    body: str
    received_at: datetime
    attachments: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PolicyRecord:
    policy_id: str
    insured_name: str
    insurer: str
    vig: date
    renewal_kind: Literal["RENOVACAO_INTERNA", "NOVO"] = "RENOVACAO_INTERNA"
    renewal_started: bool = False
    status_pgto: str = ""
    sinistro_open: bool = False
    endosso_open: bool = False
    premio_total: Decimal = Decimal("0")
    comissao: Decimal = Decimal("0")
    vehicle_item: str = ""
    vehicle_model: str = ""
    vehicle_plate: str = ""


@dataclass(slots=True)
class FollowupRecord:
    insured_name: str
    month: str
    fase: str
    status: str
    renewal_kind: Literal["RENOVACAO_INTERNA", "NOVO"] = "RENOVACAO_INTERNA"


@dataclass(slots=True)
class CashflowEntry:
    date: date
    value: Decimal
    insurer: str
    specification: str
    source: str


@dataclass(slots=True)
class ExpenseEntry:
    date: date
    value: Decimal
    description: str
    category: str


@dataclass(slots=True)
class SegfyPolicyData:
    policy_id: str
    premio_total: Decimal
    comissao: Decimal


@dataclass(slots=True)
class PortalPolicyData:
    policy_id: str
    insurer: str
    premio_total: Decimal
    comissao: Decimal


@dataclass(slots=True)
class Alert:
    code: str
    severity: Severity
    message: str
    context: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class DashboardSnapshot:
    active_policies_by_insurer: dict[str, int]
    commissions: dict[str, int]
    open_renewals: dict[str, int]
    open_incidents: dict[str, int]
    cashflow: dict[str, str]
    critical_alerts: int
    renewals_by_month: dict[str, dict[str, int]] = field(default_factory=dict)
    cashflow_by_category: dict[str, dict[str, str]] = field(default_factory=dict)


@dataclass(slots=True)
class RunResult:
    run_date: date
    alerts: list[Alert]
    dashboard: DashboardSnapshot
    cashflow_entries: list[CashflowEntry]
    insurer_emails: list[EmailMessage]
