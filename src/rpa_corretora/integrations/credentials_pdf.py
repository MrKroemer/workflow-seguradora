from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


@dataclass(frozen=True, slots=True)
class CredentialEntry:
    service: str
    username: str
    password: str


def _run_command(args: list[str]) -> str:
    process = subprocess.run(args, check=True, capture_output=True, text=True)
    return process.stdout


def _normalize_line(line: str) -> str:
    cleaned = line.strip()
    cleaned = re.sub(r"^[^A-Za-z0-9]+", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def extract_text_from_pdf_ocr(pdf_path: str | Path) -> str:
    pdf_file = Path(pdf_path)
    if not pdf_file.exists():
        raise FileNotFoundError(f"Arquivo nao encontrado: {pdf_file}")

    if shutil.which("pdftoppm") is None:
        raise RuntimeError("Comando pdftoppm nao encontrado no sistema")
    if shutil.which("tesseract") is None:
        raise RuntimeError("Comando tesseract nao encontrado no sistema")

    with tempfile.TemporaryDirectory(prefix="rpa-cred-") as temp_dir:
        temp_path = Path(temp_dir)
        image_prefix = temp_path / "page"

        subprocess.run(
            ["pdftoppm", "-png", str(pdf_file), str(image_prefix)],
            check=True,
            capture_output=True,
            text=True,
        )

        pages = sorted(temp_path.glob("page-*.png"))
        text_chunks: list[str] = []
        for page_file in pages:
            page_text = _run_command(["tesseract", str(page_file), "stdout", "-l", "por+eng"])
            text_chunks.append(page_text)

    return "\n".join(text_chunks)


def parse_credentials(text: str) -> dict[str, CredentialEntry]:
    credentials: dict[str, CredentialEntry] = {}
    ignored_tokens = {
        "ACESSOS",
        "CNAE",
        "SEGURADORA",
        "USUARIO",
        "SENHA",
    }
    marker_pattern = re.compile(r"^[O0I\]\[/|]+$")

    for raw_line in text.splitlines():
        line = _normalize_line(raw_line)
        if not line:
            continue

        normalized_upper = line.upper()
        if any(token in normalized_upper for token in ignored_tokens):
            continue

        parts = line.split(" ")
        if len(parts) < 3:
            continue

        username = parts[-2]
        password = parts[-1]
        service_tokens = [token for token in parts[:-2] if token]
        while service_tokens and marker_pattern.match(service_tokens[0].upper()):
            service_tokens.pop(0)
        service = " ".join(service_tokens).strip(" -:")

        if not service or not username or not password:
            continue

        has_login_hint = ("@" in username) or any(char.isdigit() for char in username)
        has_password_hint = any(ch.isdigit() for ch in password) or any(ch in "@#$%*!._-" for ch in password)
        if not has_login_hint or not has_password_hint:
            continue

        credentials[service.upper()] = CredentialEntry(
            service=service,
            username=username,
            password=password,
        )

    return credentials


def load_credentials_from_pdf(pdf_path: str | Path) -> dict[str, CredentialEntry]:
    raw_text = extract_text_from_pdf_ocr(pdf_path)
    return parse_credentials(raw_text)
