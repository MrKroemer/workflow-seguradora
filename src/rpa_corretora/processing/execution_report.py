from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from traceback import format_exception
from typing import Literal
import json


StageStatus = Literal["EXECUTADO", "FALHOU", "IGNORADO"]
GeneralStatus = Literal["SUCESSO TOTAL", "SUCESSO PARCIAL", "FALHA CRITICA"]


STAGE_DEFINITIONS: tuple[tuple[str, str], ...] = (
    ("google_calendar", "Google Calendar"),
    ("microsoft_todo", "Microsoft To Do"),
    ("gmail", "Gmail"),
    ("segfy", "Segfy CRM"),
    ("insurer_portals", "Portais das seguradoras"),
    ("spreadsheets", "Planilhas operacionais"),
    ("whatsapp", "Notificacoes via WhatsApp"),
    ("dashboard", "Dashboard consolidado"),
)


@dataclass(slots=True)
class StageExecution:
    key: str
    name: str
    status: StageStatus
    result: str
    started_at: datetime
    ended_at: datetime
    error_message: str = ""
    exception_type: str = ""
    error_context: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class NonExecutedItem:
    item_id: str
    reason: str
    recommended_action: str


@dataclass(slots=True)
class ErrorLogEntry:
    timestamp: datetime
    stage_name: str
    exception_type: str
    message: str
    context: dict[str, str]
    traceback_lines: list[str]


@dataclass(slots=True)
class ExecutionReport:
    run_id: str
    bot_version: str
    cycle_started_at: datetime
    cycle_ended_at: datetime
    tasks_planned: int
    tasks_succeeded: int
    tasks_failed_or_not_executed: int
    overall_status: GeneralStatus
    stages: list[StageExecution]
    non_executed_items: list[NonExecutedItem]
    error_log: list[ErrorLogEntry]


class ExecutionTraceCollector:
    def __init__(
        self,
        *,
        run_id: str,
        bot_version: str,
        cycle_started_at: datetime,
    ) -> None:
        self.run_id = run_id
        self.bot_version = bot_version
        self.cycle_started_at = cycle_started_at
        self._stage_names = {key: name for key, name in STAGE_DEFINITIONS}
        self._stage_started: dict[str, datetime] = {}
        self._stages: dict[str, StageExecution] = {}
        self.non_executed_items: list[NonExecutedItem] = []
        self.error_log: list[ErrorLogEntry] = []
        self._critical_failure = False

    def start_stage(self, stage_key: str) -> None:
        self._validate_stage(stage_key)
        self._stage_started[stage_key] = datetime.now()

    def complete_stage(self, stage_key: str, result: str) -> None:
        self._validate_stage(stage_key)
        now = datetime.now()
        started_at = self._stage_started.get(stage_key, now)
        self._stages[stage_key] = StageExecution(
            key=stage_key,
            name=self._stage_names[stage_key],
            status="EXECUTADO",
            result=result,
            started_at=started_at,
            ended_at=now,
        )

    def fail_stage(
        self,
        stage_key: str,
        error: Exception,
        *,
        context: dict[str, str] | None = None,
        result: str | None = None,
    ) -> None:
        self._validate_stage(stage_key)
        now = datetime.now()
        started_at = self._stage_started.get(stage_key, now)
        normalized_context = context or {}
        self._stages[stage_key] = StageExecution(
            key=stage_key,
            name=self._stage_names[stage_key],
            status="FALHOU",
            result=result or "Execucao interrompida por excecao.",
            started_at=started_at,
            ended_at=now,
            error_message=str(error),
            exception_type=error.__class__.__name__,
            error_context=normalized_context,
        )
        self._append_error(stage_name=self._stage_names[stage_key], error=error, context=normalized_context)

    def ignore_stage(
        self,
        stage_key: str,
        *,
        reason: str,
        recommended_action: str,
        result: str = "Etapa ignorada no ciclo atual.",
        item_id: str | None = None,
    ) -> None:
        self._validate_stage(stage_key)
        now = datetime.now()
        started_at = self._stage_started.get(stage_key, now)
        self._stages[stage_key] = StageExecution(
            key=stage_key,
            name=self._stage_names[stage_key],
            status="IGNORADO",
            result=result,
            started_at=started_at,
            ended_at=now,
        )
        self.add_non_executed_item(
            item_id=item_id or self._stage_names[stage_key],
            reason=reason,
            recommended_action=recommended_action,
        )

    def add_non_executed_item(self, *, item_id: str, reason: str, recommended_action: str) -> None:
        self.non_executed_items.append(
            NonExecutedItem(
                item_id=item_id,
                reason=reason,
                recommended_action=recommended_action,
            )
        )

    def log_error(self, *, stage_name: str, error: Exception, context: dict[str, str] | None = None) -> None:
        self._append_error(stage_name=stage_name, error=error, context=context or {})

    def mark_critical_failure(
        self,
        *,
        stage_name: str,
        error: Exception,
        context: dict[str, str] | None = None,
    ) -> None:
        self._critical_failure = True
        self._append_error(stage_name=stage_name, error=error, context=context or {})

    def finalize(self, cycle_ended_at: datetime) -> ExecutionReport:
        self._ensure_missing_stages(cycle_ended_at)
        stages_ordered = [self._stages[key] for key, _ in STAGE_DEFINITIONS]

        tasks_planned = len(STAGE_DEFINITIONS)
        tasks_succeeded = sum(1 for stage in stages_ordered if stage.status == "EXECUTADO")
        tasks_failed_or_not_executed = tasks_planned - tasks_succeeded

        overall_status: GeneralStatus
        if self._critical_failure:
            overall_status = "FALHA CRITICA"
        elif tasks_failed_or_not_executed == 0:
            overall_status = "SUCESSO TOTAL"
        else:
            overall_status = "SUCESSO PARCIAL"

        return ExecutionReport(
            run_id=self.run_id,
            bot_version=self.bot_version,
            cycle_started_at=self.cycle_started_at,
            cycle_ended_at=cycle_ended_at,
            tasks_planned=tasks_planned,
            tasks_succeeded=tasks_succeeded,
            tasks_failed_or_not_executed=tasks_failed_or_not_executed,
            overall_status=overall_status,
            stages=stages_ordered,
            non_executed_items=list(self.non_executed_items),
            error_log=list(self.error_log),
        )

    def _append_error(self, *, stage_name: str, error: Exception, context: dict[str, str]) -> None:
        self.error_log.append(
            ErrorLogEntry(
                timestamp=datetime.now(),
                stage_name=stage_name,
                exception_type=error.__class__.__name__,
                message=str(error),
                context=context,
                traceback_lines=format_exception(error),
            )
        )

    def _ensure_missing_stages(self, cycle_ended_at: datetime) -> None:
        for stage_key, stage_name in STAGE_DEFINITIONS:
            if stage_key in self._stages:
                continue
            self._stages[stage_key] = StageExecution(
                key=stage_key,
                name=stage_name,
                status="IGNORADO",
                result="Etapa nao executada devido a interrupcao antecipada do ciclo.",
                started_at=cycle_ended_at,
                ended_at=cycle_ended_at,
            )
            self.non_executed_items.append(
                NonExecutedItem(
                    item_id=stage_name,
                    reason="Fluxo interrompido antes desta etapa.",
                    recommended_action="Reprocessar o ciclo apos corrigir a falha anterior.",
                )
            )

    def _validate_stage(self, stage_key: str) -> None:
        if stage_key not in self._stage_names:
            raise ValueError(f"Etapa desconhecida: {stage_key}")


def next_run_identifier(output_dir: str | Path, started_at: datetime) -> str:
    target = Path(output_dir)
    day_token = started_at.strftime("%Y%m%d")
    existing_files = sorted(target.glob(f"relatorio_execucao_{day_token}_*.json"))
    sequence = len(existing_files) + 1
    return f"RUN-{day_token}-{sequence:03d}"


def execution_report_paths(output_dir: str | Path, started_at: datetime) -> tuple[Path, Path]:
    base_dir = Path(output_dir)
    timestamp = started_at.strftime("%Y%m%d_%H%M%S")
    stem = f"relatorio_execucao_{timestamp}"
    return base_dir / f"{stem}.json", base_dir / f"{stem}.pdf"


def execution_report_payload(report: ExecutionReport) -> dict[str, object]:
    return {
        "cabecalho": {
            "inicio_ciclo": report.cycle_started_at.isoformat(),
            "fim_ciclo": report.cycle_ended_at.isoformat(),
            "identificador_execucao": report.run_id,
            "versao_bot": report.bot_version,
        },
        "resumo_executivo": {
            "tarefas_previstas": report.tasks_planned,
            "tarefas_sucesso": report.tasks_succeeded,
            "tarefas_falha_ou_nao_executadas": report.tasks_failed_or_not_executed,
            "status_geral": report.overall_status,
        },
        "detalhamento_por_etapa": [
            {
                "nome_etapa": stage.name,
                "status": stage.status,
                "resultado": stage.result,
                "erro": {
                    "mensagem": stage.error_message,
                    "tipo_excecao": stage.exception_type,
                    "contexto": stage.error_context,
                },
                "inicio": stage.started_at.isoformat(),
                "fim": stage.ended_at.isoformat(),
            }
            for stage in report.stages
        ],
        "itens_nao_executados": [
            {
                "item_id": item.item_id,
                "motivo": item.reason,
                "acao_recomendada": item.recommended_action,
            }
            for item in report.non_executed_items
        ],
        "log_de_erros": [
            {
                "timestamp": error.timestamp.isoformat(),
                "etapa": error.stage_name,
                "tipo_excecao": error.exception_type,
                "mensagem": error.message,
                "contexto": error.context,
                "traceback": "".join(error.traceback_lines),
            }
            for error in report.error_log
        ],
    }


def write_execution_report_json(report: ExecutionReport, output_path: str | Path) -> Path:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = execution_report_payload(report)
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return target


def render_execution_report_lines(report: ExecutionReport) -> list[str]:
    lines: list[str] = []

    lines.append("RELATORIO DE EXECUCAO - RPA CORRETORA")
    lines.append("=" * 72)
    lines.append(f"Run ID: {report.run_id}")
    lines.append(f"Versao do bot: {report.bot_version}")
    lines.append(f"Inicio do ciclo: {report.cycle_started_at.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"Fim do ciclo: {report.cycle_ended_at.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")

    lines.append("RESUMO EXECUTIVO")
    lines.append("-" * 72)
    lines.append(f"Total previsto: {report.tasks_planned}")
    lines.append(f"Total com sucesso: {report.tasks_succeeded}")
    lines.append(f"Falha ou nao executadas: {report.tasks_failed_or_not_executed}")
    lines.append(f"Status geral: {report.overall_status}")
    lines.append("")

    lines.append("DETALHAMENTO POR ETAPA")
    lines.append("-" * 72)
    for stage in report.stages:
        lines.append(f"Etapa: {stage.name}")
        lines.append(f"Status: {stage.status}")
        lines.append(f"Inicio: {stage.started_at.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"Fim: {stage.ended_at.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"Resultado: {stage.result}")
        if stage.status == "FALHOU":
            lines.append(f"Erro: {stage.error_message}")
            lines.append(f"Excecao: {stage.exception_type}")
            if stage.error_context:
                lines.append(f"Contexto: {stage.error_context}")
        lines.append("")

    lines.append("ITENS NAO EXECUTADOS")
    lines.append("-" * 72)
    if not report.non_executed_items:
        lines.append("Nenhum item nao executado registrado.")
    else:
        for index, item in enumerate(report.non_executed_items, start=1):
            lines.append(f"{index}. Item: {item.item_id}")
            lines.append(f"   Motivo: {item.reason}")
            lines.append(f"   Acao recomendada: {item.recommended_action}")
    lines.append("")

    lines.append("LOG DE ERROS")
    lines.append("-" * 72)
    if not report.error_log:
        lines.append("Nenhuma excecao capturada no ciclo.")
    else:
        for index, entry in enumerate(report.error_log, start=1):
            lines.append(f"{index}. [{entry.timestamp.strftime('%Y-%m-%d %H:%M:%S')}] {entry.stage_name}")
            lines.append(f"   {entry.exception_type}: {entry.message}")
            if entry.context:
                lines.append(f"   Contexto: {entry.context}")
            lines.append("   Traceback:")
            for trace_line in "".join(entry.traceback_lines).splitlines():
                lines.append(f"     {trace_line}")
            lines.append("")

    return lines


def write_execution_report_pdf(report: ExecutionReport, output_path: str | Path) -> Path:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = render_execution_report_lines(report)
    _write_text_pdf(lines, target)
    return target


def _write_text_pdf(lines: list[str], target: Path) -> None:
    page_width = 595
    page_height = 842
    line_height = 14
    margin_left = 40
    margin_top = 800
    max_lines_per_page = 52

    if not lines:
        lines = ["Relatorio vazio."]

    pages = [lines[index : index + max_lines_per_page] for index in range(0, len(lines), max_lines_per_page)]

    objects: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }

    kids_refs: list[str] = []
    next_object_id = 4

    for page_lines in pages:
        page_object_id = next_object_id
        content_object_id = next_object_id + 1
        next_object_id += 2

        kids_refs.append(f"{page_object_id} 0 R")

        page_dict = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {page_width} {page_height}] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_object_id} 0 R >>"
        )
        objects[page_object_id] = page_dict.encode("latin-1")

        content_stream = _build_page_stream(
            lines=page_lines,
            margin_left=margin_left,
            margin_top=margin_top,
            line_height=line_height,
        )
        stream_header = f"<< /Length {len(content_stream)} >>\nstream\n".encode("latin-1")
        stream_footer = b"\nendstream"
        objects[content_object_id] = stream_header + content_stream + stream_footer

    kids_encoded = "[" + " ".join(kids_refs) + "]"
    objects[2] = f"<< /Type /Pages /Kids {kids_encoded} /Count {len(pages)} >>".encode("latin-1")

    max_object_id = max(objects.keys())
    buffer = bytearray()
    buffer.extend(b"%PDF-1.4\n")
    buffer.extend(b"%\xe2\xe3\xcf\xd3\n")

    offsets = [0] * (max_object_id + 1)
    for object_id in range(1, max_object_id + 1):
        payload = objects[object_id]
        offsets[object_id] = len(buffer)
        buffer.extend(f"{object_id} 0 obj\n".encode("latin-1"))
        buffer.extend(payload)
        buffer.extend(b"\nendobj\n")

    xref_start = len(buffer)
    buffer.extend(f"xref\n0 {max_object_id + 1}\n".encode("latin-1"))
    buffer.extend(b"0000000000 65535 f \n")
    for object_id in range(1, max_object_id + 1):
        buffer.extend(f"{offsets[object_id]:010d} 00000 n \n".encode("latin-1"))

    trailer = (
        f"trailer\n<< /Size {max_object_id + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_start}\n%%EOF\n"
    )
    buffer.extend(trailer.encode("latin-1"))

    target.write_bytes(bytes(buffer))


def _build_page_stream(*, lines: list[str], margin_left: int, margin_top: int, line_height: int) -> bytes:
    stream_lines = [
        "BT",
        "/F1 10 Tf",
        f"{line_height} TL",
        f"{margin_left} {margin_top} Td",
    ]

    for index, line in enumerate(lines):
        safe_line = _escape_pdf_text(line)
        if index > 0:
            stream_lines.append("T*")
        stream_lines.append(f"({safe_line}) Tj")

    stream_lines.append("ET")
    return "\n".join(stream_lines).encode("latin-1")


def _escape_pdf_text(text: str) -> str:
    safe = text.encode("latin-1", errors="replace").decode("latin-1")
    safe = safe.replace("\\", "\\\\")
    safe = safe.replace("(", "\\(")
    safe = safe.replace(")", "\\)")
    return safe
