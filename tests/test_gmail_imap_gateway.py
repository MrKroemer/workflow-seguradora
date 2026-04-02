from __future__ import annotations

from rpa_corretora.integrations.gmail_imap_gateway import (
    _decode_mime_header,
    _extract_attachments,
    _extract_body,
)


class _HeaderObject:
    def __init__(self, value: str) -> None:
        self.value = value

    def __str__(self) -> str:
        return self.value


class _FakePart:
    def __init__(
        self,
        *,
        disposition: str | None = None,
        content_type: str = "text/plain",
        payload: bytes | None = None,
        charset: str = "utf-8",
        filename: object | None = None,
    ) -> None:
        self._disposition = disposition
        self._content_type = content_type
        self._payload = payload
        self._charset = charset
        self._filename = filename

    def get(self, key: str):
        if key == "Content-Disposition":
            if self._disposition is None:
                return None
            return _HeaderObject(self._disposition)
        return None

    def get_content_type(self) -> str:
        return self._content_type

    def get_content_charset(self) -> str:
        return self._charset

    def get_payload(self, decode: bool = False):
        if decode:
            return self._payload
        if self._payload is None:
            return None
        return self._payload.decode(self._charset, errors="replace")

    def get_filename(self):
        return self._filename


class _FakeMessage:
    def __init__(self, parts: list[_FakePart]) -> None:
        self._parts = parts

    def is_multipart(self) -> bool:
        return True

    def walk(self):
        return self._parts


def test_decode_mime_header_accepts_header_object() -> None:
    assert _decode_mime_header(_HeaderObject("Assunto Teste")) == "Assunto Teste"


def test_extract_body_handles_header_object_disposition() -> None:
    msg = _FakeMessage(
        [
            _FakePart(disposition=None, content_type="text/plain", payload="Corpo em texto".encode("utf-8")),
        ]
    )

    body = _extract_body(msg)  # type: ignore[arg-type]

    assert body == "Corpo em texto"


def test_extract_attachments_handles_header_object_disposition_and_filename() -> None:
    msg = _FakeMessage(
        [
            _FakePart(
                disposition='attachment; filename="arquivo.pdf"',
                content_type="application/pdf",
                payload=b"PDF",
                filename=_HeaderObject("arquivo.pdf"),
            )
        ]
    )

    attachments = _extract_attachments(msg)  # type: ignore[arg-type]

    assert attachments == ["arquivo.pdf"]
