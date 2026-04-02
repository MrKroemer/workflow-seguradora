from __future__ import annotations

from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import json


class WhatsAppHttpGateway:
    def __init__(
        self,
        *,
        api_url: str,
        token: str,
        timeout_seconds: int = 20,
        auth_header: str = "Authorization",
        auth_scheme: str = "Bearer",
    ) -> None:
        self.api_url = api_url
        self.token = token
        self.timeout_seconds = timeout_seconds
        self.auth_header = auth_header
        self.auth_scheme = auth_scheme

    def _is_meta_cloud_url(self) -> bool:
        url = self.api_url.lower()
        return "graph.facebook.com" in url and url.rstrip("/").endswith("/messages")

    @staticmethod
    def _normalize_phone_for_meta(phone: str) -> str:
        digits = "".join(ch for ch in phone if ch.isdigit())
        return digits or phone.strip()

    def send_message(self, phone: str, content: str) -> None:
        if self._is_meta_cloud_url():
            payload_obj = {
                "messaging_product": "whatsapp",
                "to": self._normalize_phone_for_meta(phone),
                "type": "text",
                "text": {"preview_url": False, "body": content},
            }
        else:
            payload_obj = {
                "phone": phone,
                "message": content,
            }
        payload = json.dumps(payload_obj).encode("utf-8")
        token_value = self.token
        if self.auth_scheme.strip():
            token_value = f"{self.auth_scheme.strip()} {self.token}"

        request = Request(
            self.api_url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                self.auth_header: token_value,
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds):
                return
        except HTTPError as exc:
            details = ""
            if exc.fp is not None:
                try:
                    details = exc.fp.read().decode("utf-8", errors="replace")
                except Exception:
                    details = ""
            message = f"Falha HTTP no envio WhatsApp ({exc.code})."
            if details.strip():
                message = f"{message} Resposta: {details.strip()}"
            raise RuntimeError(message) from exc
        except URLError as exc:
            raise RuntimeError(f"Falha de rede no envio WhatsApp: {exc}") from exc
