from __future__ import annotations

import os
from pathlib import Path

from rpa_corretora.env_loader import load_env_file


def test_load_env_file_overrides_existing_values_by_default(tmp_path: Path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("RPA_TEST_KEY=from_file\n", encoding="utf-8")

    monkeypatch.setenv("RPA_TEST_KEY", "from_shell")
    load_env_file(env_file)

    assert os.getenv("RPA_TEST_KEY") == "from_file"


def test_load_env_file_can_preserve_existing_values_when_override_is_false(
    tmp_path: Path, monkeypatch
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("RPA_TEST_KEY=from_file\n", encoding="utf-8")

    monkeypatch.setenv("RPA_TEST_KEY", "from_shell")
    load_env_file(env_file, override=False)

    assert os.getenv("RPA_TEST_KEY") == "from_shell"

