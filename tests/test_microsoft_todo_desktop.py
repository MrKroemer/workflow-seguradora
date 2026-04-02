from datetime import date

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
