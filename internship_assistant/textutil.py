"""Small text helpers shared by matching, discovery, and mail parsing."""

from __future__ import annotations

import html
import re

_TAG_RE = re.compile(r"(?is)<(script|style)\b.*?>.*?</\1>")
_ANY_TAG_RE = re.compile(r"(?s)<[^>]+>")
_WS_RE = re.compile(r"\s+")
_MAILTO_RE = re.compile(
    r"mailto:([A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,})",
    re.IGNORECASE,
)
_APPLY_EMAIL_RE = re.compile(
    r"(?:apply|resume|cv|submit).{0,60}?"
    r"(\b[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}\b)",
    re.IGNORECASE,
)


def html_to_text(value: str | None) -> str:
    if not value:
        return ""
    without_blocks = _TAG_RE.sub(" ", value)
    text = _ANY_TAG_RE.sub(" ", without_blocks)
    text = html.unescape(text)
    return _WS_RE.sub(" ", text).strip()


def collapse_ws(value: str | None) -> str:
    return _WS_RE.sub(" ", (value or "")).strip()


def mentioned(skill: str, text: str) -> bool:
    """True when skill appears as its own token, so Java does not match JavaScript."""
    needle = (skill or "").strip().lower()
    if not needle:
        return False
    pattern = rf"(?<![a-z0-9+#]){re.escape(needle)}(?![a-z0-9+#])"
    return re.search(pattern, (text or "").lower()) is not None


def extract_apply_email(*chunks: str | None) -> str | None:
    blob = "\n".join(chunk for chunk in chunks if chunk)
    mailto = _MAILTO_RE.search(blob)
    if mailto:
        return mailto.group(1)
    contextual = _APPLY_EMAIL_RE.search(blob)
    if contextual:
        return contextual.group(1)
    return None


def is_example_address(email: str | None) -> bool:
    if not email or "@" not in email:
        return False
    host = email.rsplit("@", 1)[1].strip().lower().rstrip(">")
    return host in {"example.com", "example.org", "example.net"} or host.endswith(".example")


def html_escape(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=True)
