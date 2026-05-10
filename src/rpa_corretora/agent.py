"""Agente cognitivo PBSeg — Powered by Llama (Ollama).

Assistente inteligente completo com:
- LLM local (Llama 3.1 via Ollama) — open source, sem custo
- Execucao de tarefas do RPA
- Pesquisa web (DuckDuckGo)
- Consulta ao banco de dados operacional
- Geracao de dashboards e BI
- Predicoes e analise de dados
- Contexto completo do sistema
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import sys
import threading
import tkinter as tk
from datetime import date, datetime, timedelta
from pathlib import Path
from tkinter import scrolledtext
from urllib.request import Request, urlopen
from urllib.parse import quote_plus

BASE_DIR = Path(__file__).resolve().parents[2]
SRC_DIR = BASE_DIR / "src"
OUTPUTS_DIR = BASE_DIR / "outputs"
DB_PATH = OUTPUTS_DIR / "rpa_corretora.db"

# Cores
BG = "#0f0f1a"
SURFACE = "#1a1a2e"
CHAT_BG = "#0a0a14"
USER_BG = "#0ea5e9"
AGENT_BG = "#1e293b"
TEXT = "#e2e8f0"
TEXT_MUTED = "#94a3b8"
ACCENT = "#06b6d4"
BORDER = "#2d3748"

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1")

SYSTEM_PROMPT = """Você é o RPA PBSeg — assistente cognitivo da corretora de seguros PBSeg.
Você é inteligente, preciso e proativo. Responde em português brasileiro.

CAPACIDADES:
1. EXECUTAR o robô RPA (ciclo diário de automação)
2. PESQUISAR na web sobre seguros, seguradoras, notícias
3. CONSULTAR o banco de dados da corretora (apólices, comissões, sinistros, renovações)
4. GERAR dashboards, relatórios e análises de BI
5. FAZER predições baseadas nos dados históricos
6. RESPONDER dúvidas sobre processos internos da corretora

CONTEXTO DO SISTEMA:
- Corretora: PBSeg Seguros (Danielly Rodrigues)
- Carteira: ~442 apólices em 17 seguradoras
- Seguradoras: Yelum, Porto, Mapfre, Bradesco, Allianz, Suhai, Tokio, HDI, Azul, Itaú, Aliro, Justos, Zurich, Sul América, BP
- CRM: Segfy (automação web)
- Planilhas: SEGUROS PBSEG.xlsx, ACOMPANHAMENTO 2026.xlsx, FLUXO DE CAIXA.xlsx
- Comunicação: WhatsApp (Meta API), Gmail (IMAP), SMTP
- Agenda: Google Calendar (API)
- Banco: SQLite local (outputs/rpa_corretora.db)

REGRAS DE NEGÓCIO:
- Renovação: disparo exatamente 10 dias antes da vigência
- Boleto em atraso: >5 dias após vencimento
- Comissão pendente: STATUS PGTO em branco
- Sinistro/Endosso: flag na planilha ou detectado no portal

Quando o usuário pedir para EXECUTAR, responda que está iniciando e use [TOOL:EXECUTE_RPA].
Quando precisar de dados do banco, use [TOOL:QUERY_DB:sql_query].
Quando precisar pesquisar na web, use [TOOL:WEB_SEARCH:termo].
Quando precisar gerar dashboard/BI, use [TOOL:GENERATE_BI:descricao].

Seja conciso, útil e inteligente. Use emojis moderadamente."""


def _call_ollama(messages: list[dict], stream: bool = False) -> str:
    """Chama o Ollama local via API HTTP."""
    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": stream,
        "options": {"temperature": 0.7, "num_predict": 1024},
    }).encode("utf-8")

    req = Request(
        f"{OLLAMA_URL}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("message", {}).get("content", "").strip()
    except Exception as exc:
        return f"[Ollama indisponível: {exc}]\n\nDica: instale Ollama (ollama.com) e rode:\n  ollama pull {OLLAMA_MODEL}\n  ollama serve"


def _web_search(query: str, max_results: int = 5) -> str:
    """Pesquisa na web via DuckDuckGo HTML (sem API key)."""
    try:
        url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        results = []
        # Extrai resultados do HTML do DuckDuckGo
        snippets = re.findall(r'class="result__snippet">(.*?)</a>', html, re.DOTALL)
        titles = re.findall(r'class="result__a"[^>]*>(.*?)</a>', html, re.DOTALL)

        for i, (title, snippet) in enumerate(zip(titles[:max_results], snippets[:max_results])):
            clean_title = re.sub(r'<[^>]+>', '', title).strip()
            clean_snippet = re.sub(r'<[^>]+>', '', snippet).strip()
            if clean_title and clean_snippet:
                results.append(f"{i+1}. {clean_title}\n   {clean_snippet}")

        if results:
            return "\n\n".join(results)
        return "Nenhum resultado encontrado."
    except Exception as exc:
        return f"Erro na pesquisa: {exc}"


def _query_db(sql: str) -> str:
    """Executa query SQL no banco operacional."""
    if not DB_PATH.exists():
        return "Banco de dados não encontrado. Execute o ciclo primeiro."
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        # Sanitiza — só permite SELECT
        if not sql.strip().upper().startswith("SELECT"):
            return "Apenas consultas SELECT são permitidas."
        rows = conn.execute(sql).fetchall()
        conn.close()
        if not rows:
            return "Nenhum resultado."
        # Formata resultado
        cols = rows[0].keys()
        result = " | ".join(cols) + "\n" + "-" * 60 + "\n"
        for row in rows[:20]:
            result += " | ".join(str(row[c]) for c in cols) + "\n"
        if len(rows) > 20:
            result += f"\n... e mais {len(rows) - 20} registros."
        return result
    except Exception as exc:
        return f"Erro SQL: {exc}"


def _get_system_context() -> str:
    """Gera contexto atualizado do sistema para o LLM."""
    context = ""
    if DB_PATH.exists():
        try:
            conn = sqlite3.connect(str(DB_PATH))
            total = conn.execute("SELECT COUNT(*) FROM policies").fetchone()[0]
            pending = conn.execute("SELECT COUNT(*) FROM policies WHERE status_pgto = ''").fetchone()[0]
            sinistros = conn.execute("SELECT COUNT(*) FROM policies WHERE sinistro_open = 1").fetchone()[0]
            endossos = conn.execute("SELECT COUNT(*) FROM policies WHERE endosso_open = 1").fetchone()[0]

            today = date.today()
            future = (today + timedelta(days=30)).isoformat()
            expiring = conn.execute(
                "SELECT COUNT(*) FROM policies WHERE vig BETWEEN ? AND ?",
                (today.isoformat(), future)
            ).fetchone()[0]

            last_run = conn.execute("SELECT run_date, status FROM run_history ORDER BY started_at DESC LIMIT 1").fetchone()
            conn.close()

            context = (
                f"\n\nDADOS ATUAIS DA CARTEIRA (hoje {today.isoformat()}):\n"
                f"- Total apólices: {total}\n"
                f"- Comissões pendentes: {pending}\n"
                f"- Sinistros abertos: {sinistros}\n"
                f"- Endossos abertos: {endossos}\n"
                f"- Apólices vencendo em 30 dias: {expiring}\n"
            )
            if last_run:
                context += f"- Última execução: {last_run[0]} ({last_run[1]})\n"
        except Exception:
            pass
    return context


def _process_tool_calls(response: str) -> tuple[str, list[str]]:
    """Processa chamadas de ferramentas na resposta do LLM."""
    tool_results = []

    # [TOOL:EXECUTE_RPA]
    if "[TOOL:EXECUTE_RPA]" in response:
        tool_results.append("⚡ Iniciando execução do RPA...")
        response = response.replace("[TOOL:EXECUTE_RPA]", "")

    # [TOOL:QUERY_DB:sql]
    db_matches = re.findall(r'\[TOOL:QUERY_DB:(.*?)\]', response, re.DOTALL)
    for sql in db_matches:
        result = _query_db(sql.strip())
        tool_results.append(f"📊 Consulta:\n{result}")
        response = response.replace(f"[TOOL:QUERY_DB:{sql}]", "")

    # [TOOL:WEB_SEARCH:query]
    web_matches = re.findall(r'\[TOOL:WEB_SEARCH:(.*?)\]', response, re.DOTALL)
    for query in web_matches:
        result = _web_search(query.strip())
        tool_results.append(f"🌐 Pesquisa: {query.strip()}\n\n{result}")
        response = response.replace(f"[TOOL:WEB_SEARCH:{query}]", "")

    # [TOOL:GENERATE_BI:desc]
    bi_matches = re.findall(r'\[TOOL:GENERATE_BI:(.*?)\]', response, re.DOTALL)
    for desc in bi_matches:
        tool_results.append(f"📈 Gerando BI: {desc.strip()}")
        response = response.replace(f"[TOOL:GENERATE_BI:{desc}]", "")

    return response.strip(), tool_results


class LlamaAgent:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("RPA PBSeg")
        self.root.geometry("480x650+50+50")
        self.root.configure(bg=BG)
        self.root.attributes("-topmost", True)
        self.root.resizable(True, True)
        self.root.minsize(380, 500)

        self._process = None
        self._messages: list[dict] = [
            {"role": "system", "content": SYSTEM_PROMPT + _get_system_context()}
        ]
        self._drag_data = {"x": 0, "y": 0}

        self._build_ui()
        self._send_welcome()
        self.root.after(1500, self._show_proactive_alerts)

    def _build_ui(self) -> None:
        # Header
        header = tk.Frame(self.root, bg=SURFACE, height=50)
        header.pack(fill="x")
        header.pack_propagate(False)
        header.bind("<Button-1>", self._start_drag)
        header.bind("<B1-Motion>", self._do_drag)

        tk.Label(header, text="🤖", font=("Segoe UI", 16), bg=SURFACE, fg=ACCENT).pack(side="left", padx=(12, 4))
        title_frame = tk.Frame(header, bg=SURFACE)
        title_frame.pack(side="left")
        tk.Label(title_frame, text="RPA PBSeg", font=("Segoe UI", 12, "bold"), bg=SURFACE, fg=TEXT).pack(anchor="w")
        tk.Label(title_frame, text=f"Llama 3.1 • Open Source", font=("Segoe UI", 8), bg=SURFACE, fg=TEXT_MUTED).pack(anchor="w")

        # Botoes header
        btn_frame = tk.Frame(header, bg=SURFACE)
        btn_frame.pack(side="right", padx=8)
        tk.Button(btn_frame, text="─", font=("Segoe UI", 9), bg=SURFACE, fg=TEXT_MUTED, relief="flat", command=self.root.iconify, width=2).pack(side="left")
        tk.Button(btn_frame, text="✕", font=("Segoe UI", 9), bg=SURFACE, fg=TEXT_MUTED, relief="flat", command=self.root.destroy, width=2).pack(side="left")

        # Chat area
        self.chat_frame = tk.Frame(self.root, bg=CHAT_BG)
        self.chat_frame.pack(fill="both", expand=True)

        self.chat_text = scrolledtext.ScrolledText(
            self.chat_frame, font=("Segoe UI", 9), bg=CHAT_BG, fg=TEXT,
            insertbackground=TEXT, relief="flat", wrap="word", state="disabled",
            selectbackground=ACCENT, padx=12, pady=8,
        )
        self.chat_text.pack(fill="both", expand=True)
        self.chat_text.tag_configure("user", foreground=USER_BG, font=("Segoe UI", 9, "bold"))
        self.chat_text.tag_configure("agent", foreground=ACCENT)
        self.chat_text.tag_configure("tool", foreground="#10b981", font=("Consolas", 8))
        self.chat_text.tag_configure("alert", foreground="#f59e0b")

        # Input
        input_frame = tk.Frame(self.root, bg=SURFACE, height=55)
        input_frame.pack(fill="x")
        input_frame.pack_propagate(False)

        self.input_var = tk.StringVar()
        self.input_entry = tk.Entry(
            input_frame, textvariable=self.input_var, font=("Segoe UI", 10),
            bg="#0d1117", fg=TEXT, insertbackground=TEXT, relief="flat",
        )
        self.input_entry.pack(side="left", fill="both", expand=True, padx=(12, 5), pady=12)
        self.input_entry.bind("<Return>", self._on_send)

        tk.Button(
            input_frame, text="➤", font=("Segoe UI", 13), bg=ACCENT, fg="#fff",
            relief="flat", command=self._on_send, cursor="hand2", width=3,
        ).pack(side="right", padx=(0, 10), pady=10)

        # Quick actions
        actions_frame = tk.Frame(self.root, bg=BG)
        actions_frame.pack(fill="x")
        for text in ["▶ Executar", "📊 Status", "🔍 Pesquisar", "📈 Dashboard", "🚨 Alertas"]:
            btn = tk.Button(
                actions_frame, text=text, font=("Segoe UI", 8), bg=SURFACE, fg=TEXT_MUTED,
                relief="flat", padx=6, pady=3, cursor="hand2",
                command=lambda t=text.split(" ", 1)[1]: self._quick_action(t),
            )
            btn.pack(side="left", padx=2, pady=4)
            btn.bind("<Enter>", lambda e, b=btn: b.configure(bg="#2d3748"))
            btn.bind("<Leave>", lambda e, b=btn: b.configure(bg=SURFACE))

    def _add_message(self, text: str, tag: str = "agent") -> None:
        self.chat_text.configure(state="normal")
        prefix = "Você: " if tag == "user" else "🤖 "
        self.chat_text.insert("end", f"\n{prefix}", tag)
        self.chat_text.insert("end", f"{text}\n")
        self.chat_text.configure(state="disabled")
        self.chat_text.see("end")

    def _send_welcome(self) -> None:
        self._add_message(
            "Olá! Eu sou o RPA PBSeg — seu assistente cognitivo.\n\n"
            "Posso executar tarefas, pesquisar na web, analisar dados,\n"
            "gerar relatórios e responder qualquer dúvida.\n\n"
            "Exemplos:\n"
            "• \"executar\" — roda o ciclo completo\n"
            "• \"buscar Ana Silva\" — pesquisa segurado\n"
            "• \"pesquisar novidades seguro auto 2026\"\n"
            "• \"relatório Porto Seguro\" — análise da seguradora\n"
            "• \"quantas apólices vencem esse mês?\"\n"
            "• \"criar dashboard de comissões\"\n"
            "• Qualquer pergunta sobre seguros!",
            tag="agent",
        )

    def _show_proactive_alerts(self) -> None:
        if not DB_PATH.exists():
            return
        try:
            conn = sqlite3.connect(str(DB_PATH))
            pending = conn.execute("SELECT COUNT(*) FROM policies WHERE status_pgto = ''").fetchone()[0]
            sinistros = conn.execute("SELECT COUNT(*) FROM policies WHERE sinistro_open = 1").fetchone()[0]
            today = date.today()
            future = (today + timedelta(days=10)).isoformat()
            expiring = conn.execute("SELECT COUNT(*) FROM policies WHERE vig BETWEEN ? AND ?", (today.isoformat(), future)).fetchone()[0]
            conn.close()

            alerts = []
            if expiring > 0:
                alerts.append(f"🔴 {expiring} apólice(s) vencem em 10 dias")
            if sinistros > 0:
                alerts.append(f"🟠 {sinistros} sinistro(s) aberto(s)")
            if pending > 20:
                alerts.append(f"⚠️ {pending} comissões pendentes")

            if alerts:
                self._add_message("🚨 Pendências:\n" + "\n".join(alerts), tag="alert")
        except Exception:
            pass

    def _on_send(self, event=None) -> None:
        text = self.input_var.get().strip()
        if not text:
            return
        self.input_var.set("")
        self._add_message(text, tag="user")

        # Comandos diretos (sem LLM)
        lower = text.lower().strip()
        if lower in ("executar", "rodar", "run"):
            self._execute_rpa(dry_run=False)
            return
        if lower in ("dry-run", "testar", "validar"):
            self._execute_rpa(dry_run=True)
            return
        if lower == "parar" and self._process:
            self._process.terminate()
            self._add_message("⏹ Execução interrompida.", tag="agent")
            return
        if lower == "dashboard":
            self._open_dashboard()
            return

        # Envia para o LLM
        threading.Thread(target=self._ask_llm, args=(text,), daemon=True).start()

    def _ask_llm(self, question: str) -> None:
        # Atualiza contexto
        self._messages[0]["content"] = SYSTEM_PROMPT + _get_system_context()
        self._messages.append({"role": "user", "content": question})

        # Limita historico
        if len(self._messages) > 20:
            self._messages = [self._messages[0]] + self._messages[-10:]

        self.root.after(0, self._add_message, "⏳ Pensando...", "tool")

        response = _call_ollama(self._messages)
        self._messages.append({"role": "assistant", "content": response})

        # Processa tool calls
        clean_response, tool_results = _process_tool_calls(response)

        # Remove "Pensando..."
        self.root.after(0, self._remove_last_line)

        if tool_results:
            for result in tool_results:
                self.root.after(0, self._add_message, result, "tool")
                # Executa ações reais
                if "Iniciando execução" in result:
                    self.root.after(100, self._execute_rpa, False)

        if clean_response:
            self.root.after(0, self._add_message, clean_response, "agent")

    def _remove_last_line(self) -> None:
        self.chat_text.configure(state="normal")
        content = self.chat_text.get("1.0", "end")
        if "⏳ Pensando..." in content:
            idx = self.chat_text.search("⏳ Pensando...", "1.0", "end")
            if idx:
                self.chat_text.delete(f"{idx} linestart", f"{idx} lineend +1c")
        self.chat_text.configure(state="disabled")

    def _quick_action(self, action: str) -> None:
        self.input_var.set(action)
        self._on_send()

    def _execute_rpa(self, dry_run: bool = False) -> None:
        self._add_message(f"⚡ {'Dry-run' if dry_run else 'Execução'} iniciada...", tag="tool")

        cmd = [sys.executable, "-m", "rpa_corretora.main"]
        if dry_run:
            cmd.append("--dry-run")
        env = {**os.environ, "PYTHONPATH": str(SRC_DIR)}

        def run():
            try:
                self._process = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, cwd=str(BASE_DIR), env=env, bufsize=1,
                )
                for line in iter(self._process.stdout.readline, ""):
                    line = line.strip()
                    if line and any(kw in line.lower() for kw in ("alertas", "apolices", "erro", "sucesso", "dashboard", "relatorio", "[db]", "segfy")):
                        self.root.after(0, self._add_message, f"📋 {line}", "tool")
                self._process.wait()
                code = self._process.returncode
                self._process = None
                status = "✅ Concluído!" if code == 0 else f"❌ Erro (código {code})"
                self.root.after(0, self._add_message, status, "agent")
            except Exception as exc:
                self.root.after(0, self._add_message, f"❌ {exc}", "agent")
                self._process = None

        threading.Thread(target=run, daemon=True).start()

    def _open_dashboard(self) -> None:
        import webbrowser
        path = OUTPUTS_DIR / "dashboard_inteligente.html"
        if path.exists():
            webbrowser.open(str(path))
            self._add_message("📈 Dashboard aberto.", tag="agent")
        else:
            self._add_message("Execute o ciclo primeiro.", tag="agent")

    def _start_drag(self, event) -> None:
        self._drag_data = {"x": event.x, "y": event.y}

    def _do_drag(self, event) -> None:
        x = self.root.winfo_x() + (event.x - self._drag_data["x"])
        y = self.root.winfo_y() + (event.y - self._drag_data["y"])
        self.root.geometry(f"+{x}+{y}")

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    app = LlamaAgent()
    app.run()


if __name__ == "__main__":
    main()
