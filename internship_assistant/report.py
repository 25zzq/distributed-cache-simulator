"""Turn the local application log into counts and a private HTML report."""

from __future__ import annotations

from collections import Counter
from datetime import datetime

from internship_assistant.models import Application
from internship_assistant.textutil import html_escape

SUBMITTED = {"applied", "assessment", "interview", "rejected", "offer"}
RESPONDED = {"assessment", "interview", "rejected", "offer"}
INTERVIEWS = {"interview", "offer"}


def _week(value: str) -> str:
    if not value:
        return "unscheduled"
    try:
        day = datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return value[:10] or "unscheduled"
    iso = day.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _rate(part: int, whole: int) -> float | None:
    if whole == 0:
        return None
    return round(100 * part / whole, 1)


def summarize(applications: list[Application], seen_count: int) -> dict:
    by_status = Counter(application.status for application in applications)
    submitted = [application for application in applications if application.status in SUBMITTED]
    responded = [application for application in submitted if application.status in RESPONDED]
    interviews = [application for application in submitted if application.status in INTERVIEWS]
    offers = [application for application in submitted if application.status == "offer"]
    weeks: Counter[str] = Counter()
    companies: Counter[str] = Counter()
    sources: Counter[str] = Counter()
    gaps: Counter[str] = Counter()
    score_total = 0.0
    for application in applications:
        companies[application.company] += 1
        sources[application.source] += 1
        weeks[_week(application.applied_at or application.found_at)] += 1
        for skill in [part.strip() for part in application.missing_skills.split(",") if part.strip()]:
            gaps[skill] += 1
    for application in submitted:
        score_total += application.match_score
    return {
        "seen": seen_count,
        "tracked": len(applications),
        "by_status": dict(by_status),
        "submitted": len(submitted),
        "awaiting_reply": by_status.get("applied", 0),
        "needs_input": by_status.get("needs_input", 0),
        "ready_to_submit": by_status.get("ready_to_submit", 0),
        "interviews": len(interviews),
        "rejections": by_status.get("rejected", 0),
        "offers": len(offers),
        "assessments": by_status.get("assessment", 0),
        "response_rate": _rate(len(responded), len(submitted)),
        "interview_rate": _rate(len(interviews), len(submitted)),
        "offer_rate": _rate(len(offers), len(submitted)),
        "average_submitted_score": round(score_total / len(submitted), 1) if submitted else None,
        "by_company": companies.most_common(),
        "by_source": sources.most_common(),
        "by_week": sorted(weeks.items()),
        "top_gaps": gaps.most_common(8),
    }


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1f}%"


def render_text(summary: dict, applications: list[Application]) -> str:
    lines = [
        "Internship search",
        f"Listings seen: {summary['seen']}",
        f"Applications tracked: {summary['tracked']}",
        f"Submitted: {summary['submitted']}",
        f"Ready for you to submit on a form: {summary['ready_to_submit']}",
        f"Waiting on you for a missing answer: {summary['needs_input']}",
        f"Waiting on a reply: {summary['awaiting_reply']}",
        f"Assessments: {summary['assessments']}",
        f"Interviews: {summary['interviews']}",
        f"Rejections: {summary['rejections']}",
        f"Offers: {summary['offers']}",
        f"Response rate: {_pct(summary['response_rate'])}",
        f"Interview rate: {_pct(summary['interview_rate'])}",
        f"Offer rate: {_pct(summary['offer_rate'])}",
        f"Average match score of submitted applications: {summary['average_submitted_score'] if summary['average_submitted_score'] is not None else 'n/a'}",
        "",
        "By status:",
    ]
    for status, count in sorted(summary["by_status"].items()):
        lines.append(f"  {status}: {count}")
    lines.append("")
    lines.append("By week:")
    for week, count in summary["by_week"]:
        lines.append(f"  {week}: {count}")
    lines.append("")
    lines.append("By source:")
    for source, count in summary["by_source"]:
        lines.append(f"  {source}: {count}")
    lines.append("")
    lines.append("By company:")
    for company, count in summary["by_company"]:
        lines.append(f"  {company}: {count}")
    if summary["top_gaps"]:
        lines.append("")
        lines.append("Skills postings asked for that are not on your resume:")
        for skill, count in summary["top_gaps"]:
            lines.append(f"  {skill}: {count}")
    lines.append("")
    lines.append("Every application:")
    if not applications:
        lines.append("  None yet.")
    for application in sorted(applications, key=lambda item: (-item.match_score, item.company, item.title)):
        lines.append(
            f"  {application.match_score:5.1f}  {application.status:<16}  {application.company} — {application.title}  [{application.id}]"
        )
    return "\n".join(lines) + "\n"


def render_html(summary: dict, applications: list[Application]) -> str:
    def card(label: str, value: object) -> str:
        return (
            "<section><p>"
            + html_escape(label)
            + "</p><strong>"
            + html_escape(value)
            + "</strong></section>"
        )

    cards = "".join(
        [
            card("Listings seen", summary["seen"]),
            card("Tracked", summary["tracked"]),
            card("Submitted", summary["submitted"]),
            card("Interviews", summary["interviews"]),
            card("Rejections", summary["rejections"]),
            card("Offers", summary["offers"]),
            card("Response rate", _pct(summary["response_rate"])),
            card("Interview rate", _pct(summary["interview_rate"])),
        ]
    )
    rows = []
    for application in sorted(applications, key=lambda item: (-item.match_score, item.company)):
        rows.append(
            "<tr>"
            + "".join(
                f"<td>{html_escape(value)}</td>"
                for value in (
                    f"{application.match_score:.1f}",
                    application.status,
                    application.company,
                    application.title,
                    application.location,
                    application.source,
                    application.applied_at or application.found_at,
                    application.notes,
                )
            )
            + "</tr>"
        )
    body_rows = "".join(rows) or "<tr><td colspan='8'>No applications yet.</td></tr>"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Internship applications</title>
<style>
body {{ font-family: Georgia, serif; margin: 2rem; color: #1c1915; background: #f7f4ee; }}
h1 {{ font-weight: normal; }}
.cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 0.75rem; }}
section {{ background: white; border: 1px solid #ddd4c4; padding: 0.75rem; }}
section p {{ margin: 0; font-size: 0.8rem; letter-spacing: 0.04em; text-transform: uppercase; }}
section strong {{ display: block; margin-top: 0.35rem; font-size: 1.4rem; }}
table {{ width: 100%; border-collapse: collapse; margin-top: 1.5rem; background: white; }}
th, td {{ text-align: left; padding: 0.45rem 0.5rem; border-bottom: 1px solid #eee6d8; vertical-align: top; }}
th {{ font-size: 0.75rem; letter-spacing: 0.04em; text-transform: uppercase; }}
</style>
</head>
<body>
<h1>Internship applications</h1>
<p>This report was generated on your machine from the local application log.</p>
<div class="cards">{cards}</div>
<table>
<thead><tr><th>Score</th><th>Status</th><th>Company</th><th>Role</th><th>Location</th><th>Source</th><th>Date</th><th>Notes</th></tr></thead>
<tbody>{body_rows}</tbody>
</table>
</body>
</html>
"""
