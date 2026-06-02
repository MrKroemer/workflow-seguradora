"""Banco de dados operacional centralizado (SQLite).

Todas as fontes de dados (planilhas, portais, Gmail, Segfy, agenda) alimentam
este banco. Os dashboards e relatorios consultam daqui.
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from rpa_corretora.domain.models import (
    Alert,
    CalendarCommitment,
    CashflowEntry,
    EmailMessage,
    ExpenseEntry,
    FollowupRecord,
    PolicyRecord,
    PortalPolicyData,
    SegfyPolicyData,
)

DEFAULT_DB_PATH = "outputs/rpa_corretora.db"


class OperationalDatabase:
    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._create_tables()

    def close(self) -> None:
        self._conn.close()

    def _create_tables(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS policies (
                policy_id TEXT PRIMARY KEY,
                insured_name TEXT NOT NULL,
                insurer TEXT NOT NULL,
                vig DATE NOT NULL,
                renewal_kind TEXT DEFAULT 'RENOVACAO_INTERNA',
                renewal_started INTEGER DEFAULT 0,
                status_pgto TEXT DEFAULT '',
                sinistro_open INTEGER DEFAULT 0,
                endosso_open INTEGER DEFAULT 0,
                premio_total REAL DEFAULT 0,
                comissao REAL DEFAULT 0,
                vehicle_item TEXT DEFAULT '',
                vehicle_model TEXT DEFAULT '',
                vehicle_plate TEXT DEFAULT '',
                source TEXT DEFAULT 'PLANILHA',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS followups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                insured_name TEXT NOT NULL,
                month TEXT NOT NULL,
                fase TEXT DEFAULT '',
                status TEXT DEFAULT '',
                renewal_kind TEXT DEFAULT 'RENOVACAO_INTERNA',
                source TEXT DEFAULT 'PLANILHA',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(insured_name, month, renewal_kind)
            );

            CREATE TABLE IF NOT EXISTS cashflow (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_date DATE NOT NULL,
                value REAL NOT NULL,
                insurer TEXT DEFAULT '',
                specification TEXT DEFAULT '',
                source TEXT DEFAULT '',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_date DATE NOT NULL,
                value REAL NOT NULL,
                description TEXT DEFAULT '',
                category TEXT DEFAULT '',
                source TEXT DEFAULT 'PLANILHA',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS portal_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                policy_id TEXT NOT NULL,
                insurer TEXT NOT NULL,
                premio_total REAL DEFAULT 0,
                comissao REAL DEFAULT 0,
                sinistro_status TEXT DEFAULT '',
                endosso_status TEXT DEFAULT '',
                renewal_status TEXT DEFAULT '',
                parcelas_pendentes INTEGER DEFAULT 0,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL,
                severity TEXT NOT NULL,
                message TEXT NOT NULL,
                context_json TEXT DEFAULT '{}',
                run_date DATE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS commitments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                commitment_id TEXT NOT NULL,
                title TEXT NOT NULL,
                color TEXT NOT NULL,
                due_date DATE NOT NULL,
                client_name TEXT DEFAULT '',
                resolved INTEGER DEFAULT 0,
                classification TEXT DEFAULT '',
                run_date DATE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS emails (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email_id TEXT NOT NULL,
                sender TEXT NOT NULL,
                subject TEXT NOT NULL,
                received_at TIMESTAMP,
                is_insurer INTEGER DEFAULT 0,
                attachments_count INTEGER DEFAULT 0,
                run_date DATE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS run_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_date DATE NOT NULL,
                started_at TIMESTAMP NOT NULL,
                ended_at TIMESTAMP,
                status TEXT DEFAULT 'RUNNING',
                total_policies INTEGER DEFAULT 0,
                total_alerts INTEGER DEFAULT 0,
                total_emails INTEGER DEFAULT 0,
                total_cashflow REAL DEFAULT 0,
                segfy_synced INTEGER DEFAULT 0,
                portal_synced INTEGER DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_policies_insurer ON policies(insurer);
            CREATE INDEX IF NOT EXISTS idx_policies_vig ON policies(vig);
            CREATE INDEX IF NOT EXISTS idx_followups_month ON followups(month);
            CREATE INDEX IF NOT EXISTS idx_alerts_run_date ON alerts(run_date);
            CREATE INDEX IF NOT EXISTS idx_alerts_severity ON alerts(severity);
            CREATE INDEX IF NOT EXISTS idx_cashflow_date ON cashflow(entry_date);
            CREATE INDEX IF NOT EXISTS idx_portal_data_policy ON portal_data(policy_id);
        """)
        self._conn.commit()

    # --- Policies ---
    def upsert_policies(self, policies: list[PolicyRecord], source: str = "PLANILHA") -> int:
        count = 0
        for p in policies:
            self._conn.execute("""
                INSERT INTO policies (policy_id, insured_name, insurer, vig, renewal_kind,
                    renewal_started, status_pgto, sinistro_open, endosso_open,
                    premio_total, comissao, vehicle_item, vehicle_model, vehicle_plate, source, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(policy_id) DO UPDATE SET
                    insured_name=excluded.insured_name, insurer=excluded.insurer, vig=excluded.vig,
                    renewal_kind=excluded.renewal_kind, renewal_started=excluded.renewal_started,
                    status_pgto=excluded.status_pgto, sinistro_open=excluded.sinistro_open,
                    endosso_open=excluded.endosso_open, premio_total=excluded.premio_total,
                    comissao=excluded.comissao, vehicle_item=excluded.vehicle_item,
                    vehicle_model=excluded.vehicle_model, vehicle_plate=excluded.vehicle_plate,
                    source=excluded.source, updated_at=excluded.updated_at
            """, (
                p.policy_id, p.insured_name, p.insurer, p.vig.isoformat(),
                p.renewal_kind, int(p.renewal_started), p.status_pgto,
                int(p.sinistro_open), int(p.endosso_open),
                float(p.premio_total), float(p.comissao),
                p.vehicle_item, p.vehicle_model, p.vehicle_plate,
                source, datetime.now().isoformat(),
            ))
            count += 1
        self._conn.commit()
        return count

    # --- Followups ---
    def upsert_followups(self, followups: list[FollowupRecord], source: str = "PLANILHA") -> int:
        count = 0
        for f in followups:
            self._conn.execute("""
                INSERT INTO followups (insured_name, month, fase, status, renewal_kind, source, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(insured_name, month, renewal_kind) DO UPDATE SET
                    fase=excluded.fase, status=excluded.status, source=excluded.source, updated_at=excluded.updated_at
            """, (f.insured_name, f.month, f.fase, f.status, f.renewal_kind, source, datetime.now().isoformat()))
            count += 1
        self._conn.commit()
        return count

    # --- Cashflow ---
    def insert_cashflow(self, entries: list[CashflowEntry]) -> int:
        count = 0
        for e in entries:
            self._conn.execute("""
                INSERT INTO cashflow (entry_date, value, insurer, specification, source, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (e.date.isoformat(), float(e.value), e.insurer, e.specification, e.source, datetime.now().isoformat()))
            count += 1
        self._conn.commit()
        return count

    # --- Expenses ---
    def insert_expenses(self, expenses: list[ExpenseEntry]) -> int:
        count = 0
        for e in expenses:
            self._conn.execute("""
                INSERT INTO expenses (entry_date, value, description, category, updated_at)
                VALUES (?, ?, ?, ?, ?)
            """, (e.date.isoformat(), float(e.value), e.description, e.category, datetime.now().isoformat()))
            count += 1
        self._conn.commit()
        return count

    # --- Portal Data ---
    def insert_portal_data(self, data: list[PortalPolicyData]) -> int:
        count = 0
        for d in data:
            self._conn.execute("""
                INSERT INTO portal_data (policy_id, insurer, premio_total, comissao,
                    sinistro_status, endosso_status, renewal_status, parcelas_pendentes, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                d.policy_id, d.insurer, float(d.premio_total), float(d.comissao),
                d.sinistro_status, d.endosso_status, d.renewal_status,
                d.parcelas_pendentes, datetime.now().isoformat(),
            ))
            count += 1
        self._conn.commit()
        return count

    # --- Alerts ---
    def insert_alerts(self, alerts: list[Alert], run_date: date) -> int:
        import json
        count = 0
        for a in alerts:
            self._conn.execute("""
                INSERT INTO alerts (code, severity, message, context_json, run_date, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (a.code, a.severity, a.message, json.dumps(a.context, ensure_ascii=False), run_date.isoformat(), datetime.now().isoformat()))
            count += 1
        self._conn.commit()
        return count

    # --- Commitments ---
    def insert_commitments(self, commitments: list[CalendarCommitment], run_date: date, classifications: dict[str, str] | None = None) -> int:
        count = 0
        for c in commitments:
            classification = (classifications or {}).get(c.id, "")
            self._conn.execute("""
                INSERT INTO commitments (commitment_id, title, color, due_date, client_name, resolved, classification, run_date, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (c.id, c.title, c.color, c.due_date.isoformat(), c.client_name or "", int(c.resolved), classification, run_date.isoformat(), datetime.now().isoformat()))
            count += 1
        self._conn.commit()
        return count

    # --- Emails ---
    def insert_emails(self, messages: list[EmailMessage], run_date: date, insurer_ids: set[str] | None = None) -> int:
        count = 0
        for m in messages:
            is_insurer = 1 if (insurer_ids and m.id in insurer_ids) else 0
            self._conn.execute("""
                INSERT INTO emails (email_id, sender, subject, received_at, is_insurer, attachments_count, run_date, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (m.id, m.sender, m.subject, m.received_at.isoformat(), is_insurer, len(m.attachments), run_date.isoformat(), datetime.now().isoformat()))
            count += 1
        self._conn.commit()
        return count

    # --- Run History ---
    def start_run(self, run_date: date) -> int:
        cursor = self._conn.execute("""
            INSERT INTO run_history (run_date, started_at, status) VALUES (?, ?, 'RUNNING')
        """, (run_date.isoformat(), datetime.now().isoformat()))
        self._conn.commit()
        return cursor.lastrowid or 0

    def complete_run(self, run_id: int, *, total_policies: int, total_alerts: int, total_emails: int, total_cashflow: float, segfy_synced: int, portal_synced: int, status: str = "SUCESSO") -> None:
        self._conn.execute("""
            UPDATE run_history SET ended_at=?, status=?, total_policies=?, total_alerts=?,
                total_emails=?, total_cashflow=?, segfy_synced=?, portal_synced=?
            WHERE id=?
        """, (datetime.now().isoformat(), status, total_policies, total_alerts, total_emails, total_cashflow, segfy_synced, portal_synced, run_id))
        self._conn.commit()

    # --- Queries para Dashboard ---
    def query_policies_by_insurer(self) -> list[tuple[str, int]]:
        rows = self._conn.execute("SELECT insurer, COUNT(*) FROM policies GROUP BY insurer ORDER BY COUNT(*) DESC").fetchall()
        return [(r[0], r[1]) for r in rows]

    def query_commissions_summary(self) -> dict[str, int]:
        paid = self._conn.execute("SELECT COUNT(*) FROM policies WHERE status_pgto != ''").fetchone()[0]
        pending = self._conn.execute("SELECT COUNT(*) FROM policies WHERE status_pgto = ''").fetchone()[0]
        return {"paid": paid, "pending": pending}

    def query_open_incidents(self) -> dict[str, int]:
        sinistros = self._conn.execute("SELECT COUNT(*) FROM policies WHERE sinistro_open = 1").fetchone()[0]
        endossos = self._conn.execute("SELECT COUNT(*) FROM policies WHERE endosso_open = 1").fetchone()[0]
        return {"sinistros": sinistros, "endossos": endossos}

    def query_cashflow_month(self, year: int, month: int) -> dict[str, float]:
        cash_in = self._conn.execute(
            "SELECT COALESCE(SUM(value), 0) FROM cashflow WHERE strftime('%Y', entry_date)=? AND strftime('%m', entry_date)=?",
            (str(year), f"{month:02d}")
        ).fetchone()[0]
        cash_out = self._conn.execute(
            "SELECT COALESCE(SUM(value), 0) FROM expenses WHERE strftime('%Y', entry_date)=? AND strftime('%m', entry_date)=?",
            (str(year), f"{month:02d}")
        ).fetchone()[0]
        return {"cash_in": cash_in, "cash_out": cash_out, "net": cash_in - cash_out}

    def query_alerts_by_severity(self, run_date: date) -> dict[str, int]:
        rows = self._conn.execute(
            "SELECT severity, COUNT(*) FROM alerts WHERE run_date=? GROUP BY severity",
            (run_date.isoformat(),)
        ).fetchall()
        return {r[0]: r[1] for r in rows}

    def query_renewals_by_month(self) -> dict[str, dict[str, int]]:
        rows = self._conn.execute("""
            SELECT month,
                SUM(CASE WHEN status IN ('CONCLUIDO','CONCLUIDA','RENOVADO','FINALIZADO') THEN 1 ELSE 0 END) as concluded,
                SUM(CASE WHEN status NOT IN ('CONCLUIDO','CONCLUIDA','RENOVADO','FINALIZADO') OR status = '' THEN 1 ELSE 0 END) as open
            FROM followups GROUP BY month
        """).fetchall()
        return {r[0]: {"concluded": r[1], "open": r[2]} for r in rows}

    def query_portal_divergences(self) -> list[dict[str, Any]]:
        rows = self._conn.execute("""
            SELECT p.policy_id, p.insured_name, p.insurer,
                   p.premio_total as planilha_premio, pd.premio_total as portal_premio,
                   p.comissao as planilha_comissao, pd.comissao as portal_comissao
            FROM policies p
            JOIN portal_data pd ON p.policy_id = pd.policy_id
            WHERE ABS(p.premio_total - pd.premio_total) > 0.01
               OR ABS(p.comissao - pd.comissao) > 0.01
            ORDER BY ABS(p.premio_total - pd.premio_total) DESC
        """).fetchall()
        return [
            {"policy_id": r[0], "insured_name": r[1], "insurer": r[2],
             "planilha_premio": r[3], "portal_premio": r[4],
             "planilha_comissao": r[5], "portal_comissao": r[6]}
            for r in rows
        ]

    def query_run_history(self, limit: int = 30) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM run_history ORDER BY started_at DESC LIMIT ?", (limit,)
        ).fetchall()
        cols = [desc[0] for desc in self._conn.execute("SELECT * FROM run_history LIMIT 0").description]
        return [dict(zip(cols, r)) for r in rows]
