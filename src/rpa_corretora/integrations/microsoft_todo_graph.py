from __future__ import annotations

from datetime import date, datetime
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
        self._task_list_index: dict[str, str] = {}

    def fetch_open_tasks(self) -> list[TodoTask]:
        try:
            token = self._acquire_access_token()
            if token is None:
                return []

            tasks: list[TodoTask] = []
            self._task_list_index.clear()
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
                    self._task_list_index[task_id] = str(list_id)
                    tasks.append(
                        TodoTask(
                            id=task_id,
                            title=f"{list_name}: {title}",
                            due_date=due_date,
                            completed=False,
                            list_name=list_name,
                            external_ref=str(list_id),
                        )
                    )
            return tasks
        except Exception as exc:
            print(f"[Microsoft To Do] Integracao indisponivel: {exc}")
            return []

    def create_task(
        self,
        *,
        title: str,
        due_date: date | None = None,
        notes: str | None = None,
    ) -> str | None:
        try:
            token = self._acquire_access_token()
            if token is None:
                return None

            list_id = self._resolve_target_list_id(token)
            if list_id is None:
                return None

            payload: dict[str, object] = {"title": title}
            if due_date is not None:
                payload["dueDateTime"] = self._to_graph_due_date(due_date)
            if notes is not None and notes.strip():
                payload["body"] = {"contentType": "text", "content": notes.strip()}

            created = self._graph_post(
                f"/me/todo/lists/{quote(list_id, safe='')}/tasks",
                token,
                payload,
            )
            task_id = str(created.get("id") or "").strip()
            if not task_id:
                return None
            self._task_list_index[task_id] = list_id
            return task_id
        except Exception as exc:
            print(f"[Microsoft To Do] Falha ao criar tarefa: {exc}")
            return None

    def update_task(
        self,
        *,
        task_id: str,
        title: str | None = None,
        due_date: date | None = None,
        notes: str | None = None,
    ) -> bool:
        try:
            token = self._acquire_access_token()
            if token is None:
                return False
            list_id = self._resolve_list_id_for_task(task_id, token)
            if list_id is None:
                return False

            payload: dict[str, object] = {}
            if title is not None:
                payload["title"] = title
            if due_date is not None:
                payload["dueDateTime"] = self._to_graph_due_date(due_date)
            if notes is not None:
                payload["body"] = {"contentType": "text", "content": notes.strip()}
            if not payload:
                return True

            self._graph_patch(
                f"/me/todo/lists/{quote(list_id, safe='')}/tasks/{quote(task_id, safe='')}",
                token,
                payload,
            )
            return True
        except Exception as exc:
            print(f"[Microsoft To Do] Falha ao atualizar tarefa {task_id}: {exc}")
            return False

    def complete_task(self, *, task_id: str) -> bool:
        try:
            token = self._acquire_access_token()
            if token is None:
                return False
            list_id = self._resolve_list_id_for_task(task_id, token)
            if list_id is None:
                return False

            self._graph_patch(
                f"/me/todo/lists/{quote(list_id, safe='')}/tasks/{quote(task_id, safe='')}",
                token,
                {"status": "completed"},
            )
            return True
        except Exception as exc:
            print(f"[Microsoft To Do] Falha ao concluir tarefa {task_id}: {exc}")
            return False

    def _extract_due_date(self, raw_task: dict[str, object]) -> date | None:
        due_block = raw_task.get("dueDateTime")
        if isinstance(due_block, dict):
            raw_dt = due_block.get("dateTime")
            if isinstance(raw_dt, str) and raw_dt.strip():
                raw_dt = raw_dt.strip().replace("Z", "+00:00")
                try:
                    return datetime.fromisoformat(raw_dt).date()
                except ValueError:
                    pass

        return None

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
        payload = self._graph_request(path=path, access_token=access_token, method="GET")
        if isinstance(payload, dict):
            return payload
        return {}

    def _graph_post(self, path: str, access_token: str, payload: dict[str, object]) -> dict[str, object]:
        response = self._graph_request(path=path, access_token=access_token, method="POST", payload=payload)
        if isinstance(response, dict):
            return response
        return {}

    def _graph_patch(self, path: str, access_token: str, payload: dict[str, object]) -> dict[str, object]:
        response = self._graph_request(path=path, access_token=access_token, method="PATCH", payload=payload)
        if isinstance(response, dict):
            return response
        return {}

    def _graph_request(
        self,
        *,
        path: str,
        access_token: str,
        method: str,
        payload: dict[str, object] | None = None,
    ) -> dict[str, object]:
        data = None
        headers = {"Authorization": f"Bearer {access_token}"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = Request(
            f"https://graph.microsoft.com/v1.0{path}",
            headers=headers,
            method=method,
            data=data,
        )
        response = self._json_request(request)
        if isinstance(response, dict):
            return response
        return {}

    def _resolve_target_list_id(self, access_token: str) -> str | None:
        lists = self._list_metadata(access_token)
        if not lists:
            return None
        target = (self.settings.list_name or "").strip().lower()
        if target:
            for list_id, name in lists:
                if name.strip().lower() == target:
                    return list_id
        return lists[0][0]

    def _resolve_list_id_for_task(self, task_id: str, access_token: str) -> str | None:
        cached = self._task_list_index.get(task_id)
        if cached:
            return cached

        for list_id, _ in self._list_metadata(access_token):
            try:
                payload = self._graph_get(
                    f"/me/todo/lists/{quote(list_id, safe='')}/tasks?$top=200&$select=id",
                    access_token,
                )
            except Exception:
                continue
            for item in payload.get("value", []):
                if not isinstance(item, dict):
                    continue
                if str(item.get("id") or "") == task_id:
                    self._task_list_index[task_id] = list_id
                    return list_id
        return None

    def _list_metadata(self, access_token: str) -> list[tuple[str, str]]:
        payload = self._graph_get("/me/todo/lists?$select=id,displayName", access_token)
        lists: list[tuple[str, str]] = []
        for raw in payload.get("value", []):
            if not isinstance(raw, dict):
                continue
            list_id = str(raw.get("id") or "").strip()
            list_name = str(raw.get("displayName") or "Lista").strip() or "Lista"
            if not list_id:
                continue
            lists.append((list_id, list_name))
        return lists

    def _to_graph_due_date(self, value: date) -> dict[str, str]:
        return {
            "dateTime": f"{value.isoformat()}T12:00:00",
            "timeZone": "UTC",
        }

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
