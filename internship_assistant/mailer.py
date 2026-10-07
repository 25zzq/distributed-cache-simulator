"""Build and send an application email from the drafted packet."""

from __future__ import annotations

import mimetypes
import smtplib
from email.message import EmailMessage
from pathlib import Path


def build_application_message(
    *,
    from_email: str,
    to_email: str,
    full_name: str,
    role: str,
    company: str,
    cover_letter: str,
    resume_path: str | None = None,
) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = f"{role} application — {full_name}"
    message["From"] = from_email
    message["To"] = to_email
    body = (
        f"{cover_letter.rstrip()}\n\n"
        "My resume is attached.\n"
    )
    message.set_content(body)
    if resume_path:
        path = Path(resume_path)
        if path.is_file():
            mime, _encoding = mimetypes.guess_type(path.name)
            maintype, subtype = (mime or "application/octet-stream").split("/", 1)
            message.add_attachment(
                path.read_bytes(),
                maintype=maintype,
                subtype=subtype,
                filename=path.name,
            )
    return message


class SmtpSender:
    def __init__(self, host: str, port: int, username: str, password: str, factory=None):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.factory = factory or (smtplib.SMTP_SSL if port == 465 else smtplib.SMTP)

    def send(self, message: EmailMessage) -> None:
        client = self.factory(self.host, self.port, timeout=30)
        try:
            if self.port != 465:
                client.ehlo()
                client.starttls()
                client.ehlo()
            if self.username:
                client.login(self.username, self.password)
            client.send_message(message)
        finally:
            try:
                client.quit()
            except Exception:
                pass
