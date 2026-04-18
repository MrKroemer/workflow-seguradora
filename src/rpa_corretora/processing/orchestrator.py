from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from difflib import SequenceMatcher
import hashlib
import json
import re
import os
import unicodedata
from pathlib import Path

from rpa_corretora.config import AppSettings
from rpa_corretora.domain.models import (
    Alert,
    CalendarCommitment,
    CashflowEntry,
    EmailMessage,
    FollowupRecord,
    PolicyRecord,
    RunResult,
    TodoTask,
)
from rpa_corretora.domain.rules import (
    build_agenda_pending_alert,
    build_commission_pending_alert,
    build_followup_alerts,
    build_nubank_email_alert,
    extract_overdue_due_date,
    extract_renewal_vig_date,
    build_incident_alerts,
    build_renewal_alerts,
    build_renewal_report_alert,
    build_segfy_portal_alerts,
    build_todo_pending_alert,
    extract_expense_from_email,
    extract_nubank_cashflow,
    is_bank_release_commitment,
    is_insurer_email,
    is_renewal_commitment,
    is_tangerine_overdue_commitment,
    should_send_bank_release_message,
    should_send_overdue_message,
    should_send_renewal_message,
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
from rpa_corretora.templates.messages import (
    atraso_boleto_message,
    cobranca_parcela_message,
    liberacao_banco_message,
    renovacao_cliente_message,
)


@dataclass(slots=True)
class NotificationDispatchSummary:
    whatsapp_sent: int = 0
    renewal_messages_sent: int = 0
    overdue_messages_sent: int = 0
    bank_release_messages_sent: int = 0
    segfy_payments: int = 0
    segfy_payment_failures: int = 0
    segfy_payment_failed_ids: list[str] = field(default_factory=list)
    portal_claim_checks: int = 0
    portal_claim_failures: int = 0
    portal_claim_failed_ids: list[str] = field(default_factory=list)
    insured_emails_sent: int = 0
    nubank_notifications_sent: int = 0
    nubank_notifications_skipped: int = 0
    skipped_without_phone: int = 0
    skipped_without_email_target: int = 0
    duplicate_blocked: int = 0
    blocked_alerts: list[Alert] = field(default_factory=list)


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
    _todo_marker_pattern_legacy = re.compile(r"RPA-AGENDA:([A-Za-z0-9_-]+)")
    _todo_marker_pattern_compact = re.compile(r"\bAG:([A-F0-9]{10})\b")
    _phone_pattern = re.compile(r"(?:\+?55)?\s*\(?(\d{2})\)?\s*(9?\d{4})[- ]?(\d{4})")
    _email_pattern = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)

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

    @staticmethod
    def _build_compact_agenda_marker(commitment_id: str) -> str:
        # Compact marker to keep To Do task title readable while preserving a stable id.
        digest = hashlib.sha1(commitment_id.encode("utf-8")).hexdigest().upper()
        return digest[:10]

    @staticmethod
    def _normalize_todo_subject(value: str) -> str:
        normalized = " ".join(str(value or "").split())
        normalized = normalized.strip(" -|;,.")
        if len(normalized) > 72:
            return normalized[:69].rstrip() + "..."
        return normalized

    def _build_todo_subject_from_commitment(self, commitment: CalendarCommitment) -> str:
        if commitment.client_name and commitment.client_name.strip():
            subject = self._normalize_todo_subject(commitment.client_name)
            if subject:
                return subject
        return self._normalize_todo_subject(commitment.title) or "Compromisso da agenda"

    def _build_todo_title_from_commitment(self, commitment: CalendarCommitment) -> str:
        marker = self._build_compact_agenda_marker(commitment.id)
        subject = self._build_todo_subject_from_commitment(commitment)
        return f"{commitment.color} | {subject} | AG:{marker}"

    def _build_todo_notes_from_commitment(self, commitment: CalendarCommitment) -> str:
        pieces = [
            f"Origem: Google Agenda",
            f"Compromisso: {commitment.id}",
            f"Resumo agenda: {commitment.title}",
            f"Cor: {commitment.color}",
            f"Data: {commitment.due_date.isoformat()}",
        ]
        if commitment.client_name:
            pieces.append(f"Cliente: {commitment.client_name}")
        return "\n".join(pieces)

    def _extract_agenda_marker_keys(self, title: str) -> list[str]:
        keys: list[str] = []

        legacy_match = self._todo_marker_pattern_legacy.search(title)
        if legacy_match is not None:
            legacy_value = legacy_match.group(1).strip()
            if legacy_value:
                keys.append(f"id:{legacy_value}")

        compact_match = self._todo_marker_pattern_compact.search(title)
        if compact_match is not None:
            compact_value = compact_match.group(1).strip().upper()
            if compact_value:
                keys.append(f"hash:{compact_value}")

        return keys

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
            for marker_key in self._extract_agenda_marker_keys(str(title)):
                by_agenda_id[marker_key] = task

        for commitment in commitments:
            commitment_id_key = f"id:{commitment.id}"
            commitment_hash_key = f"hash:{self._build_compact_agenda_marker(commitment.id)}"
            existing = by_agenda_id.get(commitment_id_key) or by_agenda_id.get(commitment_hash_key)
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

    def _resolve_contact_from_todo(self, *, client_name: str, todo_tasks: list[TodoTask]) -> tuple[str | None, str | None]:
        target = self._normalize_name(client_name)
        if not target:
            return None, None

        for task in todo_tasks:
            haystack = "\n".join(
                [
                    str(task.title or ""),
                    str(task.external_ref or ""),
                    str(task.contact_email or ""),
                    str(task.contact_phone or ""),
                    str(task.contact_address or ""),
                ]
            )
            haystack_norm = self._normalize_name(haystack)
            if target not in haystack_norm and haystack_norm not in target:
                continue

            phone = task.contact_phone or self._extract_phone(haystack)
            email = task.contact_email or self._extract_email(haystack)
            return phone, email
        return None, None

    @classmethod
    def _extract_phone(cls, text: str) -> str | None:
        match = cls._phone_pattern.search(text)
        if match is None:
            return None
        ddd, first, last = match.groups()
        return f"+55{ddd}{first}{last}"

    @classmethod
    def _extract_email(cls, text: str) -> str | None:
        match = cls._email_pattern.search(text)
        if match is None:
            return None
        return match.group(0).strip()

    def _hydrate_commitments_with_todo_contacts(
        self,
        *,
        commitments: list[CalendarCommitment],
        todo_tasks: list[TodoTask],
    ) -> tuple[int, int]:
        hydrated_phones = 0
        hydrated_emails = 0
        for commitment in commitments:
            client_name = (commitment.client_name or "").strip()
            if not client_name:
                continue
            phone, _email = self._resolve_contact_from_todo(client_name=client_name, todo_tasks=todo_tasks)
            if not commitment.whatsapp_number and phone:
                commitment.whatsapp_number = phone
                hydrated_phones += 1
            if _email:
                hydrated_emails += 1
        return hydrated_phones, hydrated_emails

    def _sync_calendar_from_todo(self, *, todo_tasks: list[TodoTask]) -> tuple[int, int]:
        writer = getattr(self.calendar, "upsert_todo_task_event", None)
        if not callable(writer):
            return 0, 0

        created_or_updated = 0
        failed = 0
        for task in todo_tasks:
            if task.completed:
                continue
            if self._extract_agenda_marker_keys(str(task.title)):
                # Skip tasks that are already mapped from agenda into To Do.
                continue
            if "origem: google agenda" in str(task.external_ref or "").lower():
                # Legacy tasks previously mirrored from agenda may not have marker in title.
                continue
            event_id = writer(task=task)
            if event_id:
                created_or_updated += 1
            else:
                failed += 1
        return created_or_updated, failed

    def _todo_is_writable(self) -> bool:
        return self.todo.__class__.__name__ != "NoopTodoGateway"

    @staticmethod
    def _dispatch_state_path() -> Path:
        raw = (os.getenv("MESSAGE_DISPATCH_STATE_PATH") or "outputs/message_dispatch_state.json").strip()
        return Path(raw or "outputs/message_dispatch_state.json")

    def _load_dispatch_keys(self) -> set[str]:
        path = self._dispatch_state_path()
        if not path.exists():
            return set()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return set()
        keys = payload.get("sent_keys") if isinstance(payload, dict) else None
        if not isinstance(keys, list):
            return set()
        return {str(item).strip() for item in keys if str(item).strip()}

    def _save_dispatch_keys(self, sent_keys: set[str]) -> None:
        path = self._dispatch_state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"sent_keys": sorted(sent_keys)}
        path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")

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
            commitments_with_client = sum(1 for item in commitments if bool(item.client_name))
            if trace is not None:
                trace.complete_stage(
                    "google_calendar",
                    (
                        f"{len(commitments)} compromissos lidos ({unresolved_commitments} pendentes); "
                        f"{commitments_with_client} com cliente identificado."
                    ),
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

        hydrated_phones, hydrated_emails = self._hydrate_commitments_with_todo_contacts(
            commitments=commitments,
            todo_tasks=todo_tasks,
        )

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
        nubank_receipts: list[tuple[EmailMessage, CashflowEntry]] = []
        alerts: list[Alert] = []

        for message in messages:
            if is_insurer_email(message, self.settings.insurer_domains):
                insurer_emails.append(message)

            nubank_entry = extract_nubank_cashflow(message, today)
            if nubank_entry is not None:
                cashflow_entries.append(nubank_entry)
                alerts.append(build_nubank_email_alert(message, nubank_entry))
                nubank_receipts.append((message, nubank_entry))

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
            calendar_upserts, calendar_upsert_failures = self._sync_calendar_from_todo(todo_tasks=todo_tasks)
            if trace is not None:
                if calendar_upsert_failures > 0:
                    trace.add_non_executed_item(
                        item_id="Google Calendar - escrita de eventos",
                        reason=f"{calendar_upsert_failures} tarefa(s) do To Do nao puderam ser sincronizadas para a agenda.",
                        recommended_action="Revisar token/escopo do Google Calendar e repetir o ciclo.",
                    )
                trace.complete_stage(
                    "microsoft_todo",
                    (
                        f"{len(todo_tasks)} tarefas abertas lidas; "
                        f"{todo_sync.created} criadas; {todo_sync.updated} atualizadas; "
                        f"{todo_sync.completed} concluidas; {todo_sync.failed} falhas; "
                        f"{hydrated_phones} contato(s) de telefone reaproveitados do To Do; "
                        f"{hydrated_emails} e-mail(s) detectados; "
                        f"{calendar_upserts} evento(s) enviados para Google Calendar."
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
                notification_summary = self._dispatch_notifications(
                    today=today,
                    commitments=commitments,
                    policies=policies,
                    nubank_receipts=nubank_receipts,
                )
                alerts.extend(notification_summary.blocked_alerts)
                if trace is not None:
                    trace.complete_stage(
                        "whatsapp",
                        (
                            f"{notification_summary.whatsapp_sent} mensagens enviadas; "
                            f"{notification_summary.renewal_messages_sent} de renovacao; "
                            f"{notification_summary.overdue_messages_sent} de atraso; "
                            f"{notification_summary.bank_release_messages_sent} de liberacao bancaria; "
                            f"{notification_summary.nubank_notifications_sent} avisos Nubank para corretora; "
                            f"{notification_summary.skipped_without_phone} sem telefone; "
                            f"{notification_summary.duplicate_blocked} bloqueadas por duplicidade; "
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

        if dry_run and trace is not None:
            for commitment in commitments:
                if commitment.resolved:
                    continue
                if should_send_renewal_message(commitment, today):
                    trace.add_non_executed_item(
                        item_id=f"WhatsApp renovacao {commitment.id}",
                        reason="Dry-run ativo, envio de mensagem de renovacao nao executado.",
                        recommended_action="Executar sem --dry-run para disparar comunicacao de renovacao.",
                    )
                elif should_send_overdue_message(commitment, today):
                    trace.add_non_executed_item(
                        item_id=f"WhatsApp atraso {commitment.id}",
                        reason="Dry-run ativo, envio de lembrete de atraso nao executado.",
                        recommended_action="Executar sem --dry-run para disparar lembrete de boleto/parcela.",
                    )
                elif should_send_bank_release_message(commitment, today):
                    trace.add_non_executed_item(
                        item_id=f"WhatsApp liberacao banco {commitment.id}",
                        reason="Dry-run ativo, envio de aviso de liberacao bancaria nao executado.",
                        recommended_action="Executar sem --dry-run para disparar o informativo bancario.",
                    )

            for message, _entry in nubank_receipts:
                trace.add_non_executed_item(
                    item_id=f"Notificacao Nubank {message.id}",
                    reason="Dry-run ativo, aviso de recebimento Nubank nao executado.",
                    recommended_action="Executar sem --dry-run para enviar o aviso para a corretora.",
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
        *,
        today: date,
        commitments: list[CalendarCommitment],
        policies: list[PolicyRecord],
        nubank_receipts: list[tuple[EmailMessage, CashflowEntry]],
    ) -> NotificationDispatchSummary:
        sent_keys = self._load_dispatch_keys()
        state_dirty = False

        def register_once(key: str) -> bool:
            nonlocal state_dirty
            if key in sent_keys:
                return False
            sent_keys.add(key)
            state_dirty = True
            return True

        insured_notification_email = os.getenv("INSURED_NOTIFY_EMAIL_TO", "").strip()
        corretora_notification_email = (
            os.getenv("CORRETORA_NOTIFY_EMAIL_TO", "").strip()
            or os.getenv("EXECUTION_REPORT_EMAIL_TO", "").strip()
            or insured_notification_email
        )
        summary = NotificationDispatchSummary()

        for commitment in commitments:
            if commitment.resolved:
                continue
            client_name = commitment.client_name or "Cliente"
            has_context = bool((commitment.title or "").strip() or (commitment.description or "").strip())
            if not has_context:
                summary.blocked_alerts.append(
                    Alert(
                        code="DISPARO_BLOQUEADO_SEM_CONTEXTO",
                        severity="MEDIA",
                        message=f"Card {commitment.id} sem contexto textual suficiente para analise.",
                        context={"commitment_id": commitment.id},
                    )
                )
                continue

            if is_renewal_commitment(commitment):
                vig_date = extract_renewal_vig_date(commitment)
                if vig_date is None:
                    summary.blocked_alerts.append(
                        Alert(
                            code="DISPARO_BLOQUEADO_SEM_DADOS",
                            severity="MEDIA",
                            message=f"Card de renovacao sem VIG valida ({commitment.id}).",
                            context={"commitment_id": commitment.id},
                        )
                    )
                    continue
                if should_send_renewal_message(commitment, today):
                    if not commitment.whatsapp_number:
                        summary.skipped_without_phone += 1
                        summary.blocked_alerts.append(
                            Alert(
                                code="DISPARO_BLOQUEADO_SEM_TELEFONE",
                                severity="MEDIA",
                                message=f"Renovacao identificada sem telefone para envio ({commitment.id}).",
                                context={"commitment_id": commitment.id},
                            )
                        )
                        continue
                    dispatch_key = f"whatsapp:renovacao:{commitment.id}:{vig_date.isoformat()}"
                    if not register_once(dispatch_key):
                        summary.duplicate_blocked += 1
                        continue
                    self.whatsapp.send_message(commitment.whatsapp_number, renovacao_cliente_message(client_name))
                    summary.whatsapp_sent += 1
                    summary.renewal_messages_sent += 1
                continue

            if is_tangerine_overdue_commitment(commitment):
                due_date = extract_overdue_due_date(commitment)
                if due_date is None:
                    summary.blocked_alerts.append(
                        Alert(
                            code="DISPARO_BLOQUEADO_SEM_DADOS",
                            severity="MEDIA",
                            message=f"Card tangerina sem data de vencimento valida ({commitment.id}).",
                            context={"commitment_id": commitment.id},
                        )
                    )
                    continue
                if should_send_overdue_message(commitment, today):
                    if not commitment.whatsapp_number:
                        summary.skipped_without_phone += 1
                        summary.blocked_alerts.append(
                            Alert(
                                code="DISPARO_BLOQUEADO_SEM_TELEFONE",
                                severity="MEDIA",
                                message=f"Lembrete de atraso sem telefone para envio ({commitment.id}).",
                                context={"commitment_id": commitment.id},
                            )
                        )
                        continue
                    dispatch_key = f"whatsapp:atraso:{commitment.id}:{due_date.isoformat()}"
                    if not register_once(dispatch_key):
                        summary.duplicate_blocked += 1
                        continue
                    self.whatsapp.send_message(commitment.whatsapp_number, atraso_boleto_message(client_name))
                    summary.whatsapp_sent += 1
                    summary.overdue_messages_sent += 1
                continue

            if is_bank_release_commitment(commitment):
                if should_send_bank_release_message(commitment, today):
                    if not commitment.whatsapp_number:
                        summary.skipped_without_phone += 1
                        summary.blocked_alerts.append(
                            Alert(
                                code="DISPARO_BLOQUEADO_SEM_TELEFONE",
                                severity="MEDIA",
                                message=f"Aviso de liberacao bancaria sem telefone ({commitment.id}).",
                                context={"commitment_id": commitment.id},
                            )
                        )
                        continue
                    dispatch_key = f"whatsapp:liberacao_banco:{commitment.id}:{commitment.due_date.isoformat()}"
                    if not register_once(dispatch_key):
                        summary.duplicate_blocked += 1
                        continue
                    self.whatsapp.send_message(commitment.whatsapp_number, liberacao_banco_message())
                    summary.whatsapp_sent += 1
                    summary.bank_release_messages_sent += 1
                continue

            if commitment.color == "VERMELHO":
                if commitment.whatsapp_number:
                    dispatch_key = f"whatsapp:vermelho:{commitment.id}"
                    if not register_once(dispatch_key):
                        summary.duplicate_blocked += 1
                        continue
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

        for message, entry in nubank_receipts:
            if not corretora_notification_email:
                summary.nubank_notifications_skipped += 1
                summary.blocked_alerts.append(
                    Alert(
                        code="NUBANK_AVISO_BLOQUEADO_SEM_DESTINO",
                        severity="MEDIA",
                        message="E-mail Nubank identificado sem destino configurado para aviso da corretora.",
                        context={"email_id": message.id},
                    )
                )
                continue

            dispatch_key = f"email:nubank_recebimento:{message.id}"
            if not register_once(dispatch_key):
                summary.duplicate_blocked += 1
                continue

            value_brl = format(entry.value, ".2f").replace(".", ",")
            content = (
                "Recebimento identificado no e-mail do Nubank.\n"
                f"Data: {entry.date.isoformat()}\n"
                f"Valor: R$ {value_brl}\n"
                f"Descricao: {entry.specification}\n"
                f"Remetente: {message.sender}\n"
            )
            self.email_sender.send_email(
                recipient=corretora_notification_email,
                subject=f"Aviso Nubank - recebimento ({entry.specification})",
                content=content,
            )
            summary.nubank_notifications_sent += 1

        if state_dirty:
            self._save_dispatch_keys(sent_keys)
        return summary
