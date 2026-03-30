from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from rpa_corretora.config import AppSettings
from rpa_corretora.domain.models import Alert, EmailMessage, RunResult
from rpa_corretora.domain.rules import (
    build_agenda_pending_alert,
    build_commission_pending_alert,
    build_followup_alerts,
    build_incident_alerts,
    build_renewal_alerts,
    build_renewal_report_alert,
    build_segfy_portal_alerts,
    build_todo_pending_alert,
    extract_nubank_cashflow,
    is_insurer_email,
)
from rpa_corretora.integrations.interfaces import (
    CalendarGateway,
    EmailSenderGateway,
    GmailGateway,
    InsurerPortalGateway,
    SegfyGateway,
    SpreadsheetGateway,
    TodoGateway,
    WhatsAppGateway,
)
from rpa_corretora.processing.dashboard import DashboardBuilder
from rpa_corretora.templates.messages import cobranca_parcela_message


@dataclass(slots=True)
class DailyProcessor:
    settings: AppSettings
    calendar: CalendarGateway
    todo: TodoGateway
    gmail: GmailGateway
    sheets: SpreadsheetGateway
    segfy: SegfyGateway
    portals: InsurerPortalGateway
    whatsapp: WhatsAppGateway
    email_sender: EmailSenderGateway
    dashboard_builder: DashboardBuilder

    def run(self, today: date, dry_run: bool = True) -> RunResult:
        commitments = self.calendar.fetch_daily_commitments(today)
        todo_tasks = self.todo.fetch_open_tasks()
        messages = self.gmail.fetch_unread_messages()

        policies = self.sheets.load_policies()
        followups = self.sheets.load_followups(today.year)
        expenses = self.sheets.load_expenses(today.year, today.month)

        insurer_emails: list[EmailMessage] = []
        cashflow_entries = []
        alerts: list[Alert] = []

        for message in messages:
            if is_insurer_email(message, self.settings.insurer_domains):
                insurer_emails.append(message)

            nubank_entry = extract_nubank_cashflow(message, today)
            if nubank_entry is not None:
                cashflow_entries.append(nubank_entry)

            renewal_report_alert = build_renewal_report_alert(message, today)
            if renewal_report_alert is not None:
                alerts.append(renewal_report_alert)

        if cashflow_entries and not dry_run:
            self.sheets.append_cashflow_entries(cashflow_entries)

        for policy in policies:
            commission_alert = build_commission_pending_alert(policy)
            if commission_alert is not None:
                alerts.append(commission_alert)

            alerts.extend(build_renewal_alerts(policy, today, self.settings.renewal))
            alerts.extend(build_incident_alerts(policy))

        alerts.extend(build_followup_alerts(followups, policies))

        for commitment in commitments:
            agenda_alert = build_agenda_pending_alert(commitment, today)
            if agenda_alert is not None:
                alerts.append(agenda_alert)

        for task in todo_tasks:
            todo_alert = build_todo_pending_alert(task, today)
            if todo_alert is not None:
                alerts.append(todo_alert)

        segfy_data = self.segfy.fetch_policy_data()
        portal_data = self.portals.fetch_policy_data([item.policy_id for item in segfy_data])
        alerts.extend(build_segfy_portal_alerts(segfy_data, portal_data))

        if not dry_run:
            self._dispatch_notifications(commitments)

        dashboard = self.dashboard_builder.build(
            policies=policies,
            alerts=alerts,
            cashflow_entries=cashflow_entries,
            expenses=expenses,
        )

        return RunResult(
            run_date=today,
            alerts=alerts,
            dashboard=dashboard,
            cashflow_entries=cashflow_entries,
            insurer_emails=insurer_emails,
        )

    def _dispatch_notifications(self, commitments) -> None:
        for commitment in commitments:
            if commitment.color != "VERMELHO" or commitment.resolved:
                continue
            if not commitment.whatsapp_number:
                continue

            client_name = commitment.client_name or "Cliente"
            message = cobranca_parcela_message(client_name)
            self.whatsapp.send_message(commitment.whatsapp_number, message)
