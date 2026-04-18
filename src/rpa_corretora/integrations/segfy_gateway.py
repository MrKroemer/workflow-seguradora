from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen
import json
import unicodedata

from openpyxl import load_workbook

from rpa_corretora.domain.models import SegfyPolicyData


def _normalize(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text == "":
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    return text.strip().upper()


def _to_decimal(value: object) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    text = str(value).strip().replace(".", "").replace(",", ".")
    if text == "":
        return Decimal("0")
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return Decimal("0")

class SegfyGateway:
    def __init__(
        self,
        *,
        username: str | None = None,
        password: str | None = None,
        api_base_url: str | None = None,
        api_token: str | None = None,
        api_login_path: str = "/auth/login",
        api_policies_path: str = "/policies",
        api_register_payment_path: str = "/payments/register",
        export_xlsx_path: str | Path | None = None,
        queue_path: str | Path = "outputs/segfy_payment_queue.jsonl",
        timeout_seconds: int = 20,
        allow_queue_fallback: bool = True,
    ) -> None:
        self.username = (username or "").strip()
        self.password = (password or "").strip()
        self.api_base_url = (api_base_url or "").strip().rstrip("/")
        self.api_token = (api_token or "").strip()
        self.api_login_path = api_login_path
        self.api_policies_path = api_policies_path
        self.api_register_payment_path = api_register_payment_path
        self.export_xlsx_path = Path(export_xlsx_path) if export_xlsx_path else None
        self.queue_path = Path(queue_path)
        self.timeout_seconds = timeout_seconds
        self.allow_queue_fallback = allow_queue_fallback

    def fetch_policy_data(self) -> list[SegfyPolicyData]:
        api_data = self._fetch_policy_data_from_api()
        if api_data is not None:
            return api_data
        return self._fetch_policy_data_from_export()

    def import_documents(self) -> int:
        # Gateway API/export nao possui rotina de importacao documental por navegador.
        return 0

    def register_payment(self, *, commitment_id: str, description: str) -> bool:
        payload = {
            "commitment_id": commitment_id,
            "description": description,
        }
        if self._post_payment(payload):
            return True

        if not self.allow_queue_fallback:
            return False

        self.queue_path.parent.mkdir(parents=True, exist_ok=True)
        with self.queue_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(payload) + "\n")
        return False

    def _auth_token(self) -> str | None:
        if self.api_token:
            return self.api_token
        if not self.api_base_url or not self.username or not self.password:
            return None

        payload = self._request_json(
            method="POST",
            path=self.api_login_path,
            body={"username": self.username, "password": self.password},
            token=None,
        )
        if not isinstance(payload, dict):
            return None
        candidates = (
            payload.get("access_token"),
            payload.get("token"),
            payload.get("jwt"),
        )
        for token in candidates:
            if isinstance(token, str) and token.strip():
                return token.strip()
        return None

    def _fetch_policy_data_from_api(self) -> list[SegfyPolicyData] | None:
        if not self.api_base_url:
            return None
        token = self._auth_token()
        if token is None:
            print("[Segfy] Sem token para consulta de apolices via API.")
            return None

        payload = self._request_json(
            method="GET",
            path=self.api_policies_path,
            token=token,
        )
        if payload is None:
            return None

        items: list[object]
        if isinstance(payload, list):
            items = payload
        elif isinstance(payload, dict):
            maybe_items = payload.get("items")
            if isinstance(maybe_items, list):
                items = maybe_items
            elif isinstance(payload.get("data"), list):
                items = payload["data"]  # type: ignore[index]
            else:
                items = []
        else:
            items = []

        parsed: list[SegfyPolicyData] = []
        for raw in items:
            if not isinstance(raw, dict):
                continue
            policy_id = str(
                raw.get("policy_id")
                or raw.get("id")
                or raw.get("numero_apolice")
                or raw.get("apolice")
                or ""
            ).strip()
            if not policy_id:
                continue
            premio = _to_decimal(raw.get("premio_total") or raw.get("premio") or raw.get("valor_premio"))
            comissao = _to_decimal(raw.get("comissao") or raw.get("valor_comissao"))
            parsed.append(
                SegfyPolicyData(
                    policy_id=policy_id,
                    premio_total=premio,
                    comissao=comissao,
                )
            )
        return parsed

    def _post_payment(self, payload: dict[str, str]) -> bool:
        if not self.api_base_url:
            return False
        token = self._auth_token()
        if token is None:
            return False
        response = self._request_json(
            method="POST",
            path=self.api_register_payment_path,
            body=payload,
            token=token,
        )
        return response is not None

    def _request_json(
        self,
        *,
        method: str,
        path: str,
        body: dict[str, object] | None = None,
        token: str | None,
    ) -> dict[str, object] | list[object] | None:
        if not self.api_base_url:
            return None
        url = urljoin(f"{self.api_base_url}/", path.lstrip("/"))
        encoded = None
        headers = {"Content-Type": "application/json"}
        if body is not None:
            encoded = json.dumps(body).encode("utf-8")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = Request(url, data=encoded, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
                if raw.strip() == "":
                    return {}
                return json.loads(raw)
        except Exception as exc:
            print(f"[Segfy] Falha em {method} {url}: {exc}")
            return None

    def _fetch_policy_data_from_export(self) -> list[SegfyPolicyData]:
        if self.export_xlsx_path is None or not self.export_xlsx_path.exists():
            return []

        workbook = load_workbook(self.export_xlsx_path, data_only=True)
        parsed: list[SegfyPolicyData] = []
        for ws in workbook.worksheets:
            header_row, header_map = self._find_headers(ws)
            if header_row is None:
                continue
            policy_col = header_map.get("POLICY")
            premio_col = header_map.get("PREMIO")
            comissao_col = header_map.get("COMISSAO")
            if policy_col is None or premio_col is None or comissao_col is None:
                continue
            for row_index in range(header_row + 1, ws.max_row + 1):
                policy_id = str(ws.cell(row_index, policy_col).value or "").strip()
                if not policy_id:
                    continue
                parsed.append(
                    SegfyPolicyData(
                        policy_id=policy_id,
                        premio_total=_to_decimal(ws.cell(row_index, premio_col).value),
                        comissao=_to_decimal(ws.cell(row_index, comissao_col).value),
                    )
                )
        return parsed

    def _find_headers(self, ws) -> tuple[int | None, dict[str, int]]:
        aliases = defaultdict(
            set,
            {
                "POLICY": {"POLICY", "POLICY ID", "APOLICE", "NUMERO APOLICE", "N APOLICE"},
                "PREMIO": {"PREMIO", "PREMIO TOTAL", "VALOR PREMIO"},
                "COMISSAO": {"COMISSAO", "VALOR COMISSAO"},
            },
        )
        for row_index in range(1, min(ws.max_row, 50) + 1):
            resolved: dict[str, int] = {}
            for col in range(1, ws.max_column + 1):
                normalized = _normalize(ws.cell(row_index, col).value)
                if normalized == "":
                    continue
                for logical_name, values in aliases.items():
                    if normalized in values and logical_name not in resolved:
                        resolved[logical_name] = col
            if {"POLICY", "PREMIO", "COMISSAO"}.issubset(set(resolved.keys())):
                return row_index, resolved
        return None, {}
