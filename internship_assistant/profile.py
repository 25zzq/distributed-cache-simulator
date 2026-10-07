"""Load a resume profile and estimate years from dated experience only."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from internship_assistant.models import Experience, Profile, Project, SavedAnswer
from internship_assistant.textutil import is_example_address

EXAMPLE_NAMES = {"your name", "alex example", "jane doe", "john doe"}


def _month_index(value: str) -> int | None:
    raw = (value or "").strip()
    if not raw:
        return None
    parts = raw.replace("/", "-").split("-")
    try:
        year = int(parts[0])
        month = int(parts[1]) if len(parts) > 1 else 1
    except ValueError:
        return None
    if year < 1970 or not 1 <= month <= 12:
        return None
    return year * 12 + (month - 1)


def years_experience(experience: list[Experience], today: date | None = None) -> float:
    """Sum dated roles. An empty work history is zero years, not a guess."""
    today = today or date.today()
    today_index = today.year * 12 + (today.month - 1)
    total = 0
    for role in experience:
        start = _month_index(role.start)
        if start is None:
            continue
        end = _month_index(role.end)
        if end is None:
            end = today_index
        if end < start:
            continue
        total += end - start
    return round(total / 12, 1)


def profile_is_placeholder(profile: Profile) -> bool:
    if profile.example or profile.needs_review:
        return True
    if is_example_address(profile.email):
        return True
    return profile.full_name.strip().lower() in EXAMPLE_NAMES


def _projects(raw: object) -> list[Project]:
    projects: list[Project] = []
    if not isinstance(raw, list):
        return projects
    for item in raw:
        if not isinstance(item, dict):
            continue
        techs = item.get("technologies") or []
        projects.append(
            Project(
                name=str(item.get("name") or "").strip(),
                description=str(item.get("description") or "").strip(),
                technologies=[str(tech).strip() for tech in techs if str(tech).strip()],
                url=str(item.get("url") or "").strip(),
            )
        )
    return [project for project in projects if project.name]


def _experience(raw: object) -> list[Experience]:
    roles: list[Experience] = []
    if not isinstance(raw, list):
        return roles
    for item in raw:
        if not isinstance(item, dict):
            continue
        company = str(item.get("company") or "").strip()
        title = str(item.get("title") or "").strip()
        if not company and not title:
            continue
        roles.append(
            Experience(
                company=company,
                title=title,
                start=str(item.get("start") or "").strip(),
                end=str(item.get("end") or "").strip(),
                description=str(item.get("description") or "").strip(),
            )
        )
    return roles


def _saved_answers(raw: object) -> list[SavedAnswer]:
    answers: list[SavedAnswer] = []
    if not isinstance(raw, list):
        return answers
    for item in raw:
        if not isinstance(item, dict):
            continue
        match = str(item.get("match") or "").strip()
        answer = str(item.get("answer") or "").strip()
        if match and answer:
            answers.append(SavedAnswer(match=match, answer=answer))
    return answers


def _optional_bool(value: object) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"yes", "true", "y", "1"}:
        return True
    if text in {"no", "false", "n", "0"}:
        return False
    return None


def profile_from_dict(data: dict) -> Profile:
    if not isinstance(data, dict):
        raise ValueError("Profile must be a JSON object.")
    full_name = str(data.get("full_name") or "").strip()
    email = str(data.get("email") or "").strip()
    if not full_name or not email:
        raise ValueError("Profile needs full_name and email.")
    gpa = data.get("gpa")
    gpa_text = None if gpa is None or str(gpa).strip() == "" else str(gpa).strip()
    links = data.get("links") or {}
    if not isinstance(links, dict):
        links = {}
    return Profile(
        full_name=full_name,
        email=email,
        first_name=str(data.get("first_name") or "").strip(),
        last_name=str(data.get("last_name") or "").strip(),
        phone=str(data.get("phone") or "").strip(),
        location=str(data.get("location") or "").strip(),
        willing_to_relocate=bool(data.get("willing_to_relocate") or False),
        willing_remote=True if data.get("willing_remote") is None else bool(data.get("willing_remote")),
        preferred_locations=[str(item).strip() for item in (data.get("preferred_locations") or []) if str(item).strip()],
        work_authorization=str(data.get("work_authorization") or "").strip(),
        needs_sponsorship=_optional_bool(data.get("needs_sponsorship")),
        school=str(data.get("school") or "").strip(),
        degree=str(data.get("degree") or "").strip(),
        major=str(data.get("major") or "").strip(),
        graduation_date=str(data.get("graduation_date") or "").strip(),
        gpa=gpa_text,
        start_date=str(data.get("start_date") or "").strip(),
        term=str(data.get("term") or "").strip(),
        links={str(key): str(value).strip() for key, value in links.items() if str(value).strip()},
        skills=[str(item).strip() for item in (data.get("skills") or []) if str(item).strip()],
        coursework=[str(item).strip() for item in (data.get("coursework") or []) if str(item).strip()],
        projects=_projects(data.get("projects")),
        experience=_experience(data.get("experience")),
        interests=[str(item).strip() for item in (data.get("interests") or []) if str(item).strip()],
        resume_path=str(data.get("resume_path") or "").strip(),
        saved_answers=_saved_answers(data.get("saved_answers")),
        example=bool(data.get("example") or False),
        needs_review=bool(data.get("needs_review") or False),
    )


def profile_to_dict(profile: Profile) -> dict:
    return {
        "example": profile.example,
        "needs_review": profile.needs_review,
        "full_name": profile.full_name,
        "first_name": profile.first_name,
        "last_name": profile.last_name,
        "email": profile.email,
        "phone": profile.phone,
        "location": profile.location,
        "willing_to_relocate": profile.willing_to_relocate,
        "willing_remote": profile.willing_remote,
        "preferred_locations": list(profile.preferred_locations),
        "work_authorization": profile.work_authorization,
        "needs_sponsorship": profile.needs_sponsorship,
        "school": profile.school,
        "degree": profile.degree,
        "major": profile.major,
        "graduation_date": profile.graduation_date,
        "gpa": profile.gpa,
        "start_date": profile.start_date,
        "term": profile.term,
        "links": dict(profile.links),
        "skills": list(profile.skills),
        "coursework": list(profile.coursework),
        "projects": [
            {
                "name": project.name,
                "description": project.description,
                "technologies": list(project.technologies),
                "url": project.url,
            }
            for project in profile.projects
        ],
        "experience": [
            {
                "company": role.company,
                "title": role.title,
                "start": role.start,
                "end": role.end,
                "description": role.description,
            }
            for role in profile.experience
        ],
        "interests": list(profile.interests),
        "resume_path": profile.resume_path,
        "saved_answers": [{"match": item.match, "answer": item.answer} for item in profile.saved_answers],
    }


def load_profile(path: str | Path) -> Profile:
    with open(path, encoding="utf-8") as handle:
        return profile_from_dict(json.load(handle))


def save_profile(path: str | Path, profile: Profile) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(profile_to_dict(profile), indent=2) + "\n", encoding="utf-8")


def profile_from_resume_text(text: str) -> Profile:
    """Turn a labeled text resume into a profile that still needs your review.

    Recognized labels: Name, Email, Phone, Location, School, Degree, Major,
    Graduation, GPA, Start, Term, Authorization, Sponsorship, Skills,
    Coursework, Interests, GitHub, LinkedIn, Portfolio, Resume.
    Projects start with a 'Project:' line, then Technologies and a description.
    Experience starts with 'Experience:' and one role per 'Role:' line.
    """
    fields: dict[str, str] = {}
    projects: list[Project] = []
    roles: list[Experience] = []
    mode = "fields"
    project: Project | None = None
    project_lines: list[str] = []
    role: Experience | None = None
    role_lines: list[str] = []

    def finish_project() -> None:
        nonlocal project, project_lines
        if project is not None:
            project.description = " ".join(line.strip() for line in project_lines if line.strip())
            if project.name:
                projects.append(project)
        project = None
        project_lines = []

    def finish_role() -> None:
        nonlocal role, role_lines
        if role is not None:
            role.description = " ".join(line.strip() for line in role_lines if line.strip())
            if role.company or role.title:
                roles.append(role)
        role = None
        role_lines = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lower = line.lower()
        if lower.startswith("project:"):
            finish_role()
            finish_project()
            mode = "project"
            project = Project(name=line.split(":", 1)[1].strip(), description="")
            continue
        if lower.startswith("experience:"):
            finish_project()
            finish_role()
            mode = "experience"
            continue
        if lower.startswith("role:") and mode == "experience":
            finish_role()
            role = Experience(company="", title=line.split(":", 1)[1].strip())
            continue
        if mode == "project" and project is not None and lower.startswith("technologies:"):
            techs = line.split(":", 1)[1]
            project.technologies = [part.strip() for part in techs.split(",") if part.strip()]
            continue
        if mode == "project" and project is not None and lower.startswith("url:"):
            project.url = line.split(":", 1)[1].strip()
            continue
        if mode == "experience" and role is not None and lower.startswith("company:"):
            role.company = line.split(":", 1)[1].strip()
            continue
        if mode == "experience" and role is not None and lower.startswith("dates:"):
            span = line.split(":", 1)[1].strip()
            if " to " in span.lower():
                start, end = span.split("to", 1) if " to " not in span else span.split(" to ", 1)
                role.start = start.strip()
                role.end = "" if end.strip().lower() in {"present", "current", ""} else end.strip()
            continue
        if ":" in line and mode == "fields":
            label, value = line.split(":", 1)
            fields[label.strip().lower()] = value.strip()
            continue
        if mode == "project":
            project_lines.append(line)
        elif mode == "experience" and role is not None:
            role_lines.append(line)

    finish_project()
    finish_role()

    skills = [part.strip() for part in fields.get("skills", "").replace(";", ",").split(",") if part.strip()]
    coursework = [part.strip() for part in fields.get("coursework", "").replace(";", ",").split(",") if part.strip()]
    interests = [part.strip() for part in fields.get("interests", "").replace(";", ",").split(",") if part.strip()]
    links = {}
    if fields.get("github"):
        links["github"] = fields["github"]
    if fields.get("linkedin"):
        links["linkedin"] = fields["linkedin"]
    if fields.get("portfolio"):
        links["portfolio"] = fields["portfolio"]
    full_name = fields.get("name") or fields.get("full name") or ""
    first, _, last = full_name.partition(" ")
    return Profile(
        full_name=full_name or "Your Name",
        email=fields.get("email") or "you@example.com",
        first_name=first if last else "",
        last_name=last,
        phone=fields.get("phone", ""),
        location=fields.get("location", ""),
        willing_to_relocate=fields.get("relocate", "").lower() in {"yes", "true", "y"},
        willing_remote=fields.get("remote", "yes").lower() not in {"no", "false", "n"},
        preferred_locations=[part.strip() for part in fields.get("locations", "").split(",") if part.strip()],
        work_authorization=fields.get("authorization", ""),
        needs_sponsorship=_optional_bool(fields.get("sponsorship")),
        school=fields.get("school", ""),
        degree=fields.get("degree", ""),
        major=fields.get("major", ""),
        graduation_date=fields.get("graduation", ""),
        gpa=fields.get("gpa") or None,
        start_date=fields.get("start", ""),
        term=fields.get("term", ""),
        links=links,
        skills=skills,
        coursework=coursework,
        projects=projects,
        experience=roles,
        interests=interests,
        resume_path=fields.get("resume", ""),
        example=False,
        needs_review=True,
    )
