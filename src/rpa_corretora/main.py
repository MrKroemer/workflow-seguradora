from __future__ import annotations

import argparse
from datetime import date, datetime
import os
from pathlib import Path

from rpa_corretora.config import load_settings
from rpa_corretora.env_loader import load_env_file
from rpa_corretora.integrations.credentials_pdf import load_credentials_from_pdf
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
from rpa_corretora.integrations.microsoft_todo_graph import MicrosoftTodoGraphGateway
from rpa_corretora.integrations.microsoft_todo_web import (
    MicrosoftTodoWebGateway,
    todo_web_automation_available,
)
from rpa_corretora.integrations.stub_adapters import (
    ConsoleEmailSenderGateway,
    ConsoleWhatsAppGateway,
    StubCalendarGateway,
    StubGmailGateway,
    StubInsurerPortalGateway,
    StubSegfyGateway,
    StubSpreadsheetGateway,
    StubTodoGateway,
)
from rpa_corretora.integrations.workbook_gateway import WorkbookSpreadsheetGateway
from rpa_corretora.processing.dashboard import DashboardBuilder
from rpa_corretora.processing.dashboard_web import DashboardMeta, write_dashboard_html
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
        "--files-dir",
        type=str,
        default=None,
        help=(
            "Diretorio base com os arquivos operacionais. "
            "Quando informado, define automaticamente os caminhos "
            "de SEGUROS PBSEG.xlsx, ACOMPANHAMENTO 2026.xlsx, FLUXO DE CAIXA.xlsx e SENHAS.pdf."
        ),
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

    load_env_file(args.env_file)

    if args.files_dir:
        base_dir = Path(args.files_dir)
        os.environ["SEGUROS_PBSEG_XLSX"] = str(base_dir / "SEGUROS PBSEG.xlsx")
        os.environ["ACOMPANHAMENTO_2026_XLSX"] = str(base_dir / "ACOMPANHAMENTO 2026.xlsx")
        os.environ["FLUXO_CAIXA_XLSX"] = str(base_dir / "FLUXO DE CAIXA.xlsx")
        os.environ["SENHAS_PDF"] = str(base_dir / "SENHAS.pdf")

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

    todo_gateway = StubTodoGateway()
    todo_mode = "STUB"
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
                todo_hint = "Graph indisponivel sem MICROSOFT_TODO_CLIENT_ID; web automation usada como fallback."
            else:
                todo_hint = (
                    "Defina MICROSOFT_TODO_CLIENT_ID para ativar Graph "
                    "ou instale playwright no Windows para fallback sem Client ID."
                )
        elif todo_settings.client_id and not (todo_settings.refresh_token or (todo_settings.username and todo_settings.password)):
            todo_hint = "Defina MICROSOFT_TODO_REFRESH_TOKEN (ou usuario/senha) para ativar Graph."

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

    any_wave1_creds = any(
        [
            bool(yelum_user and yelum_password),
            bool(porto_user and porto_password),
            bool(mapfre_user and mapfre_password),
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

    if web_available and web_gateways:
        portal_gateway = CascadingInsurerPortalGateway(
            gateways=web_gateways,
            fallback=StubInsurerPortalGateway(),
        )
        portal_mode = "WEB_WAVE1+STUB"
        portal_hint = f"Gateways ativos: {', '.join(enabled_labels)}."
        if missing_labels:
            portal_hint += f" Sem credenciais: {', '.join(missing_labels)}."
    elif any_wave1_creds and not web_available:
        portal_hint = "Credenciais Wave1 detectadas, mas Playwright para Windows nao esta disponivel."
    else:
        portal_hint = (
            "Defina credenciais de YELUM/PORTO/MAPFRE "
            "ou habilite PORTAL_USE_PDF_CREDENTIALS=1 para mapeamento automatico."
        )

    effective_dry_run = args.dry_run or args.scan_credentials
    if args.scan_credentials and not args.dry_run:
        print("Scan de credenciais ativa dry-run automaticamente para evitar envios externos.")

    processor = DailyProcessor(
        settings=settings,
        calendar=StubCalendarGateway(),
        todo=todo_gateway,
        gmail=StubGmailGateway(),
        sheets=sheets_gateway,
        segfy=StubSegfyGateway(),
        portals=portal_gateway,
        whatsapp=ConsoleWhatsAppGateway(),
        email_sender=ConsoleEmailSenderGateway(),
        dashboard_builder=DashboardBuilder(),
    )

    result = processor.run(today=run_date, dry_run=effective_dry_run)

    print(f"Data de execucao: {result.run_date}")
    print(f"Alertas gerados: {len(result.alerts)}")
    print(f"Emails de seguradoras: {len(result.insurer_emails)}")
    print(f"Lancamentos de caixa: {len(result.cashflow_entries)}")
    print(f"Alertas criticos: {result.dashboard.critical_alerts}")
    print(f"Planilhas reais: {'SIM' if using_real_sheets else 'NAO'}")
    if sheets_hint:
        print(f"Planilhas observacao: {sheets_hint}")
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


if __name__ == "__main__":
    main()
