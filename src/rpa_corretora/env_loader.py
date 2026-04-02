from __future__ import annotations

import os
from pathlib import Path


def load_env_file(path: str | Path = ".env") -> None:
    env_file = Path(path)
    if not env_file.exists():
        return

    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        if value.startswith(('"', "'")) and value.endswith(('"', "'")) and len(value) >= 2:
            value = value[1:-1]

        # Permite preencher variaveis ja existentes, mas vazias.
        # Isso evita cenarios no Windows em que o shell exporta chave sem valor,
        # bloqueando a leitura efetiva do .env.
        existing = os.environ.get(key) if key else None
        if key and (existing is None or existing.strip() == ""):
            os.environ[key] = value
