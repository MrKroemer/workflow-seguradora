from __future__ import annotations

from datetime import date, datetime, timedelta
import json
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from rpa_corretora.config import MicrosoftTodoSettings
from rpa_corretora.domain.models import TodoTask


class MicrosoftTodoGraphGateway:
    def __init__(self, settings: MicrosoftTodoSettings, timeout_seconds: int = 20) -> None:
        self.settings = settings
        self.timeout_seconds = timeout_seconds

    def fetch_open_tasks(self) -> list[TodoTask]:
        try:
            token = self._acquire_access_token()
            if token is None:
                return []

            tasks: list[TodoTask] = []
            lists_payload = self._graph_get("/me/todo/lists?$select=id,displayName", token)
            for task_list in lists_payload.get("value", []):
                list_id = task_list.get("id")
                list_name = str(task_list.get("displayName") or "Lista")
                if not list_id:
                    continue

                list_tasks = self._graph_get(
                    f"/me/todo/lists/{quote(str(list_id), safe='')}/tasks?$top=100",
                    token,
                )
                for item in list_tasks.get("value", []):
                    status = str(item.get("status") or "").lower()
                    if status == "completed":
                        continue

                    title = str(item.get("title") or "Sem titulo")
                    task_id = str(item.get("id") or f"{list_id}:{len(tasks)+1}")
                    due_date = self._extract_due_date(item)
                    tasks.append(
                        TodoTask(
                            id=task_id,
                            title=f"{list_name}: {title}",
                            due_date=due_date,
                            completed=False,
                        )
                    )
            return tasks
        except Exception as exc:
            print(f"[Microsoft To Do] Integracao indisponivel: {exc}")
            return []

    def _extract_due_date(self, raw_task: dict[str, object]) -> date:
        due_block = raw_task.get("dueDateTime")
        if isinstance(due_block, dict):
            raw_dt = due_block.get("dateTime")
            if isinstance(raw_dt, str) and raw_dt.strip():
                raw_dt = raw_dt.strip().replace("Z", "+00:00")
                try:
                    return datetime.fromisoformat(raw_dt).date()
                except ValueError:
                    pass

        # Tarefas sem prazo nao devem virar pendencia imediata.
        return date.today() + timedelta(days=3650)

    def _acquire_access_token(self) -> str | None:
        if self.settings.client_id and self.settings.refresh_token:
            token_payload = self._token_request(
                {
                    "grant_type": "refresh_token",
                    "client_id": self.settings.client_id,
                    "refresh_token": self.settings.refresh_token,
                    "scope": "Tasks.Read Tasks.ReadWrite User.Read offline_access",
                    **({"client_secret": self.settings.client_secret} if self.settings.client_secret else {}),
                }
            )
            return token_payload.get("access_token")

        # Fallback legado: requer app configurado para ROPC e pode nao estar habilitado no tenant.
        if self.settings.client_id and self.settings.username and self.settings.password:
            token_payload = self._token_request(
                {
                    "grant_type": "password",
                    "client_id": self.settings.client_id,
                    "username": self.settings.username,
                    "password": self.settings.password,
                    "scope": "Tasks.Read Tasks.ReadWrite User.Read offline_access openid profile",
                    **({"client_secret": self.settings.client_secret} if self.settings.client_secret else {}),
                }
            )
            return token_payload.get("access_token")

        return None

    def _token_request(self, form_data: dict[str, str]) -> dict[str, str]:
        tenant = self.settings.tenant_id or "common"
        token_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
        data = urlencode(form_data).encode("utf-8")
        request = Request(
            token_url,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        return self._json_request(request)

    def _graph_get(self, path: str, access_token: str) -> dict[str, object]:
        request = Request(
            f"https://graph.microsoft.com/v1.0{path}",
            headers={"Authorization": f"Bearer {access_token}"},
            method="GET",
        )
        payload = self._json_request(request)
        if isinstance(payload, dict):
            return payload
        return {}

    def _json_request(self, request: Request) -> dict[str, object]:
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                response_text = response.read().decode("utf-8")
                if not response_text.strip():
                    return {}
                data = json.loads(response_text)
                if isinstance(data, dict):
                    return data
                return {}
        except HTTPError as exc:
            details = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"HTTP {exc.code} no Microsoft Graph: {details[:220]}") from exc
        except URLError as exc:
            raise RuntimeError(f"Falha de rede no Microsoft Graph: {exc.reason}") from exc
