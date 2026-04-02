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


def test_create_task_uses_target_list(monkeypatch) -> None:
    gateway = MicrosoftTodoGraphGateway(
        MicrosoftTodoSettings(client_id="client", refresh_token="refresh", list_name="Principal"),
    )
    monkeypatch.setattr(gateway, "_acquire_access_token", lambda: "token")
    monkeypatch.setattr(gateway, "_list_metadata", lambda _: [("list-1", "Principal"), ("list-2", "Outras")])

    captured: dict[str, object] = {}

    def fake_graph_post(path: str, access_token: str, payload: dict[str, object]):
        captured["path"] = path
        captured["token"] = access_token
        captured["payload"] = payload
        return {"id": "task-55"}

    monkeypatch.setattr(gateway, "_graph_post", fake_graph_post)

    task_id = gateway.create_task(title="Nova tarefa", due_date=date(2026, 4, 1), notes="Detalhes")

    assert task_id == "task-55"
    assert captured["token"] == "token"
    assert captured["path"] == "/me/todo/lists/list-1/tasks"
    assert "dueDateTime" in captured["payload"]


def test_complete_task_updates_status_completed(monkeypatch) -> None:
    gateway = MicrosoftTodoGraphGateway(
        MicrosoftTodoSettings(client_id="client", refresh_token="refresh"),
    )
    monkeypatch.setattr(gateway, "_acquire_access_token", lambda: "token")
    monkeypatch.setattr(gateway, "_resolve_list_id_for_task", lambda task_id, _: "list-1" if task_id == "task-1" else None)

    captured: dict[str, object] = {}

    def fake_graph_patch(path: str, access_token: str, payload: dict[str, object]):
        captured["path"] = path
        captured["token"] = access_token
        captured["payload"] = payload
        return {}

    monkeypatch.setattr(gateway, "_graph_patch", fake_graph_patch)

    assert gateway.complete_task(task_id="task-1") is True
    assert captured["path"] == "/me/todo/lists/list-1/tasks/task-1"
    assert captured["payload"] == {"status": "completed"}
