from __future__ import annotations

import os
from pathlib import Path


def load_env_file(path: str | Path = ".env", *, override: bool = True) -> None:
    env_file = Path(path)
    if not env_file.exists():
        return

    for line_no, raw_line in enumerate(env_file.read_text(encoding="utf-8").splitlines(), start=1):
        # Remove BOM acidental no inicio do arquivo
        if line_no == 1:
            raw_line = raw_line.lstrip("\ufeff")
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        if value.startswith(('"', "'")) and value.endswith(('"', "'")) and len(value) >= 2:
            value = value[1:-1]

        # Em ambiente operacional preferimos determinismo:
        # o .env informado no comando deve prevalecer sobre variaveis ja herdadas
        # da sessao do terminal/sistema.
        if not key:
            continue

        if override:
            os.environ[key] = value
            continue

        existing = os.environ.get(key)
        if existing is None or existing.strip() == "":
            os.environ[key] = value
