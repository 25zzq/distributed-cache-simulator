"""Command line for the private internship assistant."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from internship_assistant.config import AppConfig, load_config
from internship_assistant.discover import discover_jobs
from internship_assistant.inbox import fetch_imap_messages
from internship_assistant.mailer import SmtpSender
from internship_assistant.pipeline import run_cycle
from internship_assistant.profile import load_profile, profile_from_resume_text, save_profile
from internship_assistant.report import render_html, render_text, summarize
from internship_assistant.sheets import CsvTracker, GoogleSheetTracker, service_account_token
from internship_assistant.store import Store

EXAMPLES = Path(__file__).resolve().parent / "examples"
USER_AGENT = "InternshipAssistant/1.0 (personal job search)"
MARK_STATUSES = {
    "applied",
    "ready_to_submit",
    "needs_input",
    "interview",
    "assessment",
    "rejected",
    "offer",
    "withdrawn",
}


class UrlLibClient:
    def get_bytes(self, url: str) -> bytes:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.read()

    def get_json(self, url: str):
        return json.loads(self.get_bytes(url).decode("utf-8"))

    def request_json(self, method: str, url: str, headers: dict, body: dict | None):
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read().decode("utf-8")
                return response.status, json.loads(raw or "{}")
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                payload = json.loads(raw or "{}")
            except json.JSONDecodeError:
                payload = {"error": raw}
            return exc.code, payload


def _copy_example(name: str, destination: Path) -> None:
    if destination.exists():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(EXAMPLES / name, destination)


def init_workspace(root: Path | None = None) -> str:
    base = root or Path.cwd()
    data = base / "data"
    data.mkdir(parents=True, exist_ok=True)
    (data / "packets").mkdir(exist_ok=True)
    _copy_example("config.json", data / "config.json")
    _copy_example("profile.json", data / "profile.json")
    _copy_example("listings.json", data / "listings.json")
    _copy_example("env.example", data / "env.example")
    return (
        "Private workspace is in ./data (gitignored).\n"
        "Edit data/profile.json with your real resume facts, put your resume file on resume_path,\n"
        "then run: python3 -m internship_assistant run"
    )


def _store(config: AppConfig) -> Store:
    return Store(Path(config.data_dir) / "applications.db")


def _write_reports(config: AppConfig, store: Store) -> str:
    applications = store.list_applications()
    summary = summarize(applications, store.count_seen())
    text = render_text(summary, applications)
    data = Path(config.data_dir)
    data.mkdir(parents=True, exist_ok=True)
    (data / "report.txt").write_text(text, encoding="utf-8")
    (data / "report.html").write_text(render_html(summary, applications), encoding="utf-8")
    return text


def sync_trackers(config: AppConfig, store: Store, http=None) -> str:
    applications = store.list_applications()
    data = Path(config.data_dir)
    CsvTracker(data / "applications.csv").sync(applications)
    if not config.spreadsheet_id:
        return "Updated data/applications.csv. Add a spreadsheet id when you want the Google Sheet too."
    credentials = Path(config.credentials_path)
    if not credentials.is_file():
        return (
            "Updated data/applications.csv. The Google service account file is missing, "
            f"so {config.credentials_path} was not used."
        )
    token = service_account_token(str(credentials))
    tracker = GoogleSheetTracker(config.spreadsheet_id, config.worksheet, token, http or UrlLibClient())
    placed = tracker.sync(applications)
    for application_id, row_number in placed:
        application = store.get(application_id)
        if application is not None and application.sheet_row != row_number:
            application.sheet_row = row_number
            store.save(application)
    return f"Updated data/applications.csv and synced {len(placed)} rows to Google Sheets."


def _smtp(config: AppConfig, from_email: str):
    username = config.smtp_username
    password = os.environ.get(config.smtp_password_env, "")
    sender_email = config.smtp_from or from_email
    if not username or not password:
        return None, sender_email
    return SmtpSender(config.smtp_host, config.smtp_port, username, password), sender_email


def _inbox(config: AppConfig, now: datetime):
    username = config.imap_username
    password = os.environ.get(config.imap_password_env, "")
    if not username or not password:
        return [], "Inbox check skipped until IMAP username and password are set."
    messages = fetch_imap_messages(
        host=config.imap_host,
        port=config.imap_port,
        username=username,
        password=password,
        folder=config.imap_folder,
        since_days=config.imap_since_days,
        now=now,
    )
    return messages, f"Read {len(messages)} recent inbox messages."


def run_once(config: AppConfig, *, check_inbox: bool = True) -> int:
    profile = load_profile(config.profile_path)
    now = datetime.now().astimezone()
    client = UrlLibClient()
    jobs, errors = discover_jobs(
        listings_file=config.listings_file,
        json_feeds=config.json_feeds,
        rss_feeds=config.rss_feeds,
        greenhouse=config.greenhouse,
        lever=config.lever,
        ashby=config.ashby,
        get_json=client.get_json,
        get_bytes=client.get_bytes,
    )
    sender, from_email = _smtp(config, profile.email)
    inbox_messages = []
    inbox_note = "Inbox check skipped."
    if check_inbox:
        try:
            inbox_messages, inbox_note = _inbox(config, now)
        except Exception as exc:
            errors.append(f"inbox: {exc}")
            inbox_note = "Inbox check failed. See the error above."
    resume_path = profile.resume_path
    store = _store(config)
    try:
        result = run_cycle(
            profile=profile,
            store=store,
            jobs=jobs,
            now=now,
            packet_dir=Path(config.data_dir) / "packets",
            resume_path=resume_path,
            resume_exists=bool(resume_path) and Path(resume_path).is_file(),
            from_email=from_email,
            auto_apply_email=config.auto_apply_email,
            min_match_score=config.min_match_score,
            daily_apply_cap=config.daily_apply_cap,
            require_intern_signal=config.require_intern_signal,
            exclude_title_keywords=config.exclude_title_keywords,
            smtp_send=None if sender is None else sender.send,
            inbox_messages=inbox_messages,
        )
        sheet_note = sync_trackers(config, store)
        report = _write_reports(config, store)
    finally:
        store.close()
    print(inbox_note)
    print(
        f"Seen {result.discovered} listings, prepared {result.new_applications} new applications, "
        f"emailed {result.sent}."
    )
    for error in errors + result.errors:
        print(f"Error: {error}")
    for update in result.inbox_updates:
        print(f"Inbox update: {update}")
    print(sheet_note)
    print(report)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Private local internship application assistant")
    parser.add_argument("--config", default="data/config.json")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Create a private data folder and sample profile")
    sub.add_parser("run", help="Match listings, fill applications, email when allowed, update the sheet")
    sub.add_parser("stats", help="Print counts for every tracked application")
    sub.add_parser("inbox", help="Check your inbox and update application statuses")

    show = sub.add_parser("show", help="Print one filled application")
    show.add_argument("application_id")

    mark = sub.add_parser("mark", help="Update an application after you submit a form or hear back")
    mark.add_argument("application_id")
    mark.add_argument("status", choices=sorted(MARK_STATUSES))

    importer = sub.add_parser("import-resume", help="Build data/profile.json from a labeled text resume")
    importer.add_argument("resume_text")
    importer.add_argument("--force", action="store_true")

    watch = sub.add_parser("watch", help="Keep running the search on an interval")
    watch.add_argument("--interval", type=int, default=3600)
    watch.add_argument("--cycles", type=int, default=0, help="Stop after this many passes. 0 runs until you quit.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "init":
        print(init_workspace())
        return 0

    config_path = Path(args.config)
    if not config_path.is_file():
        print("No config yet. Run: python3 -m internship_assistant init")
        return 1
    config = load_config(config_path)

    if args.command == "import-resume":
        destination = Path(config.profile_path)
        if destination.exists() and not args.force:
            print(f"{destination} already exists. Re-run with --force to replace it.")
            return 1
        profile = profile_from_resume_text(Path(args.resume_text).read_text(encoding="utf-8"))
        save_profile(destination, profile)
        print(f"Wrote {destination}. Review it, set needs_review to false, then run the assistant.")
        return 0

    if args.command == "stats":
        store = _store(config)
        try:
            print(_write_reports(config, store))
        finally:
            store.close()
        return 0

    if args.command == "show":
        store = _store(config)
        try:
            application = store.get(args.application_id)
        finally:
            store.close()
        if application is None:
            print("No application with that id.")
            return 1
        packet = Path(config.data_dir) / "packets" / f"{application.id}.txt"
        if packet.is_file():
            print(packet.read_text(encoding="utf-8"))
        else:
            print(application.cover_letter)
        return 0

    if args.command == "mark":
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        store = _store(config)
        try:
            application = store.get(args.application_id)
            if application is None:
                print("No application with that id.")
                return 1
            application.status = args.status
            application.status_updated_at = now
            if args.status == "applied" and not application.applied_at:
                application.applied_at = now
                application.submit_method = application.submit_method or "packet"
            application.notes = f"Status set to {args.status} by hand."
            store.save(application)
            print(sync_trackers(config, store))
            print(_write_reports(config, store))
        finally:
            store.close()
        return 0

    if args.command == "inbox":
        now = datetime.now().astimezone()
        try:
            messages, note = _inbox(config, now)
        except Exception as exc:
            print(f"Error: inbox: {exc}")
            return 1
        store = _store(config)
        try:
            from internship_assistant.inbox import inbox_updates
            from internship_assistant.pipeline import _write_packet

            updates = inbox_updates(messages, store.list_applications())
            packet_dir = Path(config.data_dir) / "packets"
            for application, status, evidence in updates:
                application.status_updated_at = now.isoformat(timespec="seconds")
                application.email_evidence = evidence
                application.notes = f"Inbox classified this as {status}."
                store.save(application)
                _write_packet(packet_dir, application)
                print(f"Inbox update: {application.company}: {status}")
            print(note)
            print(sync_trackers(config, store))
            print(_write_reports(config, store))
        finally:
            store.close()
        return 0

    if args.command == "run":
        return run_once(config, check_inbox=True)

    if args.command == "watch":
        cycles = args.cycles
        completed = 0
        while cycles == 0 or completed < cycles:
            run_once(config, check_inbox=True)
            completed += 1
            if cycles != 0 and completed >= cycles:
                break
            time.sleep(max(args.interval, 1))
        return 0

    parser.print_help()
    return 1
