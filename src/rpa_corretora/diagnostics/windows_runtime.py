from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal
import importlib.util
import json
import os
import subprocess
import shutil
import sys


RuntimeStatus = Literal["OK", "WARN", "MISSING", "N_A"]


@dataclass(frozen=True, slots=True)
class RuntimeComponent:
    key: str
    label: str
    status: RuntimeStatus
    required: bool
    details: str


@dataclass(frozen=True, slots=True)
class FileCheck:
    path: str
    exists: bool


@dataclass(frozen=True, slots=True)
class WindowsRuntimeReport:
    generated_at: str
    platform: str
    is_windows: bool
    integrations: dict[str, str]
    components: list[RuntimeComponent]
    files: list[FileCheck]
    ready: bool


def _find_edge_executable() -> str | None:
    edge_path = shutil.which("msedge") or shutil.which("msedge.exe")
    if edge_path:
        return edge_path

    candidates = [
        Path(os.getenv("PROGRAMFILES", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        Path(os.getenv("PROGRAMFILES(X86)", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
    ]
    for candidate in candidates:
        if str(candidate).strip() and candidate.exists():
            return str(candidate)
    return None


def _find_chrome_executable() -> str | None:
    chrome_path = shutil.which("chrome") or shutil.which("chrome.exe")
    if chrome_path:
        return chrome_path

    candidates = [
        Path(os.getenv("PROGRAMFILES", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(os.getenv("PROGRAMFILES(X86)", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(os.getenv("LOCALAPPDATA", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
    ]
    for candidate in candidates:
        if str(candidate).strip() and candidate.exists():
            return str(candidate)
    return None


def _playwright_module_available() -> bool:
    try:
        return importlib.util.find_spec("playwright.sync_api") is not None
    except ModuleNotFoundError:
        return False


def _pywinauto_available() -> bool:
    try:
        return importlib.util.find_spec("pywinauto") is not None
    except ModuleNotFoundError:
        return False


def _microsoft_todo_desktop_available() -> bool:
    if not sys.platform.startswith("win"):
        return False
    try:
        command = [
            "powershell",
            "-NoProfile",
            "-Command",
            (
                "$apps = Get-StartApps | Where-Object { "
                "$_.Name -match 'To Do|A Fazer' -or $_.AppID -match 'Microsoft.Todos|ToDo' "
                "}; if ($apps) { 'FOUND' }"
            ),
        ]
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        return "FOUND" in (result.stdout or "")
    except Exception:
        return False


def _playwright_chromium_installed() -> tuple[bool, str]:
    browsers_root_env = (os.getenv("PLAYWRIGHT_BROWSERS_PATH") or "").strip()
    if browsers_root_env and browsers_root_env != "0":
        root = Path(browsers_root_env)
    elif sys.platform.startswith("win"):
        user_profile = Path(os.getenv("USERPROFILE", ""))
        root = user_profile / "AppData" / "Local" / "ms-playwright"
    else:
        root = Path.home() / ".cache" / "ms-playwright"

    if not root.exists():
        return False, str(root)

    for child in root.iterdir():
        if child.is_dir() and child.name.lower().startswith("chromium"):
            return True, str(root)
    return False, str(root)


def _component(
    *,
    key: str,
    label: str,
    status: RuntimeStatus,
    required: bool,
    details: str,
) -> RuntimeComponent:
    return RuntimeComponent(
        key=key,
        label=label,
        status=status,
        required=required,
        details=details,
    )


def build_windows_runtime_report(
    *,
    calendar_mode: str,
    gmail_mode: str,
    todo_mode: str,
    segfy_mode: str,
    portal_mode: str,
    whatsapp_mode: str,
    email_mode: str,
    files_to_check: list[Path],
) -> WindowsRuntimeReport:
    is_windows = sys.platform.startswith("win")
    platform_text = f"{sys.platform} | python={sys.version.split()[0]}"

    integrations = {
        "calendar_mode": calendar_mode,
        "gmail_mode": gmail_mode,
        "todo_mode": todo_mode,
        "segfy_mode": segfy_mode,
        "portal_mode": portal_mode,
        "whatsapp_mode": whatsapp_mode,
        "email_mode": email_mode,
    }

    components: list[RuntimeComponent] = []
    python_path = sys.executable or ""
    python_ok = python_path != "" and Path(python_path).exists()
    components.append(
        _component(
            key="python_runtime",
            label="Python Runtime",
            status="OK" if python_ok else "MISSING",
            required=True,
            details=python_path or "Executavel Python nao identificado",
        )
    )

    powershell_path = shutil.which("powershell") or shutil.which("pwsh")
    if is_windows:
        components.append(
            _component(
                key="powershell",
                label="PowerShell",
                status="OK" if powershell_path else "WARN",
                required=False,
                details=powershell_path or "Nao encontrado no PATH",
            )
        )
    else:
        components.append(
            _component(
                key="powershell",
                label="PowerShell",
                status="N_A",
                required=False,
                details="Ambiente atual nao e Windows",
            )
        )

    scheduler_path = shutil.which("schtasks") or shutil.which("schtasks.exe")
    if is_windows:
        components.append(
            _component(
                key="windows_task_scheduler",
                label="Windows Task Scheduler",
                status="OK" if scheduler_path else "WARN",
                required=False,
                details=scheduler_path or "Comando schtasks nao encontrado no PATH",
            )
        )
    else:
        components.append(
            _component(
                key="windows_task_scheduler",
                label="Windows Task Scheduler",
                status="N_A",
                required=False,
                details="Ambiente atual nao e Windows",
            )
        )

    need_browser_automation = (
        todo_mode == "WEB_AUTOMATION"
        or portal_mode.startswith("WEB")
        or segfy_mode.startswith("WEB")
    )
    need_todo_desktop = todo_mode == "DESKTOP_APP"
    edge_path = _find_edge_executable()
    chrome_path = _find_chrome_executable()
    playwright_available = _playwright_module_available()
    chromium_installed, chromium_root = _playwright_chromium_installed()
    pywinauto_available = _pywinauto_available()
    todo_desktop_available = _microsoft_todo_desktop_available()

    if is_windows:
        components.append(
            _component(
                key="msedge",
                label="Microsoft Edge",
                status="OK" if edge_path else "WARN",
                required=False,
                details=edge_path or "Executavel msedge.exe nao encontrado",
            )
        )
        components.append(
            _component(
                key="chrome",
                label="Google Chrome",
                status="OK" if chrome_path else "WARN",
                required=False,
                details=chrome_path or "Executavel chrome.exe nao encontrado",
            )
        )
        components.append(
            _component(
                key="playwright_module",
                label="Playwright Python",
                status="OK" if playwright_available else ("MISSING" if need_browser_automation else "WARN"),
                required=need_browser_automation,
                details="playwright.sync_api disponivel" if playwright_available else "Modulo playwright.sync_api ausente",
            )
        )
        components.append(
            _component(
                key="playwright_chromium",
                label="Playwright Chromium Bundle",
                status="OK" if chromium_installed else ("MISSING" if need_browser_automation else "WARN"),
                required=need_browser_automation,
                details=f"Diretorio: {chromium_root}",
            )
        )
        components.append(
            _component(
                key="pywinauto_module",
                label="Pywinauto",
                status="OK" if pywinauto_available else ("MISSING" if need_todo_desktop else "WARN"),
                required=need_todo_desktop,
                details="Modulo pywinauto disponivel" if pywinauto_available else "Modulo pywinauto ausente",
            )
        )
        components.append(
            _component(
                key="microsoft_todo_desktop",
                label="Microsoft To Do Desktop App",
                status="OK" if todo_desktop_available else ("MISSING" if need_todo_desktop else "WARN"),
                required=need_todo_desktop,
                details=(
                    "Aplicativo detectado no menu Iniciar"
                    if todo_desktop_available
                    else "Aplicativo Microsoft To Do nao detectado no menu Iniciar"
                ),
            )
        )
    else:
        components.append(
            _component(
                key="msedge",
                label="Microsoft Edge",
                status="N_A",
                required=False,
                details="Automacao web de portais/To Do/Segfy requer Windows",
            )
        )
        components.append(
            _component(
                key="chrome",
                label="Google Chrome",
                status="N_A",
                required=False,
                details="Automacao web de portais/To Do/Segfy requer Windows",
            )
        )
        components.append(
            _component(
                key="playwright_module",
                label="Playwright Python",
                status="N_A",
                required=need_browser_automation,
                details="Automacao web de portais/To Do/Segfy requer Windows",
            )
        )
        components.append(
            _component(
                key="playwright_chromium",
                label="Playwright Chromium Bundle",
                status="N_A",
                required=need_browser_automation,
                details="Automacao web de portais/To Do/Segfy requer Windows",
            )
        )
        components.append(
            _component(
                key="pywinauto_module",
                label="Pywinauto",
                status="N_A",
                required=need_todo_desktop,
                details="Automacao desktop do Microsoft To Do requer Windows",
            )
        )
        components.append(
            _component(
                key="microsoft_todo_desktop",
                label="Microsoft To Do Desktop App",
                status="N_A",
                required=need_todo_desktop,
                details="Automacao desktop do Microsoft To Do requer Windows",
            )
        )

    files = [FileCheck(path=str(path), exists=path.exists()) for path in files_to_check]
    files_ready = all(item.exists for item in files) if files else False
    components.append(
        _component(
            key="operational_files",
            label="Arquivos Operacionais",
            status="OK" if files_ready else "MISSING",
            required=True,
            details=f"{sum(1 for item in files if item.exists)}/{len(files)} encontrados" if files else "Nenhum arquivo configurado",
        )
    )

    ready = is_windows and all(
        component.status == "OK"
        for component in components
        if component.required
    )

    return WindowsRuntimeReport(
        generated_at=datetime.now().isoformat(timespec="seconds"),
        platform=platform_text,
        is_windows=is_windows,
        integrations=integrations,
        components=components,
        files=files,
        ready=ready,
    )


def render_windows_runtime_report(report: WindowsRuntimeReport) -> list[str]:
    lines = [
        f"Windows audit plataforma: {report.platform}",
        f"Windows audit ambiente Windows: {'SIM' if report.is_windows else 'NAO'}",
        (
            "Windows audit integracoes: "
            + ", ".join(f"{key}={value}" for key, value in report.integrations.items())
        ),
    ]
    for component in report.components:
        required_text = "obrigatorio" if component.required else "opcional"
        lines.append(
            f"Windows audit componente [{component.status}] {component.label} ({required_text}) -> {component.details}"
        )
    for file_item in report.files:
        lines.append(
            f"Windows audit arquivo [{'OK' if file_item.exists else 'MISSING'}] {file_item.path}"
        )
    lines.append(f"Windows audit pronto para execucao: {'SIM' if report.ready else 'NAO'}")
    return lines


def write_windows_runtime_report(report: WindowsRuntimeReport, output_path: str | Path) -> Path:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": report.generated_at,
        "platform": report.platform,
        "is_windows": report.is_windows,
        "integrations": report.integrations,
        "components": [
            {
                "key": component.key,
                "label": component.label,
                "status": component.status,
                "required": component.required,
                "details": component.details,
            }
            for component in report.components
        ],
        "files": [
            {
                "path": item.path,
                "exists": item.exists,
            }
            for item in report.files
        ],
        "ready": report.ready,
    }
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return target
