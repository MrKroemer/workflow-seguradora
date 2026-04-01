from __future__ import annotations

import argparse
from datetime import date, datetime
import os
from pathlib import Path

from rpa_corretora import __version__
from rpa_corretora.config import load_settings
from rpa_corretora.diagnostics.windows_runtime import (
    build_windows_runtime_report,
    render_windows_runtime_report,
    write_windows_runtime_report,
)
from rpa_corretora.env_loader import load_env_file
from rpa_corretora.integrations.credentials_pdf import load_credentials_from_pdf
from rpa_corretora.integrations.gmail_imap_gateway import GmailImapGateway
from rpa_corretora.integrations.google_calendar_gateway import GoogleCalendarGateway
from rpa_corretora.integrations.insurer_portal_porto import (
    PortoPortalCredentials,
    PortoSeguroPortalGateway,
)
from rpa_corretora.integrations.insurer_portal_wave1 import (
    CascadingInsurerPortalGateway,
    MapfrePortalCredentials,
    MapfrePortalGateway,
    YelumPortalCredentials,
    YelumPortalGateway,
    web_portal_automation_available,
)
from rpa_corretora.integrations.insurer_portal_wave2 import (
    AllianzPortalCredentials,
    AllianzPortalGateway,
    AzulPortalCredentials,
    AzulPortalGateway,
    BradescoPortalCredentials,
    BradescoPortalGateway,
    HDIPortalCredentials,
    HDIPortalGateway,
    SuhaiPortalCredentials,
    SuhaiPortalGateway,
    TokioMarinePortalGateway,
    TokioPortalCredentials,
)
from rpa_corretora.integrations.microsoft_todo_graph import MicrosoftTodoGraphGateway
from rpa_corretora.integrations.microsoft_todo_web import (
    MicrosoftTodoWebGateway,
    todo_web_automation_available,
)
from rpa_corretora.integrations.noop_adapters import (
    FileOutboxEmailSenderGateway,
    FileOutboxWhatsAppGateway,
    NoopCalendarGateway,
    NoopGmailGateway,
    NoopTodoGateway,
)
from rpa_corretora.integrations.segfy_gateway import SegfyGateway
from rpa_corretora.integrations.smtp_email_sender import SmtpEmailSenderGateway
from rpa_corretora.integrations.stub_adapters import (
    StubInsurerPortalGateway,
    StubSpreadsheetGateway,
)
from rpa_corretora.integrations.whatsapp_http_gateway import WhatsAppHttpGateway
from rpa_corretora.integrations.workbook_gateway import WorkbookSpreadsheetGateway
from rpa_corretora.processing.dashboard import DashboardBuilder
from rpa_corretora.processing.dashboard_web import DashboardMeta, write_dashboard_html
from rpa_corretora.processing.execution_report import (
    ExecutionTraceCollector,
    execution_report_paths,
    next_run_identifier,
    write_execution_report_json,
    write_execution_report_pdf,
)
from rpa_corretora.processing.orchestrator import DailyProcessor


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Execucao diaria do RPA Corretora")
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Data de referencia no formato YYYY-MM-DD",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Executa sem envio de notificacoes externas",
    )
    parser.add_argument(
        "--use-stub-sheets",
        action="store_true",
        help="Forca uso do gateway de planilhas stub mesmo com arquivos reais configurados",
    )
    parser.add_argument(
        "--scan-credentials",
        action="store_true",
        help="Executa OCR no SENHAS.pdf e lista apenas os servicos encontrados",
    )
    parser.add_argument(
        "--env-file",
        type=str,
        default=".env",
        help="Caminho para arquivo de variaveis de ambiente (padrao: .env)",
    )
    parser.add_argument(
        "--dashboard-html-output",
        type=str,
        default="outputs/dashboard_latest.html",
        help="Caminho do arquivo HTML de dashboard gerado ao final da execucao",
    )
    parser.add_argument(
        "--no-dashboard-html",
        action="store_true",
        help="Desativa a geracao do dashboard visual em HTML",
    )
    parser.add_argument(
        "--windows-audit-only",
        action="store_true",
        help="Executa apenas auditoria de ambiente Windows e encerra",
    )
    parser.add_argument(
        "--windows-audit-output",
        type=str,
        default="outputs/windows_runtime_report.json",
        help="Caminho do JSON com diagnostico de ambiente Windows",
    )
    parser.add_argument(
        "--files-dir",
        type=str,
        default=None,
        help=(
            "Diretorio base com os arquivos operacionais. "
            "Quando informado, define automaticamente os caminhos "
            "de SEGUROS PBSEG.xlsx, ACOMPANHAMENTO 2026.xlsx, FLUXO DE CAIXA.xlsx e SENHAS.pdf."
        ),
    )
    parser.add_argument(
        "--execution-report-dir",
        type=str,
        default=None,
        help="Diretorio para salvar relatorio_execucao_YYYYMMDD_HHMMSS.{json,pdf}",
    )
    return parser


def _parse_date(raw_date: str | None) -> date:
    if raw_date is None:
        return date.today()
    return date.fromisoformat(raw_date)


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on", "sim"}:
        return True
    if normalized in {"0", "false", "no", "off", "nao"}:
        return False
    return default


def _env_int(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _resolve_portal_credentials(
    *,
    env_user_key: str,
    env_password_key: str,
    service_tokens: tuple[str, ...],
    credentials_from_pdf: dict[str, object],
) -> tuple[str | None, str | None]:
    username = (os.getenv(env_user_key) or "").strip()
    password = (os.getenv(env_password_key) or "").strip()
    if username and password:
        return username, password

    normalized_tokens = {token.upper().strip() for token in service_tokens}
    for key, value in credentials_from_pdf.items():
        if key.upper().strip() in normalized_tokens:
            return value.username, value.password

    for key, value in credentials_from_pdf.items():
        if any(token in key.upper() for token in normalized_tokens):
            return value.username, value.password
    return None, None


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    cycle_started_at = datetime.now()
    report_json_path = Path("outputs/relatorio_execucao_fallback.json")
    report_pdf_path = Path("outputs/relatorio_execucao_fallback.pdf")
    trace: ExecutionTraceCollector | None = None
    fatal_error: Exception | None = None
    effective_dry_run = args.dry_run or args.scan_credentials
    report_email_to = ""
    email_sender_gateway = FileOutboxEmailSenderGateway()

    try:
        load_env_file(args.env_file)

        if args.files_dir:
            base_dir = Path(args.files_dir)
            os.environ["SEGUROS_PBSEG_XLSX"] = str(base_dir / "SEGUROS PBSEG.xlsx")
            os.environ["ACOMPANHAMENTO_2026_XLSX"] = str(base_dir / "ACOMPANHAMENTO 2026.xlsx")
            os.environ["FLUXO_CAIXA_XLSX"] = str(base_dir / "FLUXO DE CAIXA.xlsx")
            os.environ["SENHAS_PDF"] = str(base_dir / "SENHAS.pdf")

        report_dir = Path(
            args.execution_report_dir
            or (os.getenv("EXECUTION_REPORT_OUTPUT_DIR") or "").strip()
            or "outputs"
        )
        run_id = next_run_identifier(report_dir, cycle_started_at)
        report_json_path, report_pdf_path = execution_report_paths(report_dir, cycle_started_at)
        trace = ExecutionTraceCollector(
            run_id=run_id,
            bot_version=__version__,
            cycle_started_at=cycle_started_at,
        )

        run_date = _parse_date(args.date)
        settings = load_settings()
        credentials_from_pdf: dict[str, object] = {}
        if _env_flag("PORTAL_USE_PDF_CREDENTIALS", default=False):
            if settings.files is None or settings.files.senhas_pdf is None or not settings.files.senhas_pdf.exists():
                print("[Portais] PORTAL_USE_PDF_CREDENTIALS=1, mas SENHAS.pdf nao esta disponivel.")
            else:
                try:
                    credentials_from_pdf = load_credentials_from_pdf(settings.files.senhas_pdf)
                except Exception as exc:
                    print(f"[Portais] Falha ao ler credenciais do PDF: {exc}")

        sheets_gateway = StubSpreadsheetGateway()
        using_real_sheets = False
        sheets_hint = ""
        if not args.use_stub_sheets and settings.files is not None:
            missing_files: list[str] = []
            if not settings.files.seguros_pbseg_xlsx.exists():
                missing_files.append(str(settings.files.seguros_pbseg_xlsx))
            if not settings.files.acompanhamento_2026_xlsx.exists():
                missing_files.append(str(settings.files.acompanhamento_2026_xlsx))
            if not settings.files.fluxo_caixa_xlsx.exists():
                missing_files.append(str(settings.files.fluxo_caixa_xlsx))

            if not missing_files:
                sheets_gateway = WorkbookSpreadsheetGateway(
                    seguros_pbseg_path=settings.files.seguros_pbseg_xlsx,
                    acompanhamento_path=settings.files.acompanhamento_2026_xlsx,
                    fluxo_caixa_path=settings.files.fluxo_caixa_xlsx,
                )
                using_real_sheets = True
            else:
                sheets_hint = "Planilhas reais indisponiveis: " + "; ".join(missing_files)

        calendar_gateway = NoopCalendarGateway()
        calendar_mode = "NOOP"
        calendar_hint = ""
        google_client_id = (os.getenv("GOOGLE_CLIENT_ID") or "").strip()
        google_client_secret = (os.getenv("GOOGLE_CLIENT_SECRET") or "").strip()
        google_refresh_token = (os.getenv("GOOGLE_REFRESH_TOKEN") or "").strip()
        google_calendar_id = (os.getenv("GOOGLE_CALENDAR_ID") or "primary").strip()
        if google_client_id and google_client_secret and google_refresh_token:
            calendar_gateway = GoogleCalendarGateway(
                client_id=google_client_id,
                client_secret=google_client_secret,
                refresh_token=google_refresh_token,
                calendar_id=google_calendar_id,
                timeout_seconds=_env_int("GOOGLE_CALENDAR_TIMEOUT_SECONDS", default=20),
            )
            calendar_mode = "GOOGLE_API"
        else:
            calendar_hint = (
                "Defina GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET/GOOGLE_REFRESH_TOKEN para leitura real da agenda."
            )

        gmail_gateway = NoopGmailGateway()
        gmail_mode = "NOOP"
        gmail_hint = ""
        gmail_user = (os.getenv("GMAIL_IMAP_USER") or "").strip()
        gmail_password = (os.getenv("GMAIL_IMAP_PASSWORD") or "").strip()
        gmail_host = (os.getenv("GMAIL_IMAP_HOST") or "imap.gmail.com").strip()
        if gmail_user and gmail_password:
            gmail_gateway = GmailImapGateway(
                username=gmail_user,
                password=gmail_password,
                host=gmail_host,
                mailbox=(os.getenv("GMAIL_IMAP_MAILBOX") or "INBOX").strip(),
                max_messages=_env_int("GMAIL_IMAP_MAX_MESSAGES", default=60),
            )
            gmail_mode = "GMAIL_IMAP"
        else:
            gmail_hint = "Defina GMAIL_IMAP_USER/GMAIL_IMAP_PASSWORD para leitura real de e-mails."

        todo_gateway = NoopTodoGateway()
        todo_mode = "NOOP"
        todo_hint = ""
        todo_settings = settings.microsoft_todo
        has_todo_login = bool(todo_settings and todo_settings.username and todo_settings.password)
        can_use_graph = bool(
            todo_settings
            and todo_settings.client_id
            and (todo_settings.refresh_token or (todo_settings.username and todo_settings.password))
        )
        can_use_web_fallback = bool(has_todo_login and todo_web_automation_available())
        if can_use_graph and todo_settings is not None:
            todo_gateway = MicrosoftTodoGraphGateway(todo_settings)
            todo_mode = "GRAPH"
        elif can_use_web_fallback and todo_settings is not None:
            todo_gateway = MicrosoftTodoWebGateway(
                todo_settings,
                headless=todo_settings.web_headless,
            )
            todo_mode = "WEB_AUTOMATION"
        elif todo_settings is not None:
            if has_todo_login and not todo_settings.client_id:
                if todo_web_automation_available():
                    todo_hint = (
                        "Graph indisponivel sem MICROSOFT_TODO_CLIENT_ID; web automation usada como fallback."
                    )
                else:
                    todo_hint = (
                        "Defina MICROSOFT_TODO_CLIENT_ID para ativar Graph "
                        "ou instale playwright no Windows para fallback sem Client ID."
                    )
            elif todo_settings.client_id and not (
                todo_settings.refresh_token or (todo_settings.username and todo_settings.password)
            ):
                todo_hint = "Defina MICROSOFT_TODO_REFRESH_TOKEN (ou usuario/senha) para ativar Graph."

        segfy_gateway = SegfyGateway(
            username=(os.getenv("SEGFY_USER") or "").strip(),
            password=(os.getenv("SEGFY_PASSWORD") or "").strip(),
            api_base_url=(os.getenv("SEGFY_API_BASE_URL") or "").strip() or None,
            api_token=(os.getenv("SEGFY_API_TOKEN") or "").strip() or None,
            api_login_path=(os.getenv("SEGFY_API_LOGIN_PATH") or "/auth/login").strip(),
            api_policies_path=(os.getenv("SEGFY_API_POLICIES_PATH") or "/policies").strip(),
            api_register_payment_path=(os.getenv("SEGFY_API_REGISTER_PAYMENT_PATH") or "/payments/register").strip(),
            export_xlsx_path=(os.getenv("SEGFY_EXPORT_XLSX") or "").strip() or None,
            timeout_seconds=_env_int("SEGFY_API_TIMEOUT_SECONDS", default=20),
        )
        segfy_mode = "QUEUE_ONLY"
        segfy_hint = (
            "Defina SEGFY_API_BASE_URL + credenciais/token para integracao API "
            "ou informe SEGFY_EXPORT_XLSX para leitura por export."
        )
        if (os.getenv("SEGFY_API_BASE_URL") or "").strip():
            segfy_mode = "API_OR_QUEUE"
            segfy_hint = ""
        elif (os.getenv("SEGFY_EXPORT_XLSX") or "").strip():
            segfy_mode = "EXPORT_XLSX_OR_QUEUE"
            segfy_hint = ""

        whatsapp_gateway = FileOutboxWhatsAppGateway()
        whatsapp_mode = "OUTBOX_FILE"
        whatsapp_hint = ""
        whatsapp_url = (os.getenv("WHATSAPP_PROVIDER_URL") or "").strip()
        whatsapp_token = (os.getenv("WHATSAPP_PROVIDER_TOKEN") or "").strip()
        if whatsapp_url and whatsapp_token:
            whatsapp_gateway = WhatsAppHttpGateway(
                api_url=whatsapp_url,
                token=whatsapp_token,
                timeout_seconds=_env_int("WHATSAPP_TIMEOUT_SECONDS", default=20),
                auth_header=(os.getenv("WHATSAPP_AUTH_HEADER") or "Authorization").strip(),
                auth_scheme=(os.getenv("WHATSAPP_AUTH_SCHEME") or "Bearer").strip(),
            )
            whatsapp_mode = "HTTP_API"
        else:
            whatsapp_hint = "Defina WHATSAPP_PROVIDER_URL + WHATSAPP_PROVIDER_TOKEN para envio real via API."

        email_mode = "OUTBOX_FILE"
        email_hint = ""
        smtp_host = (os.getenv("SMTP_HOST") or "").strip()
        smtp_port = _env_int("SMTP_PORT", default=0)
        if smtp_host and smtp_port > 0:
            email_sender_gateway = SmtpEmailSenderGateway(
                host=smtp_host,
                port=smtp_port,
                username=(os.getenv("SMTP_USER") or "").strip() or None,
                password=(os.getenv("SMTP_PASSWORD") or "").strip() or None,
                from_email=(os.getenv("SMTP_FROM_EMAIL") or "").strip() or None,
                use_tls=_env_flag("SMTP_USE_TLS", default=True),
                timeout_seconds=_env_int("SMTP_TIMEOUT_SECONDS", default=20),
            )
            email_mode = "SMTP"
        else:
            email_hint = "Defina SMTP_HOST e SMTP_PORT para envio real de notificacoes por e-mail."

        report_email_to = (os.getenv("EXECUTION_REPORT_EMAIL_TO") or "").strip()

        portal_gateway = StubInsurerPortalGateway()
        portal_mode = "STUB"
        portal_hint = ""

        yelum_user, yelum_password = _resolve_portal_credentials(
            env_user_key="YELUM_PORTAL_USER",
            env_password_key="YELUM_PORTAL_PASSWORD",
            service_tokens=("YELUM",),
            credentials_from_pdf=credentials_from_pdf,
        )
        porto_user, porto_password = _resolve_portal_credentials(
            env_user_key="PORTO_PORTAL_USER",
            env_password_key="PORTO_PORTAL_PASSWORD",
            service_tokens=("PORTO",),
            credentials_from_pdf=credentials_from_pdf,
        )
        mapfre_user, mapfre_password = _resolve_portal_credentials(
            env_user_key="MAPFRE_PORTAL_USER",
            env_password_key="MAPFRE_PORTAL_PASSWORD",
            service_tokens=("MAPFRE",),
            credentials_from_pdf=credentials_from_pdf,
        )
        bradesco_user, bradesco_password = _resolve_portal_credentials(
            env_user_key="BRADESCO_PORTAL_USER",
            env_password_key="BRADESCO_PORTAL_PASSWORD",
            service_tokens=("BRADESCO",),
            credentials_from_pdf=credentials_from_pdf,
        )
        allianz_user, allianz_password = _resolve_portal_credentials(
            env_user_key="ALLIANZ_PORTAL_USER",
            env_password_key="ALLIANZ_PORTAL_PASSWORD",
            service_tokens=("ALLIANZ",),
            credentials_from_pdf=credentials_from_pdf,
        )
        suhai_user, suhai_password = _resolve_portal_credentials(
            env_user_key="SUHAI_PORTAL_USER",
            env_password_key="SUHAI_PORTAL_PASSWORD",
            service_tokens=("SUHAI VENDAS", "SUHAI"),
            credentials_from_pdf=credentials_from_pdf,
        )
        tokio_user, tokio_password = _resolve_portal_credentials(
            env_user_key="TOKIO_PORTAL_USER",
            env_password_key="TOKIO_PORTAL_PASSWORD",
            service_tokens=("TOKIO MARINE", "TOKIO"),
            credentials_from_pdf=credentials_from_pdf,
        )
        hdi_user, hdi_password = _resolve_portal_credentials(
            env_user_key="HDI_PORTAL_USER",
            env_password_key="HDI_PORTAL_PASSWORD",
            service_tokens=("HDI",),
            credentials_from_pdf=credentials_from_pdf,
        )
        azul_user, azul_password = _resolve_portal_credentials(
            env_user_key="AZUL_PORTAL_USER",
            env_password_key="AZUL_PORTAL_PASSWORD",
            service_tokens=("AZUL", "AZUL SEGUROS"),
            credentials_from_pdf=credentials_from_pdf,
        )

        any_portal_creds = any(
            [
                bool(yelum_user and yelum_password),
                bool(porto_user and porto_password),
                bool(mapfre_user and mapfre_password),
                bool(bradesco_user and bradesco_password),
                bool(allianz_user and allianz_password),
                bool(suhai_user and suhai_password),
                bool(tokio_user and tokio_password),
                bool(hdi_user and hdi_password),
                bool(azul_user and azul_password),
            ]
        )

        web_available = web_portal_automation_available()
        web_gateways = []
        enabled_labels: list[str] = []
        missing_labels: list[str] = []

        if yelum_user and yelum_password:
            web_gateways.append(
                YelumPortalGateway(
                    credentials=YelumPortalCredentials(username=yelum_user, password=yelum_password),
                    headless=_env_flag("YELUM_PORTAL_WEB_HEADLESS", default=True),
                )
            )
            enabled_labels.append("YELUM")
        else:
            missing_labels.append("YELUM")

        if porto_user and porto_password:
            web_gateways.append(
                PortoSeguroPortalGateway(
                    credentials=PortoPortalCredentials(username=porto_user, password=porto_password),
                    headless=_env_flag("PORTO_PORTAL_WEB_HEADLESS", default=True),
                )
            )
            enabled_labels.append("PORTO")
        else:
            missing_labels.append("PORTO")

        if mapfre_user and mapfre_password:
            web_gateways.append(
                MapfrePortalGateway(
                    credentials=MapfrePortalCredentials(username=mapfre_user, password=mapfre_password),
                    headless=_env_flag("MAPFRE_PORTAL_WEB_HEADLESS", default=True),
                )
            )
            enabled_labels.append("MAPFRE")
        else:
            missing_labels.append("MAPFRE")

        if bradesco_user and bradesco_password:
            web_gateways.append(
                BradescoPortalGateway(
                    credentials=BradescoPortalCredentials(username=bradesco_user, password=bradesco_password),
                    headless=_env_flag("BRADESCO_PORTAL_WEB_HEADLESS", default=True),
                )
            )
            enabled_labels.append("BRADESCO")
        else:
            missing_labels.append("BRADESCO")

        if allianz_user and allianz_password:
            web_gateways.append(
                AllianzPortalGateway(
                    credentials=AllianzPortalCredentials(username=allianz_user, password=allianz_password),
                    headless=_env_flag("ALLIANZ_PORTAL_WEB_HEADLESS", default=True),
                )
            )
            enabled_labels.append("ALLIANZ")
        else:
            missing_labels.append("ALLIANZ")

        if suhai_user and suhai_password:
            web_gateways.append(
                SuhaiPortalGateway(
                    credentials=SuhaiPortalCredentials(username=suhai_user, password=suhai_password),
                    headless=_env_flag("SUHAI_PORTAL_WEB_HEADLESS", default=True),
                )
            )
            enabled_labels.append("SUHAI")
        else:
            missing_labels.append("SUHAI")

        if tokio_user and tokio_password:
            web_gateways.append(
                TokioMarinePortalGateway(
                    credentials=TokioPortalCredentials(username=tokio_user, password=tokio_password),
                    headless=_env_flag("TOKIO_PORTAL_WEB_HEADLESS", default=True),
                )
            )
            enabled_labels.append("TOKIO")
        else:
            missing_labels.append("TOKIO")

        if hdi_user and hdi_password:
            web_gateways.append(
                HDIPortalGateway(
                    credentials=HDIPortalCredentials(username=hdi_user, password=hdi_password),
                    headless=_env_flag("HDI_PORTAL_WEB_HEADLESS", default=True),
                )
            )
            enabled_labels.append("HDI")
        else:
            missing_labels.append("HDI")

        if azul_user and azul_password:
            web_gateways.append(
                AzulPortalGateway(
                    credentials=AzulPortalCredentials(username=azul_user, password=azul_password),
                    headless=_env_flag("AZUL_PORTAL_WEB_HEADLESS", default=True),
                )
            )
            enabled_labels.append("AZUL")
        else:
            missing_labels.append("AZUL")

        if web_available and web_gateways:
            portal_gateway = CascadingInsurerPortalGateway(
                gateways=web_gateways,
                fallback=StubInsurerPortalGateway(),
            )
            portal_mode = "WEB_MULTI+STUB"
            portal_hint = f"Gateways ativos: {', '.join(enabled_labels)}."
            if missing_labels:
                portal_hint += f" Sem credenciais: {', '.join(missing_labels)}."
        elif any_portal_creds and not web_available:
            portal_hint = "Credenciais de portais detectadas, mas Playwright para Windows nao esta disponivel."
        else:
            portal_hint = (
                "Defina credenciais de YELUM/PORTO/MAPFRE/BRADESCO/ALLIANZ/SUHAI/TOKIO/HDI/AZUL "
                "ou habilite PORTAL_USE_PDF_CREDENTIALS=1 para mapeamento automatico."
            )

        files_to_check: list[Path] = []
        if settings.files is not None:
            files_to_check = [
                settings.files.seguros_pbseg_xlsx,
                settings.files.acompanhamento_2026_xlsx,
                settings.files.fluxo_caixa_xlsx,
            ]

        windows_report = build_windows_runtime_report(
            calendar_mode=calendar_mode,
            gmail_mode=gmail_mode,
            todo_mode=todo_mode,
            segfy_mode=segfy_mode,
            portal_mode=portal_mode,
            whatsapp_mode=whatsapp_mode,
            email_mode=email_mode,
            files_to_check=files_to_check,
        )
        for line in render_windows_runtime_report(windows_report):
            print(line)
        windows_report_path = write_windows_runtime_report(windows_report, args.windows_audit_output)
        print(f"Windows audit JSON: {windows_report_path.resolve()}")
        if args.windows_audit_only:
            return

        if args.scan_credentials and not args.dry_run:
            print("Scan de credenciais ativa dry-run automaticamente para evitar envios externos.")

        processor = DailyProcessor(
            settings=settings,
            calendar=calendar_gateway,
            todo=todo_gateway,
            gmail=gmail_gateway,
            sheets=sheets_gateway,
            segfy=segfy_gateway,
            portals=portal_gateway,
            whatsapp=whatsapp_gateway,
            email_sender=email_sender_gateway,
            dashboard_builder=DashboardBuilder(),
        )

        result = processor.run(today=run_date, dry_run=effective_dry_run, trace=trace)

        print(f"Data de execucao: {result.run_date}")
        print(f"Alertas gerados: {len(result.alerts)}")
        print(f"Emails de seguradoras: {len(result.insurer_emails)}")
        print(f"Lancamentos de caixa: {len(result.cashflow_entries)}")
        print(f"Alertas criticos: {result.dashboard.critical_alerts}")
        print(f"Planilhas reais: {'SIM' if using_real_sheets else 'NAO'}")
        if sheets_hint:
            print(f"Planilhas observacao: {sheets_hint}")
        print(f"Agenda modo: {calendar_mode}")
        if calendar_hint:
            print(f"Agenda observacao: {calendar_hint}")
        print(f"Gmail modo: {gmail_mode}")
        if gmail_hint:
            print(f"Gmail observacao: {gmail_hint}")
        print(f"Segfy modo: {segfy_mode}")
        if segfy_hint:
            print(f"Segfy observacao: {segfy_hint}")
        print(f"WhatsApp modo: {whatsapp_mode}")
        if whatsapp_hint:
            print(f"WhatsApp observacao: {whatsapp_hint}")
        print(f"E-mail modo: {email_mode}")
        if email_hint:
            print(f"E-mail observacao: {email_hint}")
        has_todo_creds = bool(settings.microsoft_todo and settings.microsoft_todo.username and settings.microsoft_todo.password)
        print(f"Microsoft To Do credenciais: {'SIM' if has_todo_creds else 'NAO'}")
        print(f"Microsoft To Do modo: {todo_mode}")
        if todo_hint:
            print(f"Microsoft To Do observacao: {todo_hint}")
        print(f"Portais modo: {portal_mode}")
        if portal_hint:
            print(f"Portais observacao: {portal_hint}")
        print("Dashboard:")
        print(result.dashboard)

        if not args.no_dashboard_html:
            if trace is not None:
                trace.start_stage("dashboard")
            try:
                dashboard_meta = DashboardMeta(
                    run_date=result.run_date,
                    generated_at=datetime.now(),
                    alerts_total=len(result.alerts),
                    critical_alerts=result.dashboard.critical_alerts,
                    insurer_emails=len(result.insurer_emails),
                    cashflow_entries=len(result.cashflow_entries),
                    using_real_sheets=using_real_sheets,
                    todo_mode=todo_mode,
                )
                dashboard_path = write_dashboard_html(
                    snapshot=result.dashboard,
                    meta=dashboard_meta,
                    output_path=args.dashboard_html_output,
                )
                print(f"Dashboard HTML: {dashboard_path.resolve()}")
                if trace is not None:
                    trace.complete_stage("dashboard", f"Dashboard publicado em {dashboard_path.resolve()}")
            except Exception as exc:
                if trace is not None:
                    trace.fail_stage(
                        "dashboard",
                        exc,
                        context={"output_path": str(args.dashboard_html_output)},
                    )
                raise
        else:
            if trace is not None:
                trace.ignore_stage(
                    "dashboard",
                    reason="Geracao de dashboard desativada por parametro de execucao.",
                    recommended_action="Executar sem --no-dashboard-html para publicar o painel.",
                    result="Publicacao de dashboard desativada neste ciclo.",
                )

        if args.scan_credentials:
            if settings.files is None or settings.files.senhas_pdf is None:
                print("Credenciais: caminho do SENHAS.pdf nao configurado")
                return
            if not settings.files.senhas_pdf.exists():
                print(f"Credenciais: arquivo nao encontrado em {settings.files.senhas_pdf}")
                return

            credentials = load_credentials_from_pdf(settings.files.senhas_pdf)
            print(f"Credenciais detectadas via OCR: {len(credentials)} servicos")
            print("Servicos identificados:")
            for service_name in sorted(credentials.keys()):
                print(f"- {service_name}")
    except Exception as exc:
        fatal_error = exc
        if trace is None:
            report_dir = Path(args.execution_report_dir or "outputs")
            run_id = next_run_identifier(report_dir, cycle_started_at)
            report_json_path, report_pdf_path = execution_report_paths(report_dir, cycle_started_at)
            trace = ExecutionTraceCollector(
                run_id=run_id,
                bot_version=__version__,
                cycle_started_at=cycle_started_at,
            )
        trace.mark_critical_failure(
            stage_name="Main",
            error=exc,
            context={"fase": "top_level"},
        )
    finally:
        if trace is None:
            report_dir = Path(args.execution_report_dir or "outputs")
            run_id = next_run_identifier(report_dir, cycle_started_at)
            report_json_path, report_pdf_path = execution_report_paths(report_dir, cycle_started_at)
            trace = ExecutionTraceCollector(
                run_id=run_id,
                bot_version=__version__,
                cycle_started_at=cycle_started_at,
            )
            trace.add_non_executed_item(
                item_id="Ciclo principal",
                reason="Fluxo nao inicializado corretamente.",
                recommended_action="Executar novamente e revisar parametros obrigatorios.",
            )

        if not report_email_to:
            trace.add_non_executed_item(
                item_id="Envio de relatorio por e-mail",
                reason="EXECUTION_REPORT_EMAIL_TO nao configurado.",
                recommended_action="Definir EXECUTION_REPORT_EMAIL_TO para envio automatico ao corretor.",
            )
        elif effective_dry_run:
            trace.add_non_executed_item(
                item_id="Envio de relatorio por e-mail",
                reason="Dry-run ativo, envio externo de e-mail bloqueado.",
                recommended_action="Executar sem --dry-run para disparar envio automatico do relatorio.",
            )

        report = trace.finalize(cycle_ended_at=datetime.now())
        report_json_written = write_execution_report_json(report, report_json_path)
        report_pdf_written = write_execution_report_pdf(report, report_pdf_path)
        print(f"Relatorio JSON: {report_json_written.resolve()}")
        print(f"Relatorio PDF: {report_pdf_written.resolve()}")

        if report_email_to and not effective_dry_run:
            try:
                email_sender_gateway.send_email(
                    recipient=report_email_to,
                    subject=f"Relatorio de execucao do RPA - {report.run_id}",
                    content=(
                        "Relatorio da execucao finalizado.\n"
                        f"Run ID: {report.run_id}\n"
                        f"Status geral: {report.overall_status}\n"
                        f"JSON: {report_json_written.resolve()}\n"
                        f"PDF: {report_pdf_written.resolve()}\n"
                    ),
                    attachments=[report_json_written, report_pdf_written],
                )
            except Exception as exc:
                trace.add_non_executed_item(
                    item_id="Envio de relatorio por e-mail",
                    reason=f"Falha ao enviar por e-mail: {exc}",
                    recommended_action="Validar SMTP e reenviar manualmente os arquivos de relatorio.",
                )
                trace.log_error(
                    stage_name="Entrega de relatorio",
                    error=exc,
                    context={"recipient": report_email_to},
                )
                report = trace.finalize(cycle_ended_at=datetime.now())
                report_json_written = write_execution_report_json(report, report_json_path)
                report_pdf_written = write_execution_report_pdf(report, report_pdf_path)
                print("Relatorio atualizado apos falha no envio por e-mail.")
                print(f"Relatorio JSON: {report_json_written.resolve()}")
                print(f"Relatorio PDF: {report_pdf_written.resolve()}")

    if fatal_error is not None:
        raise fatal_error


if __name__ == "__main__":
    main()
