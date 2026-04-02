import json
import os
from pathlib import Path

from rpa_corretora.config import load_settings
from rpa_corretora.env_loader import load_env_file


def _write_settings(path: Path) -> None:
    payload = {
        "timezone": "America/Fortaleza",
        "files": {
            "seguros_pbseg_xlsx": "C:/dados/SEGUROS PBSEG.xlsx",
            "acompanhamento_2026_xlsx": "C:/dados/ACOMPANHAMENTO 2026.xlsx",
            "fluxo_caixa_xlsx": "C:/dados/FLUXO DE CAIXA.xlsx",
            "senhas_pdf": "C:/dados/SENHAS.pdf",
        },
        "renewal": {
            "internal_days": 30,
            "new_days": 15,
            "reminder_days": [7, 1],
            "holidays": [],
        },
        "insurers": {},
        "insurer_domains": [],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_load_env_file_reads_todo_credentials(tmp_path: Path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "MICROSOFT_TODO_USER=usuario@exemplo.com\nMICROSOFT_TODO_PASSWORD=Senha@123\n",
        encoding="utf-8",
    )

    monkeypatch.delenv("MICROSOFT_TODO_USER", raising=False)
    monkeypatch.delenv("MICROSOFT_TODO_PASSWORD", raising=False)

    load_env_file(env_file)

    assert os.getenv("MICROSOFT_TODO_USER") == "usuario@exemplo.com"
    assert os.getenv("MICROSOFT_TODO_PASSWORD") == "Senha@123"


def test_load_env_file_overrides_empty_existing_env(tmp_path: Path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "MICROSOFT_TODO_USER=usuario@exemplo.com\nMICROSOFT_TODO_PASSWORD=Senha@123\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("MICROSOFT_TODO_USER", "")
    monkeypatch.setenv("MICROSOFT_TODO_PASSWORD", "")

    load_env_file(env_file)

    assert os.getenv("MICROSOFT_TODO_USER") == "usuario@exemplo.com"
    assert os.getenv("MICROSOFT_TODO_PASSWORD") == "Senha@123"


def test_settings_reads_todo_credentials_and_file_override(tmp_path: Path, monkeypatch) -> None:
    settings_file = tmp_path / "settings.json"
    _write_settings(settings_file)

    monkeypatch.setenv("MICROSOFT_TODO_USER", "cadastro.segurados@hotmail.com")
    monkeypatch.setenv("MICROSOFT_TODO_PASSWORD", "SenhaForte@2026")
    monkeypatch.setenv("SEGUROS_PBSEG_XLSX", "D:/RPA/SEGUROS PBSEG.xlsx")
    monkeypatch.setenv("MICROSOFT_TODO_WEB_HEADLESS", "0")

    settings = load_settings(settings_file)

    assert settings.microsoft_todo is not None
    assert settings.microsoft_todo.username == "cadastro.segurados@hotmail.com"
    assert settings.microsoft_todo.password == "SenhaForte@2026"
    assert settings.microsoft_todo.web_headless is False
    assert str(settings.files.seguros_pbseg_xlsx) == "D:/RPA/SEGUROS PBSEG.xlsx"
