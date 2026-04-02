from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from difflib import SequenceMatcher
import re
import os
import unicodedata

from rpa_corretora.config import AppSettings
from rpa_corretora.domain.models import Alert, CalendarCommitment, EmailMessage, FollowupRecord, PolicyRecord, RunResult, TodoTask
from rpa_corretora.domain.rules import (
    build_agenda_pending_alert,
    build_commission_pending_alert,
    build_followup_alerts,
    build_incident_alerts,
    build_renewal_alerts,
    build_renewal_report_alert,
    build_segfy_portal_alerts,
    build_todo_pending_alert,
    extract_expense_from_email,
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
from rpa_corretora.processing.execution_report import ExecutionTraceCollector
from rpa_corretora.templates.messages import cobranca_parcela_message


@dataclass(slots=True)
class NotificationDispatchSummary:
    whatsapp_sent: int = 0
    segfy_payments: int = 0
    segfy_payment_failures: int = 0
    segfy_payment_failed_ids: list[str] = field(default_factory=list)
    portal_claim_checks: int = 0
    portal_claim_failures: int = 0
    portal_claim_failed_ids: list[str] = field(default_factory=list)
    insured_emails_sent: int = 0
    skipped_without_phone: int = 0
    skipped_without_email_target: int = 0


@dataclass(slots=True)
class TodoSyncSummary:
    created: int = 0
    updated: int = 0
    completed: int = 0
    failed: int = 0


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
    _todo_marker_pattern = re.compile(r"RPA-AGENDA:([A-Za-z0-9_-]+)")

    @staticmethod
    def _normalize_name(value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value)
        return normalized.encode("ascii", "ignore").decode("ascii").upper().strip()

    def _match_policy_by_name(self, insured_name: str, policies: list[PolicyRecord]) -> PolicyRecord | None:
        target = self._normalize_name(insured_name)
        if not target:
            return None

        for policy in policies:
            if self._normalize_name(policy.insured_name) == target:
                return policy

        best_policy: PolicyRecord | None = None
        best_score = 0.0
        for policy in policies:
            score = SequenceMatcher(None, target, self._normalize_name(policy.insured_name)).ratio()
            if score > best_score:
                best_score = score
                best_policy = policy
        if best_policy is not None and best_score >= 0.90:
            return best_policy
        return None

    def _sync_policies_from_followups(self, policies: list[PolicyRecord], followups: list[FollowupRecord]) -> None:
        for followup in followups:
            policy = self._match_policy_by_name(followup.insured_name, policies)
            if policy is None:
                continue
            if followup.renewal_kind == "NOVO":
                policy.renewal_kind = "NOVO"
            if followup.fase.strip() or followup.status.strip():
                policy.renewal_started = True

    def _build_todo_title_from_commitment(self, commitment: CalendarCommitment) -> str:
        return f"RPA-AGENDA:{commitment.id} | {commitment.color} | {commitment.title}"

    def _build_todo_notes_from_commitment(self, commitment: CalendarCommitment) -> str:
        pieces = [
            f"Origem: Google Agenda",
            f"Compromisso: {commitment.id}",
            f"Cor: {commitment.color}",
            f"Data: {commitment.due_date.isoformat()}",
        ]
        if commitment.client_name:
            pieces.append(f"Cliente: {commitment.client_name}")
        return "\n".join(pieces)

    def _extract_agenda_marker(self, title: str) -> str | None:
        match = self._todo_marker_pattern.search(title)
        if match is None:
            return None
        value = match.group(1).strip()
        return value or None

    def _sync_todo_from_calendar(
        self,
        *,
        commitments: list[CalendarCommitment],
        todo_tasks: list[TodoTask],
    ) -> TodoSyncSummary:
        summary = TodoSyncSummary()
        by_agenda_id: dict[str, TodoTask] = {}
        for task in todo_tasks:
            title = getattr(task, "title", "")
            marker = self._extract_agenda_marker(str(title))
            if marker is not None:
                by_agenda_id[marker] = task

        for commitment in commitments:
            existing = by_agenda_id.get(commitment.id)
            if commitment.resolved:
                if existing is None:
                    continue
                task_id = str(getattr(existing, "id", "")).strip()
                if task_id and self.todo.complete_task(task_id=task_id):
                    summary.completed += 1
                else:
                    summary.failed += 1
                continue

            expected_title = self._build_todo_title_from_commitment(commitment)
            expected_notes = self._build_todo_notes_from_commitment(commitment)
            expected_due = commitment.due_date

            if existing is None:
                created_id = self.todo.create_task(
                    title=expected_title,
                    due_date=expected_due,
                    notes=expected_notes,
                )
                if created_id:
                    summary.created += 1
                else:
                    summary.failed += 1
                continue

            task_id = str(getattr(existing, "id", "")).strip()
            if not task_id:
                summary.failed += 1
                continue

            current_title = str(getattr(existing, "title", "")).strip()
            current_due = getattr(existing, "due_date", None)
            if current_title != expected_title or current_due != expected_due:
                updated = self.todo.update_task(
                    task_id=task_id,
                    title=expected_title,
                    due_date=expected_due,
                    notes=expected_notes,
                )
                if updated:
                    summary.updated += 1
                else:
                    summary.failed += 1
        return summary

    def _todo_is_writable(self) -> bool:
        return self.todo.__class__.__name__ != "NoopTodoGateway"

    def run(
        self,
        today: date,
        dry_run: bool = True,
        trace: ExecutionTraceCollector | None = None,
    ) -> RunResult:
        if trace is not None:
            trace.start_stage("google_calendar")
        try:
            commitments = self.calendar.fetch_daily_commitments(today)
            unresolved_commitments = sum(1 for item in commitments if not item.resolved)
            if trace is not None:
                trace.complete_stage(
                    "google_calendar",
                    f"{len(commitments)} compromissos lidos ({unresolved_commitments} pendentes).",
                )
                trace.add_non_executed_item(
                    item_id="Google Calendar - criacao de eventos",
                    reason="Fluxo atual nao possui rotina de criacao automatica de eventos.",
                    recommended_action="Manter criacao manual dos eventos ate mapear regras de escrita.",
                )
        except Exception as exc:
            if trace is not None:
                trace.fail_stage(
                    "google_calendar",
                    exc,
                    context={"acao": "fetch_daily_commitments", "data": today.isoformat()},
                )
            raise

        if trace is not None:
            trace.start_stage("microsoft_todo")
        try:
            todo_tasks = self.todo.fetch_open_tasks()
        except Exception as exc:
            if trace is not None:
                trace.fail_stage("microsoft_todo", exc, context={"acao": "fetch_open_tasks"})
            raise

        if trace is not None:
            trace.start_stage("gmail")
        try:
            messages = self.gmail.fetch_unread_messages()
        except Exception as exc:
            if trace is not None:
                trace.fail_stage("gmail", exc, context={"acao": "fetch_unread_messages"})
            raise

        if trace is not None:
            trace.start_stage("spreadsheets")
        try:
            policies = self.sheets.load_policies()
            followups = self.sheets.load_followups(today.year)
            self._sync_policies_from_followups(policies, followups)
        except Exception as exc:
            if trace is not None:
                trace.fail_stage(
                    "spreadsheets",
                    exc,
                    context={"acao": "load_policies_or_followups", "ano": str(today.year)},
                )
            raise

        insurer_emails: list[EmailMessage] = []
        cashflow_entries = []
        expense_entries = []
        alerts: list[Alert] = []

        for message in messages:
            if is_insurer_email(message, self.settings.insurer_domains):
                insurer_emails.append(message)

            nubank_entry = extract_nubank_cashflow(message, today)
            if nubank_entry is not None:
                cashflow_entries.append(nubank_entry)

            expense_entry = extract_expense_from_email(message, today)
            if expense_entry is not None:
                expense_entries.append(expense_entry)

            renewal_report_alert = build_renewal_report_alert(message, today)
            if renewal_report_alert is not None:
                alerts.append(renewal_report_alert)

        if trace is not None:
            trace.complete_stage(
                "gmail",
                (
                    f"{len(messages)} e-mails lidos; {len(insurer_emails)} classificados como seguradora; "
                    f"{len(cashflow_entries)} entradas e {len(expense_entries)} despesas extraidas."
                ),
            )

        try:
            if cashflow_entries and not dry_run:
                self.sheets.append_cashflow_entries(cashflow_entries)
            if expense_entries and not dry_run:
                self.sheets.append_expense_entries(expense_entries)

            if dry_run and cashflow_entries and trace is not None:
                trace.add_non_executed_item(
                    item_id="Planilhas - aba RENDIMENTO",
                    reason="Dry-run ativo, escrita em planilha foi bloqueada.",
                    recommended_action="Reexecutar o ciclo sem --dry-run para gravar os lancamentos.",
                )
            if dry_run and expense_entries and trace is not None:
                trace.add_non_executed_item(
                    item_id="Planilhas - aba Gastos Mensais",
                    reason="Dry-run ativo, escrita em planilha foi bloqueada.",
                    recommended_action="Reexecutar o ciclo sem --dry-run para gravar as despesas.",
                )

            expenses = self.sheets.load_expenses(today.year, today.month)
            if expense_entries:
                expenses.extend(expense_entries)

            summary_issues = self.sheets.validate_expense_summary(today.year, today.month)
            for issue in summary_issues:
                alerts.append(
                    Alert(
                        code="RESUMO_GASTOS_DIVERGENTE",
                        severity="ALTA",
                        message=issue,
                        context={"month": f"{today.year}-{today.month:02d}"},
                    )
                )

            if trace is not None:
                writes_count = 0 if dry_run else len(cashflow_entries) + len(expense_entries)
                trace.complete_stage(
                    "spreadsheets",
                    (
                        f"{len(policies)} apolices e {len(followups)} acompanhamentos lidos; "
                        f"{writes_count} linhas gravadas; {len(summary_issues)} divergencias no resumo de gastos."
                    ),
                )
        except Exception as exc:
            if trace is not None:
                trace.fail_stage(
                    "spreadsheets",
                    exc,
                    context={"acao": "read_write_validate", "mes": f"{today.year}-{today.month:02d}"},
                )
            raise

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

        if dry_run:
            if trace is not None:
                trace.add_non_executed_item(
                    item_id="Microsoft To Do - sincronizacao agenda",
                    reason="Dry-run ativo, criacao/atualizacao/conclusao de tarefas nao executada.",
                    recommended_action="Executar sem --dry-run para sincronizar o Microsoft To Do.",
                )
                trace.complete_stage("microsoft_todo", f"{len(todo_tasks)} tarefas abertas lidas (sincronizacao pendente).")
        elif not self._todo_is_writable():
            if trace is not None:
                trace.add_non_executed_item(
                    item_id="Microsoft To Do - sincronizacao agenda",
                    reason="Integracao de escrita no Microsoft To Do nao esta configurada.",
                    recommended_action="Definir credenciais Graph ou usuario/senha para automacao web.",
                )
                trace.complete_stage(
                    "microsoft_todo",
                    f"{len(todo_tasks)} tarefas abertas lidas (modo somente leitura).",
                )
        else:
            todo_sync = self._sync_todo_from_calendar(commitments=commitments, todo_tasks=todo_tasks)
            if trace is not None:
                trace.complete_stage(
                    "microsoft_todo",
                    (
                        f"{len(todo_tasks)} tarefas abertas lidas; "
                        f"{todo_sync.created} criadas; {todo_sync.updated} atualizadas; "
                        f"{todo_sync.completed} concluidas; {todo_sync.failed} falhas."
                    ),
                )

        if trace is not None:
            trace.start_stage("segfy")
        imported_documents = 0
        try:
            if not dry_run:
                import_func = getattr(self.segfy, "import_documents", None)
                if callable(import_func):
                    imported_documents = int(import_func() or 0)
            else:
                if trace is not None:
                    trace.add_non_executed_item(
                        item_id="Segfy - importacao de documentos",
                        reason="Dry-run ativo, importacao documental foi bloqueada.",
                        recommended_action="Executar sem --dry-run para importar arquivos no Segfy.",
                    )
            segfy_data = self.segfy.fetch_policy_data()
        except Exception as exc:
            if trace is not None:
                trace.fail_stage("segfy", exc, context={"acao": "fetch_policy_data"})
            raise

        if trace is not None:
            trace.start_stage("insurer_portals")
        try:
            portal_data = self.portals.fetch_policy_data([item.policy_id for item in segfy_data])
            alerts.extend(build_segfy_portal_alerts(segfy_data, portal_data))
        except Exception as exc:
            if trace is not None:
                trace.fail_stage(
                    "insurer_portals",
                    exc,
                    context={"acao": "fetch_policy_data", "total_apolices": str(len(segfy_data))},
                )
            raise

        notification_summary = NotificationDispatchSummary()
        if dry_run:
            if trace is not None:
                trace.ignore_stage(
                    "whatsapp",
                    reason="Dry-run ativo, notificacoes externas foram puladas.",
                    recommended_action="Executar sem --dry-run para enviar notificacoes.",
                    result="Notificacoes nao enviadas por modo dry-run.",
                )
        else:
            if trace is not None:
                trace.start_stage("whatsapp")
            try:
                notification_summary = self._dispatch_notifications(commitments, policies)
                if trace is not None:
                    trace.complete_stage(
                        "whatsapp",
                        (
                            f"{notification_summary.whatsapp_sent} mensagens enviadas; "
                            f"{notification_summary.skipped_without_phone} sem telefone; "
                            f"{notification_summary.insured_emails_sent} e-mails de segurado enviados."
                        ),
                    )
            except Exception as exc:
                if trace is not None:
                    trace.fail_stage("whatsapp", exc, context={"acao": "dispatch_notifications"})
                raise

        for commitment_id in notification_summary.segfy_payment_failed_ids:
            alerts.append(
                Alert(
                    code="SEGFY_BAIXA_FALHOU",
                    severity="CRITICA",
                    message=f"Falha ao registrar baixa de parcela no Segfy ({commitment_id}).",
                    context={"commitment_id": commitment_id},
                )
            )

        for commitment_id in notification_summary.portal_claim_failed_ids:
            alerts.append(
                Alert(
                    code="PORTAL_SINISTRO_CONSULTA_FALHOU",
                    severity="ALTA",
                    message=f"Falha ao consultar status de sinistro no portal ({commitment_id}).",
                    context={"commitment_id": commitment_id},
                )
            )

        blue_pending = [item for item in commitments if not item.resolved and item.color == "AZUL"]
        if dry_run and trace is not None:
            for commitment in blue_pending:
                trace.add_non_executed_item(
                    item_id=f"Segfy pagamento {commitment.id}",
                    reason="Dry-run ativo, baixa de parcela nao executada.",
                    recommended_action="Executar sem --dry-run para registrar baixa no Segfy.",
                )

        gray_pending = [item for item in commitments if not item.resolved and item.color == "CINZA"]
        if dry_run and trace is not None:
            for commitment in gray_pending:
                trace.add_non_executed_item(
                    item_id=f"Portal sinistro {commitment.id}",
                    reason="Dry-run ativo, consulta de sinistro nao executada.",
                    recommended_action="Executar sem --dry-run para consultar status no portal.",
                )

        green_pending = [item for item in commitments if not item.resolved and item.color == "VERDE"]
        if dry_run and trace is not None:
            for commitment in green_pending:
                trace.add_non_executed_item(
                    item_id=f"Gmail resposta {commitment.id}",
                    reason="Dry-run ativo, envio de e-mail operacional nao executado.",
                    recommended_action="Executar sem --dry-run para enviar notificacao por e-mail.",
                )

        if trace is not None:
            trace.complete_stage(
                "segfy",
                (
                    f"{len(segfy_data)} registros consultados; "
                    f"{notification_summary.segfy_payments} baixas registradas; "
                    f"{notification_summary.segfy_payment_failures} falhas de baixa; "
                    f"{imported_documents} documentos importados."
                ),
            )
            trace.complete_stage(
                "insurer_portals",
                (
                    f"{len(portal_data)} registros de apolices retornados; "
                    f"{notification_summary.portal_claim_checks} consultas de sinistro por agenda; "
                    f"{notification_summary.portal_claim_failures} falhas de consulta."
                ),
            )
            if notification_summary.skipped_without_email_target > 0:
                trace.add_non_executed_item(
                    item_id="Gmail resposta de segurados",
                    reason="Endereco INSURED_NOTIFY_EMAIL_TO nao configurado.",
                    recommended_action="Definir INSURED_NOTIFY_EMAIL_TO para habilitar envio automatico.",
                )

        dashboard = self.dashboard_builder.build(
            policies=policies,
            alerts=alerts,
            cashflow_entries=cashflow_entries,
            expenses=expenses,
            followups=followups,
        )

        return RunResult(
            run_date=today,
            alerts=alerts,
            dashboard=dashboard,
            cashflow_entries=cashflow_entries,
            insurer_emails=insurer_emails,
        )

    def _dispatch_notifications(
        self,
        commitments: list[CalendarCommitment],
        policies: list[PolicyRecord],
    ) -> NotificationDispatchSummary:
        insured_notification_email = os.getenv("INSURED_NOTIFY_EMAIL_TO", "").strip()
        summary = NotificationDispatchSummary()

        for commitment in commitments:
            if commitment.resolved:
                continue
            client_name = commitment.client_name or "Cliente"

            if commitment.color == "VERMELHO":
                if commitment.whatsapp_number:
                    message = cobranca_parcela_message(client_name)
                    self.whatsapp.send_message(commitment.whatsapp_number, message)
                    summary.whatsapp_sent += 1
                else:
                    summary.skipped_without_phone += 1
                continue

            if commitment.color == "AZUL":
                payment_ok = self.segfy.register_payment(commitment_id=commitment.id, description=commitment.title)
                if payment_ok:
                    summary.segfy_payments += 1
                else:
                    summary.segfy_payment_failures += 1
                    summary.segfy_payment_failed_ids.append(commitment.id)
                continue

            if commitment.color == "CINZA":
                claim_status = self.portals.check_claim_status(commitment_id=commitment.id, description=commitment.title)
                if claim_status is None:
                    summary.portal_claim_failures += 1
                    summary.portal_claim_failed_ids.append(commitment.id)
                else:
                    summary.portal_claim_checks += 1
                continue

            if commitment.color == "VERDE":
                if not insured_notification_email:
                    summary.skipped_without_email_target += 1
                    continue
                policy = self._match_policy_by_name(client_name, policies)
                if policy is None:
                    body = (
                        f"Segurado(a): {client_name}\n"
                        "Modelo: nao identificado\n"
                        "Placa: nao identificada\n"
                    )
                else:
                    model = policy.vehicle_model or policy.vehicle_item or "nao identificado"
                    plate = policy.vehicle_plate or "nao identificada"
                    body = (
                        f"Segurado(a): {policy.insured_name}\n"
                        f"Modelo: {model}\n"
                        f"Placa: {plate}\n"
                    )
                self.email_sender.send_email(
                    recipient=insured_notification_email,
                    subject=f"Notificacao de segurado - {client_name}",
                    content=body,
                )
                summary.insured_emails_sent += 1
        return summary
