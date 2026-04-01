from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from rpa_corretora.domain.models import PortalPolicyData
from rpa_corretora.integrations.insurer_portal_wave1 import (
    BasePortalWebGateway,
    DEFAULT_COMISSAO_LABELS,
    DEFAULT_PREMIO_LABELS,
    parse_claim_status_from_text,
    parse_policy_data_from_text_generic,
    web_portal_automation_available,
)

if TYPE_CHECKING:
    from playwright.sync_api import Page


@dataclass(frozen=True, slots=True)
class BradescoPortalCredentials:
    username: str
    password: str


@dataclass(frozen=True, slots=True)
class AllianzPortalCredentials:
    username: str
    password: str


@dataclass(frozen=True, slots=True)
class SuhaiPortalCredentials:
    username: str
    password: str


@dataclass(frozen=True, slots=True)
class TokioPortalCredentials:
    username: str
    password: str


@dataclass(frozen=True, slots=True)
class HDIPortalCredentials:
    username: str
    password: str


@dataclass(frozen=True, slots=True)
class AzulPortalCredentials:
    username: str
    password: str


def parse_bradesco_policy_data_from_text(policy_id: str, text: str) -> PortalPolicyData | None:
    return parse_policy_data_from_text_generic(
        policy_id=policy_id,
        insurer="Bradesco",
        text=text,
        premio_labels=(
            *DEFAULT_PREMIO_LABELS,
            "premio bruto",
            "premio da apolice",
        ),
        comissao_labels=(
            *DEFAULT_COMISSAO_LABELS,
            "comissao bruta",
        ),
    )


def parse_allianz_policy_data_from_text(policy_id: str, text: str) -> PortalPolicyData | None:
    return parse_policy_data_from_text_generic(
        policy_id=policy_id,
        insurer="Allianz",
        text=text,
        premio_labels=(
            *DEFAULT_PREMIO_LABELS,
            "valor premio",
        ),
        comissao_labels=(
            *DEFAULT_COMISSAO_LABELS,
            "comissao prevista",
        ),
    )


def parse_suhai_policy_data_from_text(policy_id: str, text: str) -> PortalPolicyData | None:
    return parse_policy_data_from_text_generic(
        policy_id=policy_id,
        insurer="Suhai",
        text=text,
        premio_labels=(
            *DEFAULT_PREMIO_LABELS,
            "premio mensal",
        ),
        comissao_labels=(
            *DEFAULT_COMISSAO_LABELS,
            "comissao liquida",
        ),
    )


def parse_tokio_policy_data_from_text(policy_id: str, text: str) -> PortalPolicyData | None:
    return parse_policy_data_from_text_generic(
        policy_id=policy_id,
        insurer="Tokio Marine",
        text=text,
        premio_labels=(
            *DEFAULT_PREMIO_LABELS,
            "premio liquido emitido",
            "premio emitido",
        ),
        comissao_labels=(
            *DEFAULT_COMISSAO_LABELS,
            "comissoes pagas",
            "comissao paga",
            "extrato comissao",
        ),
    )


def parse_hdi_policy_data_from_text(policy_id: str, text: str) -> PortalPolicyData | None:
    return parse_policy_data_from_text_generic(
        policy_id=policy_id,
        insurer="HDI",
        text=text,
        premio_labels=(
            *DEFAULT_PREMIO_LABELS,
            "hdi auto perfil",
            "hdi auto basico",
            "valor da cotacao",
            "valor da proposta",
        ),
        comissao_labels=(
            *DEFAULT_COMISSAO_LABELS,
            "programa de comissao especial",
            "comissao especial",
        ),
    )


def parse_azul_policy_data_from_text(policy_id: str, text: str) -> PortalPolicyData | None:
    return parse_policy_data_from_text_generic(
        policy_id=policy_id,
        insurer="Azul",
        text=text,
        premio_labels=(
            *DEFAULT_PREMIO_LABELS,
            "cota premio",
            "cota prêmio",
            "valor da cotacao",
            "valor da proposta",
        ),
        comissao_labels=(
            *DEFAULT_COMISSAO_LABELS,
            "extrato de comissoes",
            "extrato de comissões",
            "comissoes",
            "comissões",
        ),
    )


class BradescoPortalGateway(BasePortalWebGateway):
    insurer_name = "Bradesco"

    def __init__(
        self,
        credentials: BradescoPortalCredentials,
        base_url: str = "https://wwwn.bradescoseguros.com.br",
        headless: bool = True,
        timeout_seconds: int = 35,
    ) -> None:
        super().__init__(credentials=credentials, base_url=base_url, headless=headless, timeout_seconds=timeout_seconds)

    def _parse_policy_text(self, policy_id: str, page_text: str) -> PortalPolicyData | None:
        return parse_bradesco_policy_data_from_text(policy_id=policy_id, text=page_text)


class AllianzPortalGateway(BasePortalWebGateway):
    insurer_name = "Allianz"

    def __init__(
        self,
        credentials: AllianzPortalCredentials,
        base_url: str = "https://www.allianznet.com.br",
        headless: bool = True,
        timeout_seconds: int = 35,
    ) -> None:
        super().__init__(credentials=credentials, base_url=base_url, headless=headless, timeout_seconds=timeout_seconds)

    def _parse_policy_text(self, policy_id: str, page_text: str) -> PortalPolicyData | None:
        return parse_allianz_policy_data_from_text(policy_id=policy_id, text=page_text)


class SuhaiPortalGateway(BasePortalWebGateway):
    insurer_name = "Suhai"

    def __init__(
        self,
        credentials: SuhaiPortalCredentials,
        base_url: str = "https://suhaiseguradoracotacao.com.br/login",
        headless: bool = True,
        timeout_seconds: int = 35,
    ) -> None:
        super().__init__(credentials=credentials, base_url=base_url, headless=headless, timeout_seconds=timeout_seconds)

    def _login(self, page: Page) -> None:
        page.goto(self.base_url, wait_until="domcontentloaded")
        page.wait_for_timeout(1200)

        self._fill_first(
            page,
            [
                "input[name='username']",
                "input[name='login']",
                "input[name*='usuario' i]",
                "input[id*='usuario' i]",
                "input[id*='login' i]",
                "input[name*='cpf' i]",
                "input[id*='cpf' i]",
                "input[type='email']",
                "input[type='text']",
            ],
            self.credentials.username,
        )
        self._fill_first(
            page,
            [
                "input[name='password']",
                "input[name*='senha' i]",
                "input[id*='senha' i]",
                "input[type='password']",
            ],
            self.credentials.password,
        )
        self._click_first(
            page,
            [
                "button:has-text('Entrar')",
                "button:has-text('Acessar')",
                "button:has-text('Login')",
                "input[type='submit']",
                "button[type='submit']",
            ],
        )
        page.wait_for_timeout(2200)

    def _open_suhai_menu(self, page: Page, menu_name: str) -> bool:
        opened = self._hover_first(
            page,
            [
                f"a:has-text('{menu_name}')",
                f"li:has-text('{menu_name}')",
                f"button:has-text('{menu_name}')",
                f"text={menu_name}",
            ],
            timeout_ms=2200,
        )
        if not opened:
            opened = self._click_first(
                page,
                [
                    f"a:has-text('{menu_name}')",
                    f"li:has-text('{menu_name}')",
                    f"button:has-text('{menu_name}')",
                    f"text={menu_name}",
                ],
                timeout_ms=2200,
            )
        if opened:
            page.wait_for_timeout(650)
        return opened

    def _click_suhai_submenu(self, page: Page, submenu_name: str) -> bool:
        clicked = self._click_first(
            page,
            [
                f"a:has-text('{submenu_name}')",
                f"li:has-text('{submenu_name}')",
                f"text={submenu_name}",
            ],
            timeout_ms=2400,
        )
        if clicked:
            page.wait_for_timeout(700)
        return clicked

    def _fill_and_submit_suhai_search(self, page: Page, policy_id: str, selectors: list[str]) -> bool:
        has_search = self._fill_first(page, selectors, policy_id)
        if not has_search:
            return False

        submitted = self._press_enter_first(page, selectors)
        if not submitted:
            self._click_first(
                page,
                [
                    "button:has-text('Pesquisar')",
                    "button:has-text('Buscar')",
                    "button:has-text('Consultar')",
                    "button:has-text('Filtrar')",
                    "input[type='submit']",
                ],
                timeout_ms=2200,
            )
        page.wait_for_timeout(1800)
        return True

    def _fetch_policy(self, page: Page, policy_id: str) -> PortalPolicyData | None:
        page.goto(self.base_url, wait_until="domcontentloaded")
        page.wait_for_timeout(900)

        performed_search = False

        if self._open_suhai_menu(page, "Apólice") or self._open_suhai_menu(page, "Apolice"):
            self._click_suhai_submenu(page, "Consulta de Apólice") or self._click_suhai_submenu(
                page, "Consulta de Apolice"
            )
            performed_search = self._fill_and_submit_suhai_search(
                page,
                policy_id,
                [
                    "input[placeholder*='apolice' i]",
                    "input[placeholder*='apólice' i]",
                    "input[name*='apolice' i]",
                    "input[id*='apolice' i]",
                    "input[name*='numero' i]",
                    "input[id*='numero' i]",
                    "input[type='search']",
                    "input[type='text']",
                ],
            )

        if not performed_search and (self._open_suhai_menu(page, "Relatórios") or self._open_suhai_menu(page, "Relatorios")):
            self._click_suhai_submenu(page, "Seguros Emitidos") or self._click_suhai_submenu(page, "Apólices a Renovar")
            performed_search = self._fill_and_submit_suhai_search(
                page,
                policy_id,
                [
                    "input[placeholder*='apolice' i]",
                    "input[placeholder*='apólice' i]",
                    "input[name*='apolice' i]",
                    "input[id*='apolice' i]",
                    "input[type='search']",
                    "input[type='text']",
                ],
            )

        if not performed_search:
            fallback_item = super()._fetch_policy(page, policy_id)
            if fallback_item is not None:
                return fallback_item

        page_text = page.locator("body").inner_text(timeout=self.timeout_seconds * 1000)
        return self._parse_policy_text(policy_id, page_text)

    def check_claim_status(self, *, commitment_id: str, description: str) -> str | None:
        query = description.strip() or commitment_id.strip()
        if query == "":
            return None

        if not web_portal_automation_available():
            return None

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
                        page.goto(self.base_url, wait_until="domcontentloaded")
                        page.wait_for_timeout(900)

                        opened_sinistros = self._open_suhai_menu(page, "Sinistros")
                        if opened_sinistros:
                            self._click_suhai_submenu(page, "Processo de Sinistro")

                        self._fill_and_submit_suhai_search(
                            page,
                            query,
                            [
                                "input[placeholder*='sinistro' i]",
                                "input[placeholder*='apolice' i]",
                                "input[placeholder*='apólice' i]",
                                "input[placeholder*='protocolo' i]",
                                "input[name*='sinistro' i]",
                                "input[id*='sinistro' i]",
                                "input[type='search']",
                                "input[type='text']",
                            ],
                        )

                        page_text = page.locator("body").inner_text(timeout=self.timeout_seconds * 1000)
                        return parse_claim_status_from_text(page_text)
                    finally:
                        context.close()
                finally:
                    browser.close()
        except PlaywrightTimeoutError:
            print(f"[{self.insurer_name} Portal] Timeout durante consulta de sinistro.")
            return None
        except Exception as exc:
            print(f"[{self.insurer_name} Portal] Falha ao consultar sinistro: {exc}")
            return None

    def _parse_policy_text(self, policy_id: str, page_text: str) -> PortalPolicyData | None:
        return parse_suhai_policy_data_from_text(policy_id=policy_id, text=page_text)


class HDIPortalGateway(BasePortalWebGateway):
    insurer_name = "HDI"

    def __init__(
        self,
        credentials: HDIPortalCredentials,
        base_url: str = "https://www.hdi.com.br/hdidigital",
        headless: bool = True,
        timeout_seconds: int = 40,
    ) -> None:
        super().__init__(credentials=credentials, base_url=base_url, headless=headless, timeout_seconds=timeout_seconds)

    def _dismiss_hdi_overlays(self, page: Page) -> None:
        for _ in range(4):
            self._click_first(
                page,
                [
                    "button:has-text('FECHAR')",
                    "button:has-text('Fechar')",
                    "text=FECHAR",
                    "text=Fechar",
                    "button:has-text('ENTENDI')",
                    "button:has-text('Entendi')",
                    "text=ENTENDI",
                    "text=Entendi",
                    "button:has-text('ACEITAR')",
                    "button:has-text('Aceitar')",
                    "text=ACEITAR",
                    "text=Aceitar",
                    "button[aria-label*='fechar' i]",
                    "button[aria-label*='close' i]",
                    "button:has-text('x')",
                    "button:has-text('X')",
                    "text=×",
                ],
                timeout_ms=1000,
            )
            self._click_first(
                page,
                [
                    "label:has-text('Li e aceito')",
                    "text=Li e aceito",
                ],
                timeout_ms=700,
            )
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
            page.wait_for_timeout(180)

    def _open_hdi_menu(self, page: Page, menu_name: str) -> bool:
        opened = self._hover_first(
            page,
            [
                f"a:has-text('{menu_name}')",
                f"li:has-text('{menu_name}')",
                f"button:has-text('{menu_name}')",
                f"text={menu_name}",
            ],
            timeout_ms=2400,
        )
        if not opened:
            opened = self._click_first(
                page,
                [
                    f"a:has-text('{menu_name}')",
                    f"li:has-text('{menu_name}')",
                    f"button:has-text('{menu_name}')",
                    f"text={menu_name}",
                ],
                timeout_ms=2400,
            )
        if opened:
            page.wait_for_timeout(700)
        return opened

    def _click_hdi_submenu(self, page: Page, submenu_name: str) -> bool:
        clicked = self._click_first(
            page,
            [
                f"a:has-text('{submenu_name}')",
                f"li:has-text('{submenu_name}')",
                f"text={submenu_name}",
            ],
            timeout_ms=2600,
        )
        if clicked:
            page.wait_for_timeout(850)
        return clicked

    def _fill_and_submit_hdi_search(self, page: Page, value: str, selectors: list[str]) -> bool:
        has_search = self._fill_first(page, selectors, value)
        if not has_search:
            return False

        submitted = self._press_enter_first(page, selectors)
        if not submitted:
            self._click_first(
                page,
                [
                    "button:has-text('CONTINUAR')",
                    "button:has-text('Continuar')",
                    "button:has-text('Pesquisar')",
                    "button:has-text('Buscar')",
                    "button:has-text('Consultar')",
                    "button:has-text('Filtrar')",
                    "button[aria-label*='pesquisar' i]",
                    "input[type='submit']",
                ],
                timeout_ms=2500,
            )
        page.wait_for_timeout(1700)
        self._dismiss_hdi_overlays(page)
        return True

    def _login(self, page: Page) -> None:
        page.goto(self.base_url, wait_until="domcontentloaded")
        page.wait_for_timeout(1200)

        self._fill_first(
            page,
            [
                "input[name='username']",
                "input[name='login']",
                "input[name*='usuario' i]",
                "input[id*='usuario' i]",
                "input[id*='chave' i]",
                "input[name*='chave' i]",
                "input[name*='cpf' i]",
                "input[id*='cpf' i]",
                "input[name*='cnpj' i]",
                "input[id*='cnpj' i]",
                "input[type='email']",
            ],
            self.credentials.username,
        )
        self._fill_first(
            page,
            [
                "input[name='password']",
                "input[id*='senha' i]",
                "input[name*='senha' i]",
                "input[type='password']",
            ],
            self.credentials.password,
        )
        self._click_first(
            page,
            [
                "button:has-text('Entrar')",
                "button:has-text('Acessar')",
                "button:has-text('Login')",
                "input[type='submit']",
                "button[type='submit']",
            ],
        )
        page.wait_for_timeout(2500)
        self._dismiss_hdi_overlays(page)

    def _fetch_policy(self, page: Page, policy_id: str) -> PortalPolicyData | None:
        page.goto(self.base_url, wait_until="domcontentloaded")
        page.wait_for_timeout(900)
        self._dismiss_hdi_overlays(page)

        performed_search = False

        if self._open_hdi_menu(page, "Apólice") or self._open_hdi_menu(page, "Apolice"):
            self._click_hdi_submenu(page, "Buscar Apólices") or self._click_hdi_submenu(page, "Buscar Apolices")
            performed_search = self._fill_and_submit_hdi_search(
                page,
                policy_id,
                [
                    "input[placeholder*='apolice' i]",
                    "input[placeholder*='apólice' i]",
                    "input[name*='apolice' i]",
                    "input[id*='apolice' i]",
                    "input[placeholder*='cpf' i]",
                    "input[placeholder*='cnpj' i]",
                    "input[type='search']",
                ],
            )

        if not performed_search and self._open_hdi_menu(page, "Proposta"):
            self._click_hdi_submenu(page, "Buscar Proposta")
            performed_search = self._fill_and_submit_hdi_search(
                page,
                policy_id,
                [
                    "input[placeholder*='proposta' i]",
                    "input[name*='proposta' i]",
                    "input[id*='proposta' i]",
                    "input[placeholder*='cpf' i]",
                    "input[placeholder*='cnpj' i]",
                    "input[type='search']",
                ],
            )

        if not performed_search and (
            self._open_hdi_menu(page, "Renovação") or self._open_hdi_menu(page, "Renovacao")
        ):
            self._click_hdi_submenu(page, "Renovações") or self._click_hdi_submenu(page, "Renovacoes")
            performed_search = self._fill_and_submit_hdi_search(
                page,
                policy_id,
                [
                    "input[placeholder*='cpf' i]",
                    "input[placeholder*='cnpj' i]",
                    "input[placeholder*='apolice' i]",
                    "input[placeholder*='apólice' i]",
                    "input[type='search']",
                ],
            )

        if not performed_search:
            self._click_first(
                page,
                [
                    "button:has-text('Apólices')",
                    "button:has-text('Apolices')",
                    "text=Apólices",
                    "text=Apolices",
                ],
                timeout_ms=1200,
            )
            performed_search = self._fill_and_submit_hdi_search(
                page,
                policy_id,
                [
                    "input[placeholder*='cpf' i]",
                    "input[placeholder*='cnpj' i]",
                    "input[aria-label*='cpf' i]",
                    "input[aria-label*='cnpj' i]",
                    "input[placeholder*='apolice' i]",
                    "input[placeholder*='apólice' i]",
                    "input[type='search']",
                ],
            )

        if not performed_search:
            fallback_item = super()._fetch_policy(page, policy_id)
            if fallback_item is not None:
                return fallback_item

        page_text = page.locator("body").inner_text(timeout=self.timeout_seconds * 1000)
        return self._parse_policy_text(policy_id, page_text)

    def check_claim_status(self, *, commitment_id: str, description: str) -> str | None:
        query = description.strip() or commitment_id.strip()
        if query == "":
            return None
        if not web_portal_automation_available():
            return None

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
                        page.goto(self.base_url, wait_until="domcontentloaded")
                        page.wait_for_timeout(800)
                        self._dismiss_hdi_overlays(page)

                        self._open_hdi_menu(page, "Sinistro")
                        self._fill_and_submit_hdi_search(
                            page,
                            query,
                            [
                                "input[placeholder*='sinistro' i]",
                                "input[name*='sinistro' i]",
                                "input[id*='sinistro' i]",
                                "input[placeholder*='protocolo' i]",
                                "input[placeholder*='apolice' i]",
                                "input[placeholder*='apólice' i]",
                                "input[placeholder*='cpf' i]",
                                "input[placeholder*='cnpj' i]",
                                "input[type='search']",
                            ],
                        )

                        page_text = page.locator("body").inner_text(timeout=self.timeout_seconds * 1000)
                        return parse_claim_status_from_text(page_text)
                    finally:
                        context.close()
                finally:
                    browser.close()
        except PlaywrightTimeoutError:
            print(f"[{self.insurer_name} Portal] Timeout durante consulta de sinistro.")
            return None
        except Exception as exc:
            print(f"[{self.insurer_name} Portal] Falha ao consultar sinistro: {exc}")
            return None

    def _parse_policy_text(self, policy_id: str, page_text: str) -> PortalPolicyData | None:
        return parse_hdi_policy_data_from_text(policy_id=policy_id, text=page_text)


class AzulPortalGateway(BasePortalWebGateway):
    insurer_name = "Azul"

    def __init__(
        self,
        credentials: AzulPortalCredentials,
        base_url: str = "https://www.azulseguros.com.br/area-restrita",
        dashboard_url: str = "https://dashboard.azulseguros.com.br/#/home",
        headless: bool = True,
        timeout_seconds: int = 40,
    ) -> None:
        super().__init__(credentials=credentials, base_url=base_url, headless=headless, timeout_seconds=timeout_seconds)
        self.dashboard_url = dashboard_url

    def _dismiss_azul_overlays(self, page: Page) -> None:
        for _ in range(4):
            self._click_first(
                page,
                [
                    "button:has-text('Aceitar todos os cookies')",
                    "button:has-text('Dispensar')",
                    "button:has-text('Fechar')",
                    "button:has-text('FECHAR')",
                    "text=Fechar",
                    "text=×",
                    "button[aria-label*='fechar' i]",
                    "button[aria-label*='close' i]",
                    "button:has-text('x')",
                    "button:has-text('X')",
                ],
                timeout_ms=1000,
            )
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
            page.wait_for_timeout(150)

    def _open_azul_dashboard_home(self, page: Page) -> None:
        page.goto(self.dashboard_url, wait_until="domcontentloaded")
        page.wait_for_timeout(1000)
        self._dismiss_azul_overlays(page)

    def _open_azul_menu(self, page: Page, menu_name: str) -> bool:
        opened = self._hover_first(
            page,
            [
                f"a:has-text('{menu_name}')",
                f"li:has-text('{menu_name}')",
                f"button:has-text('{menu_name}')",
                f"text={menu_name}",
            ],
            timeout_ms=2300,
        )
        if not opened:
            opened = self._click_first(
                page,
                [
                    f"a:has-text('{menu_name}')",
                    f"li:has-text('{menu_name}')",
                    f"button:has-text('{menu_name}')",
                    f"text={menu_name}",
                ],
                timeout_ms=2300,
            )
        if opened:
            page.wait_for_timeout(650)
        return opened

    def _click_azul_submenu(self, page: Page, submenu_name: str) -> bool:
        clicked = self._click_first(
            page,
            [
                f"a:has-text('{submenu_name}')",
                f"li:has-text('{submenu_name}')",
                f"text={submenu_name}",
            ],
            timeout_ms=2600,
        )
        if clicked:
            page.wait_for_timeout(850)
        return clicked

    def _fill_and_submit_azul_search(self, page: Page, value: str, selectors: list[str]) -> bool:
        has_search = self._fill_first(page, selectors, value)
        if not has_search:
            return False

        submitted = self._press_enter_first(page, selectors)
        if not submitted:
            self._click_first(
                page,
                [
                    "button:has-text('Buscar Segurado')",
                    "button:has-text('Buscar')",
                    "button:has-text('Pesquisar')",
                    "button:has-text('Consultar')",
                    "button:has-text('Filtrar')",
                    "input[type='submit']",
                ],
                timeout_ms=2500,
            )
        page.wait_for_timeout(1700)
        self._dismiss_azul_overlays(page)
        return True

    def _login(self, page: Page) -> None:
        page.goto(self.base_url, wait_until="domcontentloaded")
        page.wait_for_timeout(1200)
        self._dismiss_azul_overlays(page)

        self._click_first(
            page,
            [
                "text=Área restrita",
                "text=Area restrita",
                "a:has-text('Área restrita')",
                "button:has-text('Área restrita')",
            ],
            timeout_ms=1800,
        )
        page.wait_for_timeout(450)

        self._click_first(
            page,
            [
                "text=Corretor",
                "button:has-text('Corretor')",
                "li:has-text('Corretor')",
            ],
            timeout_ms=1200,
        )

        self._fill_first(
            page,
            [
                "input[placeholder*='codigo' i]",
                "input[placeholder*='código' i]",
                "input[name*='corretor' i]",
                "input[id*='corretor' i]",
                "div[role='dialog'] input[type='text']",
                "div[role='dialog'] input:not([type])",
            ],
            self.credentials.username,
        )
        self._fill_first(
            page,
            [
                "input[placeholder*='senha' i]",
                "input[name='password']",
                "input[name*='senha' i]",
                "input[id*='senha' i]",
                "div[role='dialog'] input[type='password']",
            ],
            self.credentials.password,
        )
        self._click_first(
            page,
            [
                "button:has-text('Entrar')",
                "button:has-text('Acessar')",
                "button:has-text('Login')",
                "input[type='submit']",
                "button[type='submit']",
            ],
            timeout_ms=2200,
        )
        page.wait_for_timeout(2300)
        self._dismiss_azul_overlays(page)
        self._open_azul_dashboard_home(page)

    def _fetch_policy(self, page: Page, policy_id: str) -> PortalPolicyData | None:
        self._open_azul_dashboard_home(page)

        performed_search = False

        if self._open_azul_menu(page, "Meus Negócios") or self._open_azul_menu(page, "Meus Negocios"):
            self._click_azul_submenu(page, "Apólice") or self._click_azul_submenu(page, "Apolice")
            performed_search = self._fill_and_submit_azul_search(
                page,
                policy_id,
                [
                    "input[placeholder*='cpf' i]",
                    "input[placeholder*='cnpj' i]",
                    "input[placeholder*='placa' i]",
                    "input[placeholder*='segurado' i]",
                    "input[placeholder*='apolice' i]",
                    "input[placeholder*='apólice' i]",
                    "input[aria-label*='buscar' i]",
                    "input[type='search']",
                ],
            )

        if not performed_search and self._open_azul_menu(page, "Propostas"):
            self._click_azul_submenu(page, "Consultar Cota Prêmio") or self._click_azul_submenu(
                page, "Consultar Cota Premio"
            )
            performed_search = self._fill_and_submit_azul_search(
                page,
                policy_id,
                [
                    "input[placeholder*='proposta' i]",
                    "input[placeholder*='cpf' i]",
                    "input[placeholder*='cnpj' i]",
                    "input[placeholder*='apolice' i]",
                    "input[placeholder*='apólice' i]",
                    "input[type='search']",
                ],
            )

        if not performed_search and self._open_azul_menu(page, "Financeiro"):
            self._click_azul_submenu(page, "Extrato de Comissões") or self._click_azul_submenu(
                page, "Consultar Parcelas"
            )
            performed_search = self._fill_and_submit_azul_search(
                page,
                policy_id,
                [
                    "input[placeholder*='cpf' i]",
                    "input[placeholder*='cnpj' i]",
                    "input[placeholder*='apolice' i]",
                    "input[placeholder*='apólice' i]",
                    "input[placeholder*='placa' i]",
                    "input[type='search']",
                ],
            )

        if not performed_search:
            performed_search = self._fill_and_submit_azul_search(
                page,
                policy_id,
                [
                    "input[placeholder*='cpf' i]",
                    "input[placeholder*='cnpj' i]",
                    "input[placeholder*='placa' i]",
                    "input[placeholder*='segurado' i]",
                    "input[aria-label*='buscar' i]",
                    "input[type='search']",
                ],
            )

        if not performed_search:
            fallback_item = super()._fetch_policy(page, policy_id)
            if fallback_item is not None:
                return fallback_item

        page_text = page.locator("body").inner_text(timeout=self.timeout_seconds * 1000)
        return self._parse_policy_text(policy_id, page_text)

    def check_claim_status(self, *, commitment_id: str, description: str) -> str | None:
        query = description.strip() or commitment_id.strip()
        if query == "":
            return None
        if not web_portal_automation_available():
            return None

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
                        self._open_azul_dashboard_home(page)

                        self._open_azul_menu(page, "Sinistros")
                        self._click_azul_submenu(page, "Acompanhamento de Sinistros")

                        self._fill_and_submit_azul_search(
                            page,
                            query,
                            [
                                "input[placeholder*='sinistro' i]",
                                "input[placeholder*='protocolo' i]",
                                "input[placeholder*='apolice' i]",
                                "input[placeholder*='apólice' i]",
                                "input[placeholder*='cpf' i]",
                                "input[placeholder*='cnpj' i]",
                                "input[placeholder*='placa' i]",
                                "input[type='search']",
                            ],
                        )

                        page_text = page.locator("body").inner_text(timeout=self.timeout_seconds * 1000)
                        return parse_claim_status_from_text(page_text)
                    finally:
                        context.close()
                finally:
                    browser.close()
        except PlaywrightTimeoutError:
            print(f"[{self.insurer_name} Portal] Timeout durante consulta de sinistro.")
            return None
        except Exception as exc:
            print(f"[{self.insurer_name} Portal] Falha ao consultar sinistro: {exc}")
            return None

    def _parse_policy_text(self, policy_id: str, page_text: str) -> PortalPolicyData | None:
        return parse_azul_policy_data_from_text(policy_id=policy_id, text=page_text)


class TokioMarinePortalGateway(BasePortalWebGateway):
    insurer_name = "Tokio Marine"

    def __init__(
        self,
        credentials: TokioPortalCredentials,
        base_url: str = "https://www.tokiomarine.com.br/corretores",
        headless: bool = True,
        timeout_seconds: int = 40,
    ) -> None:
        super().__init__(credentials=credentials, base_url=base_url, headless=headless, timeout_seconds=timeout_seconds)

    def _dismiss_tokio_overlays(self, page: Page) -> None:
        # O portal Tokio costuma abrir modais de campanha/termo e barra de cookies.
        for _ in range(3):
            self._click_first(
                page,
                [
                    "button:has-text('ENTENDI')",
                    "button:has-text('Entendi')",
                    "text=ENTENDI",
                    "button:has-text('FECHAR')",
                    "button:has-text('Fechar')",
                    "text=FECHAR",
                    "button:has-text('ACEITAR')",
                    "button:has-text('Aceitar')",
                    "text=ACEITAR",
                    "button[aria-label*='fechar' i]",
                    "button[aria-label*='close' i]",
                    "text=×",
                    "text=x",
                ],
                timeout_ms=1100,
            )
            self._click_first(
                page,
                [
                    "label:has-text('Li e aceito')",
                    "text=Li e aceito",
                ],
                timeout_ms=900,
            )
            page.wait_for_timeout(180)

    def _open_tokio_access_points(self, page: Page) -> None:
        self._click_first(
            page,
            [
                "text=Acesso Parceiros",
                "text=Area do Corretor",
                "text=Área do Corretor",
                "text=Clique aqui para acesso ao Portal do Corretor",
                "text=Portal do Corretor",
                "text=Corretor",
            ],
            timeout_ms=1800,
        )
        page.wait_for_timeout(450)

    def _login(self, page: Page) -> None:
        page.goto(self.base_url, wait_until="domcontentloaded")
        page.wait_for_timeout(1200)

        self._dismiss_tokio_overlays(page)
        self._open_tokio_access_points(page)
        self._dismiss_tokio_overlays(page)

        self._fill_first(
            page,
            [
                "input[name='username']",
                "input[name='login']",
                "input[name*='cpf' i]",
                "input[id*='cpf' i]",
                "input[id*='usuario' i]",
                "input[type='email']",
                "input[type='text']",
            ],
            self.credentials.username,
        )
        self._fill_first(
            page,
            [
                "input[name='password']",
                "input[id*='senha' i]",
                "input[type='password']",
            ],
            self.credentials.password,
        )
        self._click_first(
            page,
            [
                "button:has-text('Entrar')",
                "button:has-text('Acessar')",
                "button:has-text('Login')",
                "input[type='submit']",
                "button[type='submit']",
            ],
        )
        page.wait_for_timeout(2500)
        self._dismiss_tokio_overlays(page)
        self._open_tokio_access_points(page)
        self._dismiss_tokio_overlays(page)

    def _open_tokio_menu(self, page: Page, menu_name: str) -> bool:
        opened = self._hover_first(
            page,
            [
                f"nav a:has-text('{menu_name}')",
                f"a:has-text('{menu_name}')",
                f"button:has-text('{menu_name}')",
                f"text={menu_name}",
            ],
            timeout_ms=2200,
        )
        if not opened:
            opened = self._click_first(
                page,
                [
                    f"nav a:has-text('{menu_name}')",
                    f"a:has-text('{menu_name}')",
                    f"button:has-text('{menu_name}')",
                    f"text={menu_name}",
                ],
                timeout_ms=2200,
            )
        if opened:
            page.wait_for_timeout(700)
        return opened

    def _fill_and_submit_tokio_search(self, page: Page, policy_id: str, selectors: list[str]) -> bool:
        has_search = self._fill_first(page, selectors, policy_id)
        if not has_search:
            return False

        submitted = self._press_enter_first(page, selectors)
        if not submitted:
            self._click_first(
                page,
                [
                    "button:has-text('Pesquisar')",
                    "button:has-text('Buscar')",
                    "button:has-text('Consultar')",
                    "button:has-text('Filtrar')",
                    "button[aria-label*='pesquisar' i]",
                    "input[type='submit']",
                ],
                timeout_ms=2300,
            )
        page.wait_for_timeout(1800)
        return True

    def _fetch_policy(self, page: Page, policy_id: str) -> PortalPolicyData | None:
        page.goto(self.base_url, wait_until="domcontentloaded")
        page.wait_for_timeout(900)
        self._dismiss_tokio_overlays(page)
        self._open_tokio_access_points(page)
        self._dismiss_tokio_overlays(page)

        # Fluxo orientado pelo mapeamento visual:
        # Consultas -> Financeiro -> Sinistros -> busca global.
        performed_search = False

        if self._open_tokio_menu(page, "Consultas"):
            self._click_first(
                page,
                [
                    "text=Visao Geral do Cliente",
                    "text=Visão Geral do Cliente",
                    "text=Apolice ou Endosso",
                    "text=Apólice ou Endosso",
                    "text=Acompanhar Emissoes",
                    "text=Acompanhar Emissões",
                ],
                timeout_ms=2000,
            )
            page.wait_for_timeout(700)
            performed_search = self._fill_and_submit_tokio_search(
                page,
                policy_id,
                [
                    "input[placeholder*='apolice' i]",
                    "input[placeholder*='apólice' i]",
                    "input[placeholder*='endosso' i]",
                    "input[placeholder*='cpf' i]",
                    "input[name*='apolice' i]",
                    "input[id*='apolice' i]",
                    "input[type='search']",
                ],
            )

        if not performed_search and self._open_tokio_menu(page, "Financeiro"):
            self._click_first(
                page,
                [
                    "text=Extrato Comissao",
                    "text=Extrato Comissão",
                    "text=Acompanhar Emissoes",
                    "text=Acompanhar Emissões",
                    "text=Visao Geral do Cliente",
                    "text=Visão Geral do Cliente",
                ],
                timeout_ms=2000,
            )
            page.wait_for_timeout(700)
            performed_search = self._fill_and_submit_tokio_search(
                page,
                policy_id,
                [
                    "input[placeholder*='apolice' i]",
                    "input[placeholder*='apólice' i]",
                    "input[placeholder*='cpf' i]",
                    "input[type='search']",
                ],
            )

        if not performed_search and self._open_tokio_menu(page, "Sinistros"):
            self._click_first(
                page,
                [
                    "text=Acompanhar Sinistro",
                    "text=Consultar SMS",
                ],
                timeout_ms=1800,
            )
            page.wait_for_timeout(700)
            performed_search = self._fill_and_submit_tokio_search(
                page,
                policy_id,
                [
                    "input[placeholder*='apolice' i]",
                    "input[placeholder*='apólice' i]",
                    "input[placeholder*='sinistro' i]",
                    "input[placeholder*='cpf' i]",
                    "input[type='search']",
                ],
            )

        if not performed_search:
            performed_search = self._fill_and_submit_tokio_search(
                page,
                policy_id,
                [
                    "input[placeholder*='buscar' i]",
                    "input[aria-label*='buscar' i]",
                    "input[placeholder*='cpf' i]",
                    "input[type='search']",
                    "input[placeholder*='apolice' i]",
                    "input[placeholder*='apólice' i]",
                ],
            )

        if not performed_search:
            fallback_item = super()._fetch_policy(page, policy_id)
            if fallback_item is not None:
                return fallback_item

        page_text = page.locator("body").inner_text(timeout=self.timeout_seconds * 1000)
        return self._parse_policy_text(policy_id, page_text)

    def _parse_policy_text(self, policy_id: str, page_text: str) -> PortalPolicyData | None:
        return parse_tokio_policy_data_from_text(policy_id=policy_id, text=page_text)
