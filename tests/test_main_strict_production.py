import pytest

from rpa_corretora.main import _enforce_strict_production_or_fail


def _strict_kwargs(*, segfy_mode: str) -> dict[str, object]:
    return {
        "strict_production": True,
        "using_real_sheets": True,
        "calendar_mode": "GOOGLE_API",
        "gmail_mode": "GMAIL_IMAP",
        "todo_mode": "DESKTOP_APP",
        "segfy_mode": segfy_mode,
        "portal_mode": "WEB_MULTI_ONLY",
        "whatsapp_mode": "HTTP_API",
        "email_mode": "SMTP",
        "report_email_to": "ops@example.com",
        "require_todo_desktop": True,
    }


def test_strict_production_accepts_segfy_api_only() -> None:
    _enforce_strict_production_or_fail(**_strict_kwargs(segfy_mode="API_ONLY"))


def test_strict_production_accepts_segfy_web_automation_only() -> None:
    _enforce_strict_production_or_fail(**_strict_kwargs(segfy_mode="WEB_AUTOMATION_ONLY"))


def test_strict_production_rejects_segfy_queue_only() -> None:
    with pytest.raises(RuntimeError) as exc:
        _enforce_strict_production_or_fail(**_strict_kwargs(segfy_mode="QUEUE_ONLY"))

    assert "Segfy em producao estrita precisa estar em API_ONLY ou WEB_AUTOMATION_ONLY" in str(exc.value)
