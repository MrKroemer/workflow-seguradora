from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
import html

from rpa_corretora.domain.models import DashboardSnapshot


@dataclass(frozen=True, slots=True)
class DashboardMeta:
    run_date: date
    generated_at: datetime
    alerts_total: int
    critical_alerts: int
    insurer_emails: int
    cashflow_entries: int
    using_real_sheets: bool
    todo_mode: str


def _fmt_int(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def _fmt_money_brl(value: str) -> str:
    try:
        amount = Decimal(value)
    except Exception:
        return value

    sign = "-" if amount < 0 else ""
    absolute = abs(amount)
    integer_part = int(absolute)
    decimal_part = int((absolute - integer_part) * 100)
    grouped = f"{integer_part:,}".replace(",", ".")
    return f"{sign}R$ {grouped},{decimal_part:02d}"


def _normalize_label(label: str) -> str:
    normalized = " ".join(label.strip().split())
    return html.escape(normalized)


def _insurers_table_rows(active_by_insurer: dict[str, int]) -> str:
    if not active_by_insurer:
        return "<tr><td colspan='3'>Sem dados de apolices ativas.</td></tr>"

    items = sorted(active_by_insurer.items(), key=lambda item: item[1], reverse=True)
    max_value = max(value for _, value in items) or 1
    rows = []

    for insurer, count in items:
        width = max(6, int((count / max_value) * 100))
        rows.append(
            """
            <tr>
              <td class='cell-insurer'>{insurer}</td>
              <td class='cell-count'>{count}</td>
              <td>
                <div class='bar-track' aria-hidden='true'>
                  <div class='bar-fill' style='width:{width}%;'></div>
                </div>
              </td>
            </tr>
            """.format(
                insurer=_normalize_label(insurer),
                count=_fmt_int(count),
                width=width,
            )
        )

    return "\n".join(rows)


def _renewals_month_rows(renewals_by_month: dict[str, dict[str, int]]) -> str:
    if not renewals_by_month:
        return "<tr><td colspan='4'>Sem dados de renovacao por mes.</td></tr>"

    rows = []
    for month in sorted(renewals_by_month.keys()):
        bucket = renewals_by_month[month]
        concluded = int(bucket.get("concluded", 0))
        open_count = int(bucket.get("open", 0))
        total = concluded + open_count
        rows.append(
            """
            <tr>
              <td>{month}</td>
              <td>{concluded}</td>
              <td>{open_count}</td>
              <td>{total}</td>
            </tr>
            """.format(
                month=_normalize_label(month),
                concluded=_fmt_int(concluded),
                open_count=_fmt_int(open_count),
                total=_fmt_int(total),
            )
        )
    return "\n".join(rows)


def _cashflow_category_rows(cashflow_by_category: dict[str, dict[str, str]]) -> str:
    if not cashflow_by_category:
        return "<tr><td colspan='4'>Sem dados financeiros por categoria.</td></tr>"

    rows = []
    ordered_items = sorted(
        cashflow_by_category.items(),
        key=lambda item: (Decimal(item[1].get("net", "0")), item[0]),
        reverse=True,
    )
    for category, values in ordered_items:
        rows.append(
            """
            <tr>
              <td>{category}</td>
              <td>{cash_in}</td>
              <td>{cash_out}</td>
              <td>{net}</td>
            </tr>
            """.format(
                category=_normalize_label(category),
                cash_in=_fmt_money_brl(values.get("cash_in", "0")),
                cash_out=_fmt_money_brl(values.get("cash_out", "0")),
                net=_fmt_money_brl(values.get("net", "0")),
            )
        )
    return "\n".join(rows)


def _status_badge(todo_mode: str, using_real_sheets: bool) -> str:
    sheets_text = "Planilhas reais" if using_real_sheets else "Planilhas stub"
    todo_text = f"To Do: {html.escape(todo_mode)}"
    return f"<span class='status-badge'>{sheets_text} | {todo_text}</span>"


def render_dashboard_html(snapshot: DashboardSnapshot, meta: DashboardMeta) -> str:
    paid = int(snapshot.commissions.get("paid", 0))
    pending = int(snapshot.commissions.get("pending", 0))
    commissions_total = max(1, paid + pending)
    paid_pct = round((paid / commissions_total) * 100)

    renew_internal = int(snapshot.open_renewals.get("RENOVACAO_INTERNA", 0))
    renew_new = int(snapshot.open_renewals.get("NOVO", 0))

    sinistro = int(snapshot.open_incidents.get("SINISTRO", 0))
    endosso = int(snapshot.open_incidents.get("ENDOSSO", 0))

    cash_in = snapshot.cashflow.get("cash_in", "0")
    cash_out = snapshot.cashflow.get("cash_out", "0")
    cash_net = snapshot.cashflow.get("net", "0")
    renewals_by_month_rows = _renewals_month_rows(snapshot.renewals_by_month)
    cashflow_category_rows = _cashflow_category_rows(snapshot.cashflow_by_category)

    generated_text = meta.generated_at.strftime("%d/%m/%Y %H:%M:%S")
    run_date_text = meta.run_date.strftime("%d/%m/%Y")

    return f"""<!doctype html>
<html lang='pt-BR'>
<head>
  <meta charset='utf-8' />
  <meta name='viewport' content='width=device-width, initial-scale=1' />
  <title>Dashboard RPA Corretora</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&family=Fraunces:opsz,wght@9..144,700&display=swap');

    :root {{
      --bg-0: #f5efe6;
      --bg-1: #f9f4eb;
      --bg-2: #f0e5d5;
      --ink-strong: #1b2a2f;
      --ink-soft: #445b63;
      --teal: #0b7a75;
      --teal-light: #6dc8bf;
      --sun: #f1a208;
      --sun-soft: #ffd27a;
      --danger: #ca3c25;
      --danger-soft: #f8b6aa;
      --card: rgba(255, 255, 255, 0.84);
      --line: rgba(27, 42, 47, 0.14);
      --shadow: 0 16px 40px rgba(11, 38, 44, 0.14);
      --radius: 18px;
    }}

    * {{ box-sizing: border-box; }}

    body {{
      margin: 0;
      font-family: 'Space Grotesk', 'Segoe UI', sans-serif;
      color: var(--ink-strong);
      background:
        radial-gradient(1200px 700px at 85% -10%, rgba(11, 122, 117, 0.16), transparent 60%),
        radial-gradient(1000px 700px at -10% 0%, rgba(241, 162, 8, 0.14), transparent 62%),
        linear-gradient(160deg, var(--bg-0), var(--bg-1) 45%, var(--bg-2));
      min-height: 100dvh;
    }}

    .shell {{
      width: min(1160px, calc(100% - 2rem));
      margin: 1.1rem auto 1.6rem;
      display: grid;
      gap: 1rem;
      animation: fade-up .65s ease-out both;
    }}

    .hero {{
      background: linear-gradient(135deg, rgba(9, 103, 99, 0.92), rgba(17, 64, 72, 0.9));
      border-radius: calc(var(--radius) + 6px);
      color: #f9fffe;
      box-shadow: var(--shadow);
      padding: 1.2rem 1.3rem 1.15rem;
      position: relative;
      overflow: hidden;
    }}

    .hero::after {{
      content: '';
      position: absolute;
      inset: auto -30px -45px auto;
      width: 210px;
      height: 210px;
      border-radius: 50%;
      background: radial-gradient(circle at center, rgba(255, 210, 122, .4), transparent 70%);
      pointer-events: none;
    }}

    .hero h1 {{
      margin: 0;
      font-family: 'Fraunces', Georgia, serif;
      font-size: clamp(1.5rem, 3.4vw, 2.25rem);
      line-height: 1.1;
      letter-spacing: .2px;
    }}

    .hero p {{
      margin: .4rem 0 0;
      color: rgba(244, 254, 252, .9);
      font-size: .95rem;
    }}

    .status-badge {{
      display: inline-flex;
      margin-top: .75rem;
      background: rgba(255, 255, 255, 0.14);
      border: 1px solid rgba(255, 255, 255, 0.3);
      border-radius: 999px;
      padding: .34rem .74rem;
      font-size: .78rem;
      font-weight: 700;
      letter-spacing: .2px;
    }}

    .grid-kpi {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: .8rem;
    }}

    .card {{
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      box-shadow: 0 8px 20px rgba(27, 42, 47, 0.06);
      padding: .9rem 1rem;
      backdrop-filter: blur(2px);
    }}

    .kpi-label {{
      margin: 0;
      font-size: .75rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: .45px;
      color: var(--ink-soft);
    }}

    .kpi-value {{
      margin: .18rem 0 0;
      font-size: clamp(1.25rem, 2.6vw, 1.95rem);
      font-weight: 700;
      line-height: 1.1;
    }}

    .kpi-support {{
      margin-top: .28rem;
      font-size: .78rem;
      color: #4d676f;
    }}

    .kpi-critical .kpi-value {{ color: var(--danger); }}
    .kpi-positive .kpi-value {{ color: var(--teal); }}

    .panel-grid {{
      display: grid;
      grid-template-columns: 1.35fr 1fr;
      gap: .8rem;
    }}

    .panel-title {{
      margin: 0 0 .72rem;
      font-size: .95rem;
      font-weight: 700;
      letter-spacing: .2px;
      color: var(--ink-strong);
    }}

    .table {{
      width: 100%;
      border-collapse: collapse;
      font-size: .83rem;
    }}

    .table th,
    .table td {{
      padding: .44rem .25rem;
      border-bottom: 1px dashed rgba(27, 42, 47, 0.12);
      text-align: left;
      vertical-align: middle;
    }}

    .table th {{
      color: var(--ink-soft);
      font-size: .72rem;
      text-transform: uppercase;
      letter-spacing: .34px;
      font-weight: 700;
    }}

    .cell-insurer {{ font-weight: 600; }}
    .cell-count {{ font-weight: 700; width: 68px; }}

    .bar-track {{
      width: 100%;
      height: 9px;
      border-radius: 999px;
      background: rgba(11, 122, 117, 0.14);
      overflow: hidden;
    }}

    .bar-fill {{
      height: 100%;
      border-radius: 999px;
      background: linear-gradient(90deg, var(--teal), var(--teal-light));
      animation: grow .7s ease-out both;
      transform-origin: left;
    }}

    .stack {{
      display: grid;
      gap: .65rem;
    }}

    .pill {{
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: .58rem .72rem;
      background: rgba(255, 255, 255, 0.66);
    }}

    .pill-head {{
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      gap: .6rem;
    }}

    .pill-title {{
      margin: 0;
      font-size: .76rem;
      font-weight: 700;
      text-transform: uppercase;
      color: var(--ink-soft);
      letter-spacing: .3px;
    }}

    .pill-value {{
      margin: 0;
      font-size: 1.08rem;
      font-weight: 700;
    }}

    .meter {{
      margin-top: .4rem;
      height: 9px;
      border-radius: 999px;
      background: rgba(27, 42, 47, 0.1);
      overflow: hidden;
    }}

    .meter span {{
      display: block;
      height: 100%;
      background: linear-gradient(90deg, var(--sun), var(--sun-soft));
      border-radius: 999px;
      animation: grow .72s ease-out both;
      transform-origin: left;
    }}

    .footer {{
      text-align: right;
      font-size: .75rem;
      color: #536d75;
      padding: .2rem .2rem 0;
    }}

    @keyframes grow {{
      from {{ transform: scaleX(0); opacity: .6; }}
      to {{ transform: scaleX(1); opacity: 1; }}
    }}

    @keyframes fade-up {{
      from {{ transform: translateY(12px); opacity: 0; }}
      to {{ transform: translateY(0); opacity: 1; }}
    }}

    @media (max-width: 1024px) {{
      .grid-kpi {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .panel-grid {{ grid-template-columns: 1fr; }}
    }}

    @media (max-width: 640px) {{
      .shell {{ width: min(1160px, calc(100% - 1rem)); gap: .72rem; }}
      .hero {{ padding: 1rem .9rem; }}
      .grid-kpi {{ gap: .6rem; }}
      .card {{ padding: .8rem .82rem; border-radius: 14px; }}
      .kpi-value {{ font-size: 1.36rem; }}
      .table th:nth-child(3),
      .table td:nth-child(3) {{ display: none; }}
    }}
  </style>
</head>
<body>
  <main class='shell'>
    <section class='hero'>
      <h1>Painel Operacional da Corretora</h1>
      <p>Execucao de {run_date_text} com consolidacao automatica de carteira, alertas e financeiro.</p>
      {_status_badge(meta.todo_mode, meta.using_real_sheets)}
    </section>

    <section class='grid-kpi'>
      <article class='card kpi-critical'>
        <p class='kpi-label'>Alertas Criticos</p>
        <p class='kpi-value'>{_fmt_int(meta.critical_alerts)}</p>
        <p class='kpi-support'>Total de alertas: {_fmt_int(meta.alerts_total)}</p>
      </article>

      <article class='card'>
        <p class='kpi-label'>Comissoes Pendentes</p>
        <p class='kpi-value'>{_fmt_int(pending)}</p>
        <p class='kpi-support'>Pagas: {_fmt_int(paid)} ({paid_pct}% de regularidade)</p>
      </article>

      <article class='card kpi-positive'>
        <p class='kpi-label'>Saldo do Mes</p>
        <p class='kpi-value'>{_fmt_money_brl(cash_net)}</p>
        <p class='kpi-support'>Entradas: {_fmt_money_brl(cash_in)} | Saidas: {_fmt_money_brl(cash_out)}</p>
      </article>

      <article class='card'>
        <p class='kpi-label'>Renovacoes em Aberto</p>
        <p class='kpi-value'>{_fmt_int(renew_internal + renew_new)}</p>
        <p class='kpi-support'>Internas: {_fmt_int(renew_internal)} | Novos: {_fmt_int(renew_new)}</p>
      </article>
    </section>

    <section class='panel-grid'>
      <article class='card'>
        <h2 class='panel-title'>Apolices Ativas por Seguradora</h2>
        <table class='table' role='table' aria-label='Apolices ativas por seguradora'>
          <thead>
            <tr>
              <th>Seguradora</th>
              <th>Total</th>
              <th>Distribuicao</th>
            </tr>
          </thead>
          <tbody>
            {_insurers_table_rows(snapshot.active_policies_by_insurer)}
          </tbody>
        </table>
      </article>

      <article class='card'>
        <h2 class='panel-title'>Leituras-Chave da Execucao</h2>
        <div class='stack'>
          <div class='pill'>
            <div class='pill-head'>
              <p class='pill-title'>Comissoes Pagas</p>
              <p class='pill-value'>{_fmt_int(paid)}</p>
            </div>
            <div class='meter'><span style='width:{paid_pct}%;'></span></div>
          </div>

          <div class='pill'>
            <div class='pill-head'>
              <p class='pill-title'>Sinistros em Aberto</p>
              <p class='pill-value'>{_fmt_int(sinistro)}</p>
            </div>
          </div>

          <div class='pill'>
            <div class='pill-head'>
              <p class='pill-title'>Endossos em Aberto</p>
              <p class='pill-value'>{_fmt_int(endosso)}</p>
            </div>
          </div>

          <div class='pill'>
            <div class='pill-head'>
              <p class='pill-title'>E-mails de Seguradoras</p>
              <p class='pill-value'>{_fmt_int(meta.insurer_emails)}</p>
            </div>
          </div>

          <div class='pill'>
            <div class='pill-head'>
              <p class='pill-title'>Lancamentos Financeiros</p>
              <p class='pill-value'>{_fmt_int(meta.cashflow_entries)}</p>
            </div>
          </div>
        </div>
      </article>
    </section>

    <section class='panel-grid'>
      <article class='card'>
        <h2 class='panel-title'>Renovacoes Concluidas vs Em Aberto (Por Mes)</h2>
        <table class='table' role='table' aria-label='Renovacoes por mes'>
          <thead>
            <tr>
              <th>Mes</th>
              <th>Concluidas</th>
              <th>Em Aberto</th>
              <th>Total</th>
            </tr>
          </thead>
          <tbody>
            {renewals_by_month_rows}
          </tbody>
        </table>
      </article>

      <article class='card'>
        <h2 class='panel-title'>Fluxo de Caixa por Categoria</h2>
        <table class='table' role='table' aria-label='Fluxo por categoria'>
          <thead>
            <tr>
              <th>Categoria</th>
              <th>Entradas</th>
              <th>Saidas</th>
              <th>Saldo</th>
            </tr>
          </thead>
          <tbody>
            {cashflow_category_rows}
          </tbody>
        </table>
      </article>
    </section>

    <p class='footer'>Gerado em {generated_text}</p>
  </main>
</body>
</html>
"""


def write_dashboard_html(snapshot: DashboardSnapshot, meta: DashboardMeta, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_dashboard_html(snapshot, meta), encoding="utf-8")
    return path
