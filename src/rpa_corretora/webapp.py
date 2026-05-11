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


# ============================================================
# API ENDPOINTS
# ============================================================

@app.route("/")
def index():
    return send_from_directory(str(STATIC_DIR), "index.html")


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
    if _running:
        return jsonify({"error": "Já em execução"}), 409

    dry_run = request.json.get("dry_run", False) if request.json else False
    cmd = [sys.executable, "-m", "rpa_corretora.main"]
    if dry_run:
        cmd.append("--dry-run")

    env = {**os.environ, "PYTHONPATH": str(SRC_DIR)}
    _running = True

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
    return Response(stream(), mimetype="text/event-stream")


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
# HELPERS
# ============================================================

def _query_db_for_agent(question: str) -> str:
    if not DB_PATH.exists():
        return ""
    q = question.lower()
    try:
        conn = sqlite3.connect(str(DB_PATH))

        if any(w in q for w in ("status", "carteira", "quantas", "total")):
            total = conn.execute("SELECT COUNT(*) FROM policies").fetchone()[0]
            pending = conn.execute("SELECT COUNT(*) FROM policies WHERE status_pgto = ''").fetchone()[0]
            sin = conn.execute("SELECT COUNT(*) FROM policies WHERE sinistro_open = 1").fetchone()[0]
            conn.close()
            return f"📊 Carteira:\n• Apólices: {total}\n• Comissões pendentes: {pending}\n• Sinistros abertos: {sin}"

        if any(w in q for w in ("comiss", "pendente", "pago")):
            paid = conn.execute("SELECT COUNT(*) FROM policies WHERE status_pgto != ''").fetchone()[0]
            pending = conn.execute("SELECT COUNT(*) FROM policies WHERE status_pgto = ''").fetchone()[0]
            valor = conn.execute("SELECT COALESCE(SUM(comissao), 0) FROM policies WHERE status_pgto = ''").fetchone()[0]
            conn.close()
            return f"💰 Comissões:\n• Pagas: {paid}\n• Pendentes: {pending}\n• Valor pendente: R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

        if any(w in q for w in ("alerta", "critico", "urgente", "pendencia")):
            alerts = conn.execute("SELECT severity, message FROM alerts ORDER BY created_at DESC LIMIT 5").fetchall()
            conn.close()
            if not alerts:
                return "✅ Nenhum alerta recente."
            result = "🚨 Alertas recentes:\n"
            for sev, msg in alerts:
                icon = "🔴" if sev in ("CRITICA", "ALTA") else "🟡"
                result += f"{icon} [{sev}] {msg[:60]}\n"
            return result

        if any(w in q for w in ("vencendo", "vencer", "renovar")):
            today = date.today()
            future = (today + timedelta(days=30)).isoformat()
            rows = conn.execute("SELECT insured_name, insurer, vig FROM policies WHERE vig BETWEEN ? AND ? ORDER BY vig LIMIT 5", (today.isoformat(), future)).fetchall()
            conn.close()
            if not rows:
                return "✅ Nenhuma apólice vencendo em 30 dias."
            result = f"⚠️ {len(rows)} apólice(s) vencendo:\n"
            for name, ins, vig in rows:
                result += f"• {name} ({ins}) — {vig}\n"
            return result

        # Pesquisa por nome
        if any(w in q for w in ("buscar", "procurar", "encontrar")):
            term = re.sub(r"^(buscar|procurar|encontrar)\s+", "", q).strip()
            if len(term) >= 3:
                rows = conn.execute("SELECT insured_name, insurer, premio_total, status_pgto, vehicle_item FROM policies WHERE UPPER(insured_name) LIKE ? LIMIT 3", (f"%{term.upper()}%",)).fetchall()
                conn.close()
                if rows:
                    result = f"🔍 Resultados para \"{term}\":\n\n"
                    for name, ins, premio, pgto, vehicle in rows:
                        result += f"• {name} ({ins})\n  Prêmio: R$ {premio:,.2f} | {pgto or 'PENDENTE'}\n".replace(",", "X").replace(".", ",").replace("X", ".")
                        if vehicle:
                            result += f"  Veículo: {vehicle}\n"
                    return result

        # Relatório por seguradora
        known = ["yelum", "porto", "mapfre", "bradesco", "allianz", "suhai", "tokio", "hdi", "azul"]
        for ins in known:
            if ins in q:
                total = conn.execute("SELECT COUNT(*) FROM policies WHERE UPPER(insurer) LIKE ?", (f"%{ins.upper()}%",)).fetchone()[0]
                premio = conn.execute("SELECT COALESCE(SUM(premio_total), 0) FROM policies WHERE UPPER(insurer) LIKE ?", (f"%{ins.upper()}%",)).fetchone()[0]
                conn.close()
                return f"📊 {ins.upper()}:\n• Apólices: {total}\n• Prêmio: R$ {premio:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

        conn.close()
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
    q = question.lower()
    answers = {
        "sobre": "O RPA PBSeg automatiza toda a operação da corretora: planilhas, Segfy, portais, WhatsApp, agenda, e-mails.",
        "ajuda": "Comandos: executar, dry-run, status, alertas, vencendo, buscar [nome], relatório [seguradora], pesquisar [tema]",
    }
    for key, answer in answers.items():
        if key in q:
            return answer
    return "Posso ajudar com: status, alertas, buscar segurado, relatório por seguradora, pesquisar na web, executar o ciclo. O que precisa?"


# ============================================================
# MAIN
# ============================================================

def main():
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    port = int(os.getenv("RPA_WEB_PORT", "5000"))
    print(f"[RPA Web] Servidor iniciado em http://localhost:{port}")
    print(f"[RPA Web] Abrindo navegador...")

    # Abre no navegador
    import webbrowser
    threading.Timer(1.5, lambda: webbrowser.open(f"http://localhost:{port}")).start()

    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
