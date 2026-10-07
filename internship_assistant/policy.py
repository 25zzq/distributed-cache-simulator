"""Decide whether a matched internship can be emailed or only prepared."""

from __future__ import annotations

from internship_assistant.models import ApplicationDraft, Decision, JobPosting, Profile
from internship_assistant.profile import profile_is_placeholder
from internship_assistant.textutil import is_example_address


def decide(
    profile: Profile,
    job: JobPosting,
    draft: ApplicationDraft,
    *,
    auto_apply_email: bool,
    resume_exists: bool,
    smtp_configured: bool,
) -> Decision:
    blockers: list[str] = list(draft.unanswered_required)
    if not resume_exists:
        blockers.append("Add your resume file at resume_path before sending.")
    if profile_is_placeholder(profile):
        blockers.append("Replace the sample profile, then set example and needs_review to false.")
    if job.apply_email and is_example_address(job.apply_email):
        blockers.append("This listing uses an example.com address, so it was not emailed.")
    if blockers:
        return Decision("needs_input", "hold", "packet", " ".join(blockers))
    if job.apply_email:
        if not auto_apply_email:
            return Decision(
                "ready_to_submit",
                "packet",
                "email",
                "auto_apply_email is off. The email and packet are ready when you turn it on.",
            )
        if not smtp_configured:
            return Decision("needs_input", "hold", "email", "Add SMTP settings before email applications can send.")
        return Decision("ready_to_submit", "send", "email", "")
    return Decision(
        "ready_to_submit",
        "packet",
        "packet",
        "This listing has no apply-by-email address. Paste the packet into the employer's form, then mark it applied.",
    )
