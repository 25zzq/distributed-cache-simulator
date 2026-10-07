"""Write every application to a local CSV and, when configured, a Google Sheet."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from urllib.parse import quote

from internship_assistant.models import Application

SHEET_HEADERS = [
    "application_id",
    "found_at",
    "applied_at",
    "status",
    "status_updated_at",
    "company",
    "role",
    "location",
    "source",
    "url",
    "match_score",
    "matched_skills",
    "missing_skills",
    "submit_method",
    "apply_email",
    "needs_input",
    "email_evidence",
    "notes",
]

SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"


def application_row(application: Application) -> list[str]:
    return [
        application.id,
        application.found_at,
        application.applied_at,
        application.status,
        application.status_updated_at,
        application.company,
        application.title,
        application.location,
        application.source,
        application.url,
        f"{application.match_score:.1f}",
        application.matched_skills,
        application.missing_skills,
        application.submit_method,
        application.apply_email,
        application.needs_input,
        application.email_evidence,
        application.notes,
    ]


def row_from_updated_range(updated_range: str) -> int | None:
    import re

    match = re.search(r"![A-Z]+(\d+)", updated_range or "")
    if not match:
        return None
    return int(match.group(1))


class CsvTracker:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def sync(self, applications: list[Application]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        ordered = sorted(applications, key=lambda application: (application.found_at, application.id))
        with self.path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(SHEET_HEADERS)
            for application in ordered:
                writer.writerow(application_row(application))


class GoogleSheetTracker:
    """Append and update rows with the Sheets API. Pass any HTTP client with request_json."""

    def __init__(self, spreadsheet_id: str, worksheet: str, token: str, http):
        self.spreadsheet_id = spreadsheet_id
        self.worksheet = worksheet or "Applications"
        self.token = token
        self.http = http

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    def _range(self, cells: str) -> str:
        title = self.worksheet.replace("'", "''")
        return quote(f"'{title}'!{cells}", safe="")

    def _request(self, method: str, suffix: str, body: dict | None = None) -> dict:
        status, payload = self.http.request_json(
            method,
            f"https://sheets.googleapis.com/v4/spreadsheets/{self.spreadsheet_id}{suffix}",
            self._headers(),
            body,
        )
        if status >= 400:
            message = json.dumps(payload)
            if status == 400 and "already exists" in message.lower():
                return payload
            raise RuntimeError(f"Google Sheets returned {status}: {message}")
        return payload

    def ensure_worksheet(self) -> None:
        self._request(
            "POST",
            ":batchUpdate",
            {"requests": [{"addSheet": {"properties": {"title": self.worksheet}}}]},
        )

    def ensure_header(self) -> None:
        payload = self._request("GET", f"/values/{self._range('A1:R1')}", None)
        values = payload.get("values") or []
        if not values or values[0] != SHEET_HEADERS:
            self._request(
                "PUT",
                f"/values/{self._range('A1:R1')}?valueInputOption=USER_ENTERED",
                {"values": [SHEET_HEADERS]},
            )

    def _write(self, application: Application, *, append: bool) -> int | None:
        row = application_row(application)
        if append:
            payload = self._request(
                "POST",
                f"/values/{self._range('A1:R1')}:append?valueInputOption=USER_ENTERED&insertDataOption=INSERT_ROWS",
                {"values": [row]},
            )
            updated = (payload.get("updates") or {}).get("updatedRange", "")
            return row_from_updated_range(updated)
        if not application.sheet_row:
            return None
        cells = f"A{application.sheet_row}:R{application.sheet_row}"
        self._request(
            "PUT",
            f"/values/{self._range(cells)}?valueInputOption=USER_ENTERED",
            {"values": [row]},
        )
        return application.sheet_row

    def sync(self, applications: list[Application]) -> list[tuple[str, int]]:
        self.ensure_worksheet()
        self.ensure_header()
        placed: list[tuple[str, int]] = []
        ordered = sorted(applications, key=lambda application: (application.found_at, application.id))
        for application in ordered:
            if application.sheet_row:
                self._write(application, append=False)
                placed.append((application.id, application.sheet_row))
                continue
            row_number = self._write(application, append=True)
            if row_number and row_number > 1:
                application.sheet_row = row_number
                placed.append((application.id, row_number))
        return placed


def service_account_token(credentials_path: str) -> str:
    try:
        from google.auth.transport.requests import Request
        from google.oauth2 import service_account
    except ImportError as exc:
        raise RuntimeError(
            "Google Sheets sync needs the google-auth package. "
            "Install it with: pip install -r internship_assistant/requirements.txt"
        ) from exc
    credentials = service_account.Credentials.from_service_account_file(
        credentials_path,
        scopes=[SHEETS_SCOPE],
    )
    credentials.refresh(Request())
    if not credentials.token:
        raise RuntimeError("Google did not return an access token for the service account.")
    return credentials.token
