from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import re
import sys
from typing import TYPE_CHECKING, Protocol

from rpa_corretora.domain.models import SegfyPolicyData
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

    def import_documents(self) -> int:
        if not self.import_enabled:
            return 0
        if not self.username or not self.password or not self.base_url:
            return 0
        if not segfy_web_automation_available():
            return 0
        scan_started_at = datetime.now(timezone.utc)
        last_execution = self._load_last_execution_utc()
        files = self._collect_import_files(modified_after=last_execution)
        if not files:
            self._save_last_execution_utc(scan_started_at)
            print("[Segfy] Nenhum arquivo novo para importacao.")
            return 0

        imported = 0
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
            print("[Segfy] Timeout durante importacao web de documentos.")
        except Exception as exc:
            print(f"[Segfy] Falha ao importar documentos via web: {exc}")
        finally:
            self._save_last_execution_utc(scan_started_at)
        return imported

    def fetch_policy_data(self) -> list[SegfyPolicyData]:
        if not self.username or not self.password or not self.base_url:
            return []
        if not segfy_web_automation_available():
            return []

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
                            return []

                        parser = SegfyGateway(export_xlsx_path=exported)
                        return parser.fetch_policy_data()
                    finally:
                        context.close()
                finally:
                    browser.close()
        except PlaywrightTimeoutError:
            print("[Segfy] Timeout durante automacao web.")
            return []
        except Exception as exc:
            print(f"[Segfy] Falha na automacao web: {exc}")
            return []

    def register_payment(self, *, commitment_id: str, description: str) -> bool:
        if not self.payment_enabled:
            return False
        if not self.username or not self.password or not self.base_url:
            return False
        if not segfy_web_automation_available():
            return False

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
            print(f"[Segfy] Timeout ao registrar baixa web ({commitment_id}).")
            return False
        except Exception as exc:
            print(f"[Segfy] Falha ao registrar baixa web ({commitment_id}): {exc}")
            return False

    def _launch_browser(self, playwright: Playwright):
        channels = [self.browser_channel, "chrome", "msedge"]
        seen: set[str] = set()
        for channel in channels:
            channel_name = channel.strip().lower()
            if not channel_name or channel_name in seen:
                continue
            seen.add(channel_name)
            try:
                return playwright.chromium.launch(channel=channel_name, headless=self.headless)
            except Exception:
                continue
        return playwright.chromium.launch(headless=self.headless)

    def _login(self, page: Page) -> None:
        page.goto(self.base_url, wait_until="domcontentloaded")
        page.wait_for_timeout(1200)

        self._fill_first(
            page,
            selectors=[
                "input[type='email']",
                "input[name='email']",
                "input[name='login']",
                "input[name='username']",
                "input[id*='email' i]",
                "input[placeholder*='e-mail' i]",
                "input[placeholder*='usuario' i]",
            ],
            value=self.username,
        )

        self._fill_first(
            page,
            selectors=[
                "input[type='password']",
                "input[name='password']",
                "input[name='senha']",
                "input[id*='senha' i]",
                "input[placeholder*='senha' i]",
            ],
            value=self.password,
        )

        self._click_first(
            page,
            selectors=[
                "button[type='submit']",
                "input[type='submit']",
                "button:has-text('Entrar')",
                "button:has-text('Acessar')",
                "button:has-text('Login')",
                "text=Entrar",
                "text=Acessar",
                "text=Login",
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
            if locator.count() == 0:
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
        if file_locator.count() == 0:
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
        for selector in selectors:
            locator = page.locator(selector)
            if locator.count() == 0:
                continue
            try:
                locator.first.fill(value, timeout=2500)
                return True
            except Exception:
                continue
        return False

    def _click_first(self, page: Page, *, selectors: list[str], timeout_ms: int = 3500) -> bool:
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
            if row.count() == 0:
                continue
            for action_selector in action_selectors:
                action = row.first.locator(action_selector)
                if action.count() == 0:
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
            if row.count() == 0:
                continue

            paid_selectors = [
                "select[name*='pago' i]",
                "select[id*='pago' i]",
                "select",
            ]
            for paid_selector in paid_selectors:
                paid_field = row.first.locator(paid_selector)
                if paid_field.count() == 0:
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
