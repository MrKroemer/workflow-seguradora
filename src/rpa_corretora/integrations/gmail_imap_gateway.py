from __future__ import annotations

from datetime import datetime
from email import message_from_bytes
from email.header import decode_header, make_header
from email.message import Message
from email.utils import parsedate_to_datetime
import imaplib
import re

from rpa_corretora.domain.models import EmailMessage


_HTML_TAGS = re.compile(r"<[^>]+>")


def _stringify_header(value: object | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _decode_mime_header(raw: object | None) -> str:
    if raw is None:
        return ""
    raw_text = _stringify_header(raw)
    try:
        return str(make_header(decode_header(raw_text))).strip()
    except Exception:
        return raw_text.strip()


def _extract_body(msg: Message) -> str:
    plain_parts: list[str] = []
    html_parts: list[str] = []

    if msg.is_multipart():
        for part in msg.walk():
            content_disposition = _stringify_header(part.get("Content-Disposition")).lower()
            if "attachment" in content_disposition:
                continue
            content_type = (part.get_content_type() or "").lower()
            charset = part.get_content_charset() or "utf-8"
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            try:
                text = payload.decode(charset, errors="replace")
            except Exception:
                text = payload.decode("utf-8", errors="replace")
            if content_type == "text/plain":
                plain_parts.append(text)
            elif content_type == "text/html":
                html_parts.append(text)
    else:
        payload = msg.get_payload(decode=True)
        if payload is None:
            return ""
        charset = msg.get_content_charset() or "utf-8"
        try:
            text = payload.decode(charset, errors="replace")
        except Exception:
            text = payload.decode("utf-8", errors="replace")
        if (msg.get_content_type() or "").lower() == "text/html":
            html_parts.append(text)
        else:
            plain_parts.append(text)

    if plain_parts:
        merged = "\n".join(plain_parts).strip()
        return " ".join(merged.split())
    if html_parts:
        merged_html = "\n".join(html_parts)
        no_tags = _HTML_TAGS.sub(" ", merged_html)
        return " ".join(no_tags.split())
    return ""


def _extract_attachments(msg: Message) -> list[str]:
    filenames: list[str] = []
    for part in msg.walk():
        content_disposition = _stringify_header(part.get("Content-Disposition")).lower()
        if "attachment" not in content_disposition:
            continue
        filename = _decode_mime_header(part.get_filename())
        if filename:
            filenames.append(filename)
    return filenames


class GmailImapGateway:
    def __init__(
        self,
        *,
        username: str,
        password: str,
        host: str = "imap.gmail.com",
        mailbox: str = "INBOX",
        max_messages: int = 60,
        attachment_output_dir: str | None = None,
    ) -> None:
        self.username = username
        self.password = password
        self.host = host
        self.mailbox = mailbox
        self.max_messages = max_messages
        self.attachment_output_dir = attachment_output_dir

    def fetch_unread_messages(self) -> list[EmailMessage]:
        messages: list[EmailMessage] = []
        try:
            with imaplib.IMAP4_SSL(self.host) as client:
                client.login(self.username, self.password)
                client.select(self.mailbox, readonly=True)
                status, raw_ids = client.search(None, "UNSEEN")
                if status != "OK" or not raw_ids:
                    return []

                ids = raw_ids[0].split()
                if not ids:
                    return []
                ids = ids[-self.max_messages :]

                for msg_id in ids:
                    status, payload = client.fetch(msg_id, "(RFC822)")
                    if status != "OK" or not payload:
                        continue
                    raw_message = payload[0][1] if isinstance(payload[0], tuple) and len(payload[0]) > 1 else None
                    if raw_message is None:
                        continue

                    parsed = message_from_bytes(raw_message)
                    sender = _decode_mime_header(parsed.get("From"))
                    subject = _decode_mime_header(parsed.get("Subject"))
                    body = _extract_body(parsed)
                    attachments = _extract_attachments(parsed)

                    received_at = datetime.now()
                    date_header = parsed.get("Date")
                    if date_header:
                        try:
                            received_at = parsedate_to_datetime(_stringify_header(date_header))
                        except Exception:
                            pass

                    messages.append(
                        EmailMessage(
                            id=msg_id.decode("utf-8", errors="ignore") if isinstance(msg_id, bytes) else str(msg_id),
                            sender=sender,
                            subject=subject,
                            body=body,
                            received_at=received_at,
                            attachments=attachments,
                        )
                    )
        except Exception as exc:
            print(f"[Gmail IMAP] Falha na leitura de e-mails: {exc}")
            return []
        return messages

    def save_insurer_attachments(
        self,
        messages: list[EmailMessage],
        insurer_domains: tuple[str, ...],
        output_dir: str | None = None,
    ) -> list[str]:
        """Salva anexos de e-mails de seguradoras em disco para importacao no Segfy."""
        from pathlib import Path

        target_dir = Path(output_dir or self.attachment_output_dir or "outputs/email_attachments")
        target_dir.mkdir(parents=True, exist_ok=True)

        saved: list[str] = []
        allowed_extensions = {".pdf", ".xlsx", ".xls", ".csv", ".doc", ".docx"}

        for message in messages:
            sender_lower = message.sender.lower()
            is_insurer = any(domain in sender_lower for domain in insurer_domains)
            if not is_insurer:
                continue
            if not message.attachments:
                continue

            # Re-fetch the raw message to extract attachment bytes.
            try:
                with imaplib.IMAP4_SSL(self.host) as client:
                    client.login(self.username, self.password)
                    client.select(self.mailbox, readonly=True)
                    status, raw_ids = client.search(None, "ALL")
                    if status != "OK" or not raw_ids:
                        continue

                    ids = raw_ids[0].split()
                    # Find the message by ID (best effort).
                    msg_id_bytes = message.id.encode() if isinstance(message.id, str) else message.id
                    target_ids = [mid for mid in ids if mid == msg_id_bytes]
                    if not target_ids:
                        # Fallback: use last N messages.
                        target_ids = ids[-self.max_messages:]

                    for mid in target_ids:
                        status, payload = client.fetch(mid, "(RFC822)")
                        if status != "OK" or not payload:
                            continue
                        raw = payload[0][1] if isinstance(payload[0], tuple) else None
                        if raw is None:
                            continue

                        parsed = message_from_bytes(raw)
                        for part in parsed.walk():
                            content_disposition = str(part.get("Content-Disposition") or "").lower()
                            if "attachment" not in content_disposition:
                                continue
                            filename = _decode_mime_header(part.get_filename())
                            if not filename:
                                continue

                            ext = Path(filename).suffix.lower()
                            if ext not in allowed_extensions:
                                continue

                            file_data = part.get_payload(decode=True)
                            if not file_data:
                                continue

                            safe_name = f"{message.id}_{filename}".replace("/", "_").replace("\\", "_")
                            dest = target_dir / safe_name
                            if not dest.exists():
                                dest.write_bytes(file_data)
                                saved.append(str(dest))
                        break  # Found the message, no need to continue.
            except Exception as exc:
                print(f"[Gmail IMAP] Falha ao salvar anexo de {message.sender}: {exc}")
                continue

        return saved
