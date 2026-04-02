from __future__ import annotations

from urllib.error import HTTPError
from io import BytesIO
import json

from rpa_corretora.integrations.whatsapp_http_gateway import WhatsAppHttpGateway


class _DummyResponse:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_send_message_uses_default_payload(monkeypatch) -> None:
    captured = {}

    def _fake_urlopen(request, timeout=0):
        captured["timeout"] = timeout
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _DummyResponse()

    monkeypatch.setattr("rpa_corretora.integrations.whatsapp_http_gateway.urlopen", _fake_urlopen)

    gateway = WhatsAppHttpGateway(api_url="https://provider.local/send", token="abc123")
    gateway.send_message("+55 (83) 99989-7477", "mensagem teste")

    assert captured["timeout"] == 20
    assert captured["body"] == {
        "phone": "+55 (83) 99989-7477",
        "message": "mensagem teste",
    }
    assert captured["headers"]["Authorization"] == "Bearer abc123"


def test_send_message_uses_meta_payload(monkeypatch) -> None:
    captured = {}

    def _fake_urlopen(request, timeout=0):
        captured["timeout"] = timeout
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _DummyResponse()

    monkeypatch.setattr("rpa_corretora.integrations.whatsapp_http_gateway.urlopen", _fake_urlopen)

    gateway = WhatsAppHttpGateway(
        api_url="https://graph.facebook.com/v23.0/123456789/messages",
        token="meta-token",
    )
    gateway.send_message("+55 (83) 99989-7477", "mensagem meta")

    assert captured["timeout"] == 20
    assert captured["body"] == {
        "messaging_product": "whatsapp",
        "to": "5583999897477",
        "type": "text",
        "text": {"preview_url": False, "body": "mensagem meta"},
    }
    assert captured["headers"]["Authorization"] == "Bearer meta-token"


def test_send_message_raises_runtime_error_with_http_details(monkeypatch) -> None:
    def _fake_urlopen(_request, timeout=0):
        del timeout
        raise HTTPError(
            url="https://graph.facebook.com/v23.0/123/messages",
            code=401,
            msg="Unauthorized",
            hdrs=None,
            fp=BytesIO(b'{"error":"invalid_token"}'),
        )

    monkeypatch.setattr("rpa_corretora.integrations.whatsapp_http_gateway.urlopen", _fake_urlopen)

    gateway = WhatsAppHttpGateway(
        api_url="https://graph.facebook.com/v23.0/123/messages",
        token="token-invalido",
    )

    try:
        gateway.send_message("+5583999990000", "oi")
        assert False, "Era esperado RuntimeError"
    except RuntimeError as exc:
        text = str(exc)
        assert "Falha HTTP no envio WhatsApp (401)" in text
        assert "invalid_token" in text
