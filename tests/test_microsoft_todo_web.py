from datetime import date, timedelta

from rpa_corretora.integrations import microsoft_todo_web


def test_parse_tasks_from_blocks_extracts_title_and_due_date() -> None:
    today = date(2026, 3, 30)
    blocks = [
        "Renovar apolice cliente A\nVence em 10/04/2026",
        "Conferir comissao\nPrazo 2026-05-02",
    ]

    tasks = microsoft_todo_web._parse_tasks_from_blocks(blocks, today=today)

    assert len(tasks) == 2
    assert tasks[0].title == "Renovar apolice cliente A"
    assert tasks[0].due_date == date(2026, 4, 10)
    assert tasks[1].title == "Conferir comissao"
    assert tasks[1].due_date == date(2026, 5, 2)


def test_parse_tasks_from_blocks_filters_noise_and_duplicates() -> None:
    today = date(2026, 3, 30)
    blocks = [
        "Adicionar tarefa",
        "Conferir pendencias do To Do",
        "Conferir pendencias do To Do\nHoje",
    ]

    tasks = microsoft_todo_web._parse_tasks_from_blocks(blocks, today=today)

    assert len(tasks) == 1
    assert tasks[0].title == "Conferir pendencias do To Do"
    assert tasks[0].due_date == today + timedelta(days=3650)


def test_parse_tasks_from_blocks_filters_accented_noise() -> None:
    today = date(2026, 3, 30)
    blocks = [
        "Concluido",
        "Concluído",
        "Iniciar sessão",
        "Tarefa valida de renovacao",
    ]

    tasks = microsoft_todo_web._parse_tasks_from_blocks(blocks, today=today)

    assert len(tasks) == 1
    assert tasks[0].title == "Tarefa valida de renovacao"


def test_todo_web_automation_available_requires_windows(monkeypatch) -> None:
    monkeypatch.setattr(microsoft_todo_web.sys, "platform", "linux")

    assert microsoft_todo_web.todo_web_automation_available() is False
