from __future__ import annotations

from difflib import SequenceMatcher
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
import re
import unicodedata

from rpa_corretora.config import RenewalSettings
from rpa_corretora.domain.models import (
    Alert,
    CalendarCommitment,
    CashflowEntry,
    EmailMessage,
    FollowupRecord,
    PolicyRecord,
    PortalPolicyData,
    SegfyPolicyData,
    TodoTask,
)


CONCLUSIVE_STATUSES = {"CONCLUIDO", "CONCLUIDA", "RENOVADO", "FINALIZADO"}
AMOUNT_PATTERN = re.compile(r"R\$\s*([0-9\.,]+)")
DATE_PATTERN = re.compile(r"(\d{2}/\d{2}/\d{4})")
INSURER_PATTERN = re.compile(r"seguradora\s*:\s*([a-zA-Z\s]+)", re.IGNORECASE)
NON_ALNUM_PATTERN = re.compile(r"[^A-Z0-9 ]+")
NAME_STOPWORDS = {"DA", "DE", "DO", "DAS", "DOS", "E"}


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    only_ascii = normalized.encode("ascii", "ignore").decode("ascii")
    return only_ascii.strip().upper()


def _normalize_name(value: str) -> str:
    base = _normalize(value)
    base = NON_ALNUM_PATTERN.sub(" ", base)
    tokens = [token for token in base.split() if token and token not in NAME_STOPWORDS]
    return " ".join(tokens)


def _name_similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, left, right).ratio()


def _resolve_policy_match(
    insured_name: str,
    policy_exact_map: dict[str, PolicyRecord],
    policy_candidates: list[tuple[str, PolicyRecord]],
    fuzzy_threshold: float = 0.90,
    min_margin: float = 0.06,
) -> tuple[PolicyRecord | None, str, float, PolicyRecord | None, float]:
    key = _normalize_name(insured_name)
    if key == "":
        return None, "NONE", 0.0, None, 0.0

    exact = policy_exact_map.get(key)
    if exact is not None:
        return exact, "EXACT", 1.0, exact, 1.0

    best_policy: PolicyRecord | None = None
    best_score = 0.0
    second_score = 0.0
    for candidate_key, candidate_policy in policy_candidates:
        score = _name_similarity(key, candidate_key)
        if score > best_score:
            second_score = best_score
            best_score = score
            best_policy = candidate_policy
        elif score > second_score:
            second_score = score

    if best_policy is not None and best_score >= fuzzy_threshold and (best_score - second_score) >= min_margin:
        return best_policy, "FUZZY", best_score, best_policy, best_score

    return None, "NONE", 0.0, best_policy, best_score


def is_blank(value: str | None) -> bool:
    return value is None or value.strip() == ""


def business_day_with_anticipation(target_date: date, holidays: frozenset[date]) -> date:
    adjusted = target_date
    while adjusted.weekday() >= 5 or adjusted in holidays:
        adjusted -= timedelta(days=1)
    return adjusted


def _renewal_trigger_days(policy: PolicyRecord, config: RenewalSettings) -> tuple[int, ...]:
    lead = config.internal_days if policy.renewal_kind == "RENOVACAO_INTERNA" else config.new_days
    return tuple(sorted({lead, *config.reminder_days}, reverse=True))


def _renewal_alert_severity(day_count: int) -> str:
    # A partir de D-10, tratamos como criticidade alta para priorizacao operacional.
    if day_count <= 10:
        return "CRITICA"
    return "ALTA"


def build_renewal_alerts(policy: PolicyRecord, today: date, config: RenewalSettings) -> list[Alert]:
    if policy.renewal_started:
        return []

    alerts: list[Alert] = []
    for day_count in _renewal_trigger_days(policy, config):
        trigger_day = business_day_with_anticipation(policy.vig - timedelta(days=day_count), config.holidays)
        if today == trigger_day:
            alerts.append(
                Alert(
                    code=f"RENOVACAO_D{day_count}",
                    severity=_renewal_alert_severity(day_count),
                    message=(
                        f"Renovacao de {policy.insured_name} ({policy.policy_id}) "
                        f"atingiu D-{day_count} sem inicio de renovacao."
                    ),
                    context={
                        "policy_id": policy.policy_id,
                        "insured_name": policy.insured_name,
                        "renewal_kind": policy.renewal_kind,
                    },
                )
            )
    return alerts


def build_commission_pending_alert(policy: PolicyRecord) -> Alert | None:
    if not is_blank(policy.status_pgto):
        return None
    return Alert(
        code="COMISSAO_PENDENTE",
        severity="ALTA",
        message=(
            f"Comissao pendente para apolice {policy.policy_id} "
            f"({policy.insured_name}) por STATUS PGTO em branco."
        ),
        context={"policy_id": policy.policy_id, "insured_name": policy.insured_name},
    )


def build_incident_alerts(policy: PolicyRecord) -> list[Alert]:
    alerts: list[Alert] = []
    if policy.sinistro_open:
        alerts.append(
            Alert(
                code="SINISTRO_EM_ABERTO",
                severity="MEDIA",
                message=f"Sinistro em aberto para apolice {policy.policy_id}.",
                context={"policy_id": policy.policy_id, "insured_name": policy.insured_name},
            )
        )
    if policy.endosso_open:
        alerts.append(
            Alert(
                code="ENDOSSO_EM_ABERTO",
                severity="MEDIA",
                message=f"Endosso em aberto para apolice {policy.policy_id}.",
                context={"policy_id": policy.policy_id, "insured_name": policy.insured_name},
            )
        )
    return alerts


def build_followup_alerts(followups: list[FollowupRecord], policies: list[PolicyRecord]) -> list[Alert]:
    policy_map: dict[str, PolicyRecord] = {}
    policy_candidates: list[tuple[str, PolicyRecord]] = []
    for policy in policies:
        key = _normalize_name(policy.insured_name)
        if key == "":
            continue
        if key not in policy_map:
            policy_map[key] = policy
        policy_candidates.append((key, policy))

    alerts: list[Alert] = []

    for followup in followups:
        policy, match_method, match_score, suggested_policy, suggested_score = _resolve_policy_match(
            followup.insured_name,
            policy_map,
            policy_candidates,
        )
        if policy is None:
            context = {"insured_name": followup.insured_name, "month": followup.month}
            if suggested_policy is not None and suggested_score >= 0.75:
                context["suggested_policy_id"] = suggested_policy.policy_id
                context["suggested_insured_name"] = suggested_policy.insured_name
                context["suggested_match_score"] = f"{suggested_score:.2f}"
            alerts.append(
                Alert(
                    code="DIVERGENCIA_SEGURADO_NAO_ENCONTRADO",
                    severity="MEDIA",
                    message=(
                        f"Segurado {followup.insured_name} presente no acompanhamento "
                        "e nao encontrado na carteira."
                    ),
                    context=context,
                )
            )
            continue

        base_context = {"policy_id": policy.policy_id, "month": followup.month}
        if match_method == "FUZZY":
            base_context["match_method"] = "FUZZY"
            base_context["match_score"] = f"{match_score:.2f}"

        if is_blank(followup.fase) or is_blank(followup.status):
            alerts.append(
                Alert(
                    code="ACOMPANHAMENTO_EM_ABERTO",
                    severity="MEDIA",
                    message=(
                        f"Acompanhamento de {followup.insured_name} possui FASE/STATUS em aberto "
                        f"({followup.month})."
                    ),
                    context=base_context.copy(),
                )
            )

        status_normalized = _normalize(followup.status)
        if status_normalized in CONCLUSIVE_STATUSES and not policy.renewal_started:
            alerts.append(
                Alert(
                    code="DIVERGENCIA_ACOMPANHAMENTO_CARTEIRA",
                    severity="ALTA",
                    message=(
                        f"Acompanhamento de {followup.insured_name} esta conclusivo, "
                        "mas a carteira indica renovacao nao iniciada."
                    ),
                    context={
                        "policy_id": policy.policy_id,
                        "status": followup.status,
                        **({"match_method": "FUZZY", "match_score": f"{match_score:.2f}"} if match_method == "FUZZY" else {}),
                    },
                )
            )

    return alerts


def build_agenda_pending_alert(commitment: CalendarCommitment, today: date) -> Alert | None:
    if commitment.resolved or commitment.due_date > today:
        return None

    return Alert(
        code="PENDENCIA_AGENDA",
        severity="MEDIA",
        message=f"Compromisso pendente na agenda: {commitment.title}.",
        context={"commitment_id": commitment.id, "color": commitment.color},
    )


def build_todo_pending_alert(task: TodoTask, today: date) -> Alert | None:
    if task.completed or task.due_date > today:
        return None

    return Alert(
        code="PENDENCIA_TODO",
        severity="MEDIA",
        message=f"Tarefa pendente no Microsoft To Do: {task.title}.",
        context={"task_id": task.id},
    )


def is_insurer_email(message: EmailMessage, insurer_domains: tuple[str, ...]) -> bool:
    sender = message.sender.lower()
    return any(domain in sender for domain in insurer_domains)


def parse_brazilian_amount(value: str) -> Decimal | None:
    normalized = value.strip().replace(".", "").replace(",", ".")
    try:
        return Decimal(normalized)
    except (InvalidOperation, ValueError):
        return None


def extract_nubank_cashflow(message: EmailMessage, today: date) -> CashflowEntry | None:
    if "nubank" not in message.sender.lower():
        return None

    content = f"{message.subject}\n{message.body}"
    amount_match = AMOUNT_PATTERN.search(content)
    if amount_match is None:
        return None

    value = parse_brazilian_amount(amount_match.group(1))
    if value is None:
        return None

    date_match = DATE_PATTERN.search(content)
    entry_date = today
    if date_match is not None:
        entry_date = date.fromisoformat("-".join(reversed(date_match.group(1).split("/"))))

    insurer = "Nubank"
    insurer_match = INSURER_PATTERN.search(content)
    if insurer_match is not None:
        insurer = insurer_match.group(1).strip()

    specification = message.subject.strip() or "Extrato Nubank"

    return CashflowEntry(
        date=entry_date,
        value=value,
        insurer=insurer,
        specification=specification,
        source="EMAIL_NUBANK",
    )


def is_renewal_report_email(message: EmailMessage) -> bool:
    normalized_subject = _normalize(message.subject)
    return "RELATORIO DE RENOVACAO" in normalized_subject


def build_renewal_report_alert(message: EmailMessage, today: date) -> Alert | None:
    if today.day != 20 or not is_renewal_report_email(message):
        return None

    return Alert(
        code="RELATORIO_RENOVACAO_RECEBIDO",
        severity="BAIXA",
        message="Relatorio de renovacao do dia 20 recebido e pronto para processamento.",
        context={"email_id": message.id, "sender": message.sender},
    )


def build_segfy_portal_alerts(
    segfy_data: list[SegfyPolicyData],
    portal_data: list[PortalPolicyData],
    tolerance: Decimal = Decimal("0.01"),
) -> list[Alert]:
    portal_map = {item.policy_id: item for item in portal_data}
    alerts: list[Alert] = []

    for segfy in segfy_data:
        portal = portal_map.get(segfy.policy_id)
        if portal is None:
            alerts.append(
                Alert(
                    code="PORTAL_SEM_DADOS",
                    severity="MEDIA",
                    message=f"Apolice {segfy.policy_id} sem retorno de dados no portal da seguradora.",
                    context={"policy_id": segfy.policy_id},
                )
            )
            continue

        premio_diff = abs(segfy.premio_total - portal.premio_total)
        comissao_diff = abs(segfy.comissao - portal.comissao)
        if premio_diff > tolerance or comissao_diff > tolerance:
            alerts.append(
                Alert(
                    code="INCONSISTENCIA_SEGFY_PORTAL",
                    severity="CRITICA",
                    message=(
                        f"Inconsistencia entre Segfy e portal na apolice {segfy.policy_id} "
                        f"(premio diff={premio_diff}, comissao diff={comissao_diff})."
                    ),
                    context={
                        "policy_id": segfy.policy_id,
                        "premio_diff": str(premio_diff),
                        "comissao_diff": str(comissao_diff),
                    },
                )
            )

    return alerts
