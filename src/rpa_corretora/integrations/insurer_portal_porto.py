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


def porto_web_automation_available() -> bool:
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

PREMIO_LABELS = (
    "premio total",
    "premio liquido",
    "valor do premio",
    "premio",
)
COMISSAO_LABELS = (
    "comissao",
    "comissao corretor",
    "valor comissao",
    "vl comissao",
)


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


def parse_porto_policy_data_from_text(policy_id: str, text: str) -> PortalPolicyData | None:
    premio = _find_money_near_labels(text, PREMIO_LABELS)
    comissao = _find_money_near_labels(text, COMISSAO_LABELS)
    if premio is None or comissao is None:
        return None

    return PortalPolicyData(
        policy_id=policy_id,
        insurer="Porto Seguro",
        premio_total=premio,
        comissao=comissao,
    )


class _PortalGatewayLike(Protocol):
    def fetch_policy_data(self, policy_ids: list[str]) -> list[PortalPolicyData]:
        ...


class FallbackInsurerPortalGateway:
    def __init__(self, primary: _PortalGatewayLike, fallback: _PortalGatewayLike) -> None:
        self.primary = primary
        self.fallback = fallback

    def fetch_policy_data(self, policy_ids: list[str]) -> list[PortalPolicyData]:
        if not policy_ids:
            return []

        primary_data = self.primary.fetch_policy_data(policy_ids)
        primary_ids = {item.policy_id for item in primary_data}
        missing = [policy_id for policy_id in policy_ids if policy_id not in primary_ids]
        if not missing:
            return primary_data

        fallback_data = self.fallback.fetch_policy_data(missing)
        return [*primary_data, *fallback_data]


@dataclass(frozen=True, slots=True)
class PortoPortalCredentials:
    username: str
    password: str


class PortoSeguroPortalGateway:
    def __init__(
        self,
        credentials: PortoPortalCredentials,
        base_url: str = "https://corretor.portoseguro.com.br",
        headless: bool = True,
        timeout_seconds: int = 35,
    ) -> None:
        self.credentials = credentials
        self.base_url = base_url.rstrip("/")
        self.headless = headless
        self.timeout_seconds = timeout_seconds

    def fetch_policy_data(self, policy_ids: list[str]) -> list[PortalPolicyData]:
        if not policy_ids:
            return []
        if not porto_web_automation_available():
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
                            policy_data = self._fetch_policy(page, policy_id)
                            if policy_data is not None:
                                parsed_items.append(policy_data)
                        return parsed_items
                    finally:
                        context.close()
                finally:
                    browser.close()
        except PlaywrightTimeoutError:
            print("[Porto Portal] Timeout durante automacao web.")
            return []
        except Exception as exc:
            print(f"[Porto Portal] Integracao indisponivel: {exc}")
            return []

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
        return parse_porto_policy_data_from_text(policy_id=policy_id, text=page_text)

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

