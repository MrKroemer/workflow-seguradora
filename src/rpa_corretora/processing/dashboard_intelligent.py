"""Dashboard inteligente com graficos, predicoes e exportacao.

Consulta o banco SQLite operacional e gera HTML interativo com:
- Graficos de todos os tipos (Chart.js)
- Dados cruzados de todas as fontes
- Predicoes e tendencias
- Exportacao XLSX e PDF
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

from rpa_corretora.core import OperationalDatabase


def _query_db(db_path: str | Path) -> dict:
    """Extrai todos os dados necessarios do banco para o dashboard."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    data = {}

    # Apolices por seguradora
    data["policies_by_insurer"] = [
        dict(r) for r in conn.execute(
            "SELECT insurer, COUNT(*) as total, SUM(premio_total) as premio, SUM(comissao) as comissao FROM policies GROUP BY insurer ORDER BY total DESC"
        ).fetchall()
    ]

    # Totais gerais
    row = conn.execute("SELECT COUNT(*) as total, SUM(premio_total) as premio, SUM(comissao) as comissao FROM policies").fetchone()
    data["totals"] = {"policies": row["total"], "premio": row["premio"] or 0, "comissao": row["comissao"] or 0}

    # Comissoes
    data["commissions"] = {
        "paid": conn.execute("SELECT COUNT(*) FROM policies WHERE status_pgto != ''").fetchone()[0],
        "pending": conn.execute("SELECT COUNT(*) FROM policies WHERE status_pgto = ''").fetchone()[0],
    }

    # Sinistros e endossos
    data["incidents"] = {
        "sinistros": conn.execute("SELECT COUNT(*) FROM policies WHERE sinistro_open = 1").fetchone()[0],
        "endossos": conn.execute("SELECT COUNT(*) FROM policies WHERE endosso_open = 1").fetchone()[0],
    }

    # Renovacoes por mes
    data["renewals_by_month"] = [
        dict(r) for r in conn.execute("""
            SELECT month,
                SUM(CASE WHEN status IN ('CONCLUIDO','CONCLUIDA','RENOVADO','FINALIZADO') THEN 1 ELSE 0 END) as concluded,
                SUM(CASE WHEN status NOT IN ('CONCLUIDO','CONCLUIDA','RENOVADO','FINALIZADO') OR status = '' THEN 1 ELSE 0 END) as open
            FROM followups GROUP BY month ORDER BY ROWID
        """).fetchall()
    ]

    # Fluxo de caixa por mes
    data["cashflow_monthly"] = [
        dict(r) for r in conn.execute("""
            SELECT strftime('%Y-%m', entry_date) as month, SUM(value) as total
            FROM cashflow GROUP BY month ORDER BY month
        """).fetchall()
    ]

    # Despesas por categoria
    data["expenses_by_category"] = [
        dict(r) for r in conn.execute(
            "SELECT category, SUM(value) as total FROM expenses WHERE category != '' GROUP BY category ORDER BY total DESC"
        ).fetchall()
    ]

    # Alertas por severidade (ultima execucao)
    last_run = conn.execute("SELECT run_date FROM alerts ORDER BY created_at DESC LIMIT 1").fetchone()
    if last_run:
        data["alerts_by_severity"] = [
            dict(r) for r in conn.execute(
                "SELECT severity, COUNT(*) as total FROM alerts WHERE run_date=? GROUP BY severity",
                (last_run["run_date"],)
            ).fetchall()
        ]
    else:
        data["alerts_by_severity"] = []

    # Historico de execucoes
    data["run_history"] = [
        dict(r) for r in conn.execute(
            "SELECT run_date, status, total_policies, total_alerts, total_emails, total_cashflow, segfy_synced, portal_synced FROM run_history ORDER BY started_at DESC LIMIT 30"
        ).fetchall()
    ]

    # Predicao: apolices vencendo nos proximos 30 dias
    today = date.today()
    future = today + timedelta(days=30)
    data["expiring_soon"] = [
        dict(r) for r in conn.execute(
            "SELECT policy_id, insured_name, insurer, vig, premio_total FROM policies WHERE vig BETWEEN ? AND ? ORDER BY vig",
            (today.isoformat(), future.isoformat())
        ).fetchall()
    ]

    # Predicao: tendencia de comissoes (ultimos 6 meses)
    data["commission_trend"] = [
        dict(r) for r in conn.execute("""
            SELECT strftime('%Y-%m', entry_date) as month, SUM(value) as total
            FROM cashflow WHERE source LIKE '%NUBANK%' OR insurer != ''
            GROUP BY month ORDER BY month DESC LIMIT 6
        """).fetchall()
    ]

    # Top segurados por premio
    data["top_insured"] = [
        dict(r) for r in conn.execute(
            "SELECT insured_name, insurer, premio_total, comissao, vehicle_item FROM policies ORDER BY premio_total DESC LIMIT 15"
        ).fetchall()
    ]

    # Divergencias portal vs planilha
    data["divergences"] = [
        dict(r) for r in conn.execute("""
            SELECT p.policy_id, p.insured_name, p.insurer,
                   p.premio_total as planilha_premio, pd.premio_total as portal_premio,
                   p.comissao as planilha_comissao, pd.comissao as portal_comissao
            FROM policies p
            JOIN portal_data pd ON p.policy_id = pd.policy_id
            WHERE ABS(p.premio_total - pd.premio_total) > 0.01
               OR ABS(p.comissao - pd.comissao) > 0.01
            ORDER BY ABS(p.premio_total - pd.premio_total) DESC LIMIT 20
        """).fetchall()
    ]

    conn.close()
    return data


def generate_intelligent_dashboard(db_path: str | Path = "outputs/rpa_corretora.db", output_path: str | Path = "outputs/dashboard_inteligente.html") -> Path:
    """Gera dashboard HTML inteligente com graficos e exportacao."""
    data = _query_db(db_path)
    html = _render_dashboard_html(data)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return out


def _render_dashboard_html(data: dict) -> str:
    today_str = date.today().strftime("%d/%m/%Y")
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M")
    data_json = json.dumps(data, ensure_ascii=False, default=str)

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dashboard Inteligente - PBSeg Corretora</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/xlsx/0.18.5/xlsx.full.min.js"></script>
<style>
:root {{
    --bg: #0f1419; --surface: #1a2332; --surface2: #243447;
    --accent: #0ea5e9; --accent2: #06b6d4; --success: #10b981;
    --warning: #f59e0b; --danger: #ef4444; --text: #e2e8f0;
    --text-muted: #94a3b8; --border: #334155; --radius: 12px;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: 'Segoe UI', system-ui, sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; }}
.container {{ max-width: 1400px; margin: 0 auto; padding: 1.5rem; }}
.header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 2rem; flex-wrap: wrap; gap: 1rem; }}
.header h1 {{ font-size: 1.8rem; background: linear-gradient(135deg, var(--accent), var(--accent2)); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }}
.header .meta {{ color: var(--text-muted); font-size: 0.85rem; }}
.export-btns {{ display: flex; gap: 0.5rem; }}
.export-btns button {{ padding: 0.5rem 1rem; border: 1px solid var(--border); background: var(--surface); color: var(--text); border-radius: 8px; cursor: pointer; font-size: 0.8rem; transition: all 0.2s; }}
.export-btns button:hover {{ background: var(--accent); border-color: var(--accent); color: #fff; }}
.grid {{ display: grid; gap: 1rem; }}
.grid-4 {{ grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); }}
.grid-2 {{ grid-template-columns: repeat(auto-fit, minmax(400px, 1fr)); }}
.grid-3 {{ grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); }}
.card {{ background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 1.2rem; }}
.card-title {{ font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-muted); margin-bottom: 0.5rem; }}
.kpi {{ font-size: 2rem; font-weight: 700; }}
.kpi-sub {{ font-size: 0.8rem; color: var(--text-muted); margin-top: 0.3rem; }}
.kpi-accent {{ color: var(--accent); }}
.kpi-success {{ color: var(--success); }}
.kpi-warning {{ color: var(--warning); }}
.kpi-danger {{ color: var(--danger); }}
.chart-container {{ position: relative; height: 280px; }}
.table {{ width: 100%; border-collapse: collapse; font-size: 0.8rem; }}
.table th, .table td {{ padding: 0.6rem 0.5rem; text-align: left; border-bottom: 1px solid var(--border); }}
.table th {{ color: var(--text-muted); font-weight: 600; text-transform: uppercase; font-size: 0.7rem; }}
.table tr:hover {{ background: var(--surface2); }}
.badge {{ display: inline-block; padding: 0.2rem 0.5rem; border-radius: 4px; font-size: 0.7rem; font-weight: 600; }}
.badge-danger {{ background: rgba(239,68,68,0.2); color: #fca5a5; }}
.badge-warning {{ background: rgba(245,158,11,0.2); color: #fcd34d; }}
.badge-success {{ background: rgba(16,185,129,0.2); color: #6ee7b7; }}
.section-title {{ font-size: 1.1rem; font-weight: 600; margin: 2rem 0 1rem; padding-bottom: 0.5rem; border-bottom: 1px solid var(--border); }}
.prediction {{ background: linear-gradient(135deg, rgba(14,165,233,0.1), rgba(6,182,212,0.1)); border: 1px solid rgba(14,165,233,0.3); border-radius: var(--radius); padding: 1rem; margin-top: 0.5rem; }}
.prediction-title {{ font-size: 0.8rem; color: var(--accent); font-weight: 600; margin-bottom: 0.3rem; }}
@media (max-width: 768px) {{ .grid-2, .grid-3 {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
<div class="container">
    <div class="header">
        <div>
            <h1>PBSeg - Dashboard Inteligente</h1>
            <p class="meta">Atualizado em {now_str} | Dados cruzados de planilhas, portais, Gmail e Segfy</p>
        </div>
        <div class="export-btns">
            <button onclick="exportXLSX()">📊 Exportar XLSX</button>
            <button onclick="exportPDF()">📄 Exportar PDF</button>
        </div>
    </div>

    <div class="grid grid-4" id="kpis"></div>
    <h2 class="section-title">Distribuição da Carteira</h2>
    <div class="grid grid-2">
        <div class="card"><div class="card-title">Apólices por Seguradora</div><div class="chart-container"><canvas id="chartInsurers"></canvas></div></div>
        <div class="card"><div class="card-title">Comissões: Pagas vs Pendentes</div><div class="chart-container"><canvas id="chartCommissions"></canvas></div></div>
    </div>
    <h2 class="section-title">Renovações e Acompanhamento</h2>
    <div class="grid grid-2">
        <div class="card"><div class="card-title">Renovações por Mês</div><div class="chart-container"><canvas id="chartRenewals"></canvas></div></div>
        <div class="card"><div class="card-title">Alertas por Severidade</div><div class="chart-container"><canvas id="chartAlerts"></canvas></div></div>
    </div>
    <h2 class="section-title">Financeiro</h2>
    <div class="grid grid-3">
        <div class="card"><div class="card-title">Fluxo de Caixa Mensal</div><div class="chart-container"><canvas id="chartCashflow"></canvas></div></div>
        <div class="card"><div class="card-title">Despesas por Categoria</div><div class="chart-container"><canvas id="chartExpenses"></canvas></div></div>
        <div class="card"><div class="card-title">Tendência de Receita</div><div class="chart-container"><canvas id="chartTrend"></canvas></div></div>
    </div>
    <h2 class="section-title">Predições e Inteligência</h2>
    <div class="grid grid-2">
        <div class="card">
            <div class="card-title">Apólices Vencendo nos Próximos 30 Dias</div>
            <div id="expiringTable"></div>
            <div class="prediction">
                <div class="prediction-title">⚡ Predição</div>
                <span id="predictionText"></span>
            </div>
        </div>
        <div class="card">
            <div class="card-title">Top 15 Segurados por Prêmio</div>
            <div id="topInsuredTable"></div>
        </div>
    </div>
    <h2 class="section-title">Divergências Portal × Planilha</h2>
    <div class="card"><div id="divergencesTable"></div></div>
    <h2 class="section-title">Histórico de Execuções</h2>
    <div class="card"><div id="runHistoryTable"></div></div>
</div>

<script>
const D = {data_json};
const colors = ['#0ea5e9','#06b6d4','#10b981','#f59e0b','#ef4444','#8b5cf6','#ec4899','#14b8a6','#f97316','#6366f1'];

// KPIs
document.getElementById('kpis').innerHTML = `
    <div class="card"><div class="card-title">Total Apólices</div><div class="kpi kpi-accent">${{D.totals.policies}}</div><div class="kpi-sub">${{D.policies_by_insurer.length}} seguradoras</div></div>
    <div class="card"><div class="card-title">Prêmio Total</div><div class="kpi kpi-success">R$ ${{(D.totals.premio/1000).toFixed(0)}}k</div><div class="kpi-sub">Comissão: R$ ${{(D.totals.comissao/1000).toFixed(0)}}k</div></div>
    <div class="card"><div class="card-title">Comissões Pendentes</div><div class="kpi kpi-warning">${{D.commissions.pending}}</div><div class="kpi-sub">${{D.commissions.paid}} pagas</div></div>
    <div class="card"><div class="card-title">Incidentes Abertos</div><div class="kpi kpi-danger">${{D.incidents.sinistros + D.incidents.endossos}}</div><div class="kpi-sub">${{D.incidents.sinistros}} sinistros | ${{D.incidents.endossos}} endossos</div></div>
`;

// Charts
new Chart('chartInsurers', {{type:'bar',data:{{labels:D.policies_by_insurer.map(i=>i.insurer),datasets:[{{label:'Apólices',data:D.policies_by_insurer.map(i=>i.total),backgroundColor:colors}}]}},options:{{indexAxis:'y',plugins:{{legend:{{display:false}}}},scales:{{x:{{grid:{{color:'#334155'}}}},y:{{grid:{{display:false}}}}}}}}}});

new Chart('chartCommissions', {{type:'doughnut',data:{{labels:['Pagas','Pendentes'],datasets:[{{data:[D.commissions.paid,D.commissions.pending],backgroundColor:['#10b981','#f59e0b']}}]}},options:{{plugins:{{legend:{{position:'bottom',labels:{{color:'#94a3b8'}}}}}}}}}});

if(D.renewals_by_month.length){{
    new Chart('chartRenewals', {{type:'bar',data:{{labels:D.renewals_by_month.map(r=>r.month),datasets:[{{label:'Concluídas',data:D.renewals_by_month.map(r=>r.concluded),backgroundColor:'#10b981'}},{{label:'Em Aberto',data:D.renewals_by_month.map(r=>r.open),backgroundColor:'#f59e0b'}}]}},options:{{scales:{{x:{{grid:{{color:'#334155'}}}},y:{{grid:{{color:'#334155'}}}}}}}}}});
}}

if(D.alerts_by_severity.length){{
    new Chart('chartAlerts', {{type:'polarArea',data:{{labels:D.alerts_by_severity.map(a=>a.severity),datasets:[{{data:D.alerts_by_severity.map(a=>a.total),backgroundColor:['#ef4444','#f59e0b','#0ea5e9','#10b981']}}]}},options:{{plugins:{{legend:{{position:'bottom',labels:{{color:'#94a3b8'}}}}}}}}}});
}}

if(D.cashflow_monthly.length){{
    new Chart('chartCashflow', {{type:'line',data:{{labels:D.cashflow_monthly.map(c=>c.month),datasets:[{{label:'Receita',data:D.cashflow_monthly.map(c=>c.total),borderColor:'#10b981',tension:0.3,fill:true,backgroundColor:'rgba(16,185,129,0.1)'}}]}},options:{{scales:{{x:{{grid:{{color:'#334155'}}}},y:{{grid:{{color:'#334155'}}}}}}}}}});
}}

if(D.expenses_by_category.length){{
    new Chart('chartExpenses', {{type:'pie',data:{{labels:D.expenses_by_category.map(e=>e.category),datasets:[{{data:D.expenses_by_category.map(e=>e.total),backgroundColor:colors}}]}},options:{{plugins:{{legend:{{position:'bottom',labels:{{color:'#94a3b8'}}}}}}}}}});
}}

if(D.commission_trend.length){{
    new Chart('chartTrend', {{type:'line',data:{{labels:D.commission_trend.map(c=>c.month).reverse(),datasets:[{{label:'Receita Mensal',data:D.commission_trend.map(c=>c.total).reverse(),borderColor:'#0ea5e9',tension:0.4,fill:true,backgroundColor:'rgba(14,165,233,0.1)'}}]}},options:{{scales:{{x:{{grid:{{color:'#334155'}}}},y:{{grid:{{color:'#334155'}}}}}}}}}});
}}

// Tables
function renderTable(id, headers, rows) {{
    let html = '<table class="table"><thead><tr>' + headers.map(h=>`<th>${{h}}</th>`).join('') + '</tr></thead><tbody>';
    rows.forEach(r => {{ html += '<tr>' + r.map(c=>`<td>${{c}}</td>`).join('') + '</tr>'; }});
    html += '</tbody></table>';
    document.getElementById(id).innerHTML = html;
}}

renderTable('expiringTable', ['Segurado','Seguradora','Vigência','Prêmio'],
    D.expiring_soon.map(p=>[p.insured_name, p.insurer, p.vig, 'R$ '+(p.premio_total||0).toFixed(2)]));

renderTable('topInsuredTable', ['Segurado','Seguradora','Prêmio','Comissão','Veículo'],
    D.top_insured.map(p=>[p.insured_name, p.insurer, 'R$ '+(p.premio_total||0).toFixed(2), 'R$ '+(p.comissao||0).toFixed(2), p.vehicle_item||'-']));

renderTable('divergencesTable', ['Apólice','Segurado','Seguradora','Prêmio Planilha','Prêmio Portal','Comissão Planilha','Comissão Portal'],
    D.divergences.map(d=>[d.policy_id, d.insured_name, d.insurer, 'R$ '+(d.planilha_premio||0).toFixed(2), 'R$ '+(d.portal_premio||0).toFixed(2), 'R$ '+(d.planilha_comissao||0).toFixed(2), 'R$ '+(d.portal_comissao||0).toFixed(2)]));

renderTable('runHistoryTable', ['Data','Status','Apólices','Alertas','E-mails','Segfy Sync','Portal Sync'],
    D.run_history.map(r=>[r.run_date, `<span class="badge ${{r.status==='SUCESSO'?'badge-success':'badge-warning'}}">${{r.status}}</span>`, r.total_policies, r.total_alerts, r.total_emails, r.segfy_synced, r.portal_synced]));

// Prediction
const expCount = D.expiring_soon.length;
const predText = expCount > 0
    ? `${{expCount}} apólice(s) vencem nos próximos 30 dias. Receita em risco: R$ ${{D.expiring_soon.reduce((s,p)=>s+(p.premio_total||0),0).toFixed(2)}}. Inicie contato de renovação imediatamente.`
    : 'Nenhuma apólice vencendo nos próximos 30 dias. Carteira estável.';
document.getElementById('predictionText').textContent = predText;

// Export XLSX
function exportXLSX() {{
    const wb = XLSX.utils.book_new();
    const policies = D.policies_by_insurer.map(p=>({{Seguradora:p.insurer,Apolices:p.total,Premio:p.premio,Comissao:p.comissao}}));
    XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(policies), 'Carteira');
    XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(D.expiring_soon), 'Vencendo 30d');
    XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(D.top_insured), 'Top Segurados');
    XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(D.divergences), 'Divergencias');
    XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(D.run_history), 'Historico');
    XLSX.writeFile(wb, 'dashboard_pbseg_' + new Date().toISOString().slice(0,10) + '.xlsx');
}}

// Export PDF
function exportPDF() {{
    const {{ jsPDF }} = window.jspdf;
    const doc = new jsPDF();
    doc.setFontSize(16);
    doc.text('PBSeg - Relatório Operacional', 14, 20);
    doc.setFontSize(10);
    doc.text(`Gerado em: ${{new Date().toLocaleString('pt-BR')}}`, 14, 28);
    let y = 40;
    doc.setFontSize(12);
    doc.text(`Total de Apólices: ${{D.totals.policies}}`, 14, y); y+=8;
    doc.text(`Prêmio Total: R$ ${{(D.totals.premio||0).toFixed(2)}}`, 14, y); y+=8;
    doc.text(`Comissão Total: R$ ${{(D.totals.comissao||0).toFixed(2)}}`, 14, y); y+=8;
    doc.text(`Comissões Pendentes: ${{D.commissions.pending}}`, 14, y); y+=8;
    doc.text(`Sinistros Abertos: ${{D.incidents.sinistros}}`, 14, y); y+=8;
    doc.text(`Endossos Abertos: ${{D.incidents.endossos}}`, 14, y); y+=8;
    doc.text(`Apólices Vencendo (30d): ${{D.expiring_soon.length}}`, 14, y); y+=12;
    doc.setFontSize(11);
    doc.text('Carteira por Seguradora:', 14, y); y+=7;
    doc.setFontSize(9);
    D.policies_by_insurer.forEach(p => {{
        doc.text(`  ${{p.insurer}}: ${{p.total}} apólices | R$ ${{(p.premio||0).toFixed(2)}}`, 14, y); y+=6;
        if(y > 270) {{ doc.addPage(); y = 20; }}
    }});
    doc.save('relatorio_pbseg_' + new Date().toISOString().slice(0,10) + '.pdf');
}}
</script>
</body>
</html>"""
