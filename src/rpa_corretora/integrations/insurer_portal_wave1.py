from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import importlib.util
import re
import sys
from typing import TYPE_CHECKING, Protocol
import unicodedata

from rpa_corretora.domain.models import PortalPolicyData

if TYPE_CHECKING:
    from playwright.sync_api import Page, Playwright


def web_portal_automation_available() -> bool:
    if not sys.platform.startswith("win"):
        return False
    return importlib.util.find_spec("playwright.sync_api") is not None


def _ascii_fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return normalized.encode("ascii", "ignore").decode("ascii")


def _to_decimal_brl(raw: str) -> Decimal | None:
    text = raw.strip().replace("R$", "").replace(" ", "")
    text = text.replace(".", "").replace(",", ".")
    if not text:
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


MONEY_PATTERN = re.compile(r"R\$\s*([0-9\.\,]+)|([0-9]{1,3}(?:\.[0-9]{3})*,[0-9]{2})")
DEFAULT_PREMIO_LABELS = ("premio total", "premio liquido", "valor do premio", "premio")
DEFAULT_COMISSAO_LABELS = ("comissao", "comissao corretor", "valor comissao", "vl comissao")


def _find_money_near_labels(text: str, labels: tuple[str, ...]) -> Decimal | None:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    folded_lines = [_ascii_fold(line).lower() for line in lines]

    for index, folded in enumerate(folded_lines):
        if not any(label in folded for label in labels):
            continue

        candidates = [lines[index]]
        if index + 1 < len(lines):
            candidates.append(lines[index + 1])

        for candidate in candidates:
            match = MONEY_PATTERN.search(candidate)
            if match is None:
                continue
            raw_value = match.group(1) or match.group(2) or ""
            parsed = _to_decimal_brl(raw_value)
            if parsed is not None:
                return parsed

    return None


def _extract_status_near_labels(text: str, labels: tuple[str, ...]) -> str:
    """Extrai status textual proximo a labels no texto da pagina."""
    folded = _ascii_fold(text).lower()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    folded_lines = [_ascii_fold(line).lower() for line in lines]
    for index, fl in enumerate(folded_lines):
        if not any(label in fl for label in labels):
            continue
        # Tenta extrair status da mesma linha ou proxima.
        for candidate_line in lines[index:index+2]:
            candidate_upper = _ascii_fold(candidate_line).upper()
            for status in ("EM ANDAMENTO", "EM ANALISE", "PENDENTE", "FINALIZADO", "ENCERRADO", "CONCLUIDO", "ABERTO", "EMITIDO", "CANCELADO", "RENOVADO", "NAO RENOVADO"):
                if status in candidate_upper:
                    return status
    return ""


def parse_policy_data_from_text_generic(
    *,
    policy_id: str,
    insurer: str,
    text: str,
    premio_labels: tuple[str, ...] = DEFAULT_PREMIO_LABELS,
    comissao_labels: tuple[str, ...] = DEFAULT_COMISSAO_LABELS,
) -> PortalPolicyData | None:
    premio = _find_money_near_labels(text, premio_labels)
    comissao = _find_money_near_labels(text, comissao_labels)
    if premio is None or comissao is None:
        return None

    sinistro_status = _extract_status_near_labels(
        text, ("sinistro", "acidente", "indenizacao", "regulacao")
    )
    endosso_status = _extract_status_near_labels(
        text, ("endosso", "alteracao", "inclusao", "exclusao")
    )
    renewal_status = _extract_status_near_labels(
        text, ("renovacao", "renovar", "vigencia", "renov")
    )

    return PortalPolicyData(
        policy_id=policy_id,
        insurer=insurer,
        premio_total=premio,
        comissao=comissao,
        sinistro_status=sinistro_status,
        endosso_status=endosso_status,
        renewal_status=renewal_status,
    )


def parse_yelum_policy_data_from_text(policy_id: str, text: str) -> PortalPolicyData | None:
    return parse_policy_data_from_text_generic(
        policy_id=policy_id,
        insurer="Yelum",
        text=text,
        premio_labels=DEFAULT_PREMIO_LABELS,
        comissao_labels=DEFAULT_COMISSAO_LABELS,
    )


def parse_mapfre_policy_data_from_text(policy_id: str, text: str) -> PortalPolicyData | None:
    return parse_policy_data_from_text_generic(
        policy_id=policy_id,
        insurer="Mapfre",
        text=text,
        premio_labels=(
            *DEFAULT_PREMIO_LABELS,
            "premio total da apolice",
        ),
        comissao_labels=(
            *DEFAULT_COMISSAO_LABELS,
            "comissao total",
        ),
    )


def parse_claim_status_from_text(page_text: str) -> str | None:
    folded = _ascii_fold(page_text).lower()
    if "sinistro finalizado" in folded or "sinistro encerrado" in folded:
        return "FINALIZADO"
    if "sinistro em andamento" in folded or "em analise" in folded:
        return "EM_ANDAMENTO"
    if "pendente" in folded:
        return "PENDENTE"
    return None


class _PortalGatewayLike(Protocol):
    def fetch_policy_data(self, policy_ids: list[str]) -> list[PortalPolicyData]:
        ...

    def check_claim_status(self, *, commitment_id: str, description: str) -> str | None:
        ...


class CascadingInsurerPortalGateway:
    def __init__(self, gateways: list[_PortalGatewayLike], fallback: _PortalGatewayLike) -> None:
        self.gateways = gateways
        self.fallback = fallback

    def fetch_policy_data(self, policy_ids: list[str]) -> list[PortalPolicyData]:
        if not policy_ids:
            return []

        pending = list(policy_ids)
        collected: list[PortalPolicyData] = []
        for gateway in self.gateways:
            if not pending:
                break
            data = gateway.fetch_policy_data(pending)
            if not data:
                continue
            collected.extend(data)
            found_ids = {item.policy_id for item in data}
            pending = [policy_id for policy_id in pending if policy_id not in found_ids]

        if pending:
            collected.extend(self.fallback.fetch_policy_data(pending))
        return collected

    def check_claim_status(self, *, commitment_id: str, description: str) -> str | None:
        for gateway in self.gateways:
            status = gateway.check_claim_status(commitment_id=commitment_id, description=description)
            if status:
                return status
        return self.fallback.check_claim_status(commitment_id=commitment_id, description=description)


class MultiInsurerPortalGateway:
    """Aggregator sem fallback sintético.

    Usa somente os gateways web configurados. Se um policy_id não for encontrado
    por nenhum portal, ele simplesmente não aparece no retorno.
    """

    def __init__(self, gateways: list[_PortalGatewayLike]) -> None:
        self.gateways = gateways

    def fetch_policy_data(self, policy_ids: list[str]) -> list[PortalPolicyData]:
        if not policy_ids:
            return []

        pending = list(policy_ids)
        collected: list[PortalPolicyData] = []
        for gateway in self.gateways:
            if not pending:
                break
            data = gateway.fetch_policy_data(pending)
            if not data:
                continue
            collected.extend(data)
            found_ids = {item.policy_id for item in data}
            pending = [policy_id for policy_id in pending if policy_id not in found_ids]
        return collected

    def check_claim_status(self, *, commitment_id: str, description: str) -> str | None:
        for gateway in self.gateways:
            status = gateway.check_claim_status(commitment_id=commitment_id, description=description)
            if status:
                return status
        return None


@dataclass(frozen=True, slots=True)
class YelumPortalCredentials:
    username: str
    password: str


@dataclass(frozen=True, slots=True)
class MapfrePortalCredentials:
    username: str
    password: str


class BasePortalWebGateway:
    insurer_name = "Seguradora"

    def __init__(self, credentials, base_url: str, headless: bool = True, timeout_seconds: int = 35) -> None:
        self.credentials = credentials
        self.base_url = base_url.rstrip("/")
        self.headless = headless
        self.timeout_seconds = timeout_seconds

    def fetch_policy_data(self, policy_ids: list[str]) -> list[PortalPolicyData]:
        if not policy_ids:
            return []
        if not web_portal_automation_available():
            return []

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

                        parsed_items: list[PortalPolicyData] = []
                        for policy_id in policy_ids:
                            item = self._fetch_policy(page, policy_id)
                            if item is not None:
                                parsed_items.append(item)
                        return parsed_items
                    finally:
                        context.close()
                finally:
                    browser.close()
        except PlaywrightTimeoutError:
            print(f"[{self.insurer_name} Portal] Timeout durante automacao web.")
            return []
        except Exception as exc:
            print(f"[{self.insurer_name} Portal] Integracao indisponivel: {exc}")
            return []

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
                        page.wait_for_timeout(600)
                        self._fill_first(
                            page,
                            [
                                "input[placeholder*='sinistro' i]",
                                "input[placeholder*='protocolo' i]",
                                "input[placeholder*='apolice' i]",
                                "input[placeholder*='apólice' i]",
                                "input[type='search']",
                            ],
                            query,
                        )
                        self._click_first(
                            page,
                            [
                                "button:has-text('Pesquisar')",
                                "button:has-text('Buscar')",
                                "button:has-text('Consultar')",
                                "input[type='submit']",
                            ],
                            timeout_ms=1500,
                        )
                        page.wait_for_timeout(1500)
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

    def _launch_browser(self, playwright: Playwright):
        try:
            return playwright.chromium.launch(channel="msedge", headless=self.headless)
        except Exception:
            return playwright.chromium.launch(headless=self.headless)

    def _login(self, page: Page) -> None:
        page.goto(self.base_url, wait_until="domcontentloaded")
        page.wait_for_timeout(1200)

        self._click_first(
            page,
            [
                "text=Entrar",
                "text=Login",
                "a:has-text('Entrar')",
                "button:has-text('Entrar')",
            ],
        )
        self._fill_first(
            page,
            [
                "input[name='username']",
                "input[name='login']",
                "input[type='email']",
                "input[id*='usuario']",
                "input[id*='login']",
            ],
            self.credentials.username,
        )
        self._fill_first(
            page,
            [
                "input[name='password']",
                "input[type='password']",
                "input[id*='senha']",
            ],
            self.credentials.password,
        )
        self._click_first(
            page,
            [
                "button:has-text('Entrar')",
                "button:has-text('Acessar')",
                "input[type='submit']",
                "button[type='submit']",
            ],
        )
        page.wait_for_timeout(2500)

    def _fetch_policy(self, page: Page, policy_id: str) -> PortalPolicyData | None:
        page.goto(self.base_url, wait_until="domcontentloaded")
        page.wait_for_timeout(800)
        has_search = self._fill_first(
            page,
            [
                "input[placeholder*='apolice' i]",
                "input[placeholder*='apólice' i]",
                "input[name*='apolice' i]",
                "input[id*='apolice' i]",
                "input[type='search']",
            ],
            policy_id,
        )
        if has_search:
            self._click_first(
                page,
                [
                    "button:has-text('Buscar')",
                    "button:has-text('Pesquisar')",
                    "button:has-text('Consultar')",
                    "input[type='submit']",
                ],
            )
            page.wait_for_timeout(1800)

        page_text = page.locator("body").inner_text(timeout=self.timeout_seconds * 1000)
        return self._parse_policy_text(policy_id, page_text)

    def _parse_policy_text(self, policy_id: str, page_text: str) -> PortalPolicyData | None:
        raise NotImplementedError

    def _fill_first(self, page: Page, selectors: list[str], value: str) -> bool:
        for selector in selectors:
            locator = page.locator(selector)
            if locator.count() == 0:
                continue
            try:
                locator.first.fill(value)
                return True
            except Exception:
                continue
        return False

    def _press_enter_first(self, page: Page, selectors: list[str]) -> bool:
        for selector in selectors:
            locator = page.locator(selector)
            if locator.count() == 0:
                continue
            try:
                locator.first.press("Enter")
                return True
            except Exception:
                continue
        return False

    def _hover_first(self, page: Page, selectors: list[str], timeout_ms: int = 3000) -> bool:
        for selector in selectors:
            locator = page.locator(selector)
            if locator.count() == 0:
                continue
            try:
                locator.first.hover(timeout=timeout_ms)
                return True
            except Exception:
                continue
        return False

    def _click_first(self, page: Page, selectors: list[str], timeout_ms: int = 5000) -> bool:
        for selector in selectors:
            locator = page.locator(selector)
            if locator.count() == 0:
                continue
            try:
                locator.first.click(timeout=timeout_ms)
                return True
            except Exception:
                continue
        return False


class YelumPortalGateway(BasePortalWebGateway):
    insurer_name = "Yelum"

    def __init__(
        self,
        credentials: YelumPortalCredentials,
        base_url: str = "https://novomeuespacocorretor.yelumseguros.com.br/dashboard",
        headless: bool = True,
        timeout_seconds: int = 35,
    ) -> None:
        super().__init__(credentials=credentials, base_url=base_url, headless=headless, timeout_seconds=timeout_seconds)

    def _open_yelum_consultas_apolice(self, page: Page) -> bool:
        opened_menu = self._hover_first(
            page,
            [
                "a:has-text('Consultas')",
                "button:has-text('Consultas')",
                "text=Consultas",
            ],
        )
        if not opened_menu:
            opened_menu = self._click_first(
                page,
                [
                    "a:has-text('Consultas')",
                    "button:has-text('Consultas')",
                    "text=Consultas",
                ],
                timeout_ms=2500,
            )

        page.wait_for_timeout(250)
        opened_apolice = self._click_first(
            page,
            [
                "a:has-text('Apolice')",
                "a:has-text('Apólice')",
                "li:has-text('Apolice')",
                "li:has-text('Apólice')",
                "text=Apolice",
                "text=Apólice",
            ],
            timeout_ms=2500,
        )
        if opened_apolice:
            page.wait_for_timeout(1000)
            return True

        # Fallback adicional: atalho lateral da pagina inicial.
        opened_shortcut = self._click_first(
            page,
            [
                "text=Consultar Apolice",
                "text=Consultar Apólice",
            ],
            timeout_ms=1800,
        )
        if opened_shortcut:
            page.wait_for_timeout(1000)
            return True

        return False

    def _fetch_policy(self, page: Page, policy_id: str) -> PortalPolicyData | None:
        page.goto(self.base_url, wait_until="domcontentloaded")
        page.wait_for_timeout(900)
        self._open_yelum_consultas_apolice(page)

        search_selectors = [
            "input[placeholder*='n. da apolice' i]",
            "input[placeholder*='apolice' i]",
            "input[placeholder*='apólice' i]",
            "input[name*='apolice' i]",
            "input[id*='apolice' i]",
            "input[type='search']",
        ]
        has_search = self._fill_first(page, search_selectors, policy_id)
        if has_search:
            submitted = self._press_enter_first(page, search_selectors)
            if not submitted:
                self._click_first(
                    page,
                    [
                        "button[aria-label*='pesquisar' i]",
                        "button:has-text('Pesquisar')",
                        "button:has-text('Buscar')",
                        "button:has-text('Consultar')",
                        "input[type='submit']",
                    ],
                    timeout_ms=2000,
                )
            page.wait_for_timeout(2200)

        page_text = page.locator("body").inner_text(timeout=self.timeout_seconds * 1000)
        return self._parse_policy_text(policy_id, page_text)

    def _parse_policy_text(self, policy_id: str, page_text: str) -> PortalPolicyData | None:
        return parse_yelum_policy_data_from_text(policy_id=policy_id, text=page_text)


class MapfrePortalGateway(BasePortalWebGateway):
    insurer_name = "Mapfre"

    def __init__(
        self,
        credentials: MapfrePortalCredentials,
        base_url: str = "https://negocios.mapfre.com.br/tela-principal",
        headless: bool = True,
        timeout_seconds: int = 35,
    ) -> None:
        super().__init__(credentials=credentials, base_url=base_url, headless=headless, timeout_seconds=timeout_seconds)

    def _open_mapfre_menu(self, page: Page, menu_name: str) -> bool:
        opened = self._click_first(
            page,
            [
                f"nav a:has-text('{menu_name}')",
                f"a:has-text('{menu_name}')",
                f"button:has-text('{menu_name}')",
                f"text={menu_name}",
            ],
            timeout_ms=2500,
        )
        if opened:
            page.wait_for_timeout(900)
        return opened

    def _fill_and_submit_mapfre_apolice(self, page: Page, policy_id: str) -> bool:
        search_selectors = [
            "input[placeholder*='numero da apolice' i]",
            "input[placeholder*='n\u00famero da ap\u00f3lice' i]",
            "input[name*='apolice' i]",
            "input[id*='apolice' i]",
            "input[aria-label*='apolice' i]",
            "input[aria-label*='ap\u00f3lice' i]",
            "input[type='search']",
        ]
        has_search = self._fill_first(page, search_selectors, policy_id)
        if not has_search:
            return False

        submitted = self._press_enter_first(page, search_selectors)
        if not submitted:
            self._click_first(
                page,
                [
                    "button:has-text('Pesquisar')",
                    "button:has-text('Filtrar')",
                    "button:has-text('Buscar')",
                    "input[type='submit']",
                ],
                timeout_ms=2300,
            )
        page.wait_for_timeout(1800)
        return True

    def _fetch_policy(self, page: Page, policy_id: str) -> PortalPolicyData | None:
        page.goto(self.base_url, wait_until="domcontentloaded")
        page.wait_for_timeout(900)

        # Fluxo orientado pelo mapeamento visual:
        # Carteira -> Renovacoes -> Sinistros, com fallback generico.
        performed_search = False

        if self._open_mapfre_menu(page, "Carteira"):
            performed_search = self._fill_and_submit_mapfre_apolice(page, policy_id)

        if not performed_search and self._open_mapfre_menu(page, "Renovacoes"):
            performed_search = self._fill_and_submit_mapfre_apolice(page, policy_id)

        if not performed_search and self._open_mapfre_menu(page, "Sinistros"):
            performed_search = self._fill_and_submit_mapfre_apolice(page, policy_id)

        if not performed_search:
            # Fallback generico para preservar nao regressao.
            fallback_item = super()._fetch_policy(page, policy_id)
            if fallback_item is not None:
                return fallback_item

        page_text = page.locator("body").inner_text(timeout=self.timeout_seconds * 1000)
        return self._parse_policy_text(policy_id, page_text)

    def _parse_policy_text(self, policy_id: str, page_text: str) -> PortalPolicyData | None:
        return parse_mapfre_policy_data_from_text(policy_id=policy_id, text=page_text)
