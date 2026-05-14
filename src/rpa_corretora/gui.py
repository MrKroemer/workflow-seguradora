"""GUI profissional para o RPA Corretora PBSeg.

Interface grafica com:
- Execucao do ciclo diario com monitoramento em tempo real
- Visualizacao de status de todas as integracoes
- Log de execucao ao vivo
- Acesso rapido ao dashboard, relatorios e banco de dados
- Configuracoes do .env
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import sys
import threading
import traceback
import webbrowser
import tkinter as tk
from datetime import datetime, date, timedelta
from pathlib import Path
from tkinter import ttk, scrolledtext, messagebox


# Cores do tema escuro
BG = "#0f1419"
SURFACE = "#1a2332"
SURFACE2 = "#243447"
ACCENT = "#0ea5e9"
ACCENT2 = "#06b6d4"
SUCCESS = "#10b981"
WARNING = "#f59e0b"
DANGER = "#ef4444"
TEXT = "#e2e8f0"
TEXT_MUTED = "#94a3b8"
BORDER = "#334155"

# Caminho base do projeto
BASE_DIR = Path(__file__).resolve().parents[2]
SRC_DIR = BASE_DIR / "src"
OUTPUTS_DIR = BASE_DIR / "outputs"
DB_PATH = OUTPUTS_DIR / "rpa_corretora.db"


def _global_exc_handler(exc_type, exc_val, exc_tb):
    msg = "".join(traceback.format_exception(exc_type, exc_val, exc_tb))
    try:
        OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
        (OUTPUTS_DIR / "gui_crash.log").open("a").write(f"\n[{datetime.now()}]\n{msg}\n")
    except Exception:
        pass


sys.excepthook = _global_exc_handler


class RPAApp:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("RPA Corretora PBSeg")
        self.root.geometry("1100x720")
        self.root.configure(bg=BG)
        self.root.minsize(900, 600)

        self.running = False
        self.process: subprocess.Popen | None = None

        self._setup_styles()
        self._build_ui()
        self._load_status()
        self._tick_clock()
        self._animate_dot()

    def _setup_styles(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(".", background=BG, foreground=TEXT, fieldbackground=SURFACE)
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 10))
        style.configure("Title.TLabel", font=("Segoe UI", 18, "bold"), foreground=ACCENT)
        style.configure("Subtitle.TLabel", font=("Segoe UI", 9), foreground=TEXT_MUTED)
        style.configure("Status.TLabel", font=("Segoe UI", 9, "bold"))
        style.configure("TButton", font=("Segoe UI", 10, "bold"), padding=8)
        style.configure("Accent.TButton", background=ACCENT, foreground="#fff")
        style.configure("Danger.TButton", background=DANGER, foreground="#fff")
        style.configure("Success.TButton", background=SUCCESS, foreground="#fff")
        style.configure("TNotebook", background=BG)
        style.configure("TNotebook.Tab", background=SURFACE, foreground=TEXT, padding=[12, 6])
        style.map("TNotebook.Tab", background=[("selected", ACCENT)])
        style.configure(
            "Run.Horizontal.TProgressbar",
            troughcolor=SURFACE2, background=ACCENT,
            lightcolor=ACCENT, darkcolor=ACCENT, bordercolor=SURFACE2,
        )

    def _build_ui(self) -> None:
        # Header
        header = ttk.Frame(self.root)
        header.pack(fill="x", padx=20, pady=(15, 5))

        ttk.Label(header, text="⚡ RPA Corretora PBSeg", style="Title.TLabel").pack(side="left")
        ttk.Label(header, text="Automação inteligente de corretora de seguros", style="Subtitle.TLabel").pack(
            side="left", padx=(15, 0), pady=(5, 0)
        )

        btn_frame = ttk.Frame(header)
        btn_frame.pack(side="right")

        self.btn_run = tk.Button(
            btn_frame, text="▶ Executar", font=("Segoe UI", 11, "bold"),
            bg=SUCCESS, fg="#fff", relief="flat", padx=16, pady=6,
            command=self._start_execution, cursor="hand2",
        )
        self.btn_run.pack(side="left", padx=4)

        self.btn_stop = tk.Button(
            btn_frame, text="⏹ Parar", font=("Segoe UI", 11, "bold"),
            bg=DANGER, fg="#fff", relief="flat", padx=16, pady=6,
            command=self._stop_execution, cursor="hand2", state="disabled",
        )
        self.btn_stop.pack(side="left", padx=4)

        self.btn_dryrun = tk.Button(
            btn_frame, text="🧪 Dry-Run", font=("Segoe UI", 10),
            bg=SURFACE2, fg=TEXT, relief="flat", padx=12, pady=6,
            command=self._start_dryrun, cursor="hand2",
        )
        self.btn_dryrun.pack(side="left", padx=4)

        self.btn_agent = tk.Button(
            btn_frame, text="🤖 Agente IA", font=("Segoe UI", 10),
            bg="#7c3aed", fg="#fff", relief="flat", padx=12, pady=6,
            command=self._toggle_agent, cursor="hand2",
        )
        self.btn_agent.pack(side="left", padx=4)

        # Estado do agente embutido
        self._agent_visible = False
        self._agent_frame = None
        self._agent_messages: list[dict] = []

        # FAB
        self._fab = tk.Button(
            self.root, text="🤖", font=("Segoe UI", 16),
            bg="#7c3aed", fg="#fff", relief="flat",
            width=3, height=1, cursor="hand2",
            command=self._toggle_agent,
            activebackground="#5b21b6", activeforeground="#fff",
        )
        self._fab.place(relx=1.0, rely=1.0, anchor="se", x=-25, y=-45)
        self._fab.lift()
        self._fab.bind("<Enter>", lambda e: self._fab.configure(bg="#5b21b6"))
        self._fab.bind("<Leave>", lambda e: self._fab.configure(bg="#7c3aed"))

        sep = tk.Frame(self.root, height=1, bg=BORDER)
        sep.pack(fill="x", padx=20, pady=8)

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=20, pady=(0, 15))

        self._build_execution_tab()
        self._build_status_tab()
        self._build_news_tab()
        self._build_tools_tab()

        sb_frame = tk.Frame(self.root, bg=SURFACE)
        sb_frame.pack(fill="x", side="bottom")

        self._dot_canvas = tk.Canvas(sb_frame, width=10, height=10, bg=SURFACE, highlightthickness=0)
        self._dot_canvas.pack(side="left", padx=(10, 4), pady=4)
        self._dot_oval = self._dot_canvas.create_oval(2, 2, 9, 9, fill=TEXT_MUTED, outline="")

        self.status_bar = tk.Label(
            sb_frame, text="Pronto para execução", font=("Segoe UI", 9),
            bg=SURFACE, fg=TEXT_MUTED, anchor="w", pady=4,
        )
        self.status_bar.pack(side="left", fill="x", expand=True)

        self._clock_label = tk.Label(
            sb_frame, text="", font=("Consolas", 9),
            bg=SURFACE, fg=TEXT_MUTED, padx=12, pady=4,
        )
        self._clock_label.pack(side="right")

    def _build_execution_tab(self) -> None:
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="  Execução  ")

        stages_frame = tk.Frame(tab, bg=SURFACE, relief="flat", bd=0)
        stages_frame.pack(fill="x", padx=10, pady=10)

        tk.Label(
            stages_frame, text="Etapas do Ciclo",
            font=("Segoe UI", 11, "bold"), bg=SURFACE, fg=TEXT,
        ).pack(anchor="w", padx=10, pady=(8, 4))

        self.stage_labels = {}
        stages = [
            ("google_calendar", "📅 Google Calendar"),
            ("microsoft_todo", "✅ Microsoft To Do"),
            ("gmail", "📧 Gmail IMAP"),
            ("spreadsheets", "📊 Planilhas"),
            ("segfy", "🔄 Segfy CRM"),
            ("insurer_portals", "🌐 Portais Seguradoras"),
            ("whatsapp", "💬 WhatsApp"),
            ("dashboard", "📈 Dashboard"),
        ]
        for key, label in stages:
            row = tk.Frame(stages_frame, bg=SURFACE)
            row.pack(fill="x", padx=10, pady=2)
            indicator = tk.Label(row, text="⬜", font=("Segoe UI", 10), bg=SURFACE, fg=TEXT_MUTED)
            indicator.pack(side="left")
            tk.Label(row, text=f"  {label}", font=("Segoe UI", 9), bg=SURFACE, fg=TEXT).pack(side="left")
            status_lbl = tk.Label(row, text="", font=("Segoe UI", 8), bg=SURFACE, fg=TEXT_MUTED)
            status_lbl.pack(side="right", padx=10)
            self.stage_labels[key] = (indicator, status_lbl)

        log_frame = tk.Frame(tab, bg=SURFACE)
        log_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        tk.Label(
            log_frame, text="Log de Execução",
            font=("Segoe UI", 11, "bold"), bg=SURFACE, fg=TEXT,
        ).pack(anchor="w", padx=10, pady=(8, 4))

        self._progress = ttk.Progressbar(
            log_frame, mode="indeterminate",
            style="Run.Horizontal.TProgressbar", length=100,
        )
        self._progress.pack(fill="x", padx=10, pady=(0, 4))
        self._progress.pack_forget()

        self.log_text = scrolledtext.ScrolledText(
            log_frame, font=("Consolas", 9), bg="#0d1117", fg="#c9d1d9",
            insertbackground=TEXT, relief="flat", height=12, wrap="word",
        )
        self.log_text.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.log_text.tag_configure("ts",   foreground="#2a3d55")
        self.log_text.tag_configure("ok",   foreground=SUCCESS)
        self.log_text.tag_configure("warn", foreground=WARNING)
        self.log_text.tag_configure("err",  foreground=DANGER)
        self.log_text.tag_configure("info", foreground=ACCENT2)

    def _build_status_tab(self) -> None:
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="  Status  ")

        kpi_frame = tk.Frame(tab, bg=BG)
        kpi_frame.pack(fill="x", padx=10, pady=10)

        self.kpi_widgets = {}
        kpis = [
            ("policies", "Apólices", "0", ACCENT),
            ("alerts", "Alertas", "0", WARNING),
            ("commissions", "Comissões Pend.", "0", DANGER),
            ("incidents", "Incidentes", "0", DANGER),
        ]
        for i, (key, label, value, color) in enumerate(kpis):
            kpi_frame.columnconfigure(i, weight=1)
            outer = tk.Frame(kpi_frame, bg=color)
            outer.grid(row=0, column=i, padx=5, sticky="nsew")
            card = tk.Frame(outer, bg=SURFACE, padx=12, pady=10)
            card.pack(fill="both", expand=True, padx=(3, 0))
            tk.Label(card, text=label, font=("Segoe UI", 8), bg=SURFACE, fg=TEXT_MUTED).pack(anchor="w")
            val_lbl = tk.Label(card, text=value, font=("Segoe UI", 22, "bold"), bg=SURFACE, fg=color)
            val_lbl.pack(anchor="w")
            self.kpi_widgets[key] = val_lbl

        int_frame = tk.Frame(tab, bg=SURFACE)
        int_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        tk.Label(
            int_frame, text="Integrações",
            font=("Segoe UI", 11, "bold"), bg=SURFACE, fg=TEXT,
        ).pack(anchor="w", padx=10, pady=(8, 4))

        self.integration_labels = {}
        integrations = [
            ("calendar", "Google Calendar", "GOOGLE_API"),
            ("gmail", "Gmail IMAP", "GMAIL_IMAP"),
            ("todo", "Microsoft To Do", "DESKTOP_APP"),
            ("segfy", "Segfy CRM", "WEB_AUTOMATION"),
            ("portals", "Portais (9)", "WEB_MULTI"),
            ("whatsapp", "WhatsApp", "HTTP_API"),
            ("email", "E-mail SMTP", "SMTP"),
        ]
        for key, label, mode in integrations:
            row = tk.Frame(int_frame, bg=SURFACE)
            row.pack(fill="x", padx=10, pady=3)
            tk.Label(row, text=f"  {label}", font=("Segoe UI", 9), bg=SURFACE, fg=TEXT).pack(side="left")
            mode_lbl = tk.Label(row, text=mode, font=("Segoe UI", 8, "bold"), bg=SURFACE, fg=SUCCESS)
            mode_lbl.pack(side="right", padx=10)
            self.integration_labels[key] = mode_lbl

    def _build_news_tab(self) -> None:
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="  Notícias  ")

        header = tk.Frame(tab, bg=SURFACE)
        header.pack(fill="x", padx=10, pady=10)
        tk.Label(
            header, text="📰 Notícias e Informações do Mercado",
            font=("Segoe UI", 11, "bold"), bg=SURFACE, fg=TEXT,
        ).pack(anchor="w", padx=10, pady=8)
        tk.Button(
            header, text="🔄 Atualizar", font=("Segoe UI", 9),
            bg=SURFACE2, fg=TEXT, relief="flat", padx=10, pady=4,
            command=self._refresh_news, cursor="hand2",
        ).pack(anchor="e", padx=10, pady=(0, 8))

        self.news_text = scrolledtext.ScrolledText(
            tab, font=("Segoe UI", 9), bg="#0a0a14", fg=TEXT,
            insertbackground=TEXT, relief="flat", wrap="word", state="disabled",
        )
        self.news_text.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.news_text.tag_configure("title", font=("Segoe UI", 10, "bold"), foreground=ACCENT)
        self.news_text.tag_configure("source", foreground=TEXT_MUTED, font=("Segoe UI", 8))

        self.root.after(2000, self._refresh_news)

    def _build_tools_tab(self) -> None:
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="  Ferramentas  ")

        tools_frame = tk.Frame(tab, bg=BG)
        tools_frame.pack(fill="both", expand=True, padx=10, pady=10)

        buttons = [
            ("📈 Abrir Dashboard Inteligente", self._open_dashboard),
            ("📊 Abrir Dashboard Operacional", self._open_dashboard_basic),
            ("🗄️ Abrir Banco de Dados", self._open_database),
            ("📁 Abrir Pasta de Relatórios", self._open_outputs),
            ("🔧 Configurar Chrome", self._configure_chrome),
            ("📋 Ver Último Relatório JSON", self._open_last_report),
            ("🌐 Abrir Segfy", self._open_segfy),
            ("📅 Abrir Google Agenda", self._open_calendar),
        ]

        for text, command in buttons:
            btn = tk.Button(
                tools_frame, text=text, font=("Segoe UI", 10),
                bg=SURFACE, fg=TEXT, relief="flat", padx=15, pady=8,
                command=command, cursor="hand2", anchor="w",
            )
            btn.pack(fill="x", pady=3)
            btn.bind("<Enter>", lambda e, b=btn: b.configure(bg=SURFACE2))
            btn.bind("<Leave>", lambda e, b=btn: b.configure(bg=SURFACE))

    # --- Execução ---

    def _start_execution(self) -> None:
        self._run_rpa(dry_run=False)

    def _start_dryrun(self) -> None:
        self._run_rpa(dry_run=True)

    def _run_rpa(self, dry_run: bool) -> None:
        if self.running:
            return
        self.running = True
        self.btn_run.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.btn_dryrun.configure(state="disabled")
        self.log_text.delete("1.0", "end")
        self._reset_stages()
        mode = "DRY-RUN" if dry_run else "PRODUÇÃO"
        self._log(f"[{datetime.now().strftime('%H:%M:%S')}] Iniciando ciclo ({mode})...\n")
        self.status_bar.configure(text=f"⚡ Executando ciclo ({mode})...", fg=WARNING)
        self._dot_canvas.itemconfig(self._dot_oval, fill=WARNING)
        self._progress.pack(fill="x", padx=10, pady=(0, 4))
        self._progress.start(14)

        cmd = [sys.executable, "-m", "rpa_corretora.main"]
        if dry_run:
            cmd.append("--dry-run")

        env = os.environ.copy()
        env["PYTHONPATH"] = str(SRC_DIR)

        threading.Thread(target=self._execute_process, args=(cmd, env), daemon=True).start()

    def _execute_process(self, cmd: list[str], env: dict) -> None:
        try:
            self.process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, cwd=str(BASE_DIR), env=env, bufsize=1,
            )
            for line in iter(self.process.stdout.readline, ""):
                self.root.after(0, self._process_line, line)
            self.process.wait()
            self.root.after(0, self._execution_finished, self.process.returncode)
        except Exception as exc:
            self.root.after(0, self._log, f"\n[ERRO] {exc}\n")
            self.root.after(0, self._execution_finished, 1)

    def _process_line(self, line: str) -> None:
        self._log(line)
        lower = line.lower()
        for key in self.stage_labels:
            if key.replace("_", " ") in lower or key in lower:
                if "falha" in lower or "erro" in lower:
                    self._update_stage(key, "❌", DANGER)
                elif "conclu" in lower or "ok" in lower or "sucesso" in lower:
                    self._update_stage(key, "✅", SUCCESS)
                else:
                    self._update_stage(key, "🔄", ACCENT)

    def _execution_finished(self, exit_code: int) -> None:
        self.running = False
        self.process = None
        self.btn_run.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self.btn_dryrun.configure(state="normal")

        self._progress.stop()
        self._progress.pack_forget()

        if exit_code == 0:
            self._log(f"\n[{datetime.now().strftime('%H:%M:%S')}] ✅ Ciclo finalizado com sucesso.\n")
            self.status_bar.configure(text="✅ Ciclo finalizado com sucesso", fg=SUCCESS)
            self._dot_canvas.itemconfig(self._dot_oval, fill=SUCCESS)
        else:
            self._log(f"\n[{datetime.now().strftime('%H:%M:%S')}] ❌ Ciclo finalizado com erros (código {exit_code}).\n")
            self.status_bar.configure(text=f"❌ Erro no ciclo (código {exit_code})", fg=DANGER)
            self._dot_canvas.itemconfig(self._dot_oval, fill=DANGER)

        self._load_status()

    def _stop_execution(self) -> None:
        if self.process:
            self.process.terminate()
            self._log("\n[PARADO] Execução interrompida pelo usuário.\n")

    def _log(self, text: str) -> None:
        tag = ""
        if re.search(r"✅|conclu|sucesso|\[OK\]", text, re.I): tag = "ok"
        elif re.search(r"AVISO|alerta|WARN", text, re.I):       tag = "warn"
        elif re.search(r"ERRO|falha|ERROR|exception", text, re.I): tag = "err"
        elif re.search(r"Iniciando|Segfy|Chrome|Playwright", text, re.I): tag = "info"

        ts_m = re.match(r"(\[\d{2}:\d{2}:\d{2}\])(.*)", text, re.DOTALL)
        if ts_m:
            self.log_text.insert("end", ts_m.group(1), "ts")
            self.log_text.insert("end", ts_m.group(2), tag)
        else:
            self.log_text.insert("end", text, tag)
        self.log_text.see("end")

    def _reset_stages(self) -> None:
        for _key, (indicator, status_lbl) in self.stage_labels.items():
            indicator.configure(text="⬜", fg=TEXT_MUTED)
            status_lbl.configure(text="")

    def _update_stage(self, key: str, icon: str, color: str) -> None:
        if key in self.stage_labels:
            indicator, _status_lbl = self.stage_labels[key]
            indicator.configure(text=icon, fg=color)

    def _load_status(self) -> None:
        if not DB_PATH.exists():
            return
        try:
            conn = sqlite3.connect(str(DB_PATH))
            policies = conn.execute("SELECT COUNT(*) FROM policies").fetchone()[0]
            alerts = conn.execute("SELECT COUNT(*) FROM alerts WHERE run_date = date('now')").fetchone()[0]
            pending = conn.execute("SELECT COUNT(*) FROM policies WHERE status_pgto = ''").fetchone()[0]
            incidents = conn.execute(
                "SELECT COUNT(*) FROM policies WHERE sinistro_open = 1 OR endosso_open = 1"
            ).fetchone()[0]
            conn.close()

            self.kpi_widgets["policies"].configure(text=str(policies))
            self.kpi_widgets["alerts"].configure(text=str(alerts))
            self.kpi_widgets["commissions"].configure(text=str(pending))
            self.kpi_widgets["incidents"].configure(text=str(incidents))
        except Exception:
            pass

    # --- Ferramentas ---

    def _open_dashboard(self) -> None:
        path = OUTPUTS_DIR / "dashboard_inteligente.html"
        if path.exists():
            webbrowser.open(str(path))
        else:
            messagebox.showinfo("Dashboard", "Execute o ciclo primeiro para gerar o dashboard.")

    def _open_dashboard_basic(self) -> None:
        path = OUTPUTS_DIR / "dashboard_latest.html"
        if path.exists():
            webbrowser.open(str(path))
        else:
            messagebox.showinfo("Dashboard", "Execute o ciclo primeiro para gerar o dashboard.")

    def _open_database(self) -> None:
        path = OUTPUTS_DIR / "rpa_corretora.db"
        if path.exists():
            os.startfile(str(path)) if sys.platform == "win32" else webbrowser.open(str(path))
        else:
            messagebox.showinfo("Banco", "Execute o ciclo primeiro para criar o banco de dados.")

    def _open_outputs(self) -> None:
        OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(str(OUTPUTS_DIR))
        else:
            webbrowser.open(str(OUTPUTS_DIR))

    def _configure_chrome(self) -> None:
        script = BASE_DIR / "scripts" / "configurar_chrome.bat"
        if script.exists() and sys.platform == "win32":
            subprocess.Popen(["cmd", "/c", str(script)], cwd=str(BASE_DIR))
        else:
            messagebox.showinfo("Chrome", "Execute scripts/configurar_chrome.bat manualmente.")

    def _open_last_report(self) -> None:
        reports = sorted(OUTPUTS_DIR.glob("relatorio_execucao_*.json"), reverse=True)
        if reports:
            if sys.platform == "win32":
                os.startfile(str(reports[0]))
            else:
                webbrowser.open(str(reports[0]))
        else:
            messagebox.showinfo("Relatório", "Nenhum relatório encontrado.")

    def _open_segfy(self) -> None:
        webbrowser.open("https://app.segfy.com")

    def _open_calendar(self) -> None:
        webbrowser.open("https://calendar.google.com")

    # --- Agente IA ---

    def _toggle_agent(self) -> None:
        if self._agent_visible:
            self._agent_frame.place_forget()
            self._agent_visible = False
            self.btn_agent.configure(bg="#7c3aed")
            self._fab.place(relx=1.0, rely=1.0, anchor="se", x=-25, y=-45)
            self._fab.lift()
            return

        if self._agent_frame is None:
            self._build_agent_panel()

        self._fab.place_forget()
        self._agent_frame.place(relx=1.0, rely=1.0, anchor="se", x=-20, y=-40, width=380, height=480)
        self._agent_frame.lift()
        self._agent_visible = True
        self.btn_agent.configure(bg="#5b21b6")

        if not self._agent_messages:
            self._agent_add_message(
                "🤖 Olá! Sou o agente IA da PBSeg.\n\n"
                "Pergunte qualquer coisa ou use comandos:\n"
                "• \"executar\" — roda o ciclo\n"
                "• \"buscar [nome]\" — pesquisa segurado\n"
                "• \"relatório [seguradora]\"\n"
                "• \"pesquisar [tema]\" — busca na web\n"
                "• \"alertas\" — pendências",
                is_user=False,
            )

    def _build_agent_panel(self) -> None:
        self._agent_frame = tk.Frame(
            self.root, bg="#0f0f1a", relief="raised", bd=1,
            highlightbackground="#2d3748", highlightthickness=1,
        )

        header = tk.Frame(self._agent_frame, bg="#1a1a2e", height=40)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(
            header, text="🤖 Agente IA",
            font=("Segoe UI", 10, "bold"), bg="#1a1a2e", fg="#06b6d4",
        ).pack(side="left", padx=10)
        tk.Label(header, text="Llama 3.1", font=("Segoe UI", 8), bg="#1a1a2e", fg="#94a3b8").pack(side="left")
        tk.Button(
            header, text="✕", font=("Segoe UI", 9), bg="#1a1a2e", fg="#94a3b8",
            relief="flat", command=self._toggle_agent, cursor="hand2",
        ).pack(side="right", padx=8)

        self._agent_chat = scrolledtext.ScrolledText(
            self._agent_frame, font=("Segoe UI", 9), bg="#0a0a14", fg=TEXT,
            insertbackground=TEXT, relief="flat", wrap="word", state="disabled",
            height=18, padx=10, pady=8,
        )
        self._agent_chat.pack(fill="both", expand=True, padx=4, pady=(0, 4))
        self._agent_chat.tag_configure("user", foreground="#0ea5e9", font=("Segoe UI", 9, "bold"))
        self._agent_chat.tag_configure("bot", foreground="#06b6d4")
        self._agent_chat.tag_configure("tool", foreground="#10b981", font=("Consolas", 8))

        input_frame = tk.Frame(self._agent_frame, bg="#1a1a2e")
        input_frame.pack(fill="x", padx=4, pady=(0, 4))
        self._agent_input = tk.Entry(
            input_frame, font=("Segoe UI", 9), bg="#0d1117", fg=TEXT,
            insertbackground=TEXT, relief="flat",
        )
        self._agent_input.pack(side="left", fill="x", expand=True, padx=(8, 4), pady=6)
        self._agent_input.bind("<Return>", self._agent_on_send)
        tk.Button(
            input_frame, text="➤", font=("Segoe UI", 11), bg="#06b6d4", fg="#fff",
            relief="flat", command=self._agent_on_send, cursor="hand2", width=3,
        ).pack(side="right", padx=(0, 6), pady=4)

        actions = tk.Frame(self._agent_frame, bg="#0f0f1a")
        actions.pack(fill="x", padx=4, pady=(0, 6))
        for label in ["Executar", "Status", "Alertas", "Dashboard"]:
            tk.Button(
                actions, text=label, font=("Segoe UI", 8), bg="#1a1a2e", fg="#94a3b8",
                relief="flat", padx=6, pady=2, cursor="hand2",
                command=lambda t=label: self._agent_quick(t),
            ).pack(side="left", padx=2)

    def _agent_add_message(self, text: str, is_user: bool = False) -> None:
        self._agent_chat.configure(state="normal")
        tag = "user" if is_user else "bot"
        prefix = "Você: " if is_user else "🤖 "
        self._agent_chat.insert("end", f"\n{prefix}", tag)
        self._agent_chat.insert("end", f"{text}\n")
        self._agent_chat.configure(state="disabled")
        self._agent_chat.see("end")
        self._agent_messages.append({"role": "user" if is_user else "assistant", "content": text})

    def _agent_on_send(self, event=None) -> None:
        text = self._agent_input.get().strip()
        if not text:
            return
        self._agent_input.delete(0, "end")
        self._agent_add_message(text, is_user=True)

        lower = text.lower()
        if lower in ("executar", "rodar"):
            self._agent_add_message("⚡ Iniciando ciclo...", is_user=False)
            self._start_execution()
            return
        if lower in ("dry-run", "testar"):
            self._agent_add_message("🧪 Dry-run iniciado...", is_user=False)
            self._start_dryrun()
            return
        if lower == "dashboard":
            self._open_dashboard()
            self._agent_add_message("📈 Dashboard aberto.", is_user=False)
            return
        if lower in ("status", "carteira"):
            self._agent_show_status()
            return
        if lower in ("alertas", "pendencias"):
            self._agent_show_alerts()
            return

        threading.Thread(target=self._agent_ask_llm, args=(text,), daemon=True).start()

    def _agent_quick(self, action: str) -> None:
        self._agent_input.delete(0, "end")
        self._agent_input.insert(0, action)
        self._agent_on_send()

    def _agent_show_status(self) -> None:
        if not DB_PATH.exists():
            self._agent_add_message("Execute o ciclo primeiro.", is_user=False)
            return
        try:
            conn = sqlite3.connect(str(DB_PATH))
            total = conn.execute("SELECT COUNT(*) FROM policies").fetchone()[0]
            pending = conn.execute("SELECT COUNT(*) FROM policies WHERE status_pgto = ''").fetchone()[0]
            sin = conn.execute("SELECT COUNT(*) FROM policies WHERE sinistro_open = 1").fetchone()[0]
            conn.close()
            self._agent_add_message(
                f"📊 Carteira:\n• Apólices: {total}\n• Comissões pendentes: {pending}\n• Sinistros: {sin}",
                is_user=False,
            )
        except Exception:
            self._agent_add_message("Erro ao consultar banco.", is_user=False)

    def _agent_show_alerts(self) -> None:
        if not DB_PATH.exists():
            self._agent_add_message("Execute o ciclo primeiro.", is_user=False)
            return
        try:
            conn = sqlite3.connect(str(DB_PATH))
            pending = conn.execute("SELECT COUNT(*) FROM policies WHERE status_pgto = ''").fetchone()[0]
            sin = conn.execute("SELECT COUNT(*) FROM policies WHERE sinistro_open = 1").fetchone()[0]
            end = conn.execute("SELECT COUNT(*) FROM policies WHERE endosso_open = 1").fetchone()[0]
            today = date.today()
            future = (today + timedelta(days=10)).isoformat()
            expiring = conn.execute(
                "SELECT COUNT(*) FROM policies WHERE vig BETWEEN ? AND ?",
                (today.isoformat(), future),
            ).fetchone()[0]
            conn.close()
            msg = "🚨 Pendências:\n"
            if expiring:
                msg += f"🔴 {expiring} apólice(s) vencem em 10 dias\n"
            if sin:
                msg += f"🟠 {sin} sinistro(s) aberto(s)\n"
            if end:
                msg += f"🟡 {end} endosso(s) pendente(s)\n"
            if pending > 20:
                msg += f"⚠️ {pending} comissões pendentes\n"
            if not any([expiring, sin, end, pending > 20]):
                msg = "✅ Nenhuma pendência crítica."
            self._agent_add_message(msg, is_user=False)
        except Exception:
            self._agent_add_message("Erro ao consultar alertas.", is_user=False)

    def _agent_ask_llm(self, question: str) -> None:
        try:
            from urllib.request import Request, urlopen
            payload = json.dumps({
                "model": "llama3.1",
                "messages": [{"role": "user", "content": question}],
                "stream": False,
                "options": {"temperature": 0.7, "num_predict": 512},
            }).encode("utf-8")
            req = Request(
                "http://localhost:11434/api/chat", data=payload,
                headers={"Content-Type": "application/json"}, method="POST",
            )
            with urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                answer = data.get("message", {}).get("content", "Sem resposta.")
                self.root.after(0, self._agent_add_message, answer, False)
        except Exception:
            self.root.after(
                0, self._agent_add_message,
                "Ollama não disponível. Instale com scripts/setup_ollama.bat para IA completa.\n\n"
                "Posso ajudar com: status, alertas, executar, dashboard.",
                False,
            )

    def _open_agent(self) -> None:
        env = {**os.environ, "PYTHONPATH": str(SRC_DIR)}
        subprocess.Popen(
            [sys.executable, "-m", "rpa_corretora.agent"],
            cwd=str(BASE_DIR), env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

    # --- Notícias ---

    def _refresh_news(self) -> None:
        threading.Thread(target=self._fetch_news, daemon=True).start()

    def _fetch_news(self) -> None:
        from urllib.request import Request, urlopen
        from urllib.parse import quote_plus

        queries = [
            "seguros brasil 2026 novidades",
            "SUSEP regulamentação corretores",
            "mercado seguros auto tendências",
        ]
        all_results = []
        for query in queries:
            try:
                url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
                req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urlopen(req, timeout=10) as resp:
                    html = resp.read().decode("utf-8", errors="ignore")
                titles = re.findall(r'"result__a"[^>]*>(.*?)</a>', html, re.DOTALL)[:3]
                snippets = re.findall(r'"result__snippet">(.*?)</a>', html, re.DOTALL)[:3]
                for title, snippet in zip(titles, snippets):
                    clean_title = re.sub(r"<[^>]+>", "", title).strip()
                    clean_snippet = re.sub(r"<[^>]+>", "", snippet).strip()
                    if clean_title:
                        all_results.append((clean_title, clean_snippet, query))
            except Exception:
                continue
        self.root.after(0, self._display_news, all_results)

    def _display_news(self, results: list) -> None:
        self.news_text.configure(state="normal")
        self.news_text.delete("1.0", "end")
        if not results:
            self.news_text.insert(
                "end",
                "Sem conexão ou nenhuma notícia encontrada.\nClique em Atualizar para tentar novamente.",
            )
        else:
            for i, (title, snippet, source) in enumerate(results[:12], 1):
                self.news_text.insert("end", f"\n{i}. {title}\n", "title")
                self.news_text.insert("end", f"   {snippet}\n")
                self.news_text.insert("end", f"   Fonte: {source}\n\n", "source")
        self.news_text.configure(state="disabled")

    def _tick_clock(self) -> None:
        self._clock_label.configure(text=datetime.now().strftime("🕐 %H:%M:%S"))
        self.root.after(1000, self._tick_clock)

    def _animate_dot(self) -> None:
        if self.running:
            cur = self._dot_canvas.itemcget(self._dot_oval, "fill")
            self._dot_canvas.itemconfig(self._dot_oval, fill=WARNING if cur != WARNING else SURFACE2)
        self.root.after(600, self._animate_dot)

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    app = RPAApp()
    app.run()


if __name__ == "__main__":
    main()
