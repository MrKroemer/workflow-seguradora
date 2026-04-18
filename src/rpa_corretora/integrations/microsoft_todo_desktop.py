from __future__ import annotations

from datetime import date
import importlib.util
import re
import sys
import time
from typing import TYPE_CHECKING
import unicodedata

from rpa_corretora.config import MicrosoftTodoSettings
from rpa_corretora.domain.models import TodoTask

if TYPE_CHECKING:
    from pywinauto import Desktop
    from pywinauto.base_wrapper import BaseWrapper


DATE_PATTERN_DMY = re.compile(r"\b(\d{2})/(\d{2})(?:/(\d{4}))?\b")
DATE_PATTERN_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_PATTERN = re.compile(r"(?:\+?55)?\s*\(?(\d{2})\)?\s*(9?\d{4})[- ]?(\d{4})")
ADDRESS_HINTS = ("RUA", "AV", "AVENIDA", "ALAMEDA", "TRAVESSA", "BAIRRO", "CEP", "N ", "Nº")

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

WINDOW_TITLE_PATTERNS = (
    r".*Microsoft To Do.*",
    r".* To Do.*",
    r".*A Fazer.*",
    r".*Tarefas.*",
)

LAUNCH_COMMANDS = (
    r'explorer.exe shell:AppsFolder\Microsoft.Todos_8wekyb3d8bbwe!App',
    r'explorer.exe ms-todo:',
)

LIST_NAV_EXCLUDE_PATTERNS = (
    re.compile(r".*\b(adicionar|nova)\b.*\blista\b.*", re.IGNORECASE),
    re.compile(r".*\b(settings|configuracoes|configurações)\b.*", re.IGNORECASE),
    re.compile(r".*\b(search|pesquisar|busca)\b.*", re.IGNORECASE),
    re.compile(r".*\b(help|ajuda)\b.*", re.IGNORECASE),
    re.compile(r".*\b(account|conta|perfil)\b.*", re.IGNORECASE),
    re.compile(r".*\b(menu)\b.*", re.IGNORECASE),
    re.compile(r".*\b(sort|ordenar|filtro)\b.*", re.IGNORECASE),
)

LIST_NAV_INCLUDE_HINTS = (
    "meu dia",
    "importante",
    "planejad",
    "atribu",
    "tarefas",
    "lista",
    "important",
    "planned",
    "assigned",
    "tasks",
)


def todo_desktop_automation_available() -> bool:
    if not sys.platform.startswith("win"):
        return False
    return importlib.util.find_spec("pywinauto") is not None


def _ascii_fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return normalized.encode("ascii", "ignore").decode("ascii")


def _normalize_text(value: str) -> str:
    return " ".join(value.replace("\t", " ").split())


def _first_semantic_line(text: str) -> str | None:
    for line in text.splitlines():
        candidate = _normalize_text(line)
        if len(candidate) < 2:
            continue
        folded = _ascii_fold(candidate)
        if any(pattern.match(folded) for pattern in NON_TASK_PATTERNS):
            continue
        return candidate
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


def _extract_phone(text: str) -> str | None:
    match = PHONE_PATTERN.search(text)
    if match is None:
        return None
    ddd, first, last = match.groups()
    return f"+55{ddd}{first}{last}"


def _extract_email(text: str) -> str | None:
    match = EMAIL_PATTERN.search(text)
    if match is None:
        return None
    return match.group(0).strip()


def _extract_address(text: str) -> str | None:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines:
        folded = _ascii_fold(line).upper()
        if any(hint in folded for hint in ADDRESS_HINTS):
            return line
    return None


def _parse_tasks_from_blocks(raw_blocks: list[str], *, today: date, list_name: str) -> list[TodoTask]:
    tasks: list[TodoTask] = []
    seen_titles: set[str] = set()
    for index, block in enumerate(raw_blocks, start=1):
        normalized = _normalize_text(block)
        if not normalized:
            continue
        title = _first_semantic_line(block)
        if title is None:
            continue
        if title in seen_titles:
            continue
        seen_titles.add(title)
        due = _extract_due_date(block, today)
        phone = _extract_phone(block)
        email = _extract_email(block)
        address = _extract_address(block)
        slug = _ascii_fold(title).lower().strip() or f"task-{index}"
        list_slug = _ascii_fold(list_name).lower().strip() or "lista"
        task_id = f"desktop:{list_slug}:{index}:{slug}"
        tasks.append(
            TodoTask(
                id=task_id,
                title=title,
                due_date=due,
                completed=False,
                list_name=list_name,
                external_ref=block.strip(),
                contact_phone=phone,
                contact_email=email,
                contact_address=address,
            )
        )
    return tasks


class MicrosoftTodoDesktopGateway:
    def __init__(self, settings: MicrosoftTodoSettings, timeout_seconds: int = 40) -> None:
        self.settings = settings
        self.timeout_seconds = max(10, timeout_seconds)
        self._task_title_by_id: dict[str, str] = {}
        self._task_list_by_id: dict[str, str] = {}

    def fetch_open_tasks(self) -> list[TodoTask]:
        if not todo_desktop_automation_available():
            return []
        try:
            window = self._open_app_window()
            self._clear_search_filter(window)
            tasks: list[TodoTask] = []
            seen_keys: set[tuple[str, str]] = set()
            target_list = (self.settings.list_name or "").strip()
            if target_list:
                # In production we prefer operating a single explicit list to avoid
                # side effects from navigating group/list containers.
                self._select_target_list(window, target_list_name=target_list)
                blocks = self._collect_task_blocks_with_scrolling(window)
                tasks = _parse_tasks_from_blocks(blocks, today=date.today(), list_name=target_list)
                self._enrich_tasks_with_details(window, tasks)
            else:
                lists = self._discover_task_lists(window)
                if lists:
                    for list_name, list_control in lists:
                        try:
                            list_control.click_input()
                            time.sleep(0.3)
                        except Exception:
                            continue
                        blocks = self._collect_task_blocks_with_scrolling(window)
                        parsed = _parse_tasks_from_blocks(blocks, today=date.today(), list_name=list_name)
                        self._enrich_tasks_with_details(window, parsed)
                        for task in parsed:
                            dedupe_key = (
                                _ascii_fold(task.list_name or "").lower().strip(),
                                _ascii_fold(task.title).lower().strip(),
                            )
                            if dedupe_key in seen_keys:
                                continue
                            seen_keys.add(dedupe_key)
                            tasks.append(task)
                else:
                    default_list = "Principal"
                    self._select_target_list(window, target_list_name=default_list)
                    blocks = self._collect_task_blocks_with_scrolling(window)
                    tasks = _parse_tasks_from_blocks(blocks, today=date.today(), list_name=default_list)
                    self._enrich_tasks_with_details(window, tasks)

            self._task_title_by_id = {item.id: item.title for item in tasks}
            self._task_list_by_id = {item.id: (item.list_name or "Principal") for item in tasks}
            return tasks
        except Exception as exc:
            print(f"[Microsoft To Do] Desktop app indisponivel: {exc}")
            return []

    def create_task(
        self,
        *,
        title: str,
        due_date: date | None = None,
        notes: str | None = None,
    ) -> str | None:
        if not todo_desktop_automation_available():
            return None
        normalized_title = _normalize_text(title)
        if not normalized_title:
            return None
        try:
            window = self._open_app_window()
            self._clear_search_filter(window)
            self._select_target_list(window)
            if not self._create_task_in_ui(window, normalized_title):
                return None
            created_id = f"desktop:new:{_ascii_fold(normalized_title).lower().strip()}"
            self._task_title_by_id[created_id] = normalized_title
            self._task_list_by_id[created_id] = (self.settings.list_name or "").strip() or "Principal"
            if due_date is not None or (notes is not None and notes.strip()):
                self._update_task_metadata(window, title=normalized_title, due_date=due_date, notes=notes)
            return created_id
        except Exception as exc:
            print(f"[Microsoft To Do] Falha ao criar tarefa no app: {exc}")
            return None

    def update_task(
        self,
        *,
        task_id: str,
        title: str | None = None,
        due_date: date | None = None,
        notes: str | None = None,
    ) -> bool:
        if not todo_desktop_automation_available():
            return False
        current_title = self._task_title_by_id.get(task_id)
        if current_title is None:
            for item in self.fetch_open_tasks():
                self._task_title_by_id[item.id] = item.title
                self._task_list_by_id[item.id] = item.list_name or "Principal"
            current_title = self._task_title_by_id.get(task_id)
        if current_title is None:
            return False
        current_list = self._task_list_by_id.get(task_id)

        target_title = _normalize_text(title or current_title)
        if not target_title:
            return False

        try:
            window = self._open_app_window()
            self._clear_search_filter(window)
            self._select_target_list(window, target_list_name=current_list)

            # Em UI desktop do To Do, a troca de titulo e mais robusta com "criar novo + concluir antigo".
            if target_title != current_title:
                created_id = self.create_task(title=target_title, due_date=due_date, notes=notes)
                if created_id is None:
                    return False
                if not self.complete_task(task_id=task_id):
                    return False
                self._task_title_by_id[task_id] = target_title
                return True

            updated = self._update_task_metadata(window, title=current_title, due_date=due_date, notes=notes)
            if updated:
                self._task_title_by_id[task_id] = target_title
            return updated
        except Exception as exc:
            print(f"[Microsoft To Do] Falha ao atualizar tarefa {task_id} no app: {exc}")
            return False

    def complete_task(self, *, task_id: str) -> bool:
        if not todo_desktop_automation_available():
            return False
        title = self._task_title_by_id.get(task_id)
        if title is None:
            for item in self.fetch_open_tasks():
                self._task_title_by_id[item.id] = item.title
                self._task_list_by_id[item.id] = item.list_name or "Principal"
            title = self._task_title_by_id.get(task_id)
        if title is None:
            return False
        current_list = self._task_list_by_id.get(task_id)
        try:
            window = self._open_app_window()
            self._clear_search_filter(window)
            self._select_target_list(window, target_list_name=current_list)
            completed = self._complete_task_in_ui(window, title)
            if completed:
                self._task_title_by_id.pop(task_id, None)
                self._task_list_by_id.pop(task_id, None)
            return completed
        except Exception as exc:
            print(f"[Microsoft To Do] Falha ao concluir tarefa {task_id} no app: {exc}")
            return False

    def _open_app_window(self) -> BaseWrapper:
        from pywinauto import Application, Desktop

        desktop = Desktop(backend="uia")
        existing = self._find_todo_window(desktop)
        if existing is not None:
            return existing

        launched = False
        for command in LAUNCH_COMMANDS:
            try:
                Application(backend="uia").start(command)
                launched = True
                break
            except Exception:
                continue
        if not launched:
            raise RuntimeError("Nao foi possivel iniciar o Microsoft To Do pelo shell do Windows.")

        deadline = time.time() + self.timeout_seconds
        while time.time() < deadline:
            opened = self._find_todo_window(desktop)
            if opened is not None:
                return opened
            time.sleep(0.4)
        raise RuntimeError("Janela principal do Microsoft To Do nao encontrada apos inicializacao.")

    def _find_todo_window(self, desktop: Desktop) -> BaseWrapper | None:
        for pattern in WINDOW_TITLE_PATTERNS:
            try:
                candidate = desktop.window(title_re=pattern)
                if candidate.exists(timeout=1):
                    try:
                        candidate.wait("visible ready", timeout=5)
                    except Exception:
                        pass
                    try:
                        candidate.set_focus()
                    except Exception:
                        pass
                    return candidate
            except Exception:
                continue
        return None

    def _select_target_list(self, window: BaseWrapper, target_list_name: str | None = None) -> None:
        target = (target_list_name or self.settings.list_name or "").strip()
        if not target:
            return

        escaped = re.escape(target)
        for control_type in ("ListItem", "TreeItem", "Button", "Text"):
            try:
                candidate = window.child_window(title_re=f".*{escaped}.*", control_type=control_type)
                if candidate.exists(timeout=1):
                    candidate.click_input()
                    return
            except Exception:
                continue

    def _collect_task_blocks(self, window: BaseWrapper) -> list[str]:
        blocks: list[str] = []
        seen: set[str] = set()
        candidates: list[BaseWrapper] = []
        for control_type in ("ListItem", "DataItem"):
            try:
                candidates.extend(window.descendants(control_type=control_type))
            except Exception:
                continue

        for candidate in candidates:
            text = self._build_block_text(candidate)
            if not text:
                continue
            if text in seen:
                continue
            seen.add(text)
            blocks.append(text)
        return blocks

    def _collect_task_blocks_with_scrolling(self, window: BaseWrapper, max_scroll_steps: int = 40) -> list[str]:
        from pywinauto.keyboard import send_keys

        all_blocks: list[str] = []
        seen_blocks: set[str] = set()
        stable_rounds = 0

        try:
            window.set_focus()
        except Exception:
            pass

        for _ in range(max_scroll_steps):
            current_blocks = self._collect_task_blocks(window)
            new_count = 0
            for block in current_blocks:
                if block in seen_blocks:
                    continue
                seen_blocks.add(block)
                all_blocks.append(block)
                new_count += 1

            if new_count == 0:
                stable_rounds += 1
            else:
                stable_rounds = 0

            if stable_rounds >= 3:
                break

            try:
                send_keys("{PGDN}")
            except Exception:
                break
            time.sleep(0.25)

        try:
            send_keys("^{HOME}")
        except Exception:
            pass
        return all_blocks

    def _discover_task_lists(self, window: BaseWrapper) -> list[tuple[str, BaseWrapper]]:
        discovered: list[tuple[str, BaseWrapper]] = []
        seen: set[str] = set()

        try:
            window_rect = window.rectangle()
            max_sidebar_right = window_rect.left + int(window_rect.width() * 0.45)
        except Exception:
            max_sidebar_right = None

        candidates: list[BaseWrapper] = []
        for control_type in ("TreeItem", "ListItem", "Button", "Text"):
            try:
                candidates.extend(window.descendants(control_type=control_type))
            except Exception:
                continue

        for candidate in candidates:
            label = _normalize_text(candidate.window_text() or "")
            if not label:
                continue
            if len(label) > 80:
                continue
            folded = _ascii_fold(label).lower().strip()
            if not folded:
                continue
            if any(pattern.match(folded) for pattern in LIST_NAV_EXCLUDE_PATTERNS):
                continue
            if folded in seen:
                continue

            if max_sidebar_right is not None:
                try:
                    rect = candidate.rectangle()
                    if rect.left >= max_sidebar_right:
                        continue
                    if rect.height() > 70:
                        continue
                except Exception:
                    continue

            if not self._is_probable_list_item(folded):
                continue

            seen.add(folded)
            discovered.append((label, candidate))

        target = (self.settings.list_name or "").strip()
        if target:
            target_folded = _ascii_fold(target).lower().strip()
            prioritized = [item for item in discovered if _ascii_fold(item[0]).lower().strip() == target_folded]
            if prioritized:
                others = [item for item in discovered if _ascii_fold(item[0]).lower().strip() != target_folded]
                discovered = prioritized + others
        return discovered[:30]

    def _is_probable_list_item(self, folded_label: str) -> bool:
        if any(hint in folded_label for hint in LIST_NAV_INCLUDE_HINTS):
            return True
        # Listas personalizadas frequentemente nao contem esses marcadores.
        # Aceitamos nomes curtos/medios como potenciais listas de clientes.
        return 2 <= len(folded_label) <= 40

    def _build_block_text(self, control: BaseWrapper) -> str:
        parts: list[str] = []
        for extracted in self._extract_text_values(control):
            if extracted not in parts:
                parts.append(extracted)
        try:
            for child in control.descendants(control_type="Text"):
                for extracted in self._extract_text_values(child):
                    if extracted not in parts:
                        parts.append(extracted)
        except Exception:
            pass
        return "\n".join(parts[:20]).strip()

    def _enrich_tasks_with_details(self, window: BaseWrapper, tasks: list[TodoTask]) -> None:
        # Best-effort enrichment: opens each task and reads right-side details pane
        # so phone/e-mail/endereco can be extracted even when not visible in row list.
        for task in tasks[:300]:
            row = self._find_task_row(window, task.title)
            if row is None:
                continue
            try:
                row.click_input()
                time.sleep(0.15)
            except Exception:
                continue
            detail_text = self._capture_right_panel_text(window)
            if not detail_text:
                continue
            merged = task.external_ref or ""
            if detail_text not in merged:
                merged = f"{merged}\n{detail_text}".strip()
                task.external_ref = merged

            if not task.contact_phone:
                task.contact_phone = _extract_phone(merged)
            if not task.contact_email:
                task.contact_email = _extract_email(merged)
            if not task.contact_address:
                task.contact_address = _extract_address(merged)

    def _capture_right_panel_text(self, window: BaseWrapper) -> str:
        lines: list[str] = []
        seen: set[str] = set()

        try:
            win_rect = window.rectangle()
            split_x = win_rect.left + int(win_rect.width() * 0.45)
        except Exception:
            split_x = None

        candidates: list[BaseWrapper] = []
        for control_type in ("Text", "Edit", "Document"):
            try:
                candidates.extend(window.descendants(control_type=control_type))
            except Exception:
                continue

        for candidate in candidates:
            if split_x is not None:
                try:
                    rect = candidate.rectangle()
                    if rect.left < split_x:
                        continue
                except Exception:
                    continue

            for value in self._extract_text_values(candidate):
                normalized = _normalize_text(value)
                if len(normalized) < 2:
                    continue
                folded = _ascii_fold(normalized).lower().strip()
                if not folded:
                    continue
                if any(pattern.match(folded) for pattern in NON_TASK_PATTERNS):
                    continue
                if normalized in seen:
                    continue
                seen.add(normalized)
                lines.append(normalized)

        return "\n".join(lines[:80]).strip()

    def _extract_text_values(self, control: BaseWrapper) -> list[str]:
        texts: list[str] = []
        try:
            raw_text = _normalize_text(control.window_text() or "")
            if raw_text:
                texts.append(raw_text)
        except Exception:
            pass
        try:
            raw_name = _normalize_text(getattr(control.element_info, "name", "") or "")
            if raw_name and raw_name not in texts:
                texts.append(raw_name)
        except Exception:
            pass
        return texts

    def _create_task_in_ui(self, window: BaseWrapper, title: str) -> bool:
        from pywinauto.keyboard import send_keys

        for editor in self._find_quick_add_editors(window):
            try:
                editor.click_input()
                try:
                    editor.set_edit_text(title)
                except Exception:
                    editor.type_keys("^a{BACKSPACE}", set_foreground=True)
                    editor.type_keys(title, with_spaces=True, set_foreground=True)
                send_keys("{ENTER}")
                time.sleep(0.4)
                return True
            except Exception:
                continue
        return False

    def _find_quick_add_editors(self, window: BaseWrapper) -> list[BaseWrapper]:
        editors: list[BaseWrapper] = []
        try:
            candidates = list(window.descendants(control_type="Edit"))
        except Exception:
            return editors

        add_markers = (
            "adicionar uma tarefa",
            "adicionar tarefa",
            "nova tarefa",
            "add a task",
            "add task",
            "new task",
        )
        for candidate in candidates:
            text_blob = " ".join(self._extract_text_values(candidate)).lower()
            if any(marker in text_blob for marker in add_markers):
                editors.append(candidate)
        # Nao usar fallback generico de "Edit", pois isso pode escrever em campos
        # laterais (ex.: nova lista/grupo) e gerar artefatos indesejados.
        return editors

    def _complete_task_in_ui(self, window: BaseWrapper, title: str) -> bool:
        from pywinauto.keyboard import send_keys

        row = self._find_task_row(window, title)
        if row is None:
            return False

        try:
            for checkbox in row.descendants(control_type="CheckBox"):
                checkbox.click_input()
                return True
        except Exception:
            pass

        try:
            row.click_input()
            send_keys("{SPACE}")
            time.sleep(0.25)
            return True
        except Exception:
            return False

    def _update_task_metadata(
        self,
        window: BaseWrapper,
        *,
        title: str,
        due_date: date | None = None,
        notes: str | None = None,
    ) -> bool:
        row = self._find_task_row(window, title)
        if row is None:
            return False
        try:
            row.click_input()
        except Exception:
            pass

        due_ok = True
        notes_ok = True
        if due_date is not None:
            due_ok = self._try_set_due_date(window, due_date)
        if notes is not None and notes.strip():
            notes_ok = self._try_set_notes(window, notes.strip())
        return due_ok and notes_ok

    def _try_set_due_date(self, window: BaseWrapper, due_date: date) -> bool:
        from pywinauto.keyboard import send_keys

        due_text = due_date.strftime("%d/%m/%Y")
        for control_type in ("Button", "Hyperlink", "Text"):
            try:
                date_button = window.child_window(
                    title_re=r".*(Adicionar data de vencimento|Data de vencimento|Due date|Prazo).*",
                    control_type=control_type,
                )
                if date_button.exists(timeout=1):
                    date_button.click_input()
                    break
            except Exception:
                continue

        for editor in self._candidate_due_date_editors(window):
            try:
                editor.click_input()
                try:
                    editor.set_edit_text(due_text)
                except Exception:
                    editor.type_keys("^a{BACKSPACE}", set_foreground=True)
                    editor.type_keys(due_text, with_spaces=True, set_foreground=True)
                send_keys("{ENTER}")
                return True
            except Exception:
                continue
        return False

    def _try_set_notes(self, window: BaseWrapper, notes: str) -> bool:
        for editor in self._candidate_note_editors(window):
            try:
                editor.click_input()
                try:
                    editor.set_edit_text(notes)
                except Exception:
                    editor.type_keys("^a{BACKSPACE}", set_foreground=True)
                    editor.type_keys(notes, with_spaces=True, set_foreground=True)
                return True
            except Exception:
                continue
        return False

    def _candidate_note_editors(self, window: BaseWrapper) -> list[BaseWrapper]:
        matches: list[BaseWrapper] = []
        try:
            candidates = list(window.descendants(control_type="Edit"))
        except Exception:
            return matches

        markers = ("anot", "nota", "note")
        for candidate in candidates:
            if not self._is_right_panel_control(window, candidate):
                continue
            text_blob = " ".join(self._extract_text_values(candidate)).lower()
            if self._looks_like_search_or_quick_add(text_blob):
                continue
            if any(marker in text_blob for marker in markers):
                matches.append(candidate)
        return matches

    def _candidate_due_date_editors(self, window: BaseWrapper) -> list[BaseWrapper]:
        matches: list[BaseWrapper] = []
        try:
            candidates = list(window.descendants(control_type="Edit"))
        except Exception:
            return matches

        markers = ("vencimento", "due", "prazo", "data")
        for candidate in candidates:
            if not self._is_right_panel_control(window, candidate):
                continue
            text_blob = " ".join(self._extract_text_values(candidate)).lower()
            if self._looks_like_search_or_quick_add(text_blob):
                continue
            if any(marker in text_blob for marker in markers):
                matches.append(candidate)

        if matches:
            return matches

        # Last-resort: right panel editors only, still excluding search/quick-add.
        for candidate in candidates:
            if not self._is_right_panel_control(window, candidate):
                continue
            text_blob = " ".join(self._extract_text_values(candidate)).lower()
            if self._looks_like_search_or_quick_add(text_blob):
                continue
            matches.append(candidate)
        return matches[:4]

    def _is_right_panel_control(self, window: BaseWrapper, control: BaseWrapper) -> bool:
        try:
            win_rect = window.rectangle()
            split_x = win_rect.left + int(win_rect.width() * 0.45)
            rect = control.rectangle()
            return rect.left >= split_x
        except Exception:
            return True

    @staticmethod
    def _looks_like_search_or_quick_add(text_blob: str) -> bool:
        normalized = text_blob.lower()
        search_markers = ("pesquisar", "search", "busca")
        add_markers = ("adicionar uma tarefa", "adicionar tarefa", "add a task", "nova tarefa", "new task")
        return any(marker in normalized for marker in search_markers + add_markers)

    def _clear_search_filter(self, window: BaseWrapper) -> None:
        send_keys = None
        try:
            from pywinauto.keyboard import send_keys as _send_keys
            send_keys = _send_keys
        except Exception:
            send_keys = None

        try:
            window.set_focus()
        except Exception:
            pass

        # First strategy: clear any visible search editor directly.
        try:
            for editor in self._find_search_editors(window):
                try:
                    editor.click_input()
                    try:
                        editor.set_edit_text("")
                    except Exception:
                        if send_keys is not None:
                            send_keys("^a{BACKSPACE}")
                    if send_keys is not None:
                        send_keys("{ESC}")
                    time.sleep(0.05)
                except Exception:
                    continue
        except Exception:
            pass

        try:
            if send_keys is None:
                return
            # Fallback strategy: explicit clear via Find shortcut.
            send_keys("^f")
            time.sleep(0.1)
            send_keys("^a{BACKSPACE}{ESC}")
            time.sleep(0.1)
        except Exception:
            pass

    def _find_search_editors(self, window: BaseWrapper) -> list[BaseWrapper]:
        matches: list[BaseWrapper] = []
        try:
            candidates = list(window.descendants(control_type="Edit"))
        except Exception:
            return matches

        search_markers = ("pesquisar", "search", "busca", "procurar")
        for candidate in candidates:
            text_blob = " ".join(self._extract_text_values(candidate)).lower()
            if self._looks_like_search_or_quick_add(text_blob):
                if any(marker in text_blob for marker in search_markers):
                    matches.append(candidate)
        return matches

    def _find_task_row(self, window: BaseWrapper, title: str) -> BaseWrapper | None:
        target = _ascii_fold(title).lower().strip()
        if not target:
            return None

        candidates: list[BaseWrapper] = []
        for control_type in ("ListItem", "DataItem"):
            try:
                candidates.extend(window.descendants(control_type=control_type))
            except Exception:
                continue

        for row in candidates:
            text = _ascii_fold(self._build_block_text(row)).lower()
            if target and target in text:
                return row
        return None
