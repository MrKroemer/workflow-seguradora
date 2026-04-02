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
        # O registro de baixa no Segfy web depende do mapeamento detalhado da tela.
        # Retornamos False para delegar o fallback (API ou fila local).
        _ = commitment_id, description
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
