"""Load the local config file. Secrets stay in environment variables."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_EXCLUDES = ["senior", "staff", "principal", "director", "vp", "vice president", "head of"]


@dataclass
class AppConfig:
    auto_apply_email: bool = False
    min_match_score: float = 40
    daily_apply_cap: int = 8
    require_intern_signal: bool = True
    exclude_title_keywords: list[str] = field(default_factory=lambda: list(DEFAULT_EXCLUDES))
    listings_file: str = "data/listings.json"
    json_feeds: list[str] = field(default_factory=list)
    rss_feeds: list[dict] = field(default_factory=list)
    greenhouse: list[dict] = field(default_factory=list)
    lever: list[dict] = field(default_factory=list)
    ashby: list[dict] = field(default_factory=list)
    spreadsheet_id: str = ""
    credentials_path: str = "data/google-service-account.json"
    worksheet: str = "Applications"
    imap_host: str = "imap.gmail.com"
    imap_port: int = 993
    imap_username: str = ""
    imap_password_env: str = "IMAP_PASSWORD"
    imap_folder: str = "INBOX"
    imap_since_days: int = 21
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password_env: str = "SMTP_PASSWORD"
    smtp_from: str = ""
    data_dir: str = "data"
    profile_path: str = "data/profile.json"


def _section(data: dict, key: str) -> dict:
    value = data.get(key) or {}
    return value if isinstance(value, dict) else {}


def load_config(path: str | Path) -> AppConfig:
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("Config must be a JSON object.")
    boards = _section(data, "boards")
    sheet = _section(data, "google_sheet")
    imap = _section(data, "imap")
    smtp = _section(data, "smtp")
    excludes = data.get("exclude_title_keywords")
    return AppConfig(
        auto_apply_email=bool(data.get("auto_apply_email") or False),
        min_match_score=float(data.get("min_match_score", 40)),
        daily_apply_cap=int(data.get("daily_apply_cap", 8)),
        require_intern_signal=True if data.get("require_intern_signal") is None else bool(data.get("require_intern_signal")),
        exclude_title_keywords=list(excludes) if isinstance(excludes, list) else list(DEFAULT_EXCLUDES),
        listings_file=str(data.get("listings_file") or "data/listings.json"),
        json_feeds=[str(item) for item in data.get("json_feeds") or []],
        rss_feeds=[item for item in data.get("rss_feeds") or [] if isinstance(item, dict)],
        greenhouse=[item for item in boards.get("greenhouse") or data.get("greenhouse") or [] if isinstance(item, dict)],
        lever=[item for item in boards.get("lever") or data.get("lever") or [] if isinstance(item, dict)],
        ashby=[item for item in boards.get("ashby") or data.get("ashby") or [] if isinstance(item, dict)],
        spreadsheet_id=str(sheet.get("spreadsheet_id") or data.get("spreadsheet_id") or ""),
        credentials_path=str(sheet.get("credentials_path") or data.get("credentials_path") or "data/google-service-account.json"),
        worksheet=str(sheet.get("worksheet") or data.get("worksheet") or "Applications"),
        imap_host=str(imap.get("host") or "imap.gmail.com"),
        imap_port=int(imap.get("port") or 993),
        imap_username=str(imap.get("username") or ""),
        imap_password_env=str(imap.get("password_env") or "IMAP_PASSWORD"),
        imap_folder=str(imap.get("folder") or "INBOX"),
        imap_since_days=int(imap.get("since_days") or 21),
        smtp_host=str(smtp.get("host") or "smtp.gmail.com"),
        smtp_port=int(smtp.get("port") or 587),
        smtp_username=str(smtp.get("username") or ""),
        smtp_password_env=str(smtp.get("password_env") or "SMTP_PASSWORD"),
        smtp_from=str(smtp.get("from_email") or ""),
        data_dir=str(data.get("data_dir") or "data"),
        profile_path=str(data.get("profile_path") or "data/profile.json"),
    )
