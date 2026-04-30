from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
import re
from typing import Literal
import unicodedata

from rpa_corretora.config import RenewalSettings
from rpa_corretora.domain.models import (
    Alert,
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


CONCLUSIVE_STATUSES = {"CONCLUIDO", "CONCLUIDA", "RENOVADO", "FINALIZADO"}
AMOUNT_PATTERN = re.compile(r"R\$\s*([0-9\.,]+)")
DATE_PATTERN = re.compile(r"(\d{2}/\d{2}/\d{4})")
INSURER_PATTERN = re.compile(r"seguradora\s*:\s*([a-zA-Z\s]+)", re.IGNORECASE)
PARCELA_PATTERN = re.compile(r"(?:parcela|parc\.?)\s*(\d+)\s*(?:/|de)\s*(\d+)", re.IGNORECASE)
VEHICLE_PATTERN = re.compile(
    r"(?:veiculo|veículo|carro|auto|modelo)\s*[:=\-]?\s*([A-Za-zÀ-ÿ0-9 /]+)",
    re.IGNORECASE,
)
PLATE_PATTERN = re.compile(r"\b([A-Z]{3}[0-9][A-Z0-9][0-9]{2})\b")
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
    if task.completed:
        return None

    if task.due_date is None:
        return Alert(
            code="PENDENCIA_TODO_SEM_PRAZO",
            severity="ALTA",
            message=f"Tarefa pendente no Microsoft To Do sem prazo definido: {task.title}.",
            context={"task_id": task.id},
        )

    if task.due_date > today:
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


def build_nubank_email_alert(message: EmailMessage, entry: CashflowEntry) -> Alert:
    value_brl = format(entry.value, ".2f").replace(".", ",")
    return Alert(
        code="EMAIL_NUBANK_IDENTIFICADO",
        severity="BAIXA",
        message=f"E-mail do Nubank identificado: {entry.specification} (R$ {value_brl}).",
        context={
            "email_id": message.id,
            "sender": message.sender,
            "date": entry.date.isoformat(),
            "value": str(entry.value),
            "specification": entry.specification,
        },
    )


def _extract_expense_category(content: str) -> str:
    category_match = re.search(r"categoria\s*:\s*([A-Za-zÀ-ÿ ]+)", content, re.IGNORECASE)
    if category_match is not None:
        category = _normalize(category_match.group(1))
        return category or "CORRETORA"

    hints = {
        "MERCADO": ("mercado", "supermercado", "atacadao", "carrefour"),
        "TRANSPORTE": ("uber", "99", "combustivel", "gasolina", "diesel", "posto"),
        "LAZER": ("cinema", "show", "streaming", "netflix", "spotify"),
        "MORADIA": ("aluguel", "energia", "agua", "internet", "condominio"),
        "ANIMAIS": ("pet", "veterin", "racao"),
        "SAUDE E BELEZA": ("farmacia", "hospital", "clinica", "salon", "barbearia"),
    }
    lowered = content.lower()
    for category, tokens in hints.items():
        if any(token in lowered for token in tokens):
            return category
    return "CORRETORA"


def extract_expense_from_email(message: EmailMessage, today: date) -> ExpenseEntry | None:
    if "nubank" not in message.sender.lower():
        return None

    content = f"{message.subject}\n{message.body}"
    lowered = content.lower()
    if not any(token in lowered for token in ("gasto", "debito", "débito", "compra", "pagamento")):
        return None

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

    return ExpenseEntry(
        date=entry_date,
        value=value,
        description=message.subject.strip() or "Despesa identificada por e-mail",
        category=_extract_expense_category(content),
    )


def is_renewal_report_email(message: EmailMessage) -> bool:
    normalized_subject = _normalize(message.subject)
    return "RELATORIO DE RENOVACAO" in normalized_subject


def _commitment_text(commitment: CalendarCommitment) -> str:
    return f"{commitment.title}\n{commitment.description or ''}"


def _extract_labeled_date(text: str, labels: tuple[str, ...]) -> date | None:
    labels_pattern = "|".join(re.escape(label) for label in labels)
    pattern = re.compile(
        rf"(?:{labels_pattern})\s*[:=\-]?\s*(\d{{2}}/\d{{2}}/\d{{4}}|\d{{4}}-\d{{2}}-\d{{2}})",
        re.IGNORECASE,
    )
    match = pattern.search(text)
    if match is None:
        return None
    raw = match.group(1).strip()
    if "/" in raw:
        try:
            return date.fromisoformat("-".join(reversed(raw.split("/"))))
        except ValueError:
            return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def is_renewal_commitment(commitment: CalendarCommitment) -> bool:
    # Classificacao primaria por conteudo textual completo.
    if is_renewal_commitment_by_content(commitment):
        return True
    # Fallback legado por palavra-chave direta.
    normalized = _normalize(_commitment_text(commitment))
    return "RENOVACAO" in normalized


def extract_renewal_vig_date(commitment: CalendarCommitment) -> date | None:
    text = _commitment_text(commitment)
    labeled = _extract_labeled_date(text, ("VIG", "VIGENCIA", "VIGENCIA FINAL", "DATA VIGENCIA"))
    if labeled is not None:
        return labeled
    return None


def should_send_renewal_message(commitment: CalendarCommitment, today: date) -> bool:
    if not is_renewal_commitment(commitment):
        return False
    vig_date = extract_renewal_vig_date(commitment)
    if vig_date is None:
        return False
    return today == (vig_date - timedelta(days=10))


def is_tangerine_overdue_commitment(commitment: CalendarCommitment) -> bool:
    # A cor tangerina e o indicador primario de roteamento para o fluxo de atraso.
    # O classificador de conteudo valida e enriquece, mas nao substitui a cor
    # como roteador de acao no orquestrador (VERMELHO tem fluxo proprio).
    if commitment.color != "TANGERINA":
        return False
    # Qualquer card tangerina com conteudo minimo e tratado como cobranca.
    normalized = _normalize(_commitment_text(commitment))
    return len(normalized.strip()) >= 4


def extract_overdue_due_date(commitment: CalendarCommitment) -> date | None:
    text = _commitment_text(commitment)
    labeled = _extract_labeled_date(
        text,
        ("VENCIMENTO", "VENC", "VCTO", "DATA VENCIMENTO", "VENCE", "DATA", "DT"),
    )
    if labeled is not None:
        return labeled
    # Tenta extrair qualquer data no texto do compromisso.
    date_match = DATE_PATTERN.search(text)
    if date_match is not None:
        try:
            return date.fromisoformat("-".join(reversed(date_match.group(1).split("/"))))
        except ValueError:
            pass
    # Fallback: usa a data do proprio compromisso na agenda.
    return commitment.due_date


def should_send_overdue_message(commitment: CalendarCommitment, today: date) -> bool:
    if not is_tangerine_overdue_commitment(commitment):
        return False
    due_date = extract_overdue_due_date(commitment)
    if due_date is None:
        return False
    days_overdue = (today - due_date).days
    return days_overdue > 5


def is_bank_release_commitment(commitment: CalendarCommitment) -> bool:
    if commitment.color != "AMARELO":
        return False
    normalized = _normalize(_commitment_text(commitment))
    has_release = "LIBERACAO" in normalized or "LIBERAR" in normalized
    has_bank_context = "COBRANCA" in normalized or "CONTA CORRENTE" in normalized or "BANCO" in normalized
    return has_release and has_bank_context


def should_send_bank_release_message(commitment: CalendarCommitment, today: date) -> bool:
    if not is_bank_release_commitment(commitment):
        return False
    return today == (commitment.due_date - timedelta(days=2))


def build_renewal_report_alert(message: EmailMessage, today: date) -> Alert | None:
    if today.day != 20 or not is_renewal_report_email(message):
        return None

    return Alert(
        code="RELATORIO_RENOVACAO_RECEBIDO",
        severity="BAIXA",
        message="Relatorio de renovacao do dia 20 recebido e pronto para processamento.",
        context={"email_id": message.id, "sender": message.sender},
    )


@dataclass(slots=True)
class CommitmentDetails:
    client_name: str = ""
    insurer: str = ""
    vehicle: str = ""
    plate: str = ""
    amount: Decimal | None = None
    parcela_current: int | None = None
    parcela_total: int | None = None
    due_date: date | None = None
    vig_date: date | None = None


def extract_commitment_details(commitment: CalendarCommitment) -> CommitmentDetails:
    text = _commitment_text(commitment)
    normalized = _normalize(text)
    details = CommitmentDetails()
    details.client_name = commitment.client_name or ""

    insurer_match = INSURER_PATTERN.search(text)
    if insurer_match:
        details.insurer = insurer_match.group(1).strip()
    else:
        known_insurers = (
            "YELUM", "PORTO", "MAPFRE", "BRADESCO", "ALLIANZ", "SUHAI",
            "TOKIO", "HDI", "AZUL", "ITAU", "JUSTOS", "ALIRO",
        )
        for ins in known_insurers:
            if ins in normalized:
                details.insurer = ins
                break

    amount_match = AMOUNT_PATTERN.search(text)
    if amount_match:
        details.amount = parse_brazilian_amount(amount_match.group(1))

    parcela_match = PARCELA_PATTERN.search(text)
    if parcela_match:
        details.parcela_current = int(parcela_match.group(1))
        details.parcela_total = int(parcela_match.group(2))

    vehicle_match = VEHICLE_PATTERN.search(text)
    if vehicle_match:
        details.vehicle = vehicle_match.group(1).strip()

    plate_match = PLATE_PATTERN.search(normalized)
    if plate_match:
        details.plate = plate_match.group(1)

    details.due_date = extract_overdue_due_date(commitment)
    details.vig_date = extract_renewal_vig_date(commitment)
    return details


def enrich_renewal_context(
    commitment: CalendarCommitment,
    policies: list[PolicyRecord],
) -> dict[str, str]:
    details = extract_commitment_details(commitment)
    context: dict[str, str] = {"commitment_id": commitment.id}
    if details.client_name:
        context["client_name"] = details.client_name
    if details.vig_date:
        context["vig_date"] = details.vig_date.isoformat()
    if details.insurer:
        context["insurer"] = details.insurer
    if details.vehicle:
        context["vehicle"] = details.vehicle
    if details.plate:
        context["plate"] = details.plate

    target = _normalize_name(details.client_name)
    if target:
        for policy in policies:
            if _normalize_name(policy.insured_name) == target:
                context["policy_id"] = policy.policy_id
                context["insurer"] = context.get("insurer") or policy.insurer
                context["vehicle"] = context.get("vehicle") or policy.vehicle_model or policy.vehicle_item
                context["plate"] = context.get("plate") or policy.vehicle_plate
                context["premio_total"] = str(policy.premio_total)
                break
    return context


def enrich_overdue_context(commitment: CalendarCommitment) -> dict[str, str]:
    details = extract_commitment_details(commitment)
    context: dict[str, str] = {"commitment_id": commitment.id}
    if details.client_name:
        context["client_name"] = details.client_name
    if details.insurer:
        context["insurer"] = details.insurer
    if details.amount is not None:
        context["amount"] = f"R$ {details.amount:.2f}".replace(".", ",")
    if details.parcela_current is not None and details.parcela_total is not None:
        context["parcela"] = f"{details.parcela_current}/{details.parcela_total}"
    if details.due_date:
        context["due_date"] = details.due_date.isoformat()
    if details.vehicle:
        context["vehicle"] = details.vehicle
    if details.plate:
        context["plate"] = details.plate
    return context


# ---------------------------------------------------------------------------
# Classificacao inteligente de eventos por conteudo textual
# ---------------------------------------------------------------------------
# O robo nao se limita a cores ou marcacoes visuais. Ele le e interpreta o
# conteudo completo de cada card (titulo, descricao, datas, metadados) e
# classifica automaticamente o tipo de evento. Opera com tolerancia a
# variacoes de escrita para garantir robustez com dados manuais.
# ---------------------------------------------------------------------------

CommitmentType = Literal[
    "RENOVACAO",
    "COBRANCA_BOLETO",
    "COBRANCA_PARCELA",
    "SINISTRO",
    "ENDOSSO",
    "LIBERACAO_BANCO",
    "TRATATIVA_GERAL",
    "DESCONHECIDO",
]

_RENEWAL_TOKENS = (
    "RENOVACAO", "RENOVAR", "RENOV", "VIGENCIA", "VIG",
    "PERIODO DE RENOVACAO", "COTACAO DE RENOVACAO",
)
_BILLING_TOKENS = (
    "BOLETO", "PARCELA", "FATURA", "COBRANCA", "PAGAMENTO",
    "DEBITO", "PIX", "PAGAR", "VENCIMENTO", "VENC", "VCTO",
    "ATRAS", "PEND", "DEVEDOR", "INADIMPL", "TITULO",
    "CONTA", "RECEBER", "COBRAR",
)
_SINISTRO_TOKENS = (
    "SINISTRO", "ACIDENTE", "COLISAO", "ROUBO", "FURTO",
    "PERDA TOTAL", "INDENIZACAO", "REGULACAO",
)
_ENDOSSO_TOKENS = (
    "ENDOSSO", "ALTERACAO", "INCLUSAO", "EXCLUSAO",
    "MUDANCA", "TRANSFERENCIA",
)
_BANK_RELEASE_TOKENS = (
    "LIBERACAO", "LIBERAR", "BANCO", "CONTA CORRENTE",
    "INTERNET BANKING", "DEBITO AUTOMATICO",
)


def classify_commitment_type(commitment: CalendarCommitment) -> CommitmentType:
    text = _commitment_text(commitment)
    normalized = _normalize(text)
    if not normalized.strip():
        return "DESCONHECIDO"

    scores: dict[CommitmentType, int] = {
        "RENOVACAO": 0,
        "COBRANCA_BOLETO": 0,
        "COBRANCA_PARCELA": 0,
        "SINISTRO": 0,
        "ENDOSSO": 0,
        "LIBERACAO_BANCO": 0,
    }

    for token in _RENEWAL_TOKENS:
        if token in normalized:
            scores["RENOVACAO"] += 2

    for token in _BILLING_TOKENS:
        if token in normalized:
            if "BOLETO" in normalized or "FATURA" in normalized:
                scores["COBRANCA_BOLETO"] += 2
            else:
                scores["COBRANCA_PARCELA"] += 2

    for token in _SINISTRO_TOKENS:
        if token in normalized:
            scores["SINISTRO"] += 2

    for token in _ENDOSSO_TOKENS:
        if token in normalized:
            scores["ENDOSSO"] += 2

    for token in _BANK_RELEASE_TOKENS:
        if token in normalized:
            scores["LIBERACAO_BANCO"] += 2

    # Cor como sinal secundario (nao determinante, mas reforco)
    color_hints: dict[str, CommitmentType] = {
        "TANGERINA": "COBRANCA_BOLETO",
        "CINZA": "SINISTRO",
        "AMARELO": "LIBERACAO_BANCO",
    }
    hint = color_hints.get(commitment.color)
    if hint and hint in scores:
        scores[hint] += 1

    best_type: CommitmentType = "DESCONHECIDO"
    best_score = 0
    for event_type, score in scores.items():
        if score > best_score:
            best_score = score
            best_type = event_type

    if best_score == 0:
        return "TRATATIVA_GERAL"
    return best_type


def is_billing_commitment_by_content(commitment: CalendarCommitment) -> bool:
    event_type = classify_commitment_type(commitment)
    return event_type in ("COBRANCA_BOLETO", "COBRANCA_PARCELA")


def is_renewal_commitment_by_content(commitment: CalendarCommitment) -> bool:
    return classify_commitment_type(commitment) == "RENOVACAO"


def is_sinistro_commitment_by_content(commitment: CalendarCommitment) -> bool:
    return classify_commitment_type(commitment) == "SINISTRO"


def is_endosso_commitment_by_content(commitment: CalendarCommitment) -> bool:
    return classify_commitment_type(commitment) == "ENDOSSO"


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
