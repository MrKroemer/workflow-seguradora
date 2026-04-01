from __future__ import annotations

from collections import Counter
from decimal import Decimal
import unicodedata

from rpa_corretora.domain.models import Alert, CashflowEntry, DashboardSnapshot, ExpenseEntry, FollowupRecord, PolicyRecord


CONCLUSIVE_STATUSES = {"CONCLUIDO", "CONCLUIDA", "RENOVADO", "FINALIZADO"}


def _decimal_to_str(value: Decimal) -> str:
    return f"{value:.2f}"


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return normalized.encode("ascii", "ignore").decode("ascii").strip().upper()


class DashboardBuilder:
    def build(
        self,
        policies: list[PolicyRecord],
        alerts: list[Alert],
        cashflow_entries: list[CashflowEntry],
        expenses: list[ExpenseEntry],
        followups: list[FollowupRecord] | None = None,
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

        renewals_by_month: dict[str, dict[str, int]] = {}
        for followup in followups or []:
            month = _normalize(followup.month) or "SEM_MES"
            month_bucket = renewals_by_month.setdefault(month, {"concluded": 0, "open": 0})
            status = _normalize(followup.status)
            if status in CONCLUSIVE_STATUSES:
                month_bucket["concluded"] += 1
            else:
                month_bucket["open"] += 1

        cashflow_by_category: dict[str, dict[str, Decimal]] = {}
        for entry in cashflow_entries:
            category = _normalize(entry.insurer) or "ENTRADAS"
            bucket = cashflow_by_category.setdefault(
                category,
                {"cash_in": Decimal("0"), "cash_out": Decimal("0"), "net": Decimal("0")},
            )
            bucket["cash_in"] += entry.value

        for expense in expenses:
            category = _normalize(expense.category) or "DESPESAS"
            bucket = cashflow_by_category.setdefault(
                category,
                {"cash_in": Decimal("0"), "cash_out": Decimal("0"), "net": Decimal("0")},
            )
            bucket["cash_out"] += expense.value

        for bucket in cashflow_by_category.values():
            bucket["net"] = bucket["cash_in"] - bucket["cash_out"]

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
            renewals_by_month=renewals_by_month,
            cashflow_by_category={
                category: {
                    "cash_in": _decimal_to_str(values["cash_in"]),
                    "cash_out": _decimal_to_str(values["cash_out"]),
                    "net": _decimal_to_str(values["net"]),
                }
                for category, values in cashflow_by_category.items()
            },
        )
