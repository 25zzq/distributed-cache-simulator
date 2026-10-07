"""Local page for editing the internship search and running it on demand."""

from __future__ import annotations

import json
import threading
import uuid
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from internship_assistant.cli import (
    MARK_STATUSES,
    _store,
    _write_reports,
    execute_search,
    init_workspace,
    load_config,
    sync_trackers,
)
from internship_assistant.config import AppConfig
from internship_assistant.models import Application
from internship_assistant.profile import load_profile, profile_from_dict, profile_to_dict, save_profile
from internship_assistant.report import summarize

PAGE = Path(__file__).with_name("dashboard.html")
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


def workspace_root(config_path: Path) -> Path:
    path = config_path.resolve()
    if path.parent.name == "data":
        return path.parent.parent
    return path.parent


def materialize_config(config_path: Path) -> AppConfig:
    """Resolve data paths from the folder that holds this config, not the shell's cwd."""
    config = load_config(config_path)
    root = workspace_root(config_path)

    def resolve(value: str) -> str:
        candidate = Path(value)
        if candidate.is_absolute():
            return str(candidate)
        return str((root / candidate).resolve())

    config.listings_file = resolve(config.listings_file)
    config.profile_path = resolve(config.profile_path)
    config.data_dir = resolve(config.data_dir)
    config.credentials_path = resolve(config.credentials_path)
    return config


def _brief(application: Application) -> dict:
    return {
        "id": application.id,
        "company": application.company,
        "title": application.title,
        "location": application.location,
        "source": application.source,
        "url": application.url,
        "apply_email": application.apply_email,
        "match_score": application.match_score,
        "matched_skills": application.matched_skills,
        "missing_skills": application.missing_skills,
        "status": application.status,
        "submit_method": application.submit_method,
        "needs_input": application.needs_input,
        "email_evidence": application.email_evidence,
        "notes": application.notes,
        "found_at": application.found_at,
        "applied_at": application.applied_at,
        "status_updated_at": application.status_updated_at,
    }


def _summary(config: AppConfig) -> dict:
    store = _store(config)
    try:
        raw = summarize(store.list_applications(), store.count_seen())
    finally:
        store.close()
    cleaned = {}
    for key, value in raw.items():
        if isinstance(value, list):
            cleaned[key] = [list(item) if isinstance(item, tuple) else item for item in value]
        else:
            cleaned[key] = value
    return cleaned


def _settings(config: AppConfig) -> dict:
    return {
        "auto_apply_email": config.auto_apply_email,
        "min_match_score": config.min_match_score,
        "daily_apply_cap": config.daily_apply_cap,
        "require_intern_signal": config.require_intern_signal,
        "spreadsheet_id": config.spreadsheet_id,
        "worksheet": config.worksheet,
        "imap_username": config.imap_username,
        "smtp_username": config.smtp_username,
    }


def load_listings(path: str) -> list[dict]:
    file_path = Path(path)
    if not file_path.is_file():
        return []
    payload = json.loads(file_path.read_text(encoding="utf-8"))
    rows = payload.get("jobs") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def save_listings(path: str, jobs: list) -> list[dict]:
    if not isinstance(jobs, list):
        raise ValueError("Listings need a jobs list.")
    cleaned = []
    for item in jobs:
        if not isinstance(item, dict):
            continue
        company = str(item.get("company") or "").strip()
        title = str(item.get("title") or "").strip()
        if not company or not title:
            raise ValueError("Each listing needs a company and a title.")
        listing_id = str(item.get("id") or "").strip() or uuid.uuid4().hex[:12]
        cleaned.append(
            {
                "id": listing_id,
                "company": company,
                "title": title,
                "location": str(item.get("location") or "").strip(),
                "url": str(item.get("url") or "").strip(),
                "apply_email": str(item.get("apply_email") or "").strip(),
                "description": str(item.get("description") or "").strip(),
            }
        )
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps({"jobs": cleaned}, indent=2) + "\n", encoding="utf-8")
    return cleaned


def save_settings(config_path: Path, updates: dict) -> None:
    data = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(updates, dict):
        raise ValueError("Settings must be a JSON object.")
    if "auto_apply_email" in updates:
        data["auto_apply_email"] = bool(updates["auto_apply_email"])
    if "min_match_score" in updates:
        score = float(updates["min_match_score"])
        if score < 0 or score > 100:
            raise ValueError("Match score must be between 0 and 100.")
        data["min_match_score"] = score
    if "daily_apply_cap" in updates:
        cap = int(updates["daily_apply_cap"])
        if cap < 0 or cap > 100:
            raise ValueError("Daily cap must be between 0 and 100.")
        data["daily_apply_cap"] = cap
    if "require_intern_signal" in updates:
        data["require_intern_signal"] = bool(updates["require_intern_signal"])
    sheet = data.setdefault("google_sheet", {})
    if not isinstance(sheet, dict):
        sheet = {}
        data["google_sheet"] = sheet
    if "spreadsheet_id" in updates:
        sheet["spreadsheet_id"] = str(updates["spreadsheet_id"] or "").strip()
    if "worksheet" in updates:
        sheet["worksheet"] = str(updates["worksheet"] or "Applications").strip() or "Applications"
    imap = data.setdefault("imap", {})
    smtp = data.setdefault("smtp", {})
    if isinstance(imap, dict) and "imap_username" in updates:
        imap["username"] = str(updates["imap_username"] or "").strip()
    if isinstance(smtp, dict) and "smtp_username" in updates:
        smtp["username"] = str(updates["smtp_username"] or "").strip()
    config_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def bootstrap(config_path: Path) -> dict:
    config = materialize_config(config_path)
    profile = profile_to_dict(load_profile(config.profile_path))
    store = _store(config)
    try:
        applications = [_brief(item) for item in store.list_applications()]
        summary = summarize(store.list_applications(), store.count_seen())
    finally:
        store.close()
    public_summary = {}
    for key, value in summary.items():
        if isinstance(value, list):
            public_summary[key] = [list(item) if isinstance(item, tuple) else item for item in value]
        else:
            public_summary[key] = value
    return {
        "profile": profile,
        "settings": _settings(config),
        "listings": load_listings(config.listings_file),
        "applications": applications,
        "summary": public_summary,
        "statuses": sorted(MARK_STATUSES),
    }


def application_detail(config: AppConfig, application_id: str) -> dict:
    store = _store(config)
    try:
        application = store.get(application_id)
        if application is None:
            raise ValueError("No application with that id.")
        packet_path = Path(config.data_dir) / "packets" / f"{application.id}.txt"
        packet = packet_path.read_text(encoding="utf-8") if packet_path.is_file() else application.cover_letter
        try:
            answers = json.loads(application.answers_json or "{}")
        except json.JSONDecodeError:
            answers = {}
        detail = _brief(application)
        detail["packet"] = packet
        detail["answers"] = answers
        return detail
    finally:
        store.close()


def update_application(config: AppConfig, application_id: str, payload: dict) -> dict:
    status = str(payload.get("status") or "").strip()
    if status not in MARK_STATUSES:
        raise ValueError("Choose a status from the list.")
    store = _store(config)
    try:
        application = store.get(application_id)
        if application is None:
            raise ValueError("No application with that id.")
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        application.status = status
        application.status_updated_at = now
        if status == "applied" and not application.applied_at:
            application.applied_at = now
            application.submit_method = application.submit_method or "packet"
        if isinstance(payload.get("notes"), str):
            application.notes = payload["notes"].strip()
        store.save(application)
        sync_trackers(config, store)
        _write_reports(config, store)
        return _brief(application)
    finally:
        store.close()


class DashboardServer(ThreadingHTTPServer):
    def __init__(self, server_address, config_path: Path):
        self.config_path = Path(config_path)
        self.lock = threading.Lock()
        super().__init__(server_address, DashboardHandler)


class DashboardHandler(BaseHTTPRequestHandler):
    server: DashboardServer

    def log_message(self, fmt: str, *args) -> None:
        return

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        try:
            if path == "/favicon.ico":
                self.send_response(204)
                self.end_headers()
                return
            if path in {"/", "/index.html"}:
                self._bytes(200, PAGE.read_bytes(), "text/html; charset=utf-8")
                return
            if path == "/api/bootstrap":
                with self.server.lock:
                    self._json(200, bootstrap(self.server.config_path))
                return
            if path.startswith("/api/applications/"):
                application_id = path.removeprefix("/api/applications/").strip("/")
                with self.server.lock:
                    self._json(200, application_detail(materialize_config(self.server.config_path), application_id))
                return
            self._json(404, {"error": "Not found."})
        except ValueError as exc:
            self._json(400, {"error": str(exc)})
        except Exception as exc:
            self._json(500, {"error": str(exc)})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            payload = self._read_json()
            config_path = self.server.config_path
            with self.server.lock:
                if path == "/api/profile":
                    profile = profile_from_dict(payload)
                    config = materialize_config(config_path)
                    save_profile(config.profile_path, profile)
                    self._json(200, {"profile": profile_to_dict(profile)})
                    return
                if path == "/api/settings":
                    save_settings(config_path, payload)
                    self._json(200, {"settings": _settings(materialize_config(config_path))})
                    return
                if path == "/api/listings":
                    config = materialize_config(config_path)
                    jobs = save_listings(config.listings_file, payload.get("jobs") if isinstance(payload, dict) else None)
                    self._json(200, {"listings": jobs})
                    return
                if path == "/api/run":
                    result = execute_search(materialize_config(config_path))
                    result.pop("report", None)
                    self._json(200, result)
                    return
                if path.startswith("/api/applications/"):
                    application_id = path.removeprefix("/api/applications/").strip("/")
                    updated = update_application(materialize_config(config_path), application_id, payload)
                    self._json(200, {"application": updated, "summary": _summary(materialize_config(config_path))})
                    return
            self._json(404, {"error": "Not found."})
        except ValueError as exc:
            self._json(400, {"error": str(exc)})
        except Exception as exc:
            self._json(500, {"error": str(exc)})

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length > 1_000_000:
            raise ValueError("That update is too large.")
        raw = self.rfile.read(length) if length else b"{}"
        payload = json.loads(raw.decode("utf-8") or "{}")
        if not isinstance(payload, dict):
            raise ValueError("Send a JSON object.")
        return payload

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self._bytes(status, body, "application/json; charset=utf-8")

    def _bytes(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def serve_dashboard(host: str, port: int, config_path: Path, *, open_browser: bool = False, background: bool = False):
    if host not in LOCAL_HOSTS:
        raise ValueError("The dashboard stays on this computer. Use 127.0.0.1.")
    path = Path(config_path)
    if not path.is_file():
        root = workspace_root(path)
        init_workspace(root)
    if not path.is_file():
        raise ValueError(f"No config at {path}. Run init from the project folder.")
    server = DashboardServer((host, port), path)
    if background:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        return server
    url = f"http://{host}:{server.server_address[1]}"
    print(f"Internship dashboard: {url}")
    print("Edit your profile and listings in the browser, then press Run search. Ctrl+C stops it.")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
    finally:
        server.server_close()
    return server
