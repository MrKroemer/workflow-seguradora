from __future__ import annotations

from datetime import date
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


class SegfyGateway(Protocol):
    def fetch_policy_data(self) -> list[SegfyPolicyData]:
        ...


class InsurerPortalGateway(Protocol):
    def fetch_policy_data(self, policy_ids: list[str]) -> list[PortalPolicyData]:
        ...


class WhatsAppGateway(Protocol):
    def send_message(self, phone: str, content: str) -> None:
        ...


class EmailSenderGateway(Protocol):
    def send_email(self, recipient: str, subject: str, content: str) -> None:
        ...
