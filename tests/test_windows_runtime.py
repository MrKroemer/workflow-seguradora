from pathlib import Path

from rpa_corretora.diagnostics import windows_runtime


def _component_status(report, key: str) -> str:
    for component in report.components:
        if component.key == key:
            return component.status
    raise AssertionError(f"Componente nao encontrado: {key}")


def test_windows_runtime_report_non_windows_marks_browser_as_na(monkeypatch, tmp_path: Path) -> None:
    missing_file = tmp_path / "SEGUROS PBSEG.xlsx"
    monkeypatch.setattr(windows_runtime.sys, "platform", "linux")
    monkeypatch.setattr(windows_runtime, "_find_edge_executable", lambda: None)
    monkeypatch.setattr(windows_runtime, "_playwright_module_available", lambda: False)
    monkeypatch.setattr(windows_runtime, "_playwright_chromium_installed", lambda: (False, "/tmp/ms-playwright"))
    monkeypatch.setattr(windows_runtime, "_pywinauto_available", lambda: False)
    monkeypatch.setattr(windows_runtime, "_microsoft_todo_desktop_available", lambda: False)

    report = windows_runtime.build_windows_runtime_report(
        calendar_mode="NOOP",
        gmail_mode="NOOP",
        todo_mode="WEB_AUTOMATION",
        segfy_mode="QUEUE_ONLY",
        portal_mode="WEB_MULTI+STUB",
        whatsapp_mode="OUTBOX_FILE",
        email_mode="OUTBOX_FILE",
        files_to_check=[missing_file],
    )

    assert report.is_windows is False
    assert report.ready is False
    assert _component_status(report, "msedge") == "N_A"
    assert _component_status(report, "playwright_module") == "N_A"


def test_windows_runtime_report_windows_ready_when_required_components_ok(monkeypatch, tmp_path: Path) -> None:
    file_a = tmp_path / "SEGUROS PBSEG.xlsx"
    file_b = tmp_path / "ACOMPANHAMENTO 2026.xlsx"
    file_c = tmp_path / "FLUXO DE CAIXA.xlsx"
    file_a.write_text("ok", encoding="utf-8")
    file_b.write_text("ok", encoding="utf-8")
    file_c.write_text("ok", encoding="utf-8")

    monkeypatch.setattr(windows_runtime.sys, "platform", "win32")
    monkeypatch.setattr(windows_runtime, "_find_edge_executable", lambda: r"C:\Program Files\Microsoft\Edge\Application\msedge.exe")
    monkeypatch.setattr(windows_runtime, "_playwright_module_available", lambda: True)
    monkeypatch.setattr(windows_runtime, "_playwright_chromium_installed", lambda: (True, r"C:\Users\robot\AppData\Local\ms-playwright"))
    monkeypatch.setattr(windows_runtime, "_pywinauto_available", lambda: True)
    monkeypatch.setattr(windows_runtime, "_microsoft_todo_desktop_available", lambda: True)
    monkeypatch.setattr(windows_runtime.shutil, "which", lambda _: r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")

    report = windows_runtime.build_windows_runtime_report(
        calendar_mode="GOOGLE_API",
        gmail_mode="GMAIL_IMAP",
        todo_mode="WEB_AUTOMATION",
        segfy_mode="API_OR_QUEUE",
        portal_mode="WEB_MULTI+STUB",
        whatsapp_mode="HTTP_API",
        email_mode="SMTP",
        files_to_check=[file_a, file_b, file_c],
    )

    assert report.is_windows is True
    assert report.ready is True
    assert _component_status(report, "msedge") == "OK"
    assert _component_status(report, "playwright_module") == "OK"
    assert _component_status(report, "playwright_chromium") == "OK"


def test_write_windows_runtime_report_generates_json(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(windows_runtime.sys, "platform", "win32")
    monkeypatch.setattr(windows_runtime, "_find_edge_executable", lambda: r"C:\Edge\msedge.exe")
    monkeypatch.setattr(windows_runtime, "_playwright_module_available", lambda: True)
    monkeypatch.setattr(windows_runtime, "_playwright_chromium_installed", lambda: (True, r"C:\ms-playwright"))
    monkeypatch.setattr(windows_runtime, "_pywinauto_available", lambda: True)
    monkeypatch.setattr(windows_runtime, "_microsoft_todo_desktop_available", lambda: True)
    monkeypatch.setattr(windows_runtime.shutil, "which", lambda _: r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")

    report = windows_runtime.build_windows_runtime_report(
        calendar_mode="NOOP",
        gmail_mode="NOOP",
        todo_mode="NOOP",
        segfy_mode="QUEUE_ONLY",
        portal_mode="STUB",
        whatsapp_mode="OUTBOX_FILE",
        email_mode="OUTBOX_FILE",
        files_to_check=[],
    )

    output = tmp_path / "windows_runtime_report.json"
    written = windows_runtime.write_windows_runtime_report(report, output)

    assert written == output
    assert output.exists()
    assert "\"platform\"" in output.read_text(encoding="utf-8")


def test_windows_runtime_report_requires_desktop_components_for_todo_desktop(monkeypatch, tmp_path: Path) -> None:
    file_a = tmp_path / "SEGUROS PBSEG.xlsx"
    file_b = tmp_path / "ACOMPANHAMENTO 2026.xlsx"
    file_c = tmp_path / "FLUXO DE CAIXA.xlsx"
    file_a.write_text("ok", encoding="utf-8")
    file_b.write_text("ok", encoding="utf-8")
    file_c.write_text("ok", encoding="utf-8")

    monkeypatch.setattr(windows_runtime.sys, "platform", "win32")
    monkeypatch.setattr(windows_runtime, "_find_edge_executable", lambda: r"C:\Edge\msedge.exe")
    monkeypatch.setattr(windows_runtime, "_playwright_module_available", lambda: True)
    monkeypatch.setattr(windows_runtime, "_playwright_chromium_installed", lambda: (True, r"C:\ms-playwright"))
    monkeypatch.setattr(windows_runtime, "_pywinauto_available", lambda: False)
    monkeypatch.setattr(windows_runtime, "_microsoft_todo_desktop_available", lambda: False)
    monkeypatch.setattr(windows_runtime.shutil, "which", lambda _: r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")

    report = windows_runtime.build_windows_runtime_report(
        calendar_mode="GOOGLE_API",
        gmail_mode="NOOP",
        todo_mode="DESKTOP_APP",
        segfy_mode="QUEUE_ONLY",
        portal_mode="STUB",
        whatsapp_mode="OUTBOX_FILE",
        email_mode="OUTBOX_FILE",
        files_to_check=[file_a, file_b, file_c],
    )

    assert report.ready is False
    assert _component_status(report, "pywinauto_module") == "MISSING"
    assert _component_status(report, "microsoft_todo_desktop") == "MISSING"


def test_windows_runtime_report_strict_requires_real_integration_modes(monkeypatch, tmp_path: Path) -> None:
    file_a = tmp_path / "SEGUROS PBSEG.xlsx"
    file_b = tmp_path / "ACOMPANHAMENTO 2026.xlsx"
    file_c = tmp_path / "FLUXO DE CAIXA.xlsx"
    file_a.write_text("ok", encoding="utf-8")
    file_b.write_text("ok", encoding="utf-8")
    file_c.write_text("ok", encoding="utf-8")

    monkeypatch.setattr(windows_runtime.sys, "platform", "win32")
    monkeypatch.setattr(windows_runtime, "_find_edge_executable", lambda: r"C:\Edge\msedge.exe")
    monkeypatch.setattr(windows_runtime, "_find_chrome_executable", lambda: r"C:\Chrome\chrome.exe")
    monkeypatch.setattr(windows_runtime, "_playwright_module_available", lambda: True)
    monkeypatch.setattr(windows_runtime, "_playwright_chromium_installed", lambda: (True, r"C:\ms-playwright"))
    monkeypatch.setattr(windows_runtime, "_pywinauto_available", lambda: True)
    monkeypatch.setattr(windows_runtime, "_microsoft_todo_desktop_available", lambda: True)
    monkeypatch.setattr(windows_runtime.shutil, "which", lambda _: r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")

    report = windows_runtime.build_windows_runtime_report(
        calendar_mode="GOOGLE_API",
        gmail_mode="NOOP",
        todo_mode="DESKTOP_APP",
        segfy_mode="API_ONLY",
        portal_mode="WEB_MULTI_ONLY",
        whatsapp_mode="HTTP_API",
        email_mode="SMTP",
        files_to_check=[file_a, file_b, file_c],
        strict_production=True,
        require_todo_desktop=True,
    )

    assert report.ready is False
    assert _component_status(report, "strict_integrations") == "MISSING"


def test_windows_runtime_report_strict_accepts_segfy_web_automation_only(monkeypatch, tmp_path: Path) -> None:
    file_a = tmp_path / "SEGUROS PBSEG.xlsx"
    file_b = tmp_path / "ACOMPANHAMENTO 2026.xlsx"
    file_c = tmp_path / "FLUXO DE CAIXA.xlsx"
    file_a.write_text("ok", encoding="utf-8")
    file_b.write_text("ok", encoding="utf-8")
    file_c.write_text("ok", encoding="utf-8")

    monkeypatch.setattr(windows_runtime.sys, "platform", "win32")
    monkeypatch.setattr(windows_runtime, "_find_edge_executable", lambda: r"C:\Edge\msedge.exe")
    monkeypatch.setattr(windows_runtime, "_find_chrome_executable", lambda: r"C:\Chrome\chrome.exe")
    monkeypatch.setattr(windows_runtime, "_playwright_module_available", lambda: True)
    monkeypatch.setattr(windows_runtime, "_playwright_chromium_installed", lambda: (True, r"C:\ms-playwright"))
    monkeypatch.setattr(windows_runtime, "_pywinauto_available", lambda: True)
    monkeypatch.setattr(windows_runtime, "_microsoft_todo_desktop_available", lambda: True)
    monkeypatch.setattr(windows_runtime.shutil, "which", lambda _: r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")

    report = windows_runtime.build_windows_runtime_report(
        calendar_mode="GOOGLE_API",
        gmail_mode="GMAIL_IMAP",
        todo_mode="DESKTOP_APP",
        segfy_mode="WEB_AUTOMATION_ONLY",
        portal_mode="WEB_MULTI_ONLY",
        whatsapp_mode="HTTP_API",
        email_mode="SMTP",
        files_to_check=[file_a, file_b, file_c],
        strict_production=True,
        require_todo_desktop=True,
    )

    assert report.ready is True
    assert _component_status(report, "strict_integrations") == "OK"
