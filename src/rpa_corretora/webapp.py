"""Aplicação web local do RPA PBSeg.

Servidor Flask que expõe todas as funcionalidades do RPA via interface web
com visual identico ao mockup, incluindo:
- Execução do ciclo (produção e dry-run)
- Log em tempo real via SSE (Server-Sent Events)
- Agente IA embutido (Ollama/Llama + fallback local)
- Pesquisa web (DuckDuckGo)
- Consulta ao banco SQLite
- Dashboard, alertas, status, notícias
- Exportação XLSX/PDF
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from queue import Queue
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

from flask import Flask, Response, jsonify, request, send_from_directory

BASE_DIR = Path(__file__).resolve().parents[2]
SRC_DIR = BASE_DIR / "src"
OUTPUTS_DIR = BASE_DIR / "outputs"
DB_PATH = OUTPUTS_DIR / "rpa_corretora.db"
STATIC_DIR = BASE_DIR / "web"

app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")

# Estado global
_process: subprocess.Popen | None = None
_log_queue: Queue = Queue()
_running = False
_execute_lock = threading.Lock()


# ============================================================
# API ENDPOINTS
# ============================================================

@app.route("/")
def index():
    return send_from_directory(str(STATIC_DIR), "index.html")


@app.route("/favicon.ico")
def favicon():
    return "", 204


@app.route("/api/status")
def api_status():
    """Retorna status geral do sistema."""
    data = {"running": _running, "db_exists": DB_PATH.exists()}
    if DB_PATH.exists():
        try:
            conn = sqlite3.connect(str(DB_PATH))
            data["policies"] = conn.execute("SELECT COUNT(*) FROM policies").fetchone()[0]
            data["pending_commissions"] = conn.execute("SELECT COUNT(*) FROM policies WHERE status_pgto = ''").fetchone()[0]
            data["sinistros"] = conn.execute("SELECT COUNT(*) FROM policies WHERE sinistro_open = 1").fetchone()[0]
            data["endossos"] = conn.execute("SELECT COUNT(*) FROM policies WHERE endosso_open = 1").fetchone()[0]
            data["proposals_pending"] = conn.execute("SELECT COUNT(*) FROM policies WHERE renewal_started = 0 AND status_pgto = ''").fetchone()[0]

            today = date.today()
            future = (today + timedelta(days=10)).isoformat()
            data["expiring_10d"] = conn.execute("SELECT COUNT(*) FROM policies WHERE vig BETWEEN ? AND ?", (today.isoformat(), future)).fetchone()[0]

            last_run = conn.execute("SELECT run_date, status, total_policies, total_alerts FROM run_history ORDER BY started_at DESC LIMIT 1").fetchone()
            if last_run:
                data["last_run"] = {"date": last_run[0], "status": last_run[1], "policies": last_run[2], "alerts": last_run[3]}

            data["by_insurer"] = [{"insurer": r[0], "count": r[1]} for r in conn.execute("SELECT insurer, COUNT(*) FROM policies GROUP BY insurer ORDER BY COUNT(*) DESC").fetchall()]
            conn.close()
        except Exception as exc:
            data["error"] = str(exc)
    return jsonify(data)


@app.route("/api/execute", methods=["POST"])
def api_execute():
    """Inicia execução do RPA."""
    global _process, _running
    with _execute_lock:
        if _running:
            return jsonify({"status": "already_running", "message": "Ciclo ja em execucao. Aguarde."}), 200
        _running = True

    dry_run = request.json.get("dry_run", False) if request.json else False
    cmd = [sys.executable, "-m", "rpa_corretora.main"]
    if dry_run:
        cmd.append("--dry-run")

    env = {**os.environ, "PYTHONPATH": str(SRC_DIR), "RPA_NO_CHROME_RESTART": "1", "PYTHONUNBUFFERED": "1"}

    def run():
        global _process, _running
        try:
            _process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=str(BASE_DIR), env=env, bufsize=1)
            for line in iter(_process.stdout.readline, ""):
                _log_queue.put(line.rstrip())
            _process.wait()
            code = _process.returncode
            _log_queue.put(f"[EXIT:{code}]")
        except Exception as exc:
            _log_queue.put(f"[ERROR] {exc}")
        finally:
            _running = False
            _process = None

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"status": "started", "dry_run": dry_run})


@app.route("/api/stop", methods=["POST"])
def api_stop():
    """Para a execução."""
    global _process
    if _process:
        _process.terminate()
        return jsonify({"status": "stopped"})
    return jsonify({"error": "Nada em execução"}), 400


@app.route("/api/logs")
def api_logs():
    """Stream de logs via SSE."""
    def stream():
        while True:
            try:
                line = _log_queue.get(timeout=1)
                yield f"data: {json.dumps({'line': line})}\n\n"
            except Exception:
                yield f"data: {json.dumps({'heartbeat': True})}\n\n"
    resp = Response(stream(), mimetype="text/event-stream")
    resp.headers["Cache-Control"] = "no-cache"
    resp.headers["X-Accel-Buffering"] = "no"
    return resp


@app.route("/api/agent", methods=["POST"])
def api_agent():
    """Endpoint do agente IA."""
    data = request.json or {}
    question = data.get("message", "").strip()
    if not question:
        return jsonify({"response": "Digite uma mensagem."})

    # Comandos diretos
    lower = question.lower()
    if lower in ("executar", "rodar", "run"):
        api_execute()
        return jsonify({"response": "⚡ Ciclo de produção iniciado!", "action": "execute"})
    if lower in ("dry-run", "testar"):
        request._cached_data = json.dumps({"dry_run": True}).encode()
        return jsonify({"response": "🧪 Dry-run iniciado!", "action": "dryrun"})
    if lower in ("parar", "stop"):
        api_stop()
        return jsonify({"response": "⏹ Execução interrompida."})

    # Consulta banco
    db_answer = _query_db_for_agent(question)
    if db_answer:
        return jsonify({"response": db_answer})

    # Pesquisa web
    if lower.startswith(("pesquisar ", "buscar na web ", "search ")):
        term = re.sub(r"^(pesquisar|buscar na web|search)\s+", "", lower)
        results = _web_search(term)
        return jsonify({"response": f"🌐 Pesquisa: {term}\n\n{results}", "type": "tool"})

    # Tenta Ollama
    llm_response = _call_ollama(question)
    if llm_response:
        return jsonify({"response": llm_response})

    # Fallback
    return jsonify({"response": _fallback_answer(question)})


@app.route("/api/news")
def api_news():
    """Busca notícias sobre seguros."""
    queries = ["seguros brasil 2026", "SUSEP regulamentação", "mercado seguros auto"]
    results = []
    for q in queries:
        try:
            items = _web_search(q, max_results=3)
            results.append({"query": q, "results": items})
        except Exception:
            continue
    return jsonify({"news": results})


@app.route("/api/search", methods=["POST"])
def api_search():
    """Pesquisa segurado no banco."""
    data = request.json or {}
    term = data.get("term", "").strip()
    if not term or not DB_PATH.exists():
        return jsonify({"results": []})

    conn = sqlite3.connect(str(DB_PATH))
    rows = conn.execute(
        "SELECT policy_id, insured_name, insurer, vig, premio_total, comissao, status_pgto, sinistro_open, endosso_open, vehicle_item "
        "FROM policies WHERE UPPER(insured_name) LIKE ? LIMIT 10",
        (f"%{term.upper()}%",)
    ).fetchall()
    conn.close()

    results = []
    for r in rows:
        results.append({
            "policy_id": r[0], "name": r[1], "insurer": r[2], "vig": r[3],
            "premio": r[4], "comissao": r[5], "status_pgto": r[6] or "PENDENTE",
            "sinistro": bool(r[7]), "endosso": bool(r[8]), "vehicle": r[9] or "",
        })
    return jsonify({"results": results})


@app.route("/api/report/<insurer>")
def api_report(insurer):
    """Relatório por seguradora."""
    if not DB_PATH.exists():
        return jsonify({"error": "Banco não encontrado"})

    conn = sqlite3.connect(str(DB_PATH))
    ins = insurer.upper()
    total = conn.execute("SELECT COUNT(*) FROM policies WHERE UPPER(insurer) LIKE ?", (f"%{ins}%",)).fetchone()[0]
    premio = conn.execute("SELECT COALESCE(SUM(premio_total), 0) FROM policies WHERE UPPER(insurer) LIKE ?", (f"%{ins}%",)).fetchone()[0]
    comissao = conn.execute("SELECT COALESCE(SUM(comissao), 0) FROM policies WHERE UPPER(insurer) LIKE ?", (f"%{ins}%",)).fetchone()[0]
    pending = conn.execute("SELECT COUNT(*) FROM policies WHERE UPPER(insurer) LIKE ? AND status_pgto = ''", (f"%{ins}%",)).fetchone()[0]
    sinistros = conn.execute("SELECT COUNT(*) FROM policies WHERE UPPER(insurer) LIKE ? AND sinistro_open = 1", (f"%{ins}%",)).fetchone()[0]
    conn.close()

    return jsonify({
        "insurer": ins, "total": total, "premio": premio,
        "comissao": comissao, "pending": pending, "sinistros": sinistros,
    })


@app.route("/api/alerts")
def api_alerts():
    """Retorna alertas atuais."""
    if not DB_PATH.exists():
        return jsonify({"alerts": []})

    conn = sqlite3.connect(str(DB_PATH))
    alerts = conn.execute(
        "SELECT severity, code, message FROM alerts ORDER BY created_at DESC LIMIT 20"
    ).fetchall()
    conn.close()

    return jsonify({"alerts": [{"severity": a[0], "code": a[1], "message": a[2]} for a in alerts]})


@app.route("/api/expiring")
def api_expiring():
    """Apólices vencendo em 30 dias."""
    if not DB_PATH.exists():
        return jsonify({"expiring": []})

    conn = sqlite3.connect(str(DB_PATH))
    today = date.today()
    future = (today + timedelta(days=30)).isoformat()
    rows = conn.execute(
        "SELECT insured_name, insurer, vig, premio_total, vehicle_item FROM policies WHERE vig BETWEEN ? AND ? ORDER BY vig",
        (today.isoformat(), future)
    ).fetchall()
    conn.close()

    return jsonify({"expiring": [{"name": r[0], "insurer": r[1], "vig": r[2], "premio": r[3], "vehicle": r[4] or ""} for r in rows]})


@app.route("/api/history")
def api_history():
    """Histórico de execuções."""
    if not DB_PATH.exists():
        return jsonify({"history": []})

    conn = sqlite3.connect(str(DB_PATH))
    rows = conn.execute("SELECT run_date, status, total_policies, total_alerts, total_emails, segfy_synced, portal_synced FROM run_history ORDER BY started_at DESC LIMIT 20").fetchall()
    conn.close()

    return jsonify({"history": [{"date": r[0], "status": r[1], "policies": r[2], "alerts": r[3], "emails": r[4], "segfy": r[5], "portal": r[6]} for r in rows]})


# ============================================================
# BI ENDPOINTS
# ============================================================

@app.route("/api/bi/revenue")
def api_bi_revenue():
    """Prêmio e comissão por seguradora + histórico mensal por VIG."""
    if not DB_PATH.exists():
        return jsonify({"by_insurer": [], "monthly_premio": []})
    try:
        conn = sqlite3.connect(str(DB_PATH))
        by_insurer = [
            {"insurer": r[0], "premio": r[1], "comissao": r[2], "policies": r[3]}
            for r in conn.execute(
                "SELECT insurer, COALESCE(SUM(premio_total),0), COALESCE(SUM(comissao),0), COUNT(*) "
                "FROM policies GROUP BY insurer ORDER BY SUM(premio_total) DESC"
            ).fetchall()
        ]
        monthly_premio = [
            {"month": r[0], "premio": r[1], "comissao": r[2]}
            for r in conn.execute(
                "SELECT strftime('%Y-%m', vig) as m, "
                "COALESCE(SUM(premio_total),0), COALESCE(SUM(comissao),0) "
                "FROM policies GROUP BY m ORDER BY m DESC LIMIT 18"
            ).fetchall()
        ]
        monthly_premio.reverse()
        conn.close()
        return jsonify({"by_insurer": by_insurer, "monthly_premio": monthly_premio})
    except Exception as exc:
        return jsonify({"error": str(exc), "by_insurer": [], "monthly_premio": []})


@app.route("/api/bi/pipeline")
def api_bi_pipeline():
    """Pipeline de renovações agrupado por fase com receita em risco."""
    if not DB_PATH.exists():
        return jsonify({"pipeline": {}, "summary": {}, "premio_risk": {}})
    try:
        conn = sqlite3.connect(str(DB_PATH))
        today = date.today().isoformat()
        d30 = (date.today() + timedelta(days=30)).isoformat()
        d90 = (date.today() + timedelta(days=90)).isoformat()

        def fetch_phase(where, params=()):
            return [
                {
                    "policy_id": r[0], "insured_name": r[1], "insurer": r[2],
                    "vig": r[3], "premio_total": r[4], "comissao": r[5],
                    "renewal_kind": r[6], "days": r[7],
                }
                for r in conn.execute(
                    "SELECT policy_id, insured_name, insurer, vig, premio_total, comissao, renewal_kind, "
                    "CAST(julianday(vig) - julianday('now') AS INTEGER) as days "
                    f"FROM policies WHERE {where} ORDER BY vig ASC",
                    params,
                ).fetchall()
            ]

        pipeline = {
            "VENCIDA":    fetch_phase("vig < ?", (today,)),
            "URGENTE":    fetch_phase("vig BETWEEN ? AND ?", (today, d30)),
            "NEGOCIACAO": fetch_phase("vig > ? AND vig <= ?", (d30, d90)),
            "PROSPECCAO": fetch_phase("vig > ?", (d90,)),
        }
        summary = {phase: len(items) for phase, items in pipeline.items()}
        premio_risk = {
            "urgente":    round(sum(p["premio_total"] or 0 for p in pipeline["URGENTE"]), 2),
            "negociacao": round(sum(p["premio_total"] or 0 for p in pipeline["NEGOCIACAO"]), 2),
        }
        conn.close()
        return jsonify({"pipeline": pipeline, "summary": summary, "premio_risk": premio_risk})
    except Exception as exc:
        return jsonify({"error": str(exc), "pipeline": {}, "summary": {}, "premio_risk": {}})


@app.route("/api/bi/cashflow")
def api_bi_cashflow():
    """Fluxo de caixa histórico (12m) + projeção linear 3 meses."""
    if not DB_PATH.exists():
        return jsonify({"historical": [], "projected": []})
    try:
        conn = sqlite3.connect(str(DB_PATH))
        rows = conn.execute("""
            SELECT m,
                COALESCE((SELECT SUM(value) FROM cashflow  WHERE strftime('%Y-%m', entry_date)=m),0),
                COALESCE((SELECT SUM(value) FROM expenses  WHERE strftime('%Y-%m', entry_date)=m),0)
            FROM (
                SELECT DISTINCT strftime('%Y-%m', entry_date) as m FROM cashflow
                UNION
                SELECT DISTINCT strftime('%Y-%m', entry_date) FROM expenses
            ) ORDER BY m ASC
        """).fetchall()
        historical = [
            {"month": r[0], "receita": round(r[1], 2), "despesas": round(r[2], 2),
             "liquido": round(r[1] - r[2], 2)}
            for r in rows[-12:]
        ]

        projected = []
        if len(historical) >= 3:
            ys = [h["liquido"] for h in historical]
            n = len(ys)
            xs = list(range(n))
            sx, sy = sum(xs), sum(ys)
            sxy = sum(x * y for x, y in zip(xs, ys))
            sx2 = sum(x * x for x in xs)
            denom = n * sx2 - sx * sx
            slope = (n * sxy - sx * sy) / denom if denom else 0
            intercept = (sy - slope * sx) / n
            last = historical[-1]["month"]
            yr, mo = int(last[:4]), int(last[5:7])
            for i in range(1, 4):
                mo += 1
                if mo > 12:
                    mo = 1
                    yr += 1
                projected.append({
                    "month": f"{yr:04d}-{mo:02d}",
                    "liquido_projetado": round(intercept + slope * (n + i - 1), 2),
                })
        conn.close()
        return jsonify({"historical": historical, "projected": projected})
    except Exception as exc:
        return jsonify({"error": str(exc), "historical": [], "projected": []})


@app.route("/api/bi/incidents")
def api_bi_incidents():
    """Taxa de sinistros/endossos e aging de apólices vencidas."""
    if not DB_PATH.exists():
        return jsonify({"by_insurer": [], "aging": []})
    try:
        conn = sqlite3.connect(str(DB_PATH))
        today = date.today().isoformat()
        by_insurer = [
            {
                "insurer": r[0], "total": r[1], "sinistros": r[2], "endossos": r[3],
                "sinistro_rate": round(r[2] / r[1] * 100, 1) if r[1] else 0,
                "endosso_rate":  round(r[3] / r[1] * 100, 1) if r[1] else 0,
            }
            for r in conn.execute(
                "SELECT insurer, COUNT(*), SUM(sinistro_open), SUM(endosso_open) "
                "FROM policies GROUP BY insurer ORDER BY COUNT(*) DESC"
            ).fetchall()
        ]
        buckets = [
            ("0-30d",  "julianday(?)-julianday(vig) BETWEEN 0 AND 30"),
            ("31-60d", "julianday(?)-julianday(vig) BETWEEN 31 AND 60"),
            ("61-90d", "julianday(?)-julianday(vig) BETWEEN 61 AND 90"),
            ("90d+",   "julianday(?)-julianday(vig) > 90"),
        ]
        aging = []
        for label, cond in buckets:
            r = conn.execute(
                f"SELECT COUNT(*), COALESCE(SUM(premio_total),0), COALESCE(SUM(comissao),0) "
                f"FROM policies WHERE vig < ? AND {cond}", (today, today)
            ).fetchone()
            aging.append({"bucket": label, "count": r[0], "premio": round(r[1], 2), "comissao": round(r[2], 2)})
        conn.close()
        return jsonify({"by_insurer": by_insurer, "aging": aging})
    except Exception as exc:
        return jsonify({"error": str(exc), "by_insurer": [], "aging": []})


@app.route("/api/bi/insurer_performance")
def api_bi_insurer_performance():
    """Scorecard completo por seguradora: prêmio, comissão, ticket, risco, sinistros, pgto."""
    if not DB_PATH.exists():
        return jsonify({"insurers": []})
    try:
        conn = sqlite3.connect(str(DB_PATH))
        today = date.today().isoformat()
        d30  = (date.today() + timedelta(days=30)).isoformat()
        d90  = (date.today() + timedelta(days=90)).isoformat()
        rows = conn.execute("""
            SELECT
                insurer,
                COUNT(*) as total,
                COALESCE(SUM(premio_total), 0) as premio_total,
                COALESCE(SUM(comissao), 0) as comissao_total,
                CASE WHEN SUM(premio_total)>0
                     THEN ROUND(SUM(comissao)/SUM(premio_total)*100,1) ELSE 0 END as comissao_pct,
                SUM(sinistro_open) as sinistros,
                SUM(endosso_open)  as endossos,
                SUM(CASE WHEN status_pgto=''  THEN 1 ELSE 0 END) as pgto_pendente,
                SUM(CASE WHEN status_pgto!='' THEN 1 ELSE 0 END) as pgto_ok,
                SUM(CASE WHEN vig BETWEEN ? AND ? THEN 1 ELSE 0 END) as vencendo_30d,
                COALESCE(SUM(CASE WHEN vig BETWEEN ? AND ? THEN premio_total ELSE 0 END),0) as premio_risco_90d,
                ROUND(AVG(premio_total),2) as ticket_medio
            FROM policies
            GROUP BY insurer
            ORDER BY SUM(premio_total) DESC
        """, (today, d30, today, d90)).fetchall()
        insurers = [
            {
                "insurer": r[0], "total": r[1], "premio_total": round(r[2], 2),
                "comissao_total": round(r[3], 2), "comissao_pct": r[4],
                "sinistros": r[5], "endossos": r[6], "pgto_pendente": r[7],
                "pgto_ok": r[8], "vencendo_30d": r[9],
                "premio_risco_90d": round(r[10], 2), "ticket_medio": round(r[11] or 0, 2),
            }
            for r in rows
        ]
        conn.close()
        return jsonify({"insurers": insurers})
    except Exception as exc:
        return jsonify({"error": str(exc), "insurers": []})


# ============================================================
# HELPERS
# ============================================================

def _query_db_for_agent(question: str) -> str:
    """Responde perguntas usando dados reais do banco SQLite."""
    if not DB_PATH.exists():
        return ""
    q = question.lower()
    today = date.today()

    def _fmt(v: float) -> str:
        return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    try:
        conn = sqlite3.connect(str(DB_PATH))

        # ── Status geral / carteira ──────────────────────────────────────
        if any(w in q for w in ("status", "carteira", "quantas", "total", "resumo", "panorama")):
            total = conn.execute("SELECT COUNT(*) FROM policies").fetchone()[0]
            active = conn.execute("SELECT COUNT(*) FROM policies WHERE vig >= ?", (today.isoformat(),)).fetchone()[0]
            sin = conn.execute("SELECT COUNT(*) FROM policies WHERE sinistro_open = 1").fetchone()[0]
            end = conn.execute("SELECT COUNT(*) FROM policies WHERE endosso_open = 1").fetchone()[0]
            pending = conn.execute("SELECT COUNT(*) FROM policies WHERE status_pgto = ''").fetchone()[0]
            premio = conn.execute("SELECT COALESCE(SUM(premio_total),0) FROM policies").fetchone()[0]
            com = conn.execute("SELECT COALESCE(SUM(comissao),0) FROM policies").fetchone()[0]
            d30 = (today + timedelta(days=30)).isoformat()
            urgentes = conn.execute("SELECT COUNT(*) FROM policies WHERE vig BETWEEN ? AND ?", (today.isoformat(), d30)).fetchone()[0]
            conn.close()
            return (
                f"📊 Carteira PBSeg — {today.strftime('%d/%m/%Y')}\n"
                f"• Total apólices: {total} ({active} ativas, {total - active} vencidas)\n"
                f"• Vencendo em 30 dias: {urgentes}\n"
                f"• Prêmio total: {_fmt(premio)}\n"
                f"• Comissão total: {_fmt(com)}\n"
                f"• Comissões pendentes: {pending}\n"
                f"• Sinistros: {sin} | Endossos: {end}"
            )

        # ── Apólices vencidas / expiradas ────────────────────────────────
        if any(w in q for w in ("vencida", "vencidas", "venceu", "expirada", "expiradas", "expirou", "2025", "antigas")):
            expired = conn.execute("SELECT COUNT(*) FROM policies WHERE vig < ?", (today.isoformat(),)).fetchone()[0]
            active = conn.execute("SELECT COUNT(*) FROM policies WHERE vig >= ?", (today.isoformat(),)).fetchone()[0]
            oldest = conn.execute("SELECT MIN(vig), MAX(vig) FROM policies WHERE vig < ?", (today.isoformat(),)).fetchone()
            conn.close()
            result = (
                f"📋 Situação ({today.strftime('%d/%m/%Y')}):\n"
                f"• Vencidas: {expired}\n"
                f"• Ativas (VIG futura): {active}\n"
            )
            if oldest and oldest[0]:
                result += f"• Período vencidas: {oldest[0]} → {oldest[1]}\n"
            if active == 0:
                result += "\n⚠️ Todas as apólices estão vencidas. O banco precisa ser atualizado com dados 2026 via export do Segfy."
            return result

        # ── Comissões ────────────────────────────────────────────────────
        if any(w in q for w in ("comiss", "pendente", "pago", "pagamento", "receber")):
            paid = conn.execute("SELECT COUNT(*) FROM policies WHERE status_pgto != ''").fetchone()[0]
            pending = conn.execute("SELECT COUNT(*) FROM policies WHERE status_pgto = ''").fetchone()[0]
            val_pend = conn.execute("SELECT COALESCE(SUM(comissao),0) FROM policies WHERE status_pgto = ''").fetchone()[0]
            val_paid = conn.execute("SELECT COALESCE(SUM(comissao),0) FROM policies WHERE status_pgto != ''").fetchone()[0]
            conn.close()
            return (
                f"💰 Comissões:\n"
                f"• Pagas: {paid} ({_fmt(val_paid)})\n"
                f"• Pendentes: {pending} ({_fmt(val_pend)})\n"
                f"• Total: {_fmt(val_pend + val_paid)}"
            )

        # ── Alertas / urgente / pendência ────────────────────────────────
        if any(w in q for w in ("alerta", "critico", "urgente", "pendencia", "pendências")):
            try:
                alerts = conn.execute("SELECT severity, message FROM alerts ORDER BY created_at DESC LIMIT 5").fetchall()
            except Exception:
                alerts = []
            d30 = (today + timedelta(days=30)).isoformat()
            urg_rows = conn.execute(
                "SELECT insured_name, insurer, vig FROM policies WHERE vig BETWEEN ? AND ? ORDER BY vig LIMIT 5",
                (today.isoformat(), d30)
            ).fetchall()
            conn.close()
            result = ""
            if alerts:
                result += "🚨 Alertas recentes:\n"
                for row in alerts:
                    icon = "🔴" if row[0] in ("CRITICA", "ALTA") else "🟡"
                    result += f"{icon} [{row[0]}] {row[1][:70]}\n"
            else:
                result += "✅ Nenhum alerta registrado.\n"
            if urg_rows:
                result += f"\n⚠️ {len(urg_rows)} apólice(s) URGENTES (vence ≤30d):\n"
                for name, ins, vig in urg_rows:
                    result += f"• {name} ({ins}) — {vig}\n"
            return result.strip()

        # ── Vencendo / renovação ─────────────────────────────────────────
        if any(w in q for w in ("vencendo", "vencer", "renovar", "renovação", "renovacao", "proxim")):
            d30 = (today + timedelta(days=30)).isoformat()
            d60 = (today + timedelta(days=60)).isoformat()
            d90 = (today + timedelta(days=90)).isoformat()
            u30 = conn.execute("SELECT COUNT(*) FROM policies WHERE vig BETWEEN ? AND ?", (today.isoformat(), d30)).fetchone()[0]
            u60 = conn.execute("SELECT COUNT(*) FROM policies WHERE vig BETWEEN ? AND ?", (today.isoformat(), d60)).fetchone()[0]
            u90 = conn.execute("SELECT COUNT(*) FROM policies WHERE vig BETWEEN ? AND ?", (today.isoformat(), d90)).fetchone()[0]
            rows = conn.execute(
                "SELECT insured_name, insurer, vig FROM policies WHERE vig BETWEEN ? AND ? ORDER BY vig LIMIT 7",
                (today.isoformat(), d30)
            ).fetchall()
            conn.close()
            result = f"📅 Renovações:\n• 30 dias: {u30} | 60 dias: {u60} | 90 dias: {u90}\n"
            if rows:
                result += "\nUrgentes (≤30d):\n"
                for name, ins, vig in rows:
                    days_left = (date.fromisoformat(vig) - today).days
                    result += f"• {name} ({ins}) — {vig} ({days_left}d)\n"
            else:
                result += "\n✅ Nenhuma apólice vencendo em 30 dias."
            return result

        # ── Sinistros / endossos ─────────────────────────────────────────
        if any(w in q for w in ("sinistro", "endosso", "ocorrencia", "ocorrência")):
            sin = conn.execute("SELECT COUNT(*) FROM policies WHERE sinistro_open = 1").fetchone()[0]
            end = conn.execute("SELECT COUNT(*) FROM policies WHERE endosso_open = 1").fetchone()[0]
            sin_rows = conn.execute("SELECT insured_name, insurer FROM policies WHERE sinistro_open = 1 LIMIT 5").fetchall()
            conn.close()
            result = f"🚗 Ocorrências abertas:\n• Sinistros: {sin} | Endossos: {end}\n"
            if sin_rows:
                result += "\nSinistros:\n"
                for name, ins in sin_rows:
                    result += f"• {name} ({ins})\n"
            return result

        # ── Prêmio / faturamento ─────────────────────────────────────────
        if any(w in q for w in ("premio", "prêmio", "faturamento", "receita")):
            total = conn.execute("SELECT COUNT(*) FROM policies").fetchone()[0]
            premio = conn.execute("SELECT COALESCE(SUM(premio_total),0) FROM policies").fetchone()[0]
            comissao = conn.execute("SELECT COALESCE(SUM(comissao),0) FROM policies").fetchone()[0]
            rows = conn.execute(
                "SELECT insurer, COALESCE(SUM(premio_total),0) as p FROM policies GROUP BY insurer ORDER BY p DESC LIMIT 5"
            ).fetchall()
            conn.close()
            result = (
                f"💵 Prêmio e Comissão:\n"
                f"• Prêmio total: {_fmt(premio)}\n"
                f"• Comissão total: {_fmt(comissao)}\n"
                f"• Ticket médio: {_fmt(premio / total if total else 0)}\n\nTop seguradoras:\n"
            )
            for ins, p in rows:
                result += f"• {ins}: {_fmt(p)}\n"
            return result

        # ── Busca por nome ───────────────────────────────────────────────
        if any(w in q for w in ("buscar", "procurar", "encontrar", "cliente", "segurado")):
            term = re.sub(r"^(buscar|procurar|encontrar|cliente|segurado)\s*", "", q).strip()
            if len(term) >= 3:
                rows = conn.execute(
                    "SELECT insured_name, insurer, premio_total, status_pgto, vehicle_item, vig FROM policies "
                    "WHERE UPPER(insured_name) LIKE ? LIMIT 5",
                    (f"%{term.upper()}%",)
                ).fetchall()
                conn.close()
                if rows:
                    result = f"🔍 Resultados para \"{term}\":\n\n"
                    for name, ins, premio, pgto, vehicle, vig in rows:
                        result += f"• {name} ({ins})\n  {_fmt(premio)} | {pgto or 'PENDENTE'} | VIG {vig}\n"
                        if vehicle:
                            result += f"  Veículo: {vehicle}\n"
                    return result
                conn.close()
                return f"🔍 Nenhum segurado encontrado para \"{term}\"."

        # ── Seguradora específica ────────────────────────────────────────
        known = ["yelum", "porto", "mapfre", "bradesco", "allianz", "suhai", "tokio", "hdi", "azul", "sompo", "zurich"]
        for ins in known:
            if ins in q:
                total = conn.execute("SELECT COUNT(*) FROM policies WHERE UPPER(insurer) LIKE ?", (f"%{ins.upper()}%",)).fetchone()[0]
                premio = conn.execute("SELECT COALESCE(SUM(premio_total),0) FROM policies WHERE UPPER(insurer) LIKE ?", (f"%{ins.upper()}%",)).fetchone()[0]
                comissao = conn.execute("SELECT COALESCE(SUM(comissao),0) FROM policies WHERE UPPER(insurer) LIKE ?", (f"%{ins.upper()}%",)).fetchone()[0]
                pending = conn.execute("SELECT COUNT(*) FROM policies WHERE UPPER(insurer) LIKE ? AND status_pgto = ''", (f"%{ins.upper()}%",)).fetchone()[0]
                conn.close()
                return (
                    f"📊 {ins.upper()}:\n"
                    f"• Apólices: {total}\n"
                    f"• Prêmio: {_fmt(premio)}\n"
                    f"• Comissão: {_fmt(comissao)}\n"
                    f"• Pgto pendente: {pending}"
                )

        # ── Fluxo de caixa / despesas ────────────────────────────────────
        if any(w in q for w in ("caixa", "fluxo", "cashflow", "despesa", "despesas")):
            try:
                cf = conn.execute(
                    "SELECT strftime('%Y-%m', entry_date) as m, SUM(value) FROM cashflow "
                    "GROUP BY m ORDER BY m DESC LIMIT 3"
                ).fetchall()
                exp = conn.execute(
                    "SELECT strftime('%Y-%m', entry_date) as m, SUM(value) FROM expenses "
                    "GROUP BY m ORDER BY m DESC LIMIT 3"
                ).fetchall()
                conn.close()
                result = "💳 Fluxo de Caixa:\n"
                if cf:
                    result += "Receitas:\n" + "".join(f"  {m}: {_fmt(v)}\n" for m, v in cf)
                if exp:
                    result += "Despesas:\n" + "".join(f"  {m}: {_fmt(v)}\n" for m, v in exp)
                return result
            except Exception:
                conn.close()

        # ── Nenhum padrão — snapshot geral ───────────────────────────────
        total = conn.execute("SELECT COUNT(*) FROM policies").fetchone()[0]
        active = conn.execute("SELECT COUNT(*) FROM policies WHERE vig >= ?", (today.isoformat(),)).fetchone()[0]
        d30 = (today + timedelta(days=30)).isoformat()
        urgentes = conn.execute("SELECT COUNT(*) FROM policies WHERE vig BETWEEN ? AND ?", (today.isoformat(), d30)).fetchone()[0]
        conn.close()
        return (
            f"Não entendi a pergunta. Situação atual ({today.strftime('%d/%m/%Y')}):\n"
            f"• {total} apólices ({active} ativas, {total - active} vencidas, {urgentes} urgentes)\n\n"
            f"Pergunte sobre: status, vencidas, vencendo, comissões, alertas, sinistros, prêmio, "
            f"buscar [nome], [seguradora], caixa. Ou 'pesquisar [tema]' para web."
        )

    except Exception:
        pass
    return ""


def _web_search(query: str, max_results: int = 5) -> str:
    try:
        url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
        titles = re.findall(r'class="result__a"[^>]*>(.*?)</a>', html, re.DOTALL)[:max_results]
        snippets = re.findall(r'class="result__snippet">(.*?)</a>', html, re.DOTALL)[:max_results]
        results = []
        for title, snippet in zip(titles, snippets):
            t = re.sub(r'<[^>]+>', '', title).strip()
            s = re.sub(r'<[^>]+>', '', snippet).strip()
            if t:
                results.append(f"• {t}\n  {s}")
        return "\n\n".join(results) if results else "Nenhum resultado."
    except Exception as exc:
        return f"Erro na pesquisa: {exc}"


def _call_ollama(question: str) -> str:
    try:
        context = ""
        if DB_PATH.exists():
            conn = sqlite3.connect(str(DB_PATH))
            total = conn.execute("SELECT COUNT(*) FROM policies").fetchone()[0]
            conn.close()
            context = f"\n[Contexto: carteira com {total} apólices, corretora PBSeg]"

        payload = json.dumps({
            "model": os.getenv("OLLAMA_MODEL", "llama3.1"),
            "messages": [
                {"role": "system", "content": f"Você é o assistente IA da corretora PBSeg. Responda em português, seja conciso e útil.{context}"},
                {"role": "user", "content": question},
            ],
            "stream": False,
            "options": {"temperature": 0.7, "num_predict": 512},
        }).encode()
        req = Request(f"{os.getenv('OLLAMA_URL', 'http://localhost:11434')}/api/chat", data=payload, headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
            return data.get("message", {}).get("content", "")
    except Exception:
        return ""


def _fallback_answer(question: str) -> str:
    """Resposta de último recurso com status real do sistema."""
    if DB_PATH.exists():
        try:
            conn = sqlite3.connect(str(DB_PATH))
            today = date.today()
            total = conn.execute("SELECT COUNT(*) FROM policies").fetchone()[0]
            active = conn.execute("SELECT COUNT(*) FROM policies WHERE vig >= ?", (today.isoformat(),)).fetchone()[0]
            d30 = (today + timedelta(days=30)).isoformat()
            urgentes = conn.execute("SELECT COUNT(*) FROM policies WHERE vig BETWEEN ? AND ?", (today.isoformat(), d30)).fetchone()[0]
            conn.close()
            return (
                f"Sistema PBSeg — {today.strftime('%d/%m/%Y')}\n"
                f"Banco: {total} apólices ({active} ativas, {urgentes} urgentes)\n\n"
                f"Comandos: status, vencidas, vencendo, comissões, sinistros, prêmio, alertas, "
                f"buscar [nome], [seguradora], caixa, executar, dry-run, pesquisar [tema web]"
            )
        except Exception:
            pass
    return "Comandos: status, alertas, vencendo, buscar [nome], executar, dry-run, pesquisar [tema]."


# ============================================================
# MAIN
# ============================================================

def main():
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    port = int(os.getenv("RPA_WEB_PORT", "5000"))
    print(f"[RPA Web] Servidor iniciado em http://localhost:{port}")
    print(f"[RPA Web] Acesse no navegador: http://localhost:{port}")

    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False, threaded=True)


if __name__ == "__main__":
    main()
