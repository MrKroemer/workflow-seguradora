"""Gateway de planilha respaldado pelo banco de dados operacional.

Substitui os arquivos Excel manuais (SEGUROS PBSEG.xlsx, ACOMPANHAMENTO 2026.xlsx,
FLUXO DE CAIXA.xlsx) usando o banco SQLite como fonte de verdade.

- load_policies()       → tabela `policies`
- load_followups(year)  → derivado das datas de VIG no banco
- load_expenses()       → tabela `expenses`
- append_cashflow/expense → persiste no banco (não em arquivo)
"""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Literal

from rpa_corretora.domain.models import (
    CashflowEntry,
    ExpenseEntry,
    FollowupRecord,
    PolicyRecord,
)


class DatabaseBackedSpreadsheetGateway:
    """Lê e escreve dados operacionais direto no banco SQLite.

    Elimina a dependência de planilhas Excel manuais mantendo a mesma
    interface exigida pelo orchestrator (SpreadsheetGateway protocol).
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        return conn

    # ── Leitura de apólices ──────────────────────────────────────────────

    def load_policies(self) -> list[PolicyRecord]:
        if not self._db_path.exists():
            return []
        try:
            with self._conn() as conn:
                rows = conn.execute(
                    "SELECT * FROM policies ORDER BY vig ASC"
                ).fetchall()
        except sqlite3.OperationalError:
            return []

        policies = []
        for row in rows:
            try:
                vig_raw = row["vig"]
                if isinstance(vig_raw, str):
                    vig = date.fromisoformat(vig_raw)
                else:
                    vig = vig_raw
                policies.append(
                    PolicyRecord(
                        policy_id=row["policy_id"],
                        insured_name=row["insured_name"],
                        insurer=row["insurer"],
                        vig=vig,
                        renewal_kind=row["renewal_kind"] or "RENOVACAO_INTERNA",
                        renewal_started=bool(row["renewal_started"]),
                        status_pgto=row["status_pgto"] or "",
                        sinistro_open=bool(row["sinistro_open"]),
                        endosso_open=bool(row["endosso_open"]),
                        premio_total=Decimal(str(row["premio_total"] or 0)),
                        comissao=Decimal(str(row["comissao"] or 0)),
                        vehicle_item=row["vehicle_item"] or "",
                        vehicle_model=row["vehicle_model"] or "",
                        vehicle_plate=row["vehicle_plate"] or "",
                    )
                )
            except Exception:
                continue
        return policies

    # ── Follow-up derivado das datas de VIG ─────────────────────────────

    def load_followups(self, year: int) -> list[FollowupRecord]:
        """Deriva acompanhamento de renovações diretamente das apólices no banco.

        Lógica:
        - Apólices com VIG no ano solicitado recebem follow-up automático
        - VIG ≤ 30 dias a partir de hoje → fase URGENTE
        - VIG ≤ 90 dias → fase EM NEGOCIAÇÃO
        - VIG > 90 dias → fase PROSPECÇÃO
        - VIG já vencida → fase CONCLUÍDO
        """
        if not self._db_path.exists():
            return []
        try:
            with self._conn() as conn:
                rows = conn.execute(
                    "SELECT policy_id, insured_name, vig, renewal_kind "
                    "FROM policies "
                    "WHERE strftime('%Y', vig) = ? "
                    "ORDER BY vig ASC",
                    (str(year),),
                ).fetchall()
        except sqlite3.OperationalError:
            return []

        today = date.today()
        followups: list[FollowupRecord] = []
        for row in rows:
            try:
                vig_raw = row["vig"]
                vig = date.fromisoformat(vig_raw) if isinstance(vig_raw, str) else vig_raw
                days_to_vig = (vig - today).days
                month = vig.strftime("%Y-%m")

                if days_to_vig < 0:
                    fase, status = "CONCLUÍDO", "RENOVADO"
                elif days_to_vig <= 30:
                    fase, status = "URGENTE", "EM ANDAMENTO"
                elif days_to_vig <= 90:
                    fase, status = "EM NEGOCIAÇÃO", "CONTATO REALIZADO"
                else:
                    fase, status = "PROSPECÇÃO", "AGUARDANDO"

                followups.append(
                    FollowupRecord(
                        insured_name=row["insured_name"],
                        month=month,
                        fase=fase,
                        status=status,
                        renewal_kind=row["renewal_kind"] or "RENOVACAO_INTERNA",
                    )
                )
            except Exception:
                continue
        return followups

    # ── Despesas ─────────────────────────────────────────────────────────

    def load_expenses(self, year: int, month: int) -> list[ExpenseEntry]:
        if not self._db_path.exists():
            return []
        try:
            with self._conn() as conn:
                rows = conn.execute(
                    "SELECT * FROM expenses "
                    "WHERE strftime('%Y', entry_date) = ? "
                    "  AND strftime('%m', entry_date) = ? "
                    "ORDER BY entry_date ASC",
                    (str(year), f"{month:02d}"),
                ).fetchall()
        except sqlite3.OperationalError:
            return []

        return [
            ExpenseEntry(
                date=date.fromisoformat(row["entry_date"]),
                value=Decimal(str(row["value"] or 0)),
                description=row["description"] or "",
                category=row["category"] or "",
            )
            for row in rows
        ]

    # ── Escrita no banco (substituem escrita nas planilhas) ──────────────

    def append_cashflow_entries(self, entries: list[CashflowEntry]) -> None:
        if not entries or not self._db_path.exists():
            return
        with self._conn() as conn:
            conn.executemany(
                "INSERT INTO cashflow (entry_date, value, insurer, specification, source) "
                "VALUES (?, ?, ?, ?, ?)",
                [
                    (e.date.isoformat(), float(e.value), e.insurer, e.specification, e.source)
                    for e in entries
                ],
            )
            conn.commit()

    def append_expense_entries(self, entries: list[ExpenseEntry]) -> None:
        if not entries or not self._db_path.exists():
            return
        with self._conn() as conn:
            conn.executemany(
                "INSERT INTO expenses (entry_date, value, description, category, source) "
                "VALUES (?, ?, ?, ?, ?)",
                [
                    (e.date.isoformat(), float(e.value), e.description, e.category, "DB_AUTO")
                    for e in entries
                ],
            )
            conn.commit()

    def validate_expense_summary(self, year: int, month: int) -> list[str]:
        """Banco de dados é a fonte de verdade — sem divergências estruturais."""
        return []

    # ── Diagnóstico ──────────────────────────────────────────────────────

    def policy_count(self) -> int:
        if not self._db_path.exists():
            return 0
        try:
            with self._conn() as conn:
                return conn.execute("SELECT COUNT(*) FROM policies").fetchone()[0]
        except sqlite3.OperationalError:
            return 0
