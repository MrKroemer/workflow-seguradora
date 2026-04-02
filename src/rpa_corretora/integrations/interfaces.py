from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Protocol

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


class CalendarGateway(Protocol):
    def fetch_daily_commitments(self, day: date) -> list[CalendarCommitment]:
        ...


class TodoGateway(Protocol):
    def fetch_open_tasks(self) -> list[TodoTask]:
        ...

    def create_task(
        self,
        *,
        title: str,
        due_date: date | None = None,
        notes: str | None = None,
    ) -> str | None:
        ...

    def update_task(
        self,
        *,
        task_id: str,
        title: str | None = None,
        due_date: date | None = None,
        notes: str | None = None,
    ) -> bool:
        ...

    def complete_task(self, *, task_id: str) -> bool:
        ...


class GmailGateway(Protocol):
    def fetch_unread_messages(self) -> list[EmailMessage]:
        ...


class SpreadsheetGateway(Protocol):
    def load_policies(self) -> list[PolicyRecord]:
        ...

    def load_followups(self, year: int) -> list[FollowupRecord]:
        ...

    def load_expenses(self, year: int, month: int) -> list[ExpenseEntry]:
        ...

    def append_cashflow_entries(self, entries: list[CashflowEntry]) -> None:
        ...

    def append_expense_entries(self, entries: list[ExpenseEntry]) -> None:
        ...

    def validate_expense_summary(self, year: int, month: int) -> list[str]:
        ...


class SegfyGateway(Protocol):
    def fetch_policy_data(self) -> list[SegfyPolicyData]:
        ...

    def register_payment(self, *, commitment_id: str, description: str) -> bool:
        ...


class InsurerPortalGateway(Protocol):
    def fetch_policy_data(self, policy_ids: list[str]) -> list[PortalPolicyData]:
        ...

    def check_claim_status(self, *, commitment_id: str, description: str) -> str | None:
        ...


class WhatsAppGateway(Protocol):
    def send_message(self, phone: str, content: str) -> None:
        ...


class EmailSenderGateway(Protocol):
    def send_email(
        self,
        recipient: str,
        subject: str,
        content: str,
        attachments: list[str | Path] | None = None,
    ) -> None:
        ...
