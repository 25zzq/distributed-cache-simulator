"""Classify replies in your own inbox and attach them to applications."""

from __future__ import annotations

import imaplib
import re
from datetime import datetime, timedelta
from email import message_from_bytes
from email.message import Message

from internship_assistant.models import Application, InboundMail

STATUS_RANK = {
    "discovered": 0,
    "drafted": 1,
    "needs_input": 1,
    "send_failed": 1,
    "ready_to_submit": 2,
    "sending": 3,
    "applied": 3,
    "assessment": 4,
    "interview": 5,
    "rejected": 6,
    "offer": 7,
    "withdrawn": 2,
}

_REJECTION = re.compile(
    r"("
    r"not (?:be )?moving forward|"
    r"move forward with other|"
    r"other candidates|"
    r"regret to inform|"
    r"we regret|"
    r"not selected|"
    r"position has been filled|"
    r"decided to pursue other|"
    r"application was unsuccessful|"
    r"will not be proceeding|"
    r"we won'?t be moving forward|"
    r"unfortunately.{0,80}(other candidates|not moving|not selected|filled|pursue)"
    r")",
    re.IGNORECASE | re.DOTALL,
)
_OFFER = re.compile(
    r"(offer of employment|extend(?:ing)? an offer|pleased to offer|internship offer|"
    r"like to offer you|offer letter|we are excited to offer)",
    re.IGNORECASE,
)
_INTERVIEW = re.compile(
    r"(invite you to (?:an )?interview|schedule (?:a|an) (?:call|interview|time|screen)|"
    r"phone screen|technical interview|coding interview|"
    r"would like to (?:speak|chat|talk) with you|availability for (?:a|an) (?:call|interview)|"
    r"recruiter screen|interview invitation)",
    re.IGNORECASE,
)
_ASSESSMENT = re.compile(
    r"(take[- ]home|coding challenge|hackerrank|codesignal|online assessment|"
    r"technical assessment)",
    re.IGNORECASE,
)


def classify_message(subject: str, body: str) -> str | None:
    text = f"{subject}\n{body}"
    if _REJECTION.search(text):
        return "rejected"
    if _OFFER.search(text):
        return "offer"
    if _INTERVIEW.search(text):
        return "interview"
    if _ASSESSMENT.search(text):
        return "assessment"
    return None


def next_status(current: str, proposed: str) -> str:
    if STATUS_RANK.get(proposed, -1) > STATUS_RANK.get(current, -1):
        return proposed
    return current


_GENERIC_TOKENS = {
    "inc", "llc", "corp", "the", "and", "lab", "labs", "tech", "software", "data",
    "group", "studio", "systems", "digital", "university", "college", "company",
}


def _contains_token(token: str, text: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])", text) is not None


def _company_tokens(company: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", company.lower())
    specific = [token for token in tokens if len(token) >= 4 and token not in _GENERIC_TOKENS]
    if specific:
        return specific
    return [token for token in tokens if len(token) >= 3 and token not in _GENERIC_TOKENS]


def match_application(mail: InboundMail, applications: list[Application]) -> Application | None:
    haystack = f"{mail.sender}\n{mail.subject}\n{mail.body}".lower()
    matches: list[Application] = []
    for application in applications:
        tokens = _company_tokens(application.company)
        if tokens and all(_contains_token(token, haystack) for token in tokens[:2]):
            matches.append(application)
    if not matches:
        return None
    subject = mail.subject.lower()
    for application in matches:
        if application.company.lower() in subject or any(token in subject for token in _company_tokens(application.company)):
            return application
    matches.sort(key=lambda application: application.applied_at or application.found_at, reverse=True)
    return matches[0]


def _decode(part: Message) -> str:
    payload = part.get_payload(decode=True)
    if payload is None:
        raw = part.get_payload()
        return raw if isinstance(raw, str) else ""
    charset = part.get_content_charset() or "utf-8"
    return payload.decode(charset, errors="replace")


def body_text(message: Message) -> str:
    if message.is_multipart():
        plain: list[str] = []
        html_parts: list[str] = []
        for part in message.walk():
            if part.get_content_maintype() == "multipart":
                continue
            disposition = (part.get("Content-Disposition") or "").lower()
            if "attachment" in disposition:
                continue
            content_type = part.get_content_type()
            text = _decode(part)
            if content_type == "text/plain":
                plain.append(text)
            elif content_type == "text/html":
                html_parts.append(text)
        if plain:
            return "\n".join(plain)
        if html_parts:
            from internship_assistant.textutil import html_to_text

            return html_to_text("\n".join(html_parts))
        return ""
    return _decode(message)


def parse_rfc822(raw: bytes) -> InboundMail:
    message = message_from_bytes(raw)
    return InboundMail(
        sender=str(message.get("From") or ""),
        subject=str(message.get("Subject") or ""),
        body=body_text(message),
        received_at=str(message.get("Date") or ""),
    )


def fetch_imap_messages(
    *,
    host: str,
    port: int,
    username: str,
    password: str,
    folder: str = "INBOX",
    since_days: int = 21,
    connection_factory=None,
    now: datetime | None = None,
) -> list[InboundMail]:
    factory = connection_factory or imaplib.IMAP4_SSL
    conn = factory(host, port)
    try:
        conn.login(username, password)
        conn.select(folder)
        since = ((now or datetime.now()) - timedelta(days=since_days)).strftime("%d-%b-%Y")
        _status, data = conn.search(None, "SINCE", since)
        ids = (data[0] or b"").split()
        messages: list[InboundMail] = []
        for message_id in ids[-200:]:
            _status, fetched = conn.fetch(message_id, "(RFC822)")
            raw = b""
            for item in fetched or []:
                if isinstance(item, tuple) and len(item) >= 2 and isinstance(item[1], (bytes, bytearray)):
                    raw = bytes(item[1])
                    break
            if raw:
                messages.append(parse_rfc822(raw))
        return messages
    finally:
        try:
            conn.logout()
        except Exception:
            pass


def inbox_updates(messages: list[InboundMail], applications: list[Application]) -> list[tuple[Application, str, str]]:
    """Return applications whose status should advance, with the new status and evidence."""
    updates: list[tuple[Application, str, str]] = []
    for mail in messages:
        label = classify_message(mail.subject, mail.body)
        if label is None:
            continue
        application = match_application(mail, applications)
        if application is None:
            continue
        updated = next_status(application.status, label)
        if updated == application.status:
            continue
        evidence = f"{mail.received_at} {mail.subject}".strip()
        application.status = updated
        application.email_evidence = evidence
        application.status_updated_at = mail.received_at or application.status_updated_at
        updates.append((application, updated, evidence))
    return updates
