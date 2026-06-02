from __future__ import annotations

from email.message import EmailMessage
from pathlib import Path
import mimetypes
import smtplib


class SmtpEmailSenderGateway:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str | None = None,
        password: str | None = None,
        from_email: str | None = None,
        use_tls: bool = True,
        timeout_seconds: int = 20,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.from_email = from_email or username or "noreply@localhost"
        self.use_tls = use_tls
        self.timeout_seconds = timeout_seconds

    def send_email(
        self,
        recipient: str,
        subject: str,
        content: str,
        attachments: list[str | Path] | None = None,
    ) -> None:
        message = EmailMessage()
        message["From"] = self.from_email
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(content)

        for attachment in attachments or []:
            file_path = Path(attachment)
            if not file_path.exists():
                raise FileNotFoundError(f"Anexo de e-mail nao encontrado: {file_path}")
            mime_type, _ = mimetypes.guess_type(file_path.name)
            maintype, subtype = ("application", "octet-stream")
            if mime_type and "/" in mime_type:
                maintype, subtype = mime_type.split("/", 1)
            message.add_attachment(
                file_path.read_bytes(),
                maintype=maintype,
                subtype=subtype,
                filename=file_path.name,
            )

        if self.use_tls:
            with smtplib.SMTP(self.host, self.port, timeout=self.timeout_seconds) as client:
                client.ehlo()
                client.starttls()
                client.ehlo()
                if self.username and self.password:
                    client.login(self.username, self.password)
                client.send_message(message)
            return

        with smtplib.SMTP_SSL(self.host, self.port, timeout=self.timeout_seconds) as client:
            if self.username and self.password:
                client.login(self.username, self.password)
            client.send_message(message)
