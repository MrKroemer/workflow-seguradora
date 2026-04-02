from datetime import date

from rpa_corretora.domain.models import TodoTask
from rpa_corretora.integrations.google_calendar_gateway import GoogleCalendarGateway


def test_google_calendar_gateway_maps_colors_and_fields(monkeypatch) -> None:
    gateway = GoogleCalendarGateway(
        client_id="client",
        client_secret="secret",
        refresh_token="refresh",
    )
    monkeypatch.setattr(gateway, "_acquire_access_token", lambda: "token")
    monkeypatch.setattr(
        gateway,
        "_google_get",
        lambda path, access_token: {
            "items": [
                {
                    "id": "evt-1",
                    "summary": "Cobranca de parcela - Ana Silva",
                    "colorId": "11",
                    "start": {"date": "2026-03-30"},
                    "description": "Telefone: +55 (83) 99989-7477",
                },
                {
                    "id": "evt-2",
                    "summary": "Nao mapeado",
                    "colorId": "1",
                    "start": {"date": "2026-03-30"},
                },
            ]
        },
    )

    commitments = gateway.fetch_daily_commitments(date(2026, 3, 30))

    assert len(commitments) == 1
    commitment = commitments[0]
    assert commitment.id == "evt-1"
    assert commitment.color == "VERMELHO"
    assert commitment.client_name == "Ana Silva"
    assert commitment.whatsapp_number == "+5583999897477"


def test_google_calendar_gateway_accepts_custom_color_map(monkeypatch) -> None:
    gateway = GoogleCalendarGateway(
        client_id="client",
        client_secret="secret",
        refresh_token="refresh",
        color_map={"1": "AZUL"},
    )
    monkeypatch.setattr(gateway, "_acquire_access_token", lambda: "token")
    monkeypatch.setattr(
        gateway,
        "_google_get",
        lambda path, access_token: {
            "items": [
                {
                    "id": "evt-1",
                    "summary": "Baixa de parcela - Joao",
                    "colorId": "1",
                    "start": {"date": "2026-03-30"},
                },
            ]
        },
    )

    commitments = gateway.fetch_daily_commitments(date(2026, 3, 30))

    assert len(commitments) == 1
    assert commitments[0].color == "AZUL"


def test_google_calendar_gateway_upserts_todo_event_create(monkeypatch) -> None:
    gateway = GoogleCalendarGateway(
        client_id="client",
        client_secret="secret",
        refresh_token="refresh",
        calendar_id="primary",
    )
    monkeypatch.setattr(gateway, "_acquire_access_token", lambda: "token")
    monkeypatch.setattr(gateway, "_google_get", lambda path, access_token: {"items": []})

    captured: dict[str, object] = {}

    def _fake_json_request(*, method, path, access_token, payload=None):
        captured["method"] = method
        captured["path"] = path
        captured["access_token"] = access_token
        captured["payload"] = payload
        return {"id": "evt-new-1"}

    monkeypatch.setattr(gateway, "_google_json_request", _fake_json_request)

    todo_task = TodoTask(
        id="desktop:principal:1:ana",
        title="VERMELHO | Ana Silva | AG:ABCDEF1234",
        due_date=date(2026, 4, 2),
        contact_phone="+5583999990000",
        contact_email="ana@example.com",
    )

    event_id = gateway.upsert_todo_task_event(task=todo_task)

    assert event_id == "evt-new-1"
    assert captured["method"] == "POST"
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["summary"] == "VERMELHO | Ana Silva | AG:ABCDEF1234"
    assert payload["colorId"] == "11"


def test_google_calendar_gateway_upserts_todo_event_update(monkeypatch) -> None:
    gateway = GoogleCalendarGateway(
        client_id="client",
        client_secret="secret",
        refresh_token="refresh",
        calendar_id="primary",
    )
    monkeypatch.setattr(gateway, "_acquire_access_token", lambda: "token")
    monkeypatch.setattr(gateway, "_google_get", lambda path, access_token: {"items": [{"id": "evt-existing"}]})

    captured: dict[str, object] = {}

    def _fake_json_request(*, method, path, access_token, payload=None):
        captured["method"] = method
        captured["path"] = path
        captured["access_token"] = access_token
        captured["payload"] = payload
        return {"id": "evt-existing"}

    monkeypatch.setattr(gateway, "_google_json_request", _fake_json_request)

    todo_task = TodoTask(
        id="desktop:principal:2:beto",
        title="Tratativa diversa - Beto",
        due_date=date(2026, 4, 3),
    )

    event_id = gateway.upsert_todo_task_event(task=todo_task)

    assert event_id == "evt-existing"
    assert captured["method"] == "PATCH"
