from datetime import date, datetime, timedelta
from decimal import Decimal

from rpa_corretora.config import RenewalSettings
from rpa_corretora.domain.models import CalendarCommitment, CashflowEntry, EmailMessage, FollowupRecord, PolicyRecord, TodoTask
from rpa_corretora.domain.rules import (
    build_commission_pending_alert,
    build_followup_alerts,
    build_nubank_email_alert,
    build_renewal_alerts,
    build_todo_pending_alert,
    business_day_with_anticipation,
    extract_overdue_due_date,
    extract_renewal_vig_date,
    should_send_bank_release_message,
    should_send_overdue_message,
    should_send_renewal_message,
)


def test_commission_pending_when_status_is_blank() -> None:
    policy = PolicyRecord(
        policy_id="PB-1",
        insured_name="Teste",
        insurer="Porto Seguro",
        vig=date(2026, 4, 30),
        status_pgto="",
    )

    alert = build_commission_pending_alert(policy)

    assert alert is not None
    assert alert.code == "COMISSAO_PENDENTE"


def test_internal_renewal_triggers_d30_with_business_day_anticipation() -> None:
    settings = RenewalSettings(
        internal_days=30,
        new_days=15,
        reminder_days=(7, 1),
        holidays=frozenset(),
    )

    today = date(2026, 2, 27)
    policy = PolicyRecord(
        policy_id="PB-2",
        insured_name="Cliente D30",
        insurer="Mapfre",
        vig=date(2026, 3, 31),
        renewal_kind="RENOVACAO_INTERNA",
        renewal_started=False,
    )

    alerts = build_renewal_alerts(policy, today, settings)

    assert any(alert.code == "RENOVACAO_D30" for alert in alerts)


def test_weekend_alert_is_anticipated_to_previous_business_day() -> None:
    weekend_day = date(2026, 3, 28)
    while weekend_day.weekday() < 5:
        weekend_day += timedelta(days=1)

    adjusted = business_day_with_anticipation(weekend_day, frozenset())

    assert adjusted.weekday() == 4
    assert adjusted < weekend_day


def test_renewal_d10_is_critical() -> None:
    settings = RenewalSettings(
        internal_days=30,
        new_days=15,
        reminder_days=(10, 7, 1),
        holidays=frozenset(),
    )
    today = date(2026, 4, 20)
    policy = PolicyRecord(
        policy_id="PB-CRIT",
        insured_name="Cliente Critico",
        insurer="Porto Seguro",
        vig=date(2026, 4, 30),
        renewal_kind="RENOVACAO_INTERNA",
        renewal_started=False,
    )

    alerts = build_renewal_alerts(policy, today, settings)

    d10 = next(alert for alert in alerts if alert.code == "RENOVACAO_D10")
    assert d10.severity == "CRITICA"


def test_followup_fuzzy_match_reduces_false_divergence() -> None:
    policies = [
        PolicyRecord(
            policy_id="PB-FUZZY",
            insured_name="Maria Souza",
            insurer="Allianz",
            vig=date(2026, 5, 30),
        )
    ]
    followups = [
        FollowupRecord(
            insured_name="Maria Soza",
            month="MARCO",
            fase="Contato",
            status="",
        )
    ]

    alerts = build_followup_alerts(followups, policies)

    assert any(alert.code == "ACOMPANHAMENTO_EM_ABERTO" for alert in alerts)
    assert not any(alert.code == "DIVERGENCIA_SEGURADO_NAO_ENCONTRADO" for alert in alerts)
    open_alert = next(alert for alert in alerts if alert.code == "ACOMPANHAMENTO_EM_ABERTO")
    assert open_alert.context.get("policy_id") == "PB-FUZZY"
    assert open_alert.context.get("match_method") == "FUZZY"


def test_followup_unmatched_includes_suggestion_when_close() -> None:
    policies = [
        PolicyRecord(
            policy_id="PB-SUG",
            insured_name="Carolina Mendes",
            insurer="Mapfre",
            vig=date(2026, 5, 30),
        )
    ]
    followups = [
        FollowupRecord(
            insured_name="Carla Mendes",
            month="MARCO",
            fase="Contato",
            status="Em aberto",
        )
    ]

    alerts = build_followup_alerts(followups, policies)
    mismatch = next(alert for alert in alerts if alert.code == "DIVERGENCIA_SEGURADO_NAO_ENCONTRADO")

    assert mismatch.context.get("insured_name") == "Carla Mendes"
    assert mismatch.context.get("suggested_policy_id") == "PB-SUG"


def test_todo_pending_without_due_date_is_high_severity() -> None:
    task = TodoTask(
        id="todo-sem-prazo",
        title="Revisar pendencias operacionais",
        due_date=None,
        completed=False,
    )

    alert = build_todo_pending_alert(task, today=date(2026, 3, 30))

    assert alert is not None
    assert alert.code == "PENDENCIA_TODO_SEM_PRAZO"
    assert alert.severity == "ALTA"


def test_build_nubank_email_alert_registers_context() -> None:
    message = EmailMessage(
        id="msg-nu-1",
        sender="noreply@nubank.com.br",
        subject="Extrato Nubank",
        body="Pagamento recebido",
        received_at=datetime(2026, 4, 2, 10, 0, 0),
    )
    entry = CashflowEntry(
        date=date(2026, 4, 2),
        value=Decimal("149.90"),
        insurer="Nubank",
        specification="Extrato Nubank",
        source="EMAIL_NUBANK",
    )

    alert = build_nubank_email_alert(message, entry)

    assert alert.code == "EMAIL_NUBANK_IDENTIFICADO"
    assert alert.severity == "BAIXA"
    assert "Nubank" in alert.message
    assert alert.context["email_id"] == "msg-nu-1"
    assert alert.context["value"] == "149.90"


def test_should_send_renewal_message_only_d10_with_vig_from_card() -> None:
    commitment = CalendarCommitment(
        id="ag-ren-1",
        title="RENOVACAO - ANA SILVA",
        color="VERDE",
        due_date=date(2026, 4, 1),
        description="Cliente: Ana Silva\nVIG: 15/04/2026",
    )

    assert extract_renewal_vig_date(commitment) == date(2026, 4, 15)
    assert should_send_renewal_message(commitment, date(2026, 4, 5)) is True
    assert should_send_renewal_message(commitment, date(2026, 4, 4)) is False


def test_should_send_overdue_message_only_tangerine_and_gt_5_days() -> None:
    commitment = CalendarCommitment(
        id="ag-atraso-1",
        title="BOLETO VENCIDO - JOAO",
        color="TANGERINA",
        due_date=date(2026, 4, 1),
        description="Parcela em atraso\nVENCIMENTO: 27/03/2026",
    )

    assert extract_overdue_due_date(commitment) == date(2026, 3, 27)
    assert should_send_overdue_message(commitment, date(2026, 4, 1)) is False
    assert should_send_overdue_message(commitment, date(2026, 4, 3)) is True


def test_should_send_bank_release_message_exactly_d2() -> None:
    commitment = CalendarCommitment(
        id="ag-banco-1",
        title="LIBERACAO COBRANCA EM CONTA",
        color="AMARELO",
        due_date=date(2026, 4, 10),
        description="Banco: X\nLiberacao de cobranca em conta corrente",
    )

    assert should_send_bank_release_message(commitment, date(2026, 4, 8)) is True
    assert should_send_bank_release_message(commitment, date(2026, 4, 7)) is False
