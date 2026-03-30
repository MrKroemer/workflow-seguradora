from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
import os
from pathlib import Path


@dataclass(frozen=True, slots=True)
class RenewalSettings:
    internal_days: int
    new_days: int
    reminder_days: tuple[int, ...]
    holidays: frozenset[date]


@dataclass(frozen=True, slots=True)
class FileSettings:
    seguros_pbseg_xlsx: Path
    acompanhamento_2026_xlsx: Path
    fluxo_caixa_xlsx: Path
    senhas_pdf: Path | None = None


@dataclass(frozen=True, slots=True)
class MicrosoftTodoSettings:
    username: str | None = None
    password: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    refresh_token: str | None = None
    tenant_id: str = "common"
    web_headless: bool = True


@dataclass(frozen=True, slots=True)
class AppSettings:
    timezone: str
    insurers: dict[str, str]
    insurer_domains: tuple[str, ...]
    renewal: RenewalSettings
    files: FileSettings | None = None
    microsoft_todo: MicrosoftTodoSettings | None = None


DEFAULT_SETTINGS_PATH = Path(__file__).resolve().parents[2] / "config" / "settings.json"


def _parse_holidays(raw: list[str]) -> frozenset[date]:
    parsed = set()
    for item in raw:
        parsed.add(date.fromisoformat(item))
    return frozenset(parsed)


def _env_str(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    cleaned = value.strip()
    if cleaned == "":
        return None
    return cleaned


def _env_bool(name: str, default: bool) -> bool:
    value = _env_str(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on", "sim"}:
        return True
    if normalized in {"0", "false", "no", "off", "nao"}:
        return False
    return default


def load_settings(path: str | Path = DEFAULT_SETTINGS_PATH) -> AppSettings:
    with Path(path).open("r", encoding="utf-8") as file:
        data = json.load(file)

    renewal_data = data["renewal"]
    renewal = RenewalSettings(
        internal_days=int(renewal_data["internal_days"]),
        new_days=int(renewal_data["new_days"]),
        reminder_days=tuple(int(day) for day in renewal_data["reminder_days"]),
        holidays=_parse_holidays(renewal_data.get("holidays", [])),
    )

    file_settings = None
    files_data = data.get("files")
    if isinstance(files_data, dict):
        seguros_path = _env_str("SEGUROS_PBSEG_XLSX") or files_data["seguros_pbseg_xlsx"]
        acompanhamento_path = _env_str("ACOMPANHAMENTO_2026_XLSX") or files_data["acompanhamento_2026_xlsx"]
        fluxo_path = _env_str("FLUXO_CAIXA_XLSX") or files_data["fluxo_caixa_xlsx"]
        senhas_path = _env_str("SENHAS_PDF") or files_data.get("senhas_pdf")
        file_settings = FileSettings(
            seguros_pbseg_xlsx=Path(seguros_path),
            acompanhamento_2026_xlsx=Path(acompanhamento_path),
            fluxo_caixa_xlsx=Path(fluxo_path),
            senhas_pdf=Path(senhas_path) if senhas_path else None,
        )

    todo_settings = MicrosoftTodoSettings(
        username=_env_str("MICROSOFT_TODO_USER"),
        password=_env_str("MICROSOFT_TODO_PASSWORD"),
        client_id=_env_str("MICROSOFT_TODO_CLIENT_ID"),
        client_secret=_env_str("MICROSOFT_TODO_CLIENT_SECRET"),
        refresh_token=_env_str("MICROSOFT_TODO_REFRESH_TOKEN"),
        tenant_id=_env_str("MICROSOFT_TODO_TENANT_ID") or "common",
        web_headless=_env_bool("MICROSOFT_TODO_WEB_HEADLESS", default=True),
    )

    return AppSettings(
        timezone=data["timezone"],
        insurers=dict(data["insurers"]),
        insurer_domains=tuple(item.lower() for item in data["insurer_domains"]),
        renewal=renewal,
        files=file_settings,
        microsoft_todo=todo_settings,
    )
