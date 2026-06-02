from __future__ import annotations

from datetime import date
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


def _extract_due_date(text: str, today: date) -> date | None:
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

    return None


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
        normalized_id = _ascii_fold(title).lower().strip() or f"task-{index}"
        tasks.append(
            TodoTask(
                id=f"web:{normalized_id}",
                title=title,
                due_date=due,
                completed=False,
                list_name="Principal",
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
        self._task_title_by_id: dict[str, str] = {}

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
                        tasks = _parse_tasks_from_blocks(blocks, today=date.today())
                        self._task_title_by_id = {item.id: item.title for item in tasks}
                        return tasks
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

    def create_task(
        self,
        *,
        title: str,
        due_date: date | None = None,
        notes: str | None = None,
    ) -> str | None:
        username = (self.settings.username or "").strip()
        password = (self.settings.password or "").strip()
        if not username or not password:
            return None
        if not todo_web_automation_available():
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
                        self._login(page, username, password)
                        page.goto("https://to-do.live.com/tasks/", wait_until="domcontentloaded")
                        page.wait_for_timeout(1800)

                        if not self._create_task_in_page(page, title):
                            return None
                        task_id = f"web:{_ascii_fold(title).lower().strip()}"
                        self._task_title_by_id[task_id] = title
                        if due_date is not None or (notes is not None and notes.strip()):
                            self._update_task_in_page(
                                page,
                                current_title=title,
                                new_title=title,
                                due_date=due_date,
                                notes=notes,
                            )
                        return task_id
                    finally:
                        context.close()
                finally:
                    browser.close()
        except PlaywrightTimeoutError:
            print("[Microsoft To Do] Timeout ao criar tarefa (web).")
            return None
        except Exception as exc:
            print(f"[Microsoft To Do] Falha ao criar tarefa (web): {exc}")
            return None

    def update_task(
        self,
        *,
        task_id: str,
        title: str | None = None,
        due_date: date | None = None,
        notes: str | None = None,
    ) -> bool:
        username = (self.settings.username or "").strip()
        password = (self.settings.password or "").strip()
        if not username or not password:
            return False
        if not todo_web_automation_available():
            return False

        current_title = self._task_title_by_id.get(task_id)
        if current_title is None:
            for item in self.fetch_open_tasks():
                self._task_title_by_id[item.id] = item.title
            current_title = self._task_title_by_id.get(task_id)
        if current_title is None:
            return False

        target_title = title if title is not None and title.strip() else current_title

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
                        page.wait_for_timeout(1800)

                        updated = self._update_task_in_page(
                            page,
                            current_title=current_title,
                            new_title=target_title,
                            due_date=due_date,
                            notes=notes,
                        )
                        if updated:
                            self._task_title_by_id[task_id] = target_title
                        return updated
                    finally:
                        context.close()
                finally:
                    browser.close()
        except PlaywrightTimeoutError:
            print(f"[Microsoft To Do] Timeout ao atualizar tarefa {task_id} (web).")
            return False
        except Exception as exc:
            print(f"[Microsoft To Do] Falha ao atualizar tarefa {task_id} (web): {exc}")
            return False

    def complete_task(self, *, task_id: str) -> bool:
        username = (self.settings.username or "").strip()
        password = (self.settings.password or "").strip()
        if not username or not password:
            return False
        if not todo_web_automation_available():
            return False

        title = self._task_title_by_id.get(task_id)
        if title is None:
            for item in self.fetch_open_tasks():
                self._task_title_by_id[item.id] = item.title
            title = self._task_title_by_id.get(task_id)
        if title is None:
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
                        self._login(page, username, password)
                        page.goto("https://to-do.live.com/tasks/", wait_until="domcontentloaded")
                        page.wait_for_timeout(1800)
                        done = self._complete_task_in_page(page, title)
                        if done:
                            self._task_title_by_id.pop(task_id, None)
                        return done
                    finally:
                        context.close()
                finally:
                    browser.close()
        except PlaywrightTimeoutError:
            print(f"[Microsoft To Do] Timeout ao concluir tarefa {task_id} (web).")
            return False
        except Exception as exc:
            print(f"[Microsoft To Do] Falha ao concluir tarefa {task_id} (web): {exc}")
            return False

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

    def _create_task_in_page(self, page: Page, title: str) -> bool:
        selectors = [
            "input[aria-label*='Adicionar uma tarefa' i]",
            "input[placeholder*='Adicionar tarefa' i]",
            "input[placeholder*='Add a task' i]",
            "textarea[aria-label*='Adicionar uma tarefa' i]",
            "textarea[placeholder*='Adicionar tarefa' i]",
            "textarea[placeholder*='Add a task' i]",
        ]
        for selector in selectors:
            locator = page.locator(selector)
            if locator.count() == 0:
                continue
            try:
                locator.first.fill(title, timeout=2000)
                locator.first.press("Enter", timeout=2000)
                page.wait_for_timeout(800)
                return True
            except Exception:
                continue
        return False

    def _complete_task_in_page(self, page: Page, title: str) -> bool:
        row_selectors = ["[role='listitem']", "[data-testid*='task']", "[data-is-focusable='true']"]
        checkbox_selectors = [
            "input[type='checkbox']",
            "button[aria-label*='Concluir' i]",
            "button[aria-label*='Complete' i]",
            "button[aria-label*='Marcar como concluida' i]",
        ]
        for row_selector in row_selectors:
            row = page.locator(row_selector).filter(has_text=title)
            if row.count() == 0:
                continue
            for checkbox_selector in checkbox_selectors:
                checkbox = row.first.locator(checkbox_selector)
                if checkbox.count() == 0:
                    continue
                try:
                    checkbox.first.click(timeout=2000)
                    page.wait_for_timeout(600)
                    return True
                except Exception:
                    continue
        return False

    def _update_task_in_page(
        self,
        page: Page,
        *,
        current_title: str,
        new_title: str,
        due_date: date | None,
        notes: str | None,
    ) -> bool:
        row = page.locator("[role='listitem']").filter(has_text=current_title)
        if row.count() == 0:
            row = page.locator("[data-testid*='task']").filter(has_text=current_title)
        if row.count() == 0:
            return False

        if new_title != current_title:
            if not self._create_task_in_page(page, new_title):
                return False
            return self._complete_task_in_page(page, current_title)

        try:
            row.first.click(timeout=2000)
        except Exception:
            pass

        if due_date is not None:
            due_text = due_date.strftime("%d/%m/%Y")
            due_clicked = self._click_if_visible(
                page,
                selectors=[
                    "text=Adicionar data de vencimento",
                    "text=Due date",
                    "button[aria-label*='vencimento' i]",
                ],
                timeout_ms=1800,
            )
            if due_clicked:
                for selector in (
                    "input[aria-label*='vencimento' i]",
                    "input[placeholder*='dd/mm' i]",
                    "input[aria-label*='due date' i]",
                ):
                    field = page.locator(selector)
                    if field.count() == 0:
                        continue
                    try:
                        field.first.fill(due_text, timeout=1800)
                        field.first.press("Enter", timeout=1000)
                        break
                    except Exception:
                        continue

        if notes is not None and notes.strip():
            for selector in (
                "textarea[aria-label*='Anotacao' i]",
                "textarea[placeholder*='Adicionar anotacao' i]",
                "textarea[placeholder*='Add note' i]",
            ):
                field = page.locator(selector)
                if field.count() == 0:
                    continue
                try:
                    field.first.fill(notes.strip(), timeout=1800)
                    break
                except Exception:
                    continue

        return True
