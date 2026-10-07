"""Score internship listings against a resume without inventing experience."""

from __future__ import annotations

import re

from internship_assistant.models import JobPosting, MatchResult, Profile
from internship_assistant.textutil import mentioned

INTERN_RE = re.compile(r"\b(intern|internship|co-op|coop|new grad|new-grad)\b", re.IGNORECASE)
INTERN_ROLE_RE = re.compile(r"\bintern\b", re.IGNORECASE)
SENIOR_RE = re.compile(
    r"\b(senior|staff|principal|director|vp|vice president|head|manager|lead)\b",
    re.IGNORECASE,
)
YEAR_RANGE_RE = re.compile(
    r"(\d+)\s*(?:-|–|to)\s*(\d+)\s*\+?\s*(?:years?|yrs)\s+(?:of\s+)?"
    r"(?:professional\s+|relevant\s+|work\s+|industry\s+)?experience",
    re.IGNORECASE,
)
YEAR_SINGLE_RE = re.compile(
    r"(\d+)\s*\+?\s*(?:years?|yrs)\s+(?:of\s+)?"
    r"(?:professional\s+|relevant\s+|work\s+|industry\s+)?experience",
    re.IGNORECASE,
)

# Skills worth surfacing as gaps. Matching uses the student's own skill list.
KNOWN_SKILLS = (
    "python", "java", "c++", "c#", "javascript", "typescript", "go", "rust", "sql",
    "react", "node", "django", "flask", "spring", "aws", "gcp", "azure", "docker",
    "kubernetes", "git", "linux", "html", "css", "pandas", "numpy", "tensorflow",
    "pytorch", "spark", "hadoop", "kotlin", "swift", "ruby", "php", "scala",
    "mongodb", "postgres", "mysql", "redis", "graphql", "rest", "android", "ios",
)


def years_required(text: str) -> int | None:
    ranges = [(int(match.group(1)), int(match.group(2))) for match in YEAR_RANGE_RE.finditer(text or "")]
    if ranges:
        return min(start for start, _end in ranges)
    singles = [int(match.group(1)) for match in YEAR_SINGLE_RE.finditer(text or "")]
    if singles:
        return min(singles)
    return None


def title_is_internship(title: str) -> bool:
    return INTERN_RE.search(title or "") is not None


def is_internship_posting(title: str, description: str, *, require_intern_signal: bool) -> bool:
    # "Head of Internship Programs" is a leadership job. "Software Engineering Intern" is a student role.
    if SENIOR_RE.search(title or "") and not INTERN_ROLE_RE.search(title or ""):
        return False
    if title_is_internship(title):
        return True
    if not require_intern_signal:
        return True
    opening = (description or "")[:500]
    return INTERN_RE.search(opening) is not None


def _location_points(profile: Profile, location: str) -> float:
    loc = (location or "").lower()
    if profile.willing_remote and "remote" in loc:
        return 10
    for preferred in profile.preferred_locations:
        token = preferred.lower().strip()
        if token and token in loc:
            return 10
    if profile.willing_to_relocate:
        return 6
    if not profile.preferred_locations:
        return 5
    return 0


def _interest_points(profile: Profile, text: str) -> float:
    lowered = text.lower()
    for interest in profile.interests:
        token = interest.lower().strip()
        if token and token in lowered:
            return 5
    return 0


def score_job(
    profile: Profile,
    job: JobPosting,
    *,
    require_intern_signal: bool = True,
    exclude_title_keywords: list[str] | None = None,
) -> MatchResult:
    title = job.title or ""
    description = job.description or ""
    text = f"{title}\n{description}\n{job.location}"
    exclude = [word.lower() for word in (exclude_title_keywords or [])]
    title_lower = title.lower()
    if any(word and word in title_lower for word in exclude) and not title_is_internship(title):
        return MatchResult(False, 0, "title_excluded", years_required=years_required(description))
    if not is_internship_posting(title, description, require_intern_signal=require_intern_signal):
        return MatchResult(False, 0, "not_an_internship", years_required=years_required(description))

    required = years_required(description)
    if required is not None and required >= 3 and not title_is_internship(title):
        return MatchResult(False, 0, "years_required", years_required=required)

    matched = [skill for skill in profile.skills if mentioned(skill, text)]
    skill_frac = (len(matched) / len(profile.skills)) if profile.skills else 0
    techs: list[str] = []
    for project in profile.projects:
        for tech in project.technologies:
            if tech not in techs:
                techs.append(tech)
    project_hits = [tech for tech in techs if mentioned(tech, text)]
    project_frac = (len(project_hits) / len(techs)) if techs else 0
    course_hits = [course for course in profile.coursework if course.lower() in text.lower()]
    course_frac = (len(course_hits) / len(profile.coursework)) if profile.coursework else 0
    score = (
        skill_frac * 50
        + project_frac * 20
        + course_frac * 15
        + _location_points(profile, job.location)
        + _interest_points(profile, f"{title}\n{description}")
    )
    if required is not None and required >= 2 and (title_is_internship(title) or INTERN_RE.search(description[:500])):
        score -= 10
    score = round(max(0, min(100, score)), 1)

    profile_skills = {skill.lower() for skill in profile.skills}
    missing = [
        skill
        for skill in KNOWN_SKILLS
        if mentioned(skill, text) and skill not in profile_skills and not any(mentioned(skill, owned) for owned in profile.skills)
    ]
    reason = "matched" if score else "low_overlap"
    return MatchResult(
        eligible=True,
        score=score,
        reason=reason,
        matched_skills=matched,
        missing_skills=missing[:8],
        years_required=required,
    )
