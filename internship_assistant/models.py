"""Data records for the local internship assistant."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field


def _job_key(source: str, external_id: str, company: str, title: str, url: str) -> str:
    if external_id:
        return f"{source}:{external_id}"
    digest = hashlib.sha256(f"{company}|{title}|{url}".encode()).hexdigest()[:16]
    return f"{source}:{digest}"


@dataclass
class Project:
    name: str
    description: str
    technologies: list[str] = field(default_factory=list)
    url: str = ""


@dataclass
class Experience:
    company: str
    title: str
    start: str = ""
    end: str = ""
    description: str = ""


@dataclass
class SavedAnswer:
    match: str
    answer: str


@dataclass
class Profile:
    full_name: str
    email: str
    first_name: str = ""
    last_name: str = ""
    phone: str = ""
    location: str = ""
    willing_to_relocate: bool = False
    willing_remote: bool = True
    preferred_locations: list[str] = field(default_factory=list)
    work_authorization: str = ""
    needs_sponsorship: bool | None = None
    school: str = ""
    degree: str = ""
    major: str = ""
    graduation_date: str = ""
    gpa: str | None = None
    start_date: str = ""
    term: str = ""
    links: dict[str, str] = field(default_factory=dict)
    skills: list[str] = field(default_factory=list)
    coursework: list[str] = field(default_factory=list)
    projects: list[Project] = field(default_factory=list)
    experience: list[Experience] = field(default_factory=list)
    interests: list[str] = field(default_factory=list)
    resume_path: str = ""
    saved_answers: list[SavedAnswer] = field(default_factory=list)
    example: bool = False
    needs_review: bool = False

    @property
    def display_first(self) -> str:
        if self.first_name:
            return self.first_name
        return self.full_name.split(" ", 1)[0] if self.full_name else ""

    @property
    def display_last(self) -> str:
        if self.last_name:
            return self.last_name
        parts = self.full_name.split(" ", 1)
        return parts[1] if len(parts) > 1 else ""


@dataclass
class JobQuestion:
    text: str
    required: bool = False


@dataclass
class JobPosting:
    source: str
    company: str
    title: str
    location: str
    url: str
    description: str
    external_id: str = ""
    apply_email: str | None = None
    apply_url: str | None = None
    questions: list[JobQuestion] = field(default_factory=list)

    @property
    def key(self) -> str:
        return _job_key(self.source, self.external_id, self.company, self.title, self.url)


@dataclass
class MatchResult:
    eligible: bool
    score: float
    reason: str
    matched_skills: list[str] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)
    years_required: int | None = None


@dataclass
class ApplicationDraft:
    cover_letter: str
    answers: dict[str, str]
    unanswered_required: list[str]
    copy_block: str


@dataclass
class Application:
    id: str
    job_key: str
    company: str
    title: str
    location: str
    source: str
    url: str
    apply_email: str
    apply_url: str
    match_score: float
    matched_skills: str
    missing_skills: str
    status: str
    submit_method: str
    cover_letter: str
    answers_json: str
    needs_input: str
    email_evidence: str
    notes: str
    sheet_row: int | None
    send_attempts: int
    send_day: str
    found_at: str
    applied_at: str
    status_updated_at: str


@dataclass
class InboundMail:
    sender: str
    subject: str
    body: str
    received_at: str = ""


@dataclass
class Decision:
    status: str
    action: str
    submit_method: str
    note: str
