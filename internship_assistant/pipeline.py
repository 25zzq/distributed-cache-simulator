"""Discover, score, draft, email, and update statuses for one search pass."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from internship_assistant.draft import draft_application
from internship_assistant.inbox import inbox_updates
from internship_assistant.mailer import build_application_message
from internship_assistant.matcher import score_job
from internship_assistant.models import Application, InboundMail, JobPosting, Profile
from internship_assistant.policy import decide
from internship_assistant.store import Store

SendMail = Callable[[object], None]


@dataclass
class RunResult:
    discovered: int = 0
    new_applications: int = 0
    sent: int = 0
    held: int = 0
    inbox_updates: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _application(
    *,
    job: JobPosting,
    score: float,
    matched: list[str],
    missing: list[str],
    status: str,
    submit_method: str,
    cover_letter: str,
    answers: dict,
    needs_input: list[str],
    notes: str,
    now_iso: str,
) -> Application:
    return Application(
        id=uuid.uuid4().hex[:12],
        job_key=job.key,
        company=job.company,
        title=job.title,
        location=job.location,
        source=job.source,
        url=job.apply_url or job.url,
        apply_email=job.apply_email or "",
        apply_url=job.apply_url or job.url,
        match_score=score,
        matched_skills=", ".join(matched),
        missing_skills=", ".join(missing),
        status=status,
        submit_method=submit_method,
        cover_letter=cover_letter,
        answers_json=json.dumps(answers, indent=2),
        needs_input="; ".join(needs_input),
        email_evidence="",
        notes=notes,
        sheet_row=None,
        send_attempts=0,
        send_day="",
        found_at=now_iso,
        applied_at="",
        status_updated_at=now_iso,
    )


def _write_packet(packet_dir: Path, application: Application) -> None:
    packet_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "id": application.id,
        "company": application.company,
        "title": application.title,
        "url": application.url,
        "apply_email": application.apply_email,
        "status": application.status,
        "match_score": application.match_score,
        "answers": json.loads(application.answers_json),
        "needs_input": application.needs_input,
        "cover_letter": application.cover_letter,
    }
    (packet_dir / f"{application.id}.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    (packet_dir / f"{application.id}.txt").write_text(
        application.cover_letter if not application.answers_json else _packet_text(application),
        encoding="utf-8",
    )


def _packet_text(application: Application) -> str:
    answers = json.loads(application.answers_json)
    lines = [f"{label}: {value}" for label, value in answers.items()]
    if application.needs_input:
        lines.extend(["", "Still needs your answer:", application.needs_input])
    if application.notes:
        lines.extend(["", "Notes:", application.notes])
    lines.extend(["", "Cover letter:", application.cover_letter.strip(), ""])
    if application.url:
        lines.append(f"Apply link: {application.url}")
    return "\n".join(lines)


def _send(profile: Profile, application: Application, resume_path: str, from_email: str, smtp_send: SendMail) -> None:
    message = build_application_message(
        from_email=from_email,
        to_email=application.apply_email,
        full_name=profile.full_name,
        role=application.title,
        company=application.company,
        cover_letter=application.cover_letter,
        resume_path=resume_path,
    )
    smtp_send(message)


def run_cycle(
    *,
    profile: Profile,
    store: Store,
    jobs: list[JobPosting],
    now: datetime,
    packet_dir: str | Path,
    resume_path: str,
    resume_exists: bool,
    from_email: str,
    auto_apply_email: bool,
    min_match_score: float,
    daily_apply_cap: int,
    require_intern_signal: bool,
    exclude_title_keywords: list[str],
    smtp_send: SendMail | None,
    inbox_messages: list[InboundMail] | None = None,
) -> RunResult:
    result = RunResult(discovered=len(jobs))
    now_iso = now.isoformat(timespec="seconds")
    day = now.date().isoformat()
    packets = Path(packet_dir)
    smtp_configured = smtp_send is not None

    for stuck in store.list_status("sending"):
        if smtp_send is None:
            stuck.status = "send_failed"
            stuck.notes = "A send was reserved, then SMTP was unavailable."
            stuck.status_updated_at = now_iso
            store.save(stuck)
            _write_packet(packets, stuck)
            result.errors.append(f"{stuck.company}: reserved send could not be finished")
            continue
        try:
            _send(profile, stuck, resume_path, from_email, smtp_send)
        except Exception as exc:
            stuck.status = "send_failed"
            stuck.notes = f"Email failed: {exc}"
            stuck.status_updated_at = now_iso
            store.save(stuck)
            _write_packet(packets, stuck)
            result.errors.append(f"{stuck.company}: {exc}")
            continue
        stuck.status = "applied"
        stuck.applied_at = stuck.applied_at or now_iso
        stuck.status_updated_at = now_iso
        stuck.notes = "Emailed the application with the resume attached."
        stuck.submit_method = "email"
        store.save(stuck)
        _write_packet(packets, stuck)
        result.sent += 1

    for failed in store.list_status("send_failed"):
        if smtp_send is None or failed.send_attempts >= 2:
            continue
        if not store.claim_for_send(failed.id, day, daily_apply_cap, now_iso):
            continue
        current = store.get(failed.id) or failed
        try:
            _send(profile, current, resume_path, from_email, smtp_send)
        except Exception as exc:
            current.status = "send_failed"
            current.notes = f"Email failed: {exc}"
            current.status_updated_at = now_iso
            store.save(current)
            _write_packet(packets, current)
            result.errors.append(f"{current.company}: {exc}")
            continue
        current.status = "applied"
        current.applied_at = current.applied_at or now_iso
        current.status_updated_at = now_iso
        current.submit_method = "email"
        current.notes = "Emailed the application with the resume attached."
        store.save(current)
        _write_packet(packets, current)
        result.sent += 1

    ranked: list[tuple[float, list[str], list[str], JobPosting]] = []
    seen_keys: set[str] = set()
    for job in jobs:
        if job.key in seen_keys:
            continue
        seen_keys.add(job.key)
        if store.get_by_job_key(job.key):
            continue
        match = score_job(
            profile,
            job,
            require_intern_signal=require_intern_signal,
            exclude_title_keywords=exclude_title_keywords,
        )
        if not match.eligible or match.score < min_match_score:
            reason = match.reason if not match.eligible else "below_score"
            store.upsert_seen(job.key, job.company, job.title, match.score, reason, now_iso)
            continue
        ranked.append((match.score, match.matched_skills, match.missing_skills, job))
    ranked.sort(key=lambda item: item[0], reverse=True)

    for score, matched, missing, job in ranked:
        draft = draft_application(profile, job, matched)
        decision = decide(
            profile,
            job,
            draft,
            auto_apply_email=auto_apply_email,
            resume_exists=resume_exists,
            smtp_configured=smtp_configured,
        )
        application = _application(
            job=job,
            score=score,
            matched=matched,
            missing=missing,
            status=decision.status,
            submit_method=decision.submit_method,
            cover_letter=draft.cover_letter,
            answers=draft.answers,
            needs_input=draft.unanswered_required,
            notes=decision.note,
            now_iso=now_iso,
        )
        store.save(application)
        store.upsert_seen(job.key, job.company, job.title, score, "tracked", now_iso)
        _write_packet(packets, application)
        result.new_applications += 1

        if decision.action != "send":
            result.held += 1
            continue
        if smtp_send is None or not store.claim_for_send(application.id, day, daily_apply_cap, now_iso):
            application.notes = (
                f"Daily cap of {daily_apply_cap} sent applications was already reached. "
                "The packet is saved and this one was not emailed."
            )
            application.status = "ready_to_submit"
            store.save(application)
            _write_packet(packets, application)
            result.held += 1
            continue
        try:
            _send(profile, application, resume_path, from_email, smtp_send)
        except Exception as exc:
            current = store.get(application.id) or application
            current.status = "send_failed"
            current.notes = f"Email failed: {exc}"
            current.status_updated_at = now_iso
            store.save(current)
            _write_packet(packets, current)
            result.errors.append(f"{application.company}: {exc}")
            result.held += 1
            continue
        current = store.get(application.id) or application
        current.status = "applied"
        current.applied_at = now_iso
        current.status_updated_at = now_iso
        current.submit_method = "email"
        current.notes = "Emailed the application with the resume attached."
        store.save(current)
        _write_packet(packets, current)
        result.sent += 1

    updates = inbox_updates(list(inbox_messages or []), store.list_applications())
    for application, status, evidence in updates:
        application.status_updated_at = now_iso
        application.email_evidence = evidence
        application.notes = f"Inbox classified this as {status}."
        store.save(application)
        _write_packet(packets, application)
        result.inbox_updates.append(f"{application.company}: {status}")
    return result
