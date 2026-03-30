from __future__ import annotations

from collections import Counter
from decimal import Decimal

from rpa_corretora.domain.models import Alert, CashflowEntry, DashboardSnapshot, ExpenseEntry, PolicyRecord


def _decimal_to_str(value: Decimal) -> str:
    return f"{value:.2f}"


class DashboardBuilder:
    def build(
        self,
        policies: list[PolicyRecord],
        alerts: list[Alert],
        cashflow_entries: list[CashflowEntry],
        expenses: list[ExpenseEntry],
    ) -> DashboardSnapshot:
        active_by_insurer = Counter(policy.insurer for policy in policies)

        commissions_pending = sum(1 for policy in policies if policy.status_pgto.strip() == "")
        commissions_paid = len(policies) - commissions_pending

        open_renewals = {
            "RENOVACAO_INTERNA": sum(
                1
                for policy in policies
                if policy.renewal_kind == "RENOVACAO_INTERNA" and not policy.renewal_started
            ),
            "NOVO": sum(
                1
                for policy in policies
                if policy.renewal_kind == "NOVO" and not policy.renewal_started
            ),
        }

        incidents = {
            "SINISTRO": sum(1 for policy in policies if policy.sinistro_open),
            "ENDOSSO": sum(1 for policy in policies if policy.endosso_open),
        }

        cash_in = sum((entry.value for entry in cashflow_entries), start=Decimal("0"))
        cash_out = sum((expense.value for expense in expenses), start=Decimal("0"))

        critical_alerts = sum(1 for alert in alerts if alert.severity in {"ALTA", "CRITICA"})

        return DashboardSnapshot(
            active_policies_by_insurer=dict(active_by_insurer),
            commissions={"paid": commissions_paid, "pending": commissions_pending},
            open_renewals=open_renewals,
            open_incidents=incidents,
            cashflow={
                "cash_in": _decimal_to_str(cash_in),
                "cash_out": _decimal_to_str(cash_out),
                "net": _decimal_to_str(cash_in - cash_out),
            },
            critical_alerts=critical_alerts,
        )
