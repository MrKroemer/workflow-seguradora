from __future__ import annotations

from datetime import date, timedelta
import importlib.util
import re
import sys
from typing import TYPE_CHECKING
import unicodedata

from rpa_corretora.config import MicrosoftTodoSettings
from rpa_corretora.domain.models import TodoTask

if TYPE_CHECKING:
    from playwright.sync_api import Page, Playwright


SIGN_IN_PATTERNS = (
    re.compile(r"^entrar$", re.IGNORECASE),
    re.compile(r"^sign in$", re.IGNORECASE),
    re.compile(r"^iniciar sessao$", re.IGNORECASE),
)

NON_TASK_PATTERNS = (
    re.compile(r"^adicionar tarefa$", re.IGNORECASE),
    re.compile(r"^add a task$", re.IGNORECASE),
    re.compile(r"^hoje$", re.IGNORECASE),
    re.compile(r"^today$", re.IGNORECASE),
    re.compile(r"^importante$", re.IGNORECASE),
    re.compile(r"^important$", re.IGNORECASE),
    re.compile(r"^planejado$", re.IGNORECASE),
    re.compile(r"^planned$", re.IGNORECASE),
    re.compile(r"^concluido$", re.IGNORECASE),
    re.compile(r"^completed$", re.IGNORECASE),
)

DATE_PATTERN_DMY = re.compile(r"\b(\d{2})/(\d{2})(?:/(\d{4}))?\b")
DATE_PATTERN_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")


def todo_web_automation_available() -> bool:
    if not sys.platform.startswith("win"):
        return False
    return importlib.util.find_spec("playwright.sync_api") is not None


def _ascii_fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return normalized.encode("ascii", "ignore").decode("ascii")


def _first_semantic_line(text: str) -> str | None:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines:
        if len(line) < 2:
            continue
        folded = _ascii_fold(line)
        if any(pattern.match(folded) for pattern in NON_TASK_PATTERNS):
            continue
        return line
    return None


def _extract_due_date(text: str, today: date) -> date:
    match_iso = DATE_PATTERN_ISO.search(text)
    if match_iso is not None:
        year = int(match_iso.group(1))
        month = int(match_iso.group(2))
        day = int(match_iso.group(3))
        try:
            return date(year, month, day)
        except ValueError:
            pass

    match_dmy = DATE_PATTERN_DMY.search(text)
    if match_dmy is not None:
        day = int(match_dmy.group(1))
        month = int(match_dmy.group(2))
        year = int(match_dmy.group(3)) if match_dmy.group(3) else today.year
        try:
            return date(year, month, day)
        except ValueError:
            pass

    # Sem data explicita -> evita alerta imediato.
    return today + timedelta(days=3650)


def _normalize_text(value: str) -> str:
    return " ".join(value.replace("\t", " ").split())


def _collect_candidate_blocks(page: Page) -> list[str]:
    selectors = [
        '[role="listitem"]',
        '[data-testid*="task"]',
        "[data-is-focusable='true']",
    ]
    script = """
(selectors) => {
  const out = [];
  for (const selector of selectors) {
    const nodes = Array.from(document.querySelectorAll(selector));
    for (const node of nodes) {
      const text = (node.innerText || '').replace(/\\s+/g, ' ').trim();
      if (text.length > 0) out.push(text);
    }
  }
  return out.slice(0, 500);
}
"""
    raw_blocks = page.evaluate(script, selectors)
    if not isinstance(raw_blocks, list):
        return []
    return [str(item) for item in raw_blocks if str(item).strip()]


def _parse_tasks_from_blocks(raw_blocks: list[str], today: date) -> list[TodoTask]:
    tasks: list[TodoTask] = []
    seen_titles: set[str] = set()

    for index, block in enumerate(raw_blocks, start=1):
        normalized = _normalize_text(block)
        if not normalized:
            continue
        title = _first_semantic_line(block)
        if title is None:
            continue
        title = _normalize_text(title)
        if title in seen_titles:
            continue
        if any(pattern.match(_ascii_fold(title)) for pattern in SIGN_IN_PATTERNS):
            continue

        due = _extract_due_date(block, today)
        seen_titles.add(title)
        tasks.append(
            TodoTask(
                id=f"web-{index}",
                title=title,
                due_date=due,
                completed=False,
            )
        )

    return tasks


class MicrosoftTodoWebGateway:
    def __init__(
        self,
        settings: MicrosoftTodoSettings,
        timeout_seconds: int = 35,
        headless: bool = True,
    ) -> None:
        self.settings = settings
        self.timeout_seconds = timeout_seconds
        self.headless = headless

    def fetch_open_tasks(self) -> list[TodoTask]:
        username = (self.settings.username or "").strip()
        password = (self.settings.password or "").strip()
        if not username or not password:
            return []
        if not todo_web_automation_available():
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
                        self._login(page, username, password)
                        page.goto("https://to-do.live.com/tasks/", wait_until="domcontentloaded")
                        page.wait_for_timeout(3000)

                        blocks = _collect_candidate_blocks(page)
                        return _parse_tasks_from_blocks(blocks, today=date.today())
                    finally:
                        context.close()
                finally:
                    browser.close()
        except PlaywrightTimeoutError:
            print("[Microsoft To Do] Web automation expirou durante leitura das tarefas.")
            return []
        except Exception as exc:
            print(f"[Microsoft To Do] Web automation indisponivel: {exc}")
            return []

    def _launch_browser(self, playwright: Playwright):
        # No Windows, preferimos o Edge instalado na maquina.
        try:
            return playwright.chromium.launch(channel="msedge", headless=self.headless)
        except Exception:
            return playwright.chromium.launch(headless=self.headless)

    def _login(self, page: Page, username: str, password: str) -> None:
        page.goto("https://to-do.live.com/tasks/", wait_until="domcontentloaded")
        page.wait_for_timeout(1200)

        self._click_if_visible(
            page,
            [
                "text=Entrar",
                "text=Sign in",
                "a[data-bi-id*='sign-in']",
            ],
        )

        login_field = page.locator("input[name='loginfmt']")
        if login_field.count() > 0:
            login_field.first.fill(username)
            self._click_if_visible(page, ["input[type='submit']", "button[type='submit']", "#idSIButton9"])

        password_field = page.locator("input[name='passwd']")
        if password_field.count() > 0:
            password_field.first.fill(password)
            self._click_if_visible(page, ["input[type='submit']", "button[type='submit']", "#idSIButton9"])

        # Prompt "Permanecer conectado?"
        self._click_if_visible(page, ["#idSIButton9", "text=Sim", "text=Yes"], timeout_ms=3000)

    def _click_if_visible(self, page: Page, selectors: list[str], timeout_ms: int = 5000) -> bool:
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
