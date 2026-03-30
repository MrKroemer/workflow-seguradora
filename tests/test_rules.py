from datetime import date, timedelta

from rpa_corretora.config import RenewalSettings
from rpa_corretora.domain.models import FollowupRecord, PolicyRecord
from rpa_corretora.domain.rules import (
    build_commission_pending_alert,
    build_followup_alerts,
    build_renewal_alerts,
    business_day_with_anticipation,
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
