from __future__ import annotations

from datetime import datetime
import json

from rpa_corretora.processing.execution_report import (
    ExecutionTraceCollector,
    STAGE_DEFINITIONS,
    execution_report_payload,
    write_execution_report_json,
    write_execution_report_pdf,
)


def test_execution_report_payload_contains_required_sections() -> None:
    trace = ExecutionTraceCollector(
        run_id="RUN-20260401-001",
        bot_version="0.1.0",
        cycle_started_at=datetime(2026, 4, 1, 9, 0, 0),
    )
    trace.start_stage("google_calendar")
    trace.complete_stage("google_calendar", "2 compromissos lidos")
    trace.ignore_stage(
        "dashboard",
        reason="Dashboard desativado para teste.",
        recommended_action="Habilitar dashboard.",
    )

    report = trace.finalize(cycle_ended_at=datetime(2026, 4, 1, 9, 10, 0))
    payload = execution_report_payload(report)

    assert "cabecalho" in payload
    assert "resumo_executivo" in payload
    assert "detalhamento_por_etapa" in payload
    assert "itens_nao_executados" in payload
    assert "log_de_erros" in payload

    details = payload["detalhamento_por_etapa"]
    assert isinstance(details, list)
    assert len(details) == len(STAGE_DEFINITIONS)

    names = {item["nome_etapa"] for item in details}
    assert "Google Calendar" in names
    assert "Dashboard consolidado" in names


def test_write_execution_report_outputs_json_and_pdf(tmp_path) -> None:
    trace = ExecutionTraceCollector(
        run_id="RUN-20260401-002",
        bot_version="0.1.0",
        cycle_started_at=datetime(2026, 4, 1, 10, 0, 0),
    )

    for stage_key, _ in STAGE_DEFINITIONS:
        trace.start_stage(stage_key)
        trace.complete_stage(stage_key, "ok")

    report = trace.finalize(cycle_ended_at=datetime(2026, 4, 1, 10, 5, 0))

    json_path = tmp_path / "relatorio_execucao_20260401_100500.json"
    pdf_path = tmp_path / "relatorio_execucao_20260401_100500.pdf"

    written_json = write_execution_report_json(report, json_path)
    written_pdf = write_execution_report_pdf(report, pdf_path)

    assert written_json == json_path
    assert written_pdf == pdf_path
    assert json_path.exists()
    assert pdf_path.exists()

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["cabecalho"]["identificador_execucao"] == "RUN-20260401-002"
    assert payload["resumo_executivo"]["status_geral"] == "SUCESSO TOTAL"

    pdf_bytes = pdf_path.read_bytes()
    assert pdf_bytes.startswith(b"%PDF-1.4")


def test_critical_failure_still_generates_complete_stage_list() -> None:
    trace = ExecutionTraceCollector(
        run_id="RUN-20260401-003",
        bot_version="0.1.0",
        cycle_started_at=datetime(2026, 4, 1, 11, 0, 0),
    )
    trace.start_stage("google_calendar")
    trace.complete_stage("google_calendar", "ok")
    trace.mark_critical_failure(
        stage_name="Main",
        error=RuntimeError("falha critica simulada"),
        context={"fase": "teste"},
    )

    report = trace.finalize(cycle_ended_at=datetime(2026, 4, 1, 11, 1, 0))

    assert report.overall_status == "FALHA CRITICA"
    assert len(report.stages) == len(STAGE_DEFINITIONS)
    assert len(report.error_log) == 1
