from datetime import date

from rpa_corretora.config import MicrosoftTodoSettings
from rpa_corretora.integrations.microsoft_todo_graph import MicrosoftTodoGraphGateway


def test_fetch_open_tasks_filters_completed_and_maps_due_date(monkeypatch) -> None:
    gateway = MicrosoftTodoGraphGateway(
        MicrosoftTodoSettings(client_id="client", refresh_token="refresh"),
    )

    monkeypatch.setattr(gateway, "_acquire_access_token", lambda: "token")

    def fake_graph_get(path: str, access_token: str):
        assert access_token == "token"
        if path.startswith("/me/todo/lists?$select=id,displayName"):
            return {"value": [{"id": "list-1", "displayName": "Principal"}]}
        if path.startswith("/me/todo/lists/list-1/tasks"):
            return {
                "value": [
                    {
                        "id": "task-1",
                        "title": "Ligar para cliente",
                        "status": "notStarted",
                        "dueDateTime": {"dateTime": "2026-04-01T12:30:00Z"},
                    },
                    {
                        "id": "task-2",
                        "title": "Concluida",
                        "status": "completed",
                    },
                ]
            }
        return {"value": []}

    monkeypatch.setattr(gateway, "_graph_get", fake_graph_get)

    tasks = gateway.fetch_open_tasks()

    assert len(tasks) == 1
    assert tasks[0].id == "task-1"
    assert tasks[0].title == "Principal: Ligar para cliente"
    assert tasks[0].due_date == date(2026, 4, 1)


def test_acquire_access_token_uses_refresh_token_first(monkeypatch) -> None:
    gateway = MicrosoftTodoGraphGateway(
        MicrosoftTodoSettings(
            client_id="client",
            client_secret="secret",
            refresh_token="refresh",
            username="usuario@exemplo.com",
            password="Senha@123",
        )
    )

    captured: dict[str, str] = {}

    def fake_token_request(form_data: dict[str, str]):
        captured.update(form_data)
        return {"access_token": "token-123"}

    monkeypatch.setattr(gateway, "_token_request", fake_token_request)

    token = gateway._acquire_access_token()

    assert token == "token-123"
    assert captured["grant_type"] == "refresh_token"
    assert captured["refresh_token"] == "refresh"


def test_fetch_open_tasks_returns_empty_when_no_credentials() -> None:
    gateway = MicrosoftTodoGraphGateway(MicrosoftTodoSettings())

    tasks = gateway.fetch_open_tasks()

    assert tasks == []
