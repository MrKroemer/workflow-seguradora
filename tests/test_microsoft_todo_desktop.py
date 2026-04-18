from datetime import date

from rpa_corretora.config import MicrosoftTodoSettings
from rpa_corretora.integrations import microsoft_todo_desktop


def test_parse_tasks_from_blocks_desktop_extracts_title_and_due_date() -> None:
    today = date(2026, 4, 2)
    blocks = [
        "Renovar apolice cliente B\nVence em 15/04/2026",
        "Cobrar parcela aberta\nPrazo 2026-04-20",
    ]

    tasks = microsoft_todo_desktop._parse_tasks_from_blocks(
        blocks,
        today=today,
        list_name="Principal",
    )

    assert len(tasks) == 2
    assert tasks[0].title == "Renovar apolice cliente B"
    assert tasks[0].due_date == date(2026, 4, 15)
    assert tasks[1].title == "Cobrar parcela aberta"
    assert tasks[1].due_date == date(2026, 4, 20)


def test_parse_tasks_from_blocks_desktop_filters_noise_and_duplicates() -> None:
    today = date(2026, 4, 2)
    blocks = [
        "Adicionar tarefa",
        "Conferir pendencias",
        "Conferir pendencias\nHoje",
    ]

    tasks = microsoft_todo_desktop._parse_tasks_from_blocks(
        blocks,
        today=today,
        list_name="Principal",
    )

    assert len(tasks) == 1
    assert tasks[0].title == "Conferir pendencias"


def test_todo_desktop_automation_available_requires_windows(monkeypatch) -> None:
    monkeypatch.setattr(microsoft_todo_desktop.sys, "platform", "linux")
    monkeypatch.setattr(microsoft_todo_desktop.importlib.util, "find_spec", lambda _: object())

    assert microsoft_todo_desktop.todo_desktop_automation_available() is False


def test_todo_desktop_automation_available_requires_pywinauto(monkeypatch) -> None:
    monkeypatch.setattr(microsoft_todo_desktop.sys, "platform", "win32")
    monkeypatch.setattr(
        microsoft_todo_desktop.importlib.util,
        "find_spec",
        lambda module_name: None if module_name == "pywinauto" else object(),
    )

    assert microsoft_todo_desktop.todo_desktop_automation_available() is False


def test_parse_tasks_from_blocks_desktop_extracts_contact_fields() -> None:
    today = date(2026, 4, 2)
    blocks = [
        (
            "Cliente: Ana Silva\n"
            "Telefone: +55 (83) 99989-7477\n"
            "E-mail: ana.silva@pbseg.com\n"
            "Endereco: Rua das Flores, 100 - Centro"
        ),
    ]

    tasks = microsoft_todo_desktop._parse_tasks_from_blocks(
        blocks,
        today=today,
        list_name="INATIVOS",
    )

    assert len(tasks) == 1
    task = tasks[0]
    assert task.contact_phone == "+5583999897477"
    assert task.contact_email == "ana.silva@pbseg.com"
    assert "Rua das Flores" in (task.contact_address or "")


class _FakeElementInfo:
    def __init__(self, name: str) -> None:
        self.name = name


class _FakeEdit:
    def __init__(self, label: str) -> None:
        self._label = label
        self.element_info = _FakeElementInfo(label)
        self.cleared_to: str | None = None
        self.clicked = False

    def window_text(self) -> str:
        return self._label

    def click_input(self) -> None:
        self.clicked = True

    def set_edit_text(self, value: str) -> None:
        self.cleared_to = value


class _FakeWindow:
    def __init__(self, edits: list[_FakeEdit]) -> None:
        self._edits = edits
        self.focused = False

    def set_focus(self) -> None:
        self.focused = True

    def descendants(self, control_type: str):
        if control_type == "Edit":
            return list(self._edits)
        return []


def test_clear_search_filter_prefers_search_editor_cleanup() -> None:
    gateway = microsoft_todo_desktop.MicrosoftTodoDesktopGateway(
        settings=MicrosoftTodoSettings(username="user@example.com", password="Senha@123")
    )
    search_edit = _FakeEdit("Pesquisar")
    add_task_edit = _FakeEdit("Adicionar uma tarefa")
    window = _FakeWindow([search_edit, add_task_edit])

    gateway._clear_search_filter(window)

    assert window.focused is True
    assert search_edit.clicked is True
    assert search_edit.cleared_to == ""
    # Quick add should not be manipulated while clearing filters.
    assert add_task_edit.cleared_to is None
