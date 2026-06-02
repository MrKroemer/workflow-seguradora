from datetime import date, datetime

from rpa_corretora.domain.models import DashboardSnapshot
from rpa_corretora.processing.dashboard_web import DashboardMeta, render_dashboard_html, write_dashboard_html


def _sample_snapshot() -> DashboardSnapshot:
    return DashboardSnapshot(
        active_policies_by_insurer={"PORTO": 12, "MAPFRE": 9},
        commissions={"paid": 10, "pending": 2},
        open_renewals={"RENOVACAO_INTERNA": 8, "NOVO": 3},
        open_incidents={"SINISTRO": 1, "ENDOSSO": 2},
        cashflow={"cash_in": "2500.00", "cash_out": "1000.00", "net": "1500.00"},
        critical_alerts=7,
    )


def _sample_meta() -> DashboardMeta:
    return DashboardMeta(
        run_date=date(2026, 3, 27),
        generated_at=datetime(2026, 3, 27, 10, 30, 0),
        alerts_total=18,
        critical_alerts=7,
        insurer_emails=4,
        cashflow_entries=3,
        using_real_sheets=True,
        todo_mode="GRAPH",
    )


def test_render_dashboard_html_contains_core_values() -> None:
    html = render_dashboard_html(_sample_snapshot(), _sample_meta())

    assert "Painel Operacional da Corretora" in html
    assert "R$ 1.500,00" in html
    assert "To Do: GRAPH" in html
    assert "PORTO" in html


def test_write_dashboard_html_creates_file(tmp_path) -> None:
    output = tmp_path / "dashboard.html"

    written = write_dashboard_html(_sample_snapshot(), _sample_meta(), output)

    assert written == output
    assert output.exists()
    content = output.read_text(encoding="utf-8")
    assert "Dashboard RPA Corretora" in content
