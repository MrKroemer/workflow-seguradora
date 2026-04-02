from __future__ import annotations

from datetime import date
from pathlib import Path
import json

from rpa_corretora.domain.models import CalendarCommitment, EmailMessage, TodoTask


class NoopCalendarGateway:
    def fetch_daily_commitments(self, day: date) -> list[CalendarCommitment]:
        _ = day
        return []


class NoopTodoGateway:
    def fetch_open_tasks(self) -> list[TodoTask]:
        return []

    def create_task(
        self,
        *,
        title: str,
        due_date: date | None = None,
        notes: str | None = None,
    ) -> str | None:
        _ = (title, due_date, notes)
        return None

    def update_task(
        self,
        *,
        task_id: str,
        title: str | None = None,
        due_date: date | None = None,
        notes: str | None = None,
    ) -> bool:
        _ = (task_id, title, due_date, notes)
        return False

    def complete_task(self, *, task_id: str) -> bool:
        _ = task_id
        return False


class NoopGmailGateway:
    def fetch_unread_messages(self) -> list[EmailMessage]:
        return []


class FileOutboxWhatsAppGateway:
    def __init__(self, output_path: str | Path = "outputs/whatsapp_outbox.jsonl") -> None:
        self.output_path = Path(output_path)

    def send_message(self, phone: str, content: str) -> None:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "phone": phone,
            "content": content,
        }
        with self.output_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(payload) + "\n")


class FileOutboxEmailSenderGateway:
    def __init__(self, output_path: str | Path = "outputs/email_outbox.jsonl") -> None:
        self.output_path = Path(output_path)

    def send_email(
        self,
        recipient: str,
        subject: str,
        content: str,
        attachments: list[str | Path] | None = None,
    ) -> None:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "recipient": recipient,
            "subject": subject,
            "content": content,
            "attachments": [str(item) for item in attachments or []],
        }
        with self.output_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(payload) + "\n")
