"""Fill application answers from resume facts. Unanswered required questions stay blank."""

from __future__ import annotations

import re

from internship_assistant.models import ApplicationDraft, JobPosting, JobQuestion, Profile
from internship_assistant.profile import years_experience

_QUESTION_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"sponsor", re.I), "sponsorship"),
    (re.compile(r"authoriz|eligible to work|legally authorized|work authorization", re.I), "authorization"),
    (re.compile(r"gpa|grade point", re.I), "gpa"),
    (re.compile(r"graduat", re.I), "graduation"),
    (re.compile(r"github", re.I), "github"),
    (re.compile(r"linkedin", re.I), "linkedin"),
    (re.compile(r"portfolio|personal site|website|url", re.I), "website"),
    (re.compile(r"phone", re.I), "phone"),
    (re.compile(r"why .* (role|company|position|intern)|why are you interested|why do you want", re.I), "why"),
    (re.compile(r"years of (?:professional |work |relevant )?experience|how many years", re.I), "years"),
    (re.compile(r"start date|when can you start|available to start|availability", re.I), "start"),
    (re.compile(r"school|university|college", re.I), "school"),
    (re.compile(r"degree|major", re.I), "degree"),
    (re.compile(r"hear about|how did you hear", re.I), "saved"),
]


def _years_text(profile: Profile) -> str:
    value = years_experience(profile.experience)
    if value == 0:
        return "0"
    return str(value)


def _why(profile: Profile, job: JobPosting, matched_skills: list[str]) -> str:
    sentences: list[str] = []
    if matched_skills:
        shown = ", ".join(matched_skills[:6])
        sentences.append(
            f"The skills from my resume that match the {job.title} role at {job.company} are {shown}."
        )
    if profile.projects:
        project = profile.projects[0]
        detail = project.description.strip().rstrip(".")
        tech = f" ({', '.join(project.technologies)})" if project.technologies else ""
        sentences.append(f"One project I can point to is {project.name}{tech}: {detail}.")
    if profile.coursework:
        sentences.append("Relevant coursework includes " + ", ".join(profile.coursework[:5]) + ".")
    if not profile.experience:
        sentences.append("I do not have full-time industry experience yet, so this internship is how I would get it.")
    if not sentences:
        sentences.append(f"I am a {profile.major or 'computer science'} student applying for the {job.title} role.")
    return " ".join(sentences)


def _saved_answer(profile: Profile, question: str) -> str | None:
    lowered = question.lower()
    for saved in profile.saved_answers:
        if saved.match.lower() in lowered:
            return saved.answer
    return None


def _answer_for(kind: str, profile: Profile, job: JobPosting, matched_skills: list[str], question: str) -> str | None:
    saved = _saved_answer(profile, question)
    if saved:
        return saved
    if kind == "sponsorship":
        if profile.needs_sponsorship is True:
            return "Yes"
        if profile.needs_sponsorship is False:
            return "No"
        return None
    if kind == "authorization":
        return profile.work_authorization or None
    if kind == "gpa":
        return profile.gpa
    if kind == "graduation":
        return profile.graduation_date or None
    if kind == "github":
        return profile.links.get("github") or None
    if kind == "linkedin":
        return profile.links.get("linkedin") or None
    if kind == "website":
        return profile.links.get("portfolio") or profile.links.get("website") or profile.links.get("github") or None
    if kind == "phone":
        return profile.phone or None
    if kind == "why":
        return _why(profile, job, matched_skills)
    if kind == "years":
        return _years_text(profile)
    if kind == "start":
        return profile.start_date or profile.term or None
    if kind == "school":
        return profile.school or None
    if kind == "degree":
        parts = [part for part in (profile.degree, profile.major) if part]
        return ", ".join(parts) or None
    if kind == "saved":
        return None
    return None


def _rule_kind(question: str) -> str | None:
    for pattern, kind in _QUESTION_RULES:
        if pattern.search(question):
            return kind
    return None


def cover_letter(profile: Profile, job: JobPosting, matched_skills: list[str]) -> str:
    projects = []
    for project in profile.projects[:3]:
        detail = project.description.strip().rstrip(".")
        tech = f" Technologies: {', '.join(project.technologies)}." if project.technologies else ""
        projects.append(f"- {project.name}: {detail}.{tech}")
    project_block = "\n".join(projects) if projects else "- None listed yet."
    roles = []
    for role in profile.experience[:3]:
        when = " ".join(part for part in (role.start, "to", role.end or "present") if part)
        roles.append(f"- {role.title} at {role.company} ({when}). {role.description}".strip())
    if roles:
        experience_block = "Experience:\n" + "\n".join(roles)
    else:
        experience_block = (
            "Experience:\n"
            "I do not have full-time industry experience yet. "
            "The projects and coursework below are the work I can point to."
        )
    if matched_skills:
        skill_line = f"Skills from my resume that show up in this role: {', '.join(matched_skills)}."
    elif profile.skills:
        skill_line = f"Skills from my resume: {', '.join(profile.skills[:8])}."
    else:
        skill_line = "Skills from my resume: see the coursework below."
    coursework = ", ".join(profile.coursework) if profile.coursework else "not listed"
    authorization = profile.work_authorization.strip()
    degree = " ".join(part for part in (profile.degree, "in", profile.major) if part).replace(" in in ", " in ")
    school_line = f"I am a {degree} student at {profile.school}".strip()
    if profile.graduation_date:
        school_line += f", graduating {profile.graduation_date}"
    school_line += "."
    links = [url for url in (profile.links.get("github"), profile.links.get("linkedin"), profile.links.get("portfolio")) if url]
    link_line = f"Links: {', '.join(links)}\n" if links else ""
    return (
        f"Dear {job.company} hiring team,\n\n"
        f"{school_line} I am applying for the {job.title} role"
        f"{f' ({profile.term})' if profile.term else ''}.\n\n"
        f"{experience_block}\n\n"
        f"Projects:\n{project_block}\n\n"
        f"Coursework: {coursework}.\n"
        f"{skill_line}\n\n"
        f"{_why(profile, job, matched_skills)}\n\n"
        f"I can start {profile.start_date or profile.term or 'on the posted start date'}."
        f"{(' ' + authorization) if authorization else ''}\n"
        f"{link_line}\n"
        f"Thank you,\n{profile.full_name}\n"
    )


def _standard_answers(profile: Profile, job: JobPosting, matched_skills: list[str]) -> dict[str, str]:
    answers = {
        "First name": profile.display_first,
        "Last name": profile.display_last,
        "Full name": profile.full_name,
        "Email": profile.email,
        "Phone": profile.phone,
        "Location": profile.location,
        "School": profile.school,
        "Degree": profile.degree,
        "Major": profile.major,
        "Graduation date": profile.graduation_date,
        "Earliest start date": profile.start_date,
        "Term": profile.term,
        "Years of experience": _years_text(profile),
        "Why this role": _why(profile, job, matched_skills),
    }
    if profile.gpa:
        answers["GPA"] = profile.gpa
    if profile.work_authorization:
        answers["Work authorization"] = profile.work_authorization
    if profile.needs_sponsorship is True:
        answers["Needs sponsorship"] = "Yes"
    elif profile.needs_sponsorship is False:
        answers["Needs sponsorship"] = "No"
    for label, key in (("GitHub", "github"), ("LinkedIn", "linkedin"), ("Portfolio", "portfolio")):
        if profile.links.get(key):
            answers[label] = profile.links[key]
    return {key: value for key, value in answers.items() if value}


def _copy_block(answers: dict[str, str], letter: str, unanswered: list[str]) -> str:
    lines = [f"{label}: {value}" for label, value in answers.items()]
    if unanswered:
        lines.append("")
        lines.append("Still needs your answer:")
        lines.extend(f"- {item}" for item in unanswered)
    lines.append("")
    lines.append("Cover letter:")
    lines.append(letter.strip())
    return "\n".join(lines).strip() + "\n"


def draft_application(
    profile: Profile,
    job: JobPosting,
    matched_skills: list[str] | None = None,
    questions: list[JobQuestion] | None = None,
) -> ApplicationDraft:
    matched = list(matched_skills or [])
    answers = _standard_answers(profile, job, matched)
    unanswered: list[str] = []
    for question in questions if questions is not None else job.questions:
        kind = _rule_kind(question.text)
        answer = _answer_for(kind, profile, job, matched, question.text) if kind else _saved_answer(profile, question.text)
        if answer:
            answers[question.text] = answer
        elif question.required:
            unanswered.append(question.text)
    letter = cover_letter(profile, job, matched)
    return ApplicationDraft(
        cover_letter=letter,
        answers=answers,
        unanswered_required=unanswered,
        copy_block=_copy_block(answers, letter, unanswered),
    )
