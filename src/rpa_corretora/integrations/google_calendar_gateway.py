from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
import json
import re
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen

from rpa_corretora.domain.models import CalendarCommitment, TodoTask


_DEFAULT_COLOR_MAP = {
    "4": "VERMELHO",
    "5": "AMARELO",
    "6": "TANGERINA",
    "8": "CINZA",
    "9": "AZUL",
    "10": "VERDE",
    "11": "VERMELHO",
}

_PHONE_PATTERN = re.compile(r"(?:\+?55)?\s*\(?(\d{2})\)?\s*(9?\d{4})[- ]?(\d{4})")
_MARKER_PATTERN = re.compile(r"\bAG:([A-F0-9]{10})\b", re.IGNORECASE)
_CLIENT_LABEL_PATTERN = re.compile(r"\b(?:cliente|segurado(?:a)?|nome)\s*:\s*([^\n\r|;]+)", re.IGNORECASE)
_ACTION_BREAK_PATTERN = re.compile(
    r"\s[-|:]\s*(?=(?:GERAR|ENVIAR|COBRAN|BAIXA|SINISTRO|ENDOSSO|TRATATIVA|RENOVA|PAGAMENTO|VENCIMENTO)\b)",
    re.IGNORECASE,
)
_COLOR_PREFIX_PATTERN = re.compile(
    r"^(?:VERMELHO|AZUL|CINZA|VERDE|AMARELO|TANGERINA)(?:/[A-Z0-9() _-]+)?\s*:\s*",
    re.IGNORECASE,
)
_OPERATION_KEYWORDS = (
    "COBRANCA",
    "COBRANÇA",
    "PARCELA",
    "BAIXA",
    "SINISTRO",
    "ENDOSSO",
    "TRATATIVA",
    "RENOVACAO",
    "RENOVAÇÃO",
    "PAGAMENTO",
    "AGENDA",
    "GOOGLE",
)


def _parse_date_only(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _parse_datetime_to_date(raw: str | None) -> date | None:
    if not raw:
        return None
    value = raw.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        return None


def _looks_like_client_name(value: str) -> bool:
    candidate = " ".join(value.split()).strip(" -|;,.")
    if len(candidate) < 4:
        return False
    if candidate.upper().startswith("RPA-AGENDA"):
        return False
    if any(ch.isdigit() for ch in candidate):
        return False
    words = [token for token in candidate.replace("/", " ").split() if token]
    if len(words) < 2 or len(words) > 10:
        return False
    normalized = candidate.upper()
    operation_hits = sum(1 for key in _OPERATION_KEYWORDS if key in normalized)
    if operation_hits >= 2:
        return False
    if operation_hits >= 1 and len(words) <= 3:
        return False
    alpha_chars = sum(1 for ch in candidate if ch.isalpha())
    return alpha_chars >= int(len(candidate) * 0.6)


def _trim_action_suffix(value: str) -> str:
    match = _ACTION_BREAK_PATTERN.search(value)
    if match is None:
        return value
    return value[: match.start()]


def _clean_name(value: str) -> str:
    cleaned = " ".join(value.split())
    cleaned = _COLOR_PREFIX_PATTERN.sub("", cleaned)
    cleaned = _trim_action_suffix(cleaned)
    return cleaned.strip(" -|;,.")


def _iter_name_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    if text.strip() == "":
        return candidates

    for chunk in re.split(r"[\n\r|;]", text):
        chunk = chunk.strip()
        if not chunk:
            continue
        chunk = re.sub(r"^\s*RPA-AGENDA:[^|]*\|\s*", "", chunk, flags=re.IGNORECASE)
        if ":" in chunk:
            left, right = chunk.split(":", 1)
            candidates.append(right.strip())
            candidates.append(left.strip())
        if " - " in chunk:
            left, right = chunk.split(" - ", 1)
            candidates.append(right.strip())
            candidates.append(left.strip())
        candidates.append(chunk)
    return candidates


def _extract_client_name(summary: str, description: str = "") -> str | None:
    combined = f"{summary}\n{description}"
    for labeled in _CLIENT_LABEL_PATTERN.finditer(combined):
        parsed = _clean_name(labeled.group(1))
        if _looks_like_client_name(parsed):
            return parsed

    for candidate_raw in _iter_name_candidates(summary):
        candidate = _clean_name(candidate_raw)
        if _looks_like_client_name(candidate):
            return candidate

    for candidate_raw in _iter_name_candidates(description):
        candidate = _clean_name(candidate_raw)
        if _looks_like_client_name(candidate):
            return candidate
    return None


def _extract_whatsapp_number(text: str) -> str | None:
    match = _PHONE_PATTERN.search(text)
    if match is None:
        return None
    ddd, first, last = match.groups()
    return f"+55{ddd}{first}{last}"


def _extract_commitment_color(
    event: dict[str, object],
    color_map: dict[str, str],
) -> str | None:
    color_id = str(event.get("colorId", "")).strip()
    if color_id in color_map:
        return color_map[color_id]

    summary = str(event.get("summary", "")).upper()
    description = str(event.get("description", "")).upper()
    text = f"{summary}\n{description}"
    if "[VERMELHO]" in text:
        return "VERMELHO"
    if "[AZUL]" in text:
        return "AZUL"
    if "[CINZA]" in text:
        return "CINZA"
    if "[VERDE]" in text:
        return "VERDE"
    if "[AMARELO]" in text:
        return "AMARELO"
    if "[TANGERINA]" in text:
        return "TANGERINA"
    return None


class GoogleCalendarGateway:
    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        calendar_id: str = "primary",
        timeout_seconds: int = 20,
        color_map: dict[str, str] | None = None,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.calendar_id = calendar_id
        self.timeout_seconds = timeout_seconds
        self.color_map = dict(color_map or _DEFAULT_COLOR_MAP)
        self._semantic_color_to_google_id = {
            "VERMELHO": "11",
            "AZUL": "9",
            "CINZA": "8",
            "VERDE": "10",
            "AMARELO": "5",
            "TANGERINA": "6",
        }

    def fetch_daily_commitments(self, day: date) -> list[CalendarCommitment]:
        access_token = self._acquire_access_token()
        if access_token is None:
            return []

        day_start = datetime.combine(day, time.min, tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1)
        query = urlencode(
            {
                "timeMin": day_start.isoformat().replace("+00:00", "Z"),
                "timeMax": day_end.isoformat().replace("+00:00", "Z"),
                "singleEvents": "true",
                "orderBy": "startTime",
            }
        )
        calendar_id = quote(self.calendar_id, safe="")
        path = f"/calendar/v3/calendars/{calendar_id}/events?{query}"
        payload = self._google_get(path, access_token)
        if payload is None:
            return []

        items = payload.get("items", [])
        if not isinstance(items, list):
            return []

        commitments: list[CalendarCommitment] = []
        for raw_item in items:
            if not isinstance(raw_item, dict):
                continue
            color = _extract_commitment_color(raw_item, self.color_map)
            if color is None:
                continue

            start_data = raw_item.get("start")
            if not isinstance(start_data, dict):
                continue
            due_date = _parse_datetime_to_date(str(start_data.get("dateTime", "")))
            if due_date is None:
                due_date = _parse_date_only(str(start_data.get("date", "")))
            if due_date is None:
                continue

            summary = str(raw_item.get("summary", "")).strip() or "Compromisso sem titulo"
            description = str(raw_item.get("description", "")).strip()
            status = str(raw_item.get("status", "")).strip().lower()
            resolved = status == "cancelled" or "concluido" in description.lower() or "resolvido" in description.lower()
            client_name = _extract_client_name(summary, description)
            whatsapp_number = _extract_whatsapp_number(f"{summary}\n{description}")

            commitments.append(
                CalendarCommitment(
                    id=str(raw_item.get("id", "")) or f"calendar-{len(commitments) + 1}",
                    title=summary,
                    color=color,
                    due_date=due_date,
                    description=description,
                    resolved=resolved,
                    client_name=client_name,
                    whatsapp_number=whatsapp_number,
                )
            )
        return commitments

    def upsert_todo_task_event(self, *, task: TodoTask) -> str | None:
        access_token = self._acquire_access_token()
        if access_token is None:
            return None

        event_date = task.due_date or date.today()
        marker = self._extract_task_marker(task.title)
        source_key = marker or task.id
        event_summary = task.title.strip() or "Tarefa Microsoft To Do"
        event_description = self._build_todo_event_description(task=task, marker=marker)

        existing_event = self._find_todo_event_by_source_key(access_token=access_token, source_key=source_key)
        body = {
            "summary": event_summary,
            "description": event_description,
            "start": {"date": event_date.isoformat()},
            "end": {"date": (event_date + timedelta(days=1)).isoformat()},
            "colorId": self._infer_google_color_id_from_task(task),
            "extendedProperties": {
                "private": {
                    "rpaSource": "microsoft_todo",
                    "rpaTodoTaskId": task.id,
                    "rpaSourceKey": source_key,
                }
            },
        }

        try:
            if existing_event is None:
                created = self._google_json_request(
                    method="POST",
                    path=f"/calendar/v3/calendars/{quote(self.calendar_id, safe='')}/events",
                    access_token=access_token,
                    payload=body,
                )
                if not isinstance(created, dict):
                    return None
                return str(created.get("id", "")).strip() or None

            event_id = str(existing_event.get("id", "")).strip()
            if not event_id:
                return None
            updated = self._google_json_request(
                method="PATCH",
                path=f"/calendar/v3/calendars/{quote(self.calendar_id, safe='')}/events/{quote(event_id, safe='')}",
                access_token=access_token,
                payload=body,
            )
            if not isinstance(updated, dict):
                return None
            return str(updated.get("id", "")).strip() or event_id
        except Exception as exc:
            print(f"[Google Calendar] Falha ao criar/atualizar evento vindo do To Do: {exc}")
            return None

    @staticmethod
    def _extract_task_marker(title: str) -> str | None:
        match = _MARKER_PATTERN.search(title or "")
        if match is None:
            return None
        return match.group(1).upper()

    def _infer_google_color_id_from_task(self, task: TodoTask) -> str:
        text = f"{task.title}\n{task.external_ref or ''}".upper()
        if "VERMELHO" in text:
            return self._semantic_color_to_google_id["VERMELHO"]
        if "AZUL" in text:
            return self._semantic_color_to_google_id["AZUL"]
        if "CINZA" in text:
            return self._semantic_color_to_google_id["CINZA"]
        if "AMARELO" in text:
            return self._semantic_color_to_google_id["AMARELO"]
        if "TANGERINA" in text:
            return self._semantic_color_to_google_id["TANGERINA"]
        return self._semantic_color_to_google_id["VERDE"]

    @staticmethod
    def _build_todo_event_description(task: TodoTask, marker: str | None) -> str:
        lines: list[str] = [
            "Origem: Microsoft To Do",
            f"ToDo ID: {task.id}",
        ]
        if marker:
            lines.append(f"Marcador agenda: AG:{marker}")
        if task.contact_phone:
            lines.append(f"Telefone: {task.contact_phone}")
        if task.contact_email:
            lines.append(f"E-mail: {task.contact_email}")
        if task.contact_address:
            lines.append(f"Endereco: {task.contact_address}")
        if task.external_ref:
            lines.append("")
            lines.append("Detalhes:")
            lines.append(task.external_ref.strip())
        return "\n".join(lines)

    def _find_todo_event_by_source_key(self, *, access_token: str, source_key: str) -> dict[str, object] | None:
        calendar_id = quote(self.calendar_id, safe="")
        query = urlencode(
            {
                "singleEvents": "true",
                "maxResults": "1",
                "privateExtendedProperty": f"rpaSourceKey={source_key}",
            }
        )
        payload = self._google_get(f"/calendar/v3/calendars/{calendar_id}/events?{query}", access_token)
        if payload is None:
            return None
        items = payload.get("items")
        if not isinstance(items, list) or not items:
            return None
        item = items[0]
        if isinstance(item, dict):
            return item
        return None

    def _acquire_access_token(self) -> str | None:
        data = urlencode(
            {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
            }
        ).encode("utf-8")
        request = Request(
            "https://oauth2.googleapis.com/token",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            print(f"[Google Calendar] Falha ao obter token: {exc}")
            return None

        token = payload.get("access_token")
        if not isinstance(token, str) or token.strip() == "":
            return None
        return token.strip()

    def _google_get(self, path: str, access_token: str) -> dict[str, object] | None:
        payload = self._google_json_request(method="GET", path=path, access_token=access_token)
        if isinstance(payload, dict):
            return payload
        return None

    def _google_json_request(
        self,
        *,
        method: str,
        path: str,
        access_token: str,
        payload: dict[str, object] | None = None,
    ) -> dict[str, object] | None:
        base = "https://www.googleapis.com"
        parsed = urlparse(path)
        if parsed.scheme:
            url = path
        else:
            url = f"{base}{path}"
        headers = {"Authorization": f"Bearer {access_token}"}
        body = None
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(
            url,
            headers=headers,
            data=body,
            method=method.upper(),
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            print(f"[Google Calendar] Falha na requisicao {method.upper()} ({path}): {exc}")
            return None
