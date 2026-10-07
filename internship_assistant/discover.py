"""Read internship listings from local files and public job-board APIs."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from collections.abc import Callable
from pathlib import Path

from internship_assistant.models import JobPosting, JobQuestion
from internship_assistant.textutil import extract_apply_email, html_to_text

GetJson = Callable[[str], object]


def _questions(raw: object) -> list[JobQuestion]:
    questions: list[JobQuestion] = []
    if not isinstance(raw, list):
        return questions
    for item in raw:
        if isinstance(item, str):
            text = item.strip()
            if text:
                questions.append(JobQuestion(text=text, required=False))
            continue
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or item.get("label") or item.get("question") or "").strip()
        if not text:
            continue
        required = bool(item.get("required") or False)
        questions.append(JobQuestion(text=text, required=required))
    return questions


def _with_email(job: JobPosting) -> JobPosting:
    if not job.apply_email:
        job.apply_email = extract_apply_email(job.description, job.url)
    return job


def parse_json_feed(payload: object, source: str = "json") -> list[JobPosting]:
    if isinstance(payload, dict):
        rows = payload.get("jobs") or payload.get("listings") or []
    elif isinstance(payload, list):
        rows = payload
    else:
        return []
    jobs: list[JobPosting] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        company = str(item.get("company") or "").strip()
        if not title or not company:
            continue
        description = str(item.get("description") or "")
        url = str(item.get("url") or item.get("apply_url") or "").strip()
        jobs.append(
            _with_email(
                JobPosting(
                    source=str(item.get("source") or source),
                    company=company,
                    title=title,
                    location=str(item.get("location") or "").strip(),
                    url=url,
                    description=description,
                    external_id=str(item.get("id") or "").strip(),
                    apply_email=(str(item.get("apply_email")).strip() if item.get("apply_email") else None),
                    apply_url=str(item.get("apply_url") or url).strip() or None,
                    questions=_questions(item.get("questions")),
                )
            )
        )
    return jobs


def parse_greenhouse(payload: object, company: str, token: str) -> list[JobPosting]:
    rows = payload.get("jobs", []) if isinstance(payload, dict) else []
    jobs: list[JobPosting] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        location = item.get("location") or {}
        if isinstance(location, dict):
            location_name = str(location.get("name") or "")
        else:
            location_name = str(location or "")
        url = str(item.get("absolute_url") or "")
        jobs.append(
            _with_email(
                JobPosting(
                    source="greenhouse",
                    company=company or token,
                    title=str(item.get("title") or ""),
                    location=location_name,
                    url=url,
                    description=html_to_text(str(item.get("content") or "")),
                    external_id=str(item.get("id") or ""),
                    apply_url=url or None,
                )
            )
        )
    return [job for job in jobs if job.title]


def parse_lever(payload: object, company: str, site: str) -> list[JobPosting]:
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = payload.get("postings") or payload.get("data") or []
    else:
        rows = []
    jobs: list[JobPosting] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        categories = item.get("categories") or {}
        location = ""
        commitment = ""
        if isinstance(categories, dict):
            raw_location = categories.get("location") or ""
            location = raw_location.get("name") if isinstance(raw_location, dict) else str(raw_location or "")
            if not location:
                all_locations = categories.get("allLocations") or []
                location = ", ".join(str(part) for part in all_locations)
            commitment = str(categories.get("commitment") or "")
        description = str(item.get("descriptionPlain") or html_to_text(str(item.get("description") or "")))
        if commitment:
            description = f"{description}\nCommitment: {commitment}"
        workplace = str(item.get("workplaceType") or "")
        if workplace == "remote" and "remote" not in location.lower():
            location = f"{location} Remote".strip()
        url = str(item.get("hostedUrl") or "")
        apply_url = str(item.get("applyUrl") or url)
        jobs.append(
            _with_email(
                JobPosting(
                    source="lever",
                    company=company or site,
                    title=str(item.get("text") or item.get("title") or ""),
                    location=location,
                    url=url or apply_url,
                    description=description,
                    external_id=str(item.get("id") or ""),
                    apply_url=apply_url or None,
                )
            )
        )
    return [job for job in jobs if job.title]


def parse_ashby(payload: object, company: str, board: str) -> list[JobPosting]:
    rows: list = []
    if isinstance(payload, dict):
        rows = payload.get("jobs") or payload.get("jobPostings") or []
    jobs: list[JobPosting] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        if item.get("isListed") is False:
            continue
        employment = str(item.get("employmentType") or "")
        description = str(
            item.get("descriptionPlain")
            or item.get("description")
            or html_to_text(str(item.get("jobDescription") or ""))
        )
        if employment:
            description = f"{description}\nEmployment type: {employment}"
        location = str(item.get("location") or "")
        if item.get("isRemote") and "remote" not in location.lower():
            location = f"{location} Remote".strip()
        url = str(item.get("jobUrl") or item.get("applyUrl") or "")
        jobs.append(
            _with_email(
                JobPosting(
                    source="ashby",
                    company=company or board,
                    title=str(item.get("title") or ""),
                    location=location,
                    url=url,
                    description=description,
                    external_id=str(item.get("id") or ""),
                    apply_url=str(item.get("applyUrl") or url) or None,
                )
            )
        )
    return [job for job in jobs if job.title]


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def parse_feed(xml_bytes: bytes, source_name: str) -> list[JobPosting]:
    root = ET.fromstring(xml_bytes)
    jobs: list[JobPosting] = []
    for node in root.iter():
        if _local_name(node.tag) not in {"item", "entry"}:
            continue
        title = ""
        link = ""
        description = ""
        guid = ""
        for child in list(node):
            name = _local_name(child.tag)
            text = "".join(child.itertext()).strip()
            if name == "title":
                title = text
            elif name in {"description", "summary", "content"} and not description:
                description = html_to_text(text)
            elif name == "link":
                link = child.attrib.get("href") or text
            elif name in {"guid", "id"} and not guid:
                guid = text
        if not title:
            continue
        jobs.append(
            _with_email(
                JobPosting(
                    source=source_name,
                    company=source_name,
                    title=title,
                    location="",
                    url=link,
                    description=description,
                    external_id=guid or link,
                    apply_url=link or None,
                )
            )
        )
    return jobs


def load_listings_file(path: str | Path) -> list[JobPosting]:
    file_path = Path(path)
    if not file_path.is_file():
        return []
    return parse_json_feed(json.loads(file_path.read_text(encoding="utf-8")), source="listings")


def discover_jobs(
    *,
    listings_file: str,
    json_feeds: list[str],
    rss_feeds: list[dict],
    greenhouse: list[dict],
    lever: list[dict],
    ashby: list[dict],
    get_json: GetJson,
    get_bytes: Callable[[str], bytes],
) -> tuple[list[JobPosting], list[str]]:
    jobs: list[JobPosting] = []
    errors: list[str] = []
    try:
        jobs.extend(load_listings_file(listings_file))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        errors.append(f"listings file: {exc}")

    def pull(label: str, loader) -> None:
        try:
            jobs.extend(loader())
        except Exception as exc:  # one bad board should not stop the rest
            errors.append(f"{label}: {exc}")

    for url in json_feeds:
        pull(url, lambda url=url: parse_json_feed(get_json(url), source="json"))
    for feed in rss_feeds:
        url = str(feed.get("url") or "")
        name = str(feed.get("name") or url)
        if url:
            pull(name, lambda url=url, name=name: parse_feed(get_bytes(url), name))
    for board in greenhouse:
        token = str(board.get("token") or "").strip()
        company = str(board.get("company") or token)
        if not token:
            continue
        url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"
        pull(f"greenhouse:{token}", lambda url=url, company=company, token=token: parse_greenhouse(get_json(url), company, token))
    for board in lever:
        site = str(board.get("site") or "").strip()
        company = str(board.get("company") or site)
        if not site:
            continue
        url = f"https://api.lever.co/v0/postings/{site}?mode=json"
        pull(f"lever:{site}", lambda url=url, company=company, site=site: parse_lever(get_json(url), company, site))
    for board in ashby:
        name = str(board.get("board") or "").strip()
        company = str(board.get("company") or name)
        if not name:
            continue
        url = f"https://api.ashbyhq.com/posting-api/job-board/{name}"
        pull(f"ashby:{name}", lambda url=url, company=company, name=name: parse_ashby(get_json(url), company, name))

    deduped: list[JobPosting] = []
    seen: set[str] = set()
    for job in jobs:
        if job.key in seen:
            continue
        seen.add(job.key)
        deduped.append(job)
    return deduped, errors
