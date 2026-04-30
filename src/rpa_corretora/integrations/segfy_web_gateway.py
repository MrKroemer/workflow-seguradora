from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import re
import sys
from typing import TYPE_CHECKING, Any, Protocol

from rpa_corretora.domain.models import CashflowEntry, FollowupRecord, PolicyRecord, SegfyPolicyData
from rpa_corretora.integrations.segfy_gateway import SegfyGateway

if TYPE_CHECKING:
    from playwright.sync_api import Page, Playwright


def segfy_web_automation_available() -> bool:
    if not sys.platform.startswith("win"):
        return False
    return importlib.util.find_spec("playwright.sync_api") is not None


class _SegfyGatewayLike(Protocol):
    def import_documents(self) -> int:
        ...

    def fetch_policy_data(self) -> list[SegfyPolicyData]:
        ...

    def register_payment(self, *, commitment_id: str, description: str) -> bool:
        ...

    def sync_policies(self, policies: list[PolicyRecord]) -> int:
        ...

    def sync_followups(self, followups: list[FollowupRecord]) -> int:
        ...

    def sync_cashflow(self, entries: list[CashflowEntry]) -> int:
        ...

    def register_incident(self, *, policy_id: str, incident_type: str, description: str) -> bool:
        ...

    def update_commission_status(self, *, policy_id: str, status: str) -> bool:
        ...

    def register_renewal(self, *, policy_id: str, phase: str, status: str) -> bool:
        ...


class CascadingSegfyGateway:
    def __init__(self, *, primary: _SegfyGatewayLike, fallback: _SegfyGatewayLike) -> None:
        self.primary = primary
        self.fallback = fallback

    def fetch_policy_data(self) -> list[SegfyPolicyData]:
        data = self.primary.fetch_policy_data()
        if data:
            return data
        return self.fallback.fetch_policy_data()

    def import_documents(self) -> int:
        imported = self.primary.import_documents()
        if imported > 0:
            return imported
        return self.fallback.import_documents()

    def register_payment(self, *, commitment_id: str, description: str) -> bool:
        if self.primary.register_payment(commitment_id=commitment_id, description=description):
            return True
        return self.fallback.register_payment(commitment_id=commitment_id, description=description)

    def sync_policies(self, policies: list[PolicyRecord]) -> int:
        count = self.primary.sync_policies(policies)
        if count > 0:
            return count
        return self.fallback.sync_policies(policies)

    def sync_followups(self, followups: list[FollowupRecord]) -> int:
        count = self.primary.sync_followups(followups)
        if count > 0:
            return count
        return self.fallback.sync_followups(followups)

    def sync_cashflow(self, entries: list[CashflowEntry]) -> int:
        count = self.primary.sync_cashflow(entries)
        if count > 0:
            return count
        return self.fallback.sync_cashflow(entries)

    def register_incident(self, *, policy_id: str, incident_type: str, description: str) -> bool:
        if self.primary.register_incident(policy_id=policy_id, incident_type=incident_type, description=description):
            return True
        return self.fallback.register_incident(policy_id=policy_id, incident_type=incident_type, description=description)

    def update_commission_status(self, *, policy_id: str, status: str) -> bool:
        if self.primary.update_commission_status(policy_id=policy_id, status=status):
            return True
        return self.fallback.update_commission_status(policy_id=policy_id, status=status)

    def register_renewal(self, *, policy_id: str, phase: str, status: str) -> bool:
        if self.primary.register_renewal(policy_id=policy_id, phase=phase, status=status):
            return True
        return self.fallback.register_renewal(policy_id=policy_id, phase=phase, status=status)


class SegfyWebGateway:
    def __init__(
        self,
        *,
        username: str,
        password: str,
        base_url: str,
        headless: bool = True,
        browser_channel: str = "chrome",
        timeout_seconds: int = 35,
        export_output_path: str | Path = "outputs/segfy_export_web_latest.xlsx",
        import_enabled: bool = True,
        import_page_url: str | None = None,
        import_source_dir: str | Path | None = None,
        import_max_files: int = 100,
        import_state_path: str | Path = "outputs/segfy_import_state.json",
        payment_enabled: bool = True,
        payment_page_url: str | None = None,
        allow_channel_fallback: bool = True,
    ) -> None:
        self.username = username.strip()
        self.password = password.strip()
        self.base_url = base_url.strip().rstrip("/")
        self.headless = headless
        self.browser_channel = browser_channel.strip().lower()
        self.timeout_seconds = timeout_seconds
        self.export_output_path = Path(export_output_path)
        self.import_enabled = import_enabled
        self.import_page_url = (import_page_url or "").strip()
        self.import_source_dir = Path(import_source_dir) if import_source_dir else None
        self.import_max_files = max(1, import_max_files)
        self.import_state_path = Path(import_state_path)
        self.payment_enabled = payment_enabled
        self.payment_page_url = (payment_page_url or "").strip()
        self.allow_channel_fallback = allow_channel_fallback
        self.debug_output_dir = Path("outputs/segfy_debug")

    def import_documents(self) -> int:
        if not self.import_enabled:
            return 0
        if not self.username or not self.password or not self.base_url:
            return 0
        if not segfy_web_automation_available():
            return 0
        print(f"[Segfy] Importacao web iniciada (headless={'ON' if self.headless else 'OFF'}).")
        scan_started_at = datetime.now(timezone.utc)
        last_execution = self._load_last_execution_utc()
        files = self._collect_import_files(modified_after=last_execution)
        if not files:
            self._save_last_execution_utc(scan_started_at)
            source_label = str(self.import_source_dir) if self.import_source_dir else "(nao configurado)"
            print(
                "[Segfy] Nenhum arquivo novo para importacao. "
                f"Pasta monitorada: {source_label}."
            )
            return 0

        imported = 0
        page: Page | None = None
        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright

            with sync_playwright() as playwright:
                browser = self._launch_browser(playwright)
                try:
                    context = browser.new_context(locale="pt-BR", accept_downloads=True)
                    try:
                        page = context.new_page()
                        page.set_default_timeout(self.timeout_seconds * 1000)
                        self._login(page)
                        imported = self._upload_documents(page, files)
                    finally:
                        context.close()
                finally:
                    browser.close()
        except PlaywrightTimeoutError:
            self._capture_debug_snapshot(page=page, label="import_timeout")
            print("[Segfy] Timeout durante importacao web de documentos.")
        except Exception as exc:
            self._capture_debug_snapshot(page=page, label="import_exception")
            print(f"[Segfy] Falha ao importar documentos via web: {exc}")
        finally:
            self._save_last_execution_utc(scan_started_at)
        return imported

    def fetch_policy_data(self) -> list[SegfyPolicyData]:
        if not self.username or not self.password or not self.base_url:
            return []
        if not segfy_web_automation_available():
            return []
        print(f"[Segfy] Leitura web iniciada (headless={'ON' if self.headless else 'OFF'}).")

        page: Page | None = None
        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright

            with sync_playwright() as playwright:
                browser = self._launch_browser(playwright)
                try:
                    context = browser.new_context(locale="pt-BR", accept_downloads=True)
                    try:
                        page = context.new_page()
                        page.set_default_timeout(self.timeout_seconds * 1000)
                        self._login(page)
                        exported = self._try_export_policies(page)
                        if exported is None:
                            print(
                                "[Segfy] Exportacao web nao encontrada/baixada nesta execucao. "
                                "Se houver fallback configurado, sera utilizado."
                            )
                            return []

                        parser = SegfyGateway(export_xlsx_path=exported)
                        return parser.fetch_policy_data()
                    finally:
                        context.close()
                finally:
                    browser.close()
        except PlaywrightTimeoutError:
            self._capture_debug_snapshot(page=page, label="fetch_timeout")
            print("[Segfy] Timeout durante automacao web.")
            return []
        except Exception as exc:
            self._capture_debug_snapshot(page=page, label="fetch_exception")
            print(f"[Segfy] Falha na automacao web: {exc}")
            return []

    def register_payment(self, *, commitment_id: str, description: str) -> bool:
        if not self.payment_enabled:
            return False
        if not self.username or not self.password or not self.base_url:
            return False
        if not segfy_web_automation_available():
            return False
        print(
            f"[Segfy] Baixa web iniciada ({commitment_id}) "
            f"(headless={'ON' if self.headless else 'OFF'})."
        )

        page: Page | None = None
        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright

            with sync_playwright() as playwright:
                browser = self._launch_browser(playwright)
                try:
                    context = browser.new_context(locale="pt-BR")
                    try:
                        page = context.new_page()
                        page.set_default_timeout(self.timeout_seconds * 1000)
                        self._login(page)
                        return self._register_payment_on_page(
                            page=page,
                            commitment_id=commitment_id,
                            description=description,
                        )
                    finally:
                        context.close()
                finally:
                    browser.close()
        except PlaywrightTimeoutError:
            self._capture_debug_snapshot(page=page, label=f"payment_timeout_{commitment_id}")
            print(f"[Segfy] Timeout ao registrar baixa web ({commitment_id}).")
            return False
        except Exception as exc:
            self._capture_debug_snapshot(page=page, label=f"payment_exception_{commitment_id}")
            print(f"[Segfy] Falha ao registrar baixa web ({commitment_id}): {exc}")
            return False

    def sync_policies(self, policies: list[PolicyRecord]) -> int:
        if not policies or not self._can_automate():
            return 0
        print(f"[Segfy] Sincronizacao web de {len(policies)} apolices iniciada.")
        return self._run_web_session(lambda page: self._sync_policies_on_page(page, policies))

    def sync_followups(self, followups: list[FollowupRecord]) -> int:
        if not followups or not self._can_automate():
            return 0
        print(f"[Segfy] Sincronizacao web de {len(followups)} acompanhamentos iniciada.")
        return self._run_web_session(lambda page: self._sync_followups_on_page(page, followups))

    def sync_cashflow(self, entries: list[CashflowEntry]) -> int:
        if not entries or not self._can_automate():
            return 0
        print(f"[Segfy] Sincronizacao web de {len(entries)} lancamentos financeiros iniciada.")
        return self._run_web_session(lambda page: self._sync_cashflow_on_page(page, entries))

    def register_incident(self, *, policy_id: str, incident_type: str, description: str) -> bool:
        if not self._can_automate():
            return False
        print(f"[Segfy] Registro web de {incident_type} para {policy_id}.")
        return self._run_web_session(
            lambda page: 1 if self._register_incident_on_page(page, policy_id, incident_type, description) else 0,
        ) > 0

    def update_commission_status(self, *, policy_id: str, status: str) -> bool:
        if not self._can_automate():
            return False
        print(f"[Segfy] Atualizacao web de comissao {policy_id} -> {status}.")
        return self._run_web_session(
            lambda page: 1 if self._update_commission_on_page(page, policy_id, status) else 0,
        ) > 0

    def register_renewal(self, *, policy_id: str, phase: str, status: str) -> bool:
        if not self._can_automate():
            return False
        print(f"[Segfy] Registro web de renovacao {policy_id} fase={phase} status={status}.")
        return self._run_web_session(
            lambda page: 1 if self._register_renewal_on_page(page, policy_id, phase, status) else 0,
        ) > 0

    def _can_automate(self) -> bool:
        return bool(self.username and self.password and self.base_url and segfy_web_automation_available())

    def _run_web_session(self, action) -> int:
        page: Page | None = None
        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright

            with sync_playwright() as playwright:
                browser = self._launch_browser(playwright)
                try:
                    context = browser.new_context(locale="pt-BR")
                    try:
                        page = context.new_page()
                        page.set_default_timeout(self.timeout_seconds * 1000)
                        self._login(page)
                        return action(page)
                    finally:
                        context.close()
                finally:
                    browser.close()
        except Exception as exc:
            self._capture_debug_snapshot(page=page, label="web_session_error")
            print(f"[Segfy] Falha na sessao web: {exc}")
            return 0

    def _navigate_to_section(self, page: Page, section_labels: list[str]) -> bool:
        for label in section_labels:
            clicked = self._click_first(
                page,
                selectors=[
                    f"a:has-text('{label}')",
                    f"button:has-text('{label}')",
                    f"text={label}",
                    f"nav a:has-text('{label}')",
                    f"li a:has-text('{label}')",
                ],
                timeout_ms=2500,
            )
            if clicked:
                page.wait_for_timeout(1200)
                return True
        return False

    def _search_and_open_record(self, page: Page, query: str) -> bool:
        search_selectors = [
            "input[type='search']",
            "input[placeholder*='Buscar' i]",
            "input[placeholder*='Pesquisar' i]",
            "input[placeholder*='Segurado' i]",
            "input[placeholder*='Apolice' i]",
            "input[placeholder*='Apólice' i]",
            "input[name*='search' i]",
            "input[name*='busca' i]",
        ]
        filled = self._fill_first(page, selectors=search_selectors, value=query)
        if not filled:
            return False
        try:
            page.keyboard.press("Enter")
        except Exception:
            pass
        page.wait_for_timeout(1500)

        query_escaped = query.replace("\\", "\\\\").replace('"', '\\"')
        for row_sel in [f'tr:has-text("{query_escaped}")', f'div[role="row"]:has-text("{query_escaped}")', f'li:has-text("{query_escaped}")', f'div:has-text("{query_escaped}")', f'a:has-text("{query_escaped}")']:
            locator = page.locator(row_sel)
            if self._locator_count(locator) > 0:
                try:
                    locator.first.click(timeout=2500)
                    page.wait_for_timeout(800)
                    return True
                except Exception:
                    continue
        return False

    def _fill_form_field(self, page: Page, *, field_labels: list[str], value: str) -> bool:
        for label in field_labels:
            selectors = [
                f"input[placeholder*='{label}' i]",
                f"input[name*='{label}' i]",
                f"input[id*='{label}' i]",
                f"input[aria-label*='{label}' i]",
                f"textarea[placeholder*='{label}' i]",
                f"textarea[name*='{label}' i]",
            ]
            if self._fill_first(page, selectors=selectors, value=value):
                return True
        return False

    def _submit_form(self, page: Page) -> bool:
        return self._click_first(
            page,
            selectors=[
                "button:has-text('Salvar')",
                "button:has-text('Gravar')",
                "button:has-text('Confirmar')",
                "button:has-text('Cadastrar')",
                "button:has-text('Registrar')",
                "button:has-text('Concluir')",
                "button[type='submit']",
                "input[type='submit']",
            ],
            timeout_ms=3000,
        )

    def _sync_policies_on_page(self, page: Page, policies: list[PolicyRecord]) -> int:
        self._navigate_to_section(page, [
            "Segurados", "Clientes", "Propostas e Apólices",
            "Propostas e Apolices", "Apólices", "Apolices",
        ])
        synced = 0
        for policy in policies:
            try:
                self._click_first(page, selectors=[
                    "button:has-text('Novo')", "button:has-text('Adicionar')",
                    "button:has-text('Cadastrar')", "a:has-text('Novo')",
                    "a:has-text('Adicionar')", "text=Novo Segurado",
                ], timeout_ms=2000)
                page.wait_for_timeout(600)

                self._fill_form_field(page, field_labels=["segurado", "nome", "cliente"], value=policy.insured_name)
                self._fill_form_field(page, field_labels=["seguradora"], value=policy.insurer)
                self._fill_form_field(page, field_labels=["vigencia", "vigência", "vig"], value=policy.vig.strftime("%d/%m/%Y"))
                self._fill_form_field(page, field_labels=["premio", "prêmio", "valor"], value=str(policy.premio_total))
                self._fill_form_field(page, field_labels=["comissao", "comissão"], value=str(policy.comissao))
                if policy.vehicle_item:
                    self._fill_form_field(page, field_labels=["item", "veiculo", "veículo", "modelo"], value=policy.vehicle_item)
                if policy.status_pgto:
                    self._fill_form_field(page, field_labels=["status", "pagamento", "pgto"], value=policy.status_pgto)

                if self._submit_form(page):
                    page.wait_for_timeout(800)
                    synced += 1
                else:
                    self._capture_debug_snapshot(page=page, label=f"sync_policy_submit_{policy.policy_id}")
            except Exception as exc:
                self._capture_debug_snapshot(page=page, label=f"sync_policy_{policy.policy_id}")
                print(f"[Segfy] Falha ao sincronizar apolice {policy.policy_id}: {exc}")
        return synced

    def _sync_followups_on_page(self, page: Page, followups: list[FollowupRecord]) -> int:
        self._navigate_to_section(page, ["Tarefas", "Acompanhamento", "Atividades"])
        synced = 0
        for followup in followups:
            try:
                self._click_first(page, selectors=[
                    "button:has-text('Nova Tarefa')", "button:has-text('Novo')",
                    "button:has-text('Adicionar')", "a:has-text('Nova Tarefa')",
                ], timeout_ms=2000)
                page.wait_for_timeout(600)

                title = f"Acompanhamento {followup.renewal_kind} - {followup.insured_name} ({followup.month})"
                self._fill_form_field(page, field_labels=["titulo", "título", "assunto", "tarefa", "descricao", "descrição"], value=title)
                self._fill_form_field(page, field_labels=["segurado", "nome", "cliente"], value=followup.insured_name)
                if followup.fase:
                    self._fill_form_field(page, field_labels=["fase", "etapa"], value=followup.fase)
                if followup.status:
                    self._fill_form_field(page, field_labels=["status", "situacao", "situação"], value=followup.status)

                if self._submit_form(page):
                    page.wait_for_timeout(600)
                    synced += 1
                else:
                    self._capture_debug_snapshot(page=page, label=f"sync_followup_{followup.insured_name}")
            except Exception as exc:
                print(f"[Segfy] Falha ao sincronizar acompanhamento {followup.insured_name}: {exc}")
        return synced

    def _sync_cashflow_on_page(self, page: Page, entries: list[CashflowEntry]) -> int:
        self._navigate_to_section(page, [
            "Financeiro", "Recebimentos", "Fluxo de Caixa",
            "Extrato", "Extratos Bancários", "Extratos Bancarios",
        ])
        synced = 0
        for entry in entries:
            try:
                self._click_first(page, selectors=[
                    "button:has-text('Novo')", "button:has-text('Adicionar')",
                    "button:has-text('Lançar')", "button:has-text('Lancar')",
                    "a:has-text('Novo')", "a:has-text('Lançar')",
                ], timeout_ms=2000)
                page.wait_for_timeout(600)

                self._fill_form_field(page, field_labels=["data", "date"], value=entry.date.strftime("%d/%m/%Y"))
                self._fill_form_field(page, field_labels=["valor", "value"], value=f"{entry.value:.2f}".replace(".", ","))
                self._fill_form_field(page, field_labels=["seguradora", "origem", "fonte"], value=entry.insurer)
                self._fill_form_field(page, field_labels=["descricao", "descrição", "especificacao", "especificação", "observacao", "observação"], value=entry.specification)

                if self._submit_form(page):
                    page.wait_for_timeout(600)
                    synced += 1
                else:
                    self._capture_debug_snapshot(page=page, label="sync_cashflow_submit")
            except Exception as exc:
                print(f"[Segfy] Falha ao sincronizar lancamento financeiro: {exc}")
        return synced

    def _register_incident_on_page(self, page: Page, policy_id: str, incident_type: str, description: str) -> bool:
        self._navigate_to_section(page, ["Sinistros", "Endossos", "Ocorrências", "Ocorrencias"])
        self._click_first(page, selectors=[
            "button:has-text('Novo')", "button:has-text('Registrar')",
            "button:has-text('Adicionar')", "a:has-text('Novo')",
        ], timeout_ms=2000)
        page.wait_for_timeout(600)

        self._fill_form_field(page, field_labels=["apolice", "apólice", "numero", "número"], value=policy_id)
        self._fill_form_field(page, field_labels=["tipo", "type"], value=incident_type)
        self._fill_form_field(page, field_labels=["descricao", "descrição", "observacao", "observação"], value=description)
        return self._submit_form(page)

    def _update_commission_on_page(self, page: Page, policy_id: str, status: str) -> bool:
        self._navigate_to_section(page, [
            "Financeiro", "Comissões", "Comissoes",
            "Pagamentos de Comissões", "Pagamentos de Comissoes",
        ])
        if not self._search_and_open_record(page, policy_id):
            return False

        self._fill_form_field(page, field_labels=["status", "pagamento", "pgto", "situacao", "situação"], value=status)
        return self._submit_form(page)

    def _register_renewal_on_page(self, page: Page, policy_id: str, phase: str, status: str) -> bool:
        self._navigate_to_section(page, ["Renovações", "Renovacoes", "Renovação", "Renovacao"])
        self._click_first(page, selectors=[
            "button:has-text('Novo')", "button:has-text('Registrar')",
            "button:has-text('Adicionar')", "a:has-text('Novo')",
        ], timeout_ms=2000)
        page.wait_for_timeout(600)

        self._fill_form_field(page, field_labels=["apolice", "apólice", "numero", "número"], value=policy_id)
        self._fill_form_field(page, field_labels=["fase", "etapa", "phase"], value=phase)
        self._fill_form_field(page, field_labels=["status", "situacao", "situação"], value=status)
        return self._submit_form(page)

    def _launch_browser(self, playwright: Playwright):
        channels = [self.browser_channel, "chrome", "msedge"]
        if not self.allow_channel_fallback:
            channels = [self.browser_channel]
        seen: set[str] = set()
        for channel in channels:
            channel_name = channel.strip().lower()
            if not channel_name or channel_name in seen:
                continue
            seen.add(channel_name)
            try:
                browser = playwright.chromium.launch(channel=channel_name, headless=self.headless)
                print(f"[Segfy] Navegador Playwright iniciado com canal: {channel_name}.")
                return browser
            except Exception:
                continue
        if not self.allow_channel_fallback:
            raise RuntimeError(
                "Falha ao iniciar o navegador no canal solicitado para o Segfy: "
                f"{self.browser_channel or 'indefinido'}."
            )
        browser = playwright.chromium.launch(headless=self.headless)
        print("[Segfy] Navegador Playwright iniciado com Chromium padrao (fallback).")
        return browser

    def _login(self, page: Page) -> None:
        page.goto(self.base_url, wait_until="domcontentloaded")
        page.wait_for_timeout(1200)
        current_url = (page.url or "").strip()
        if current_url.startswith("about:blank") or current_url.startswith("data:"):
            login_url = f"{self.base_url}/login"
            print(f"[Segfy] Pagina inicial em branco; tentando rota de login: {login_url}")
            page.goto(login_url, wait_until="domcontentloaded")
            page.wait_for_timeout(1200)

        # Aceitar cookies antes de qualquer interacao (banner pode bloquear cliques).
        self._click_first(
            page,
            selectors=[
                "button:has-text('Aceitar')",
                "button:has-text('Aceito')",
                "button:has-text('Concordo')",
                "button:has-text('OK')",
                "a:has-text('Aceitar')",
                "text=Aceitar",
            ],
            timeout_ms=2000,
        )
        page.wait_for_timeout(400)

        # Alguns layouts exibem "Entrar com e-mail"/"Usar conta local".
        self._click_first(
            page,
            selectors=[
                "button:has-text('Entrar com e-mail')",
                "button:has-text('Entrar com email')",
                "button:has-text('Usar e-mail')",
                "button:has-text('Usar email')",
                "button:has-text('Usar conta local')",
                "text=Entrar com e-mail",
                "text=Usar conta local",
            ],
            timeout_ms=1400,
        )
        page.wait_for_timeout(500)

        # Campo de e-mail/usuario — seletores ordenados do mais especifico ao generico.
        user_filled = self._fill_first(
            page,
            selectors=[
                "input[placeholder='E-mail']",
                "input[placeholder='e-mail']",
                "input[placeholder*='E-mail' i]",
                "input[placeholder*='email' i]",
                "input[aria-label*='E-mail' i]",
                "input[aria-label*='email' i]",
                "input[type='email']",
                "input[name='email']",
                "input[name*='email' i]",
                "input[id*='email' i]",
                "input[autocomplete='username']",
                "input[name='login']",
                "input[name*='login' i]",
                "input[id*='login' i]",
                "input[name='username']",
                "input[name*='user' i]",
                "input[id*='user' i]",
                "input[name='usuario']",
                "input[name*='usuario' i]",
                "input[id*='usuario' i]",
                "input[placeholder*='usuario' i]",
                "input[type='text']",
            ],
            value=self.username,
        )

        password_selectors = [
            "input[type='password']",
            "input[name='password']",
            "input[name*='password' i]",
            "input[id*='password' i]",
            "input[autocomplete='current-password']",
            "input[name='senha']",
            "input[name*='senha' i]",
            "input[id*='senha' i]",
            "input[placeholder*='senha' i]",
        ]
        password_filled = self._fill_first(
            page,
            selectors=password_selectors,
            value=self.password,
        )

        # Alguns fluxos de login exibem e-mail e senha em etapas separadas.
        if user_filled and not password_filled:
            stepped = self._click_first(
                page,
                selectors=[
                    "button:has-text('Proximo')",
                    "button:has-text('Próximo')",
                    "button:has-text('Continuar')",
                    "button:has-text('Avancar')",
                    "button:has-text('Avançar')",
                    "input[type='submit']",
                    "button[type='submit']",
                    "text=Proximo",
                    "text=Próximo",
                    "text=Continuar",
                ],
                timeout_ms=2000,
            )
            if stepped:
                page.wait_for_timeout(1200)
                password_filled = self._fill_first(
                    page,
                    selectors=password_selectors,
                    value=self.password,
                )

        if not user_filled and password_filled:
            # Cenário comum quando o site já mantém o usuário em sessão/parcialmente preenchido.
            print("[Segfy] Aviso: usuario nao encontrado no formulario; seguindo com senha preenchida.")

        if not user_filled and not password_filled:
            print(
                "[Segfy] Aviso: campos de login nao encontrados; mantendo fluxo "
                "(sessao previa pode ja estar autenticada)."
            )
            self._capture_debug_snapshot(page=page, label="login_fields_not_found")
        elif user_filled and not password_filled:
            print(
                "[Segfy] Aviso: senha nao encontrada apos tentativa em etapas; "
                "seguindo fluxo para verificar se a sessao ja esta autenticada."
            )
            self._capture_debug_snapshot(page=page, label="login_password_not_found")

        self._click_first(
            page,
            selectors=[
                "button[type='submit']",
                "input[type='submit']",
                "button:has-text('Entrar')",
                "button:has-text('Acessar')",
                "button:has-text('Login')",
                "button:has-text('Continuar')",
                "button:has-text('Proximo')",
                "button:has-text('Próximo')",
                "text=Entrar",
                "text=Acessar",
                "text=Login",
                "text=Continuar",
            ],
        )
        page.wait_for_timeout(2200)

    def _try_export_policies(self, page: Page) -> Path | None:
        # Tenta abrir area de apolices/relatorios antes de exportar.
        self._click_first(
            page,
            selectors=[
                "text=Apolices",
                "text=Apólices",
                "text=Carteira",
                "text=Relatorios",
                "text=Relatórios",
            ],
            timeout_ms=2000,
        )
        page.wait_for_timeout(800)

        export_selectors = [
            "button:has-text('Exportar')",
            "a:has-text('Exportar')",
            "text=Exportar",
            "button:has-text('Baixar')",
            "a:has-text('Baixar')",
            "text=Baixar",
            "button:has-text('Download')",
            "a:has-text('Download')",
            "text=Download",
        ]

        for selector in export_selectors:
            locator = page.locator(selector)
            if self._locator_count(locator) == 0:
                continue
            try:
                with page.expect_download(timeout=5000) as download_info:
                    locator.first.click(timeout=2500)
                download = download_info.value
                target = self.export_output_path
                if not re.search(r"\.xlsx?$", target.name, re.IGNORECASE):
                    target = target.with_suffix(".xlsx")
                target.parent.mkdir(parents=True, exist_ok=True)
                download.save_as(str(target))
                return target
            except Exception:
                continue
        return None

    def _collect_import_files(self, modified_after: datetime | None = None) -> list[Path]:
        if self.import_source_dir is None:
            return []
        if not self.import_source_dir.exists() or not self.import_source_dir.is_dir():
            return []

        allowed = {".pdf", ".xls", ".xlsx", ".csv"}
        candidates: list[tuple[datetime, Path]] = []
        for path in self.import_source_dir.iterdir():
            if not path.is_file() or path.suffix.lower() not in allowed:
                continue
            file_ts = self._file_timestamp(path)
            if modified_after is not None and file_ts <= modified_after:
                continue
            candidates.append((file_ts, path))
        candidates.sort(key=lambda item: item[1].name.lower())
        return [item[1] for item in candidates[: self.import_max_files]]

    def _file_timestamp(self, path: Path) -> datetime:
        stat = path.stat()
        mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        if sys.platform.startswith("win"):
            ctime = datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc)
            return max(mtime, ctime)
        return mtime

    def _load_last_execution_utc(self) -> datetime | None:
        if not self.import_state_path.exists():
            return None
        try:
            payload = json.loads(self.import_state_path.read_text(encoding="utf-8"))
        except Exception:
            return None
        raw_value = str(payload.get("last_execution_utc", "")).strip()
        if not raw_value:
            return None
        try:
            return datetime.fromisoformat(raw_value)
        except ValueError:
            return None

    def _save_last_execution_utc(self, value: datetime) -> None:
        self.import_state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"last_execution_utc": value.isoformat()}
        self.import_state_path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")

    def _upload_documents(self, page: Page, files: list[Path]) -> int:
        target_url = self.import_page_url or f"{self.base_url}/centralVendas/importacaoPropostas"
        page.goto(target_url, wait_until="domcontentloaded")
        page.wait_for_timeout(1400)

        # Atalho quando a tela ja abre na etapa "Importar PDF/Excel".
        self._click_first(
            page,
            selectors=[
                "text=Importar PDF/Excel",
                "text=Importar PDF",
                "text=Importação de propostas e apólices",
                "text=Importacao de propostas e apolices",
            ],
            timeout_ms=1800,
        )
        page.wait_for_timeout(700)

        file_locator = page.locator("input[type='file']")
        if self._locator_count(file_locator) == 0:
            return 0

        file_paths = [str(path) for path in files]
        try:
            file_locator.first.set_input_files(file_paths, timeout=3000)
        except Exception:
            # Fallback para casos em que a tela aceita apenas um arquivo por vez.
            imported = 0
            for file_path in file_paths:
                try:
                    file_locator.first.set_input_files(file_path, timeout=3000)
                    imported += 1
                except Exception:
                    continue
            if imported == 0:
                return 0
            self._click_first(page, selectors=["text=Prosseguir", "button:has-text('Prosseguir')"], timeout_ms=2000)
            return imported

        self._click_first(page, selectors=["text=Prosseguir", "button:has-text('Prosseguir')"], timeout_ms=2000)
        return len(file_paths)

    def _fill_first(self, page: Page, *, selectors: list[str], value: str) -> bool:
        for context in self._iter_locator_contexts(page):
            for selector in selectors:
                try:
                    locator = context.locator(selector)
                    if locator.count() == 0:
                        continue
                    locator.first.fill(value, timeout=2500)
                    return True
                except Exception:
                    continue
        return False

    def _click_first(self, page: Page, *, selectors: list[str], timeout_ms: int = 3500) -> bool:
        for context in self._iter_locator_contexts(page):
            for selector in selectors:
                try:
                    locator = context.locator(selector)
                    if locator.count() == 0:
                        continue
                    locator.first.click(timeout=timeout_ms)
                    return True
                except Exception:
                    continue
        return False

    def _iter_locator_contexts(self, page: Page):
        # Alguns layouts do Segfy colocam o formulario de login dentro de iframe.
        # Percorremos pagina principal + frames para tornar o login robusto.
        contexts: list[object] = [page]
        try:
            for frame in page.frames:
                if frame == page.main_frame:
                    continue
                contexts.append(frame)
        except Exception:
            return contexts
        return contexts

    def _register_payment_on_page(self, *, page: Page, commitment_id: str, description: str) -> bool:
        candidates = self._build_payment_queries(commitment_id=commitment_id, description=description)
        target_urls = self._payment_urls()

        # Tenta diretamente na tela corrente (dashboard inicial ja autenticado).
        for query in candidates:
            if self._try_register_payment_via_parcelas(page=page, query=query):
                return True
            if self._try_register_payment_by_query(page=page, query=query):
                return True

        for target_url in target_urls:
            try:
                page.goto(target_url, wait_until="domcontentloaded")
                page.wait_for_timeout(900)
            except Exception:
                continue
            for query in candidates:
                if self._try_register_payment_via_parcelas(page=page, query=query):
                    return True
                if self._try_register_payment_by_query(page=page, query=query):
                    return True
        return False

    def _payment_urls(self) -> list[str]:
        urls: list[str] = []
        if self.payment_page_url:
            urls.append(self.payment_page_url)
        urls.extend(
            [
                f"{self.base_url}/financeiro/parcelas",
                f"{self.base_url}/financeiro/recebimentos",
                f"{self.base_url}/financeiro/contasAReceber",
                f"{self.base_url}/financeiro",
                f"{self.base_url}/financeiro/faturas",
                f"{self.base_url}/centralVendas",
                self.base_url,
            ]
        )
        dedup: list[str] = []
        seen: set[str] = set()
        for url in urls:
            normalized = url.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            dedup.append(normalized)
        return dedup

    def _build_payment_queries(self, *, commitment_id: str, description: str) -> list[str]:
        raw_values = [
            commitment_id.strip(),
            description.strip(),
        ]
        queries: list[str] = []
        seen: set[str] = set()
        for raw in raw_values:
            if not raw:
                continue
            tokens = [raw]
            compact_digits = "".join(ch for ch in raw if ch.isdigit())
            if len(compact_digits) >= 6:
                tokens.append(compact_digits)
            for token in tokens:
                clean = " ".join(token.split()).strip()
                if len(clean) < 3:
                    continue
                key = clean.casefold()
                if key in seen:
                    continue
                seen.add(key)
                queries.append(clean)

                words = [item for item in re.split(r"\s+", clean) if len(item.strip(".,;:-_/")) >= 3]
                if words:
                    first_word = words[0].strip(".,;:-_/")
                    key_first = first_word.casefold()
                    if key_first not in seen and len(first_word) >= 3:
                        seen.add(key_first)
                        queries.append(first_word)
                if len(words) >= 2:
                    compact_name = " ".join(item.strip(".,;:-_/") for item in words[:3]).strip()
                    key_compact = compact_name.casefold()
                    if compact_name and key_compact not in seen:
                        seen.add(key_compact)
                        queries.append(compact_name)
        return queries[:6]

    def _try_register_payment_by_query(self, *, page: Page, query: str) -> bool:
        if not query:
            return False

        search_selectors = [
            "input[type='search']",
            "input[placeholder*='Buscar' i]",
            "input[placeholder*='Pesquisar' i]",
            "input[placeholder*='Proposta' i]",
            "input[placeholder*='Apolice' i]",
            "input[placeholder*='Apolice' i]",
            "input[name*='search' i]",
            "input[name*='busca' i]",
        ]
        self._fill_first(page, selectors=search_selectors, value=query)
        try:
            page.keyboard.press("Enter")
        except Exception:
            pass
        page.wait_for_timeout(650)

        action_selectors = [
            "button:has-text('Registrar pagamento')",
            "button:has-text('Registrar baixa')",
            "button:has-text('Baixar')",
            "button:has-text('Receber')",
            "button:has-text('Baixa manual')",
            "a:has-text('Registrar pagamento')",
            "a:has-text('Registrar baixa')",
            "a:has-text('Baixar')",
            "a:has-text('Receber')",
            "a:has-text('Baixa manual')",
        ]

        query_selector = query.replace("\\", "\\\\").replace('"', '\\"')
        row_selectors = [
            f'tr:has-text("{query_selector}")',
            f'div[role="row"]:has-text("{query_selector}")',
            f'li:has-text("{query_selector}")',
            f'div:has-text("{query_selector}")',
        ]
        for row_selector in row_selectors:
            row = page.locator(row_selector)
            if self._locator_count(row) == 0:
                continue
            for action_selector in action_selectors:
                action = row.first.locator(action_selector)
                if self._locator_count(action) == 0:
                    continue
                try:
                    action.first.click(timeout=2200)
                    return self._confirm_payment_modal(page)
                except Exception:
                    continue

        if self._click_first(page, selectors=action_selectors, timeout_ms=1800):
            return self._confirm_payment_modal(page)
        return False

    def _try_register_payment_via_parcelas(self, *, page: Page, query: str) -> bool:
        if not query:
            return False

        # Fluxo observado nas telas enviadas:
        # Financeiro > Parcelas do Segurado > pesquisar > coluna "Segurado pagou?" (Nao/Sim)
        self._fill_first(
            page,
            selectors=[
                "input[placeholder*='Segurado' i]",
                "input[placeholder*='Apolice' i]",
                "input[placeholder*='Apólice' i]",
                "input[name*='segurado' i]",
                "input[name*='apolice' i]",
            ],
            value=query,
        )
        self._click_first(
            page,
            selectors=[
                "button:has-text('Pesquisar')",
                "a:has-text('Pesquisar')",
                "text=Pesquisar",
            ],
            timeout_ms=1800,
        )
        page.wait_for_timeout(650)

        query_selector = query.replace("\\", "\\\\").replace('"', '\\"')
        row_selectors = [
            f'tr:has-text("{query_selector}")',
            f'div[role="row"]:has-text("{query_selector}")',
            f'li:has-text("{query_selector}")',
            f'div:has-text("{query_selector}")',
        ]
        for row_selector in row_selectors:
            row = page.locator(row_selector)
            if self._locator_count(row) == 0:
                continue

            paid_selectors = [
                "select[name*='pago' i]",
                "select[id*='pago' i]",
                "select",
            ]
            for paid_selector in paid_selectors:
                paid_field = row.first.locator(paid_selector)
                if self._locator_count(paid_field) == 0:
                    continue
                select = paid_field.first

                current_value = ""
                try:
                    current_value = (select.input_value(timeout=1000) or "").strip().upper()
                except Exception:
                    pass
                if current_value in {"SIM", "1", "TRUE"}:
                    return True

                switched = False
                try:
                    select.select_option(label="Sim", timeout=1800)
                    switched = True
                except Exception:
                    try:
                        select.select_option(value="1", timeout=1800)
                        switched = True
                    except Exception:
                        try:
                            select.select_option(index=1, timeout=1800)
                            switched = True
                        except Exception:
                            switched = False

                if not switched:
                    continue

                self._click_first(
                    page,
                    selectors=[
                        "button:has-text('Salvar')",
                        "button:has-text('Confirmar')",
                        "button:has-text('Registrar')",
                        "button:has-text('Concluir')",
                        "text=Salvar",
                        "text=Confirmar",
                    ],
                    timeout_ms=1200,
                )
                page.wait_for_timeout(450)

                try:
                    updated_value = (select.input_value(timeout=1000) or "").strip().upper()
                    if updated_value in {"SIM", "1", "TRUE"}:
                        return True
                except Exception:
                    pass

                try:
                    row_text = (row.first.inner_text(timeout=1200) or "").upper()
                except Exception:
                    row_text = ""
                if "SIM" in row_text:
                    return True
        return False

    def _confirm_payment_modal(self, page: Page) -> bool:
        today_iso = datetime.now().date().isoformat()
        self._fill_first(
            page,
            selectors=[
                "input[type='date']",
                "input[name*='data' i]",
                "input[id*='data' i]",
                "input[placeholder*='Data' i]",
            ],
            value=today_iso,
        )

        confirmed = self._click_first(
            page,
            selectors=[
                "button:has-text('Confirmar')",
                "button:has-text('Salvar')",
                "button:has-text('Registrar')",
                "button:has-text('Concluir')",
                "button:has-text('OK')",
                "text=Confirmar",
                "text=Salvar",
                "text=Registrar",
            ],
            timeout_ms=2500,
        )
        if not confirmed:
            return False

        page.wait_for_timeout(700)
        return True

    def _locator_count(self, locator: Any) -> int:
        try:
            return int(locator.count())
        except Exception:
            return 0

    def _capture_debug_snapshot(self, *, page: Page | None, label: str) -> None:
        if page is None:
            return
        try:
            if page.is_closed():
                return
        except Exception:
            return
        try:
            self.debug_output_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_label = re.sub(r"[^a-zA-Z0-9_-]+", "_", label).strip("_") or "segfy_debug"
            base_name = f"{stamp}_{safe_label}"
            html_path = self.debug_output_dir / f"{base_name}.html"
            png_path = self.debug_output_dir / f"{base_name}.png"
            txt_path = self.debug_output_dir / f"{base_name}.txt"

            try:
                html_content = page.content()
                html_path.write_text(html_content, encoding="utf-8")
            except Exception:
                pass

            try:
                page.screenshot(path=str(png_path), full_page=True)
            except Exception:
                pass

            url = ""
            title = ""
            try:
                url = page.url or ""
            except Exception:
                pass
            try:
                title = page.title() or ""
            except Exception:
                pass
            txt_path.write_text(
                f"url={url}\ntitle={title}\nlabel={label}\n",
                encoding="utf-8",
            )
            print(f"[Segfy][debug] Evidencias salvas em: {self.debug_output_dir.resolve()}")
        except Exception:
            # Nunca interrompe o fluxo principal por falha de dump de debug.
            return
