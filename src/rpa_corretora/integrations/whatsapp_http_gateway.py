from __future__ import annotations

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

    def send_message(self, phone: str, content: str) -> None:
        payload = json.dumps(
            {
                "phone": phone,
                "message": content,
            }
        ).encode("utf-8")
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
        with urlopen(request, timeout=self.timeout_seconds):
            return
