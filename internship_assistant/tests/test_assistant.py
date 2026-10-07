"""Offline tests for matching, drafting, tracking, email classification, and the CLI."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

from internship_assistant.cli import main
from internship_assistant.config import load_config
from internship_assistant.discover import parse_ashby, parse_feed, parse_greenhouse, parse_json_feed, parse_lever
from internship_assistant.draft import draft_application
from internship_assistant.inbox import classify_message, fetch_imap_messages, match_application, parse_rfc822
from internship_assistant.mailer import SmtpSender, build_application_message
from internship_assistant.matcher import score_job
from internship_assistant.models import Application, Experience, InboundMail, JobPosting, JobQuestion, Profile, Project
from internship_assistant.pipeline import run_cycle
from internship_assistant.profile import load_profile, profile_from_resume_text, years_experience
from internship_assistant.report import render_html, summarize
from internship_assistant.sheets import SHEET_HEADERS, CsvTracker, GoogleSheetTracker, application_row, row_from_updated_range
from internship_assistant.store import Store
from internship_assistant.textutil import extract_apply_email, mentioned


def student(**overrides) -> Profile:
    profile = Profile(
        full_name="Sam Rivera",
        first_name="Sam",
        last_name="Rivera",
        email="sam.rivera@university.edu",
        phone="555-0100",
        location="Austin, TX",
        willing_to_relocate=True,
        willing_remote=True,
        preferred_locations=["Austin"],
        work_authorization="Authorized to work in the US",
        needs_sponsorship=False,
        school="State University",
        degree="B.S.",
        major="Computer Science",
        graduation_date="2027-05",
        start_date="2026-05",
        term="Summer 2026",
        links={"github": "https://github.com/samrivera"},
        skills=["Python", "SQL", "Java"],
        coursework=["Data Structures", "Algorithms"],
        projects=[
            Project(
                name="Campus Planner",
                description="built a scheduler for exams",
                technologies=["Python", "Flask"],
            )
        ],
        interests=["software engineering"],
        resume_path="resume.pdf",
    )
    for key, value in overrides.items():
        setattr(profile, key, value)
    return profile


def posting(**overrides) -> JobPosting:
    job = JobPosting(
        source="listings",
        company="Northwind Labs",
        title="Software Engineering Intern",
        location="Austin, TX",
        url="https://jobs.northwind.test/intern",
        description=(
            "Software engineering internship using Python and SQL. "
            "Coursework in data structures and algorithms is relevant."
        ),
        external_id="northwind",
        apply_email="jobs@northwind.test",
        apply_url="https://jobs.northwind.test/intern",
    )
    for key, value in overrides.items():
        setattr(job, key, value)
    return job


class MatchAndDraftTests(unittest.TestCase):
    def test_student_without_a_job_is_zero_years(self):
        self.assertEqual(years_experience([]), 0)
        worked = [Experience(company="Help Desk", title="Tutor", start="2024-01", end="2025-01")]
        self.assertEqual(years_experience(worked), 1.0)

    def test_java_does_not_match_javascript(self):
        self.assertFalse(mentioned("Java", "JavaScript internship"))
        self.assertTrue(mentioned("Java", "Java and SQL"))

    def test_internship_scores_above_unrelated_and_senior_roles(self):
        profile = student()
        good = score_job(profile, posting())
        self.assertTrue(good.eligible)
        self.assertGreaterEqual(good.score, 40)
        self.assertIn("Python", good.matched_skills)
        self.assertIn("SQL", good.matched_skills)
        self.assertNotIn("Java", good.matched_skills)

        marketing = score_job(
            profile,
            posting(
                company="Litware",
                title="Marketing Intern",
                description="Social campaigns, copywriting, and event planning.",
                external_id="litware",
                apply_email=None,
            ),
        )
        self.assertTrue(marketing.eligible)
        self.assertLess(marketing.score, 40)

        senior = score_job(
            profile,
            posting(
                title="Senior Software Engineer",
                description="Requires 5+ years of professional experience.",
                external_id="senior",
            ),
        )
        self.assertFalse(senior.eligible)
        self.assertEqual(senior.reason, "not_an_internship")

        program_lead = score_job(
            profile,
            posting(
                title="Head of Internship Programs",
                description="Manage the university recruiting program.",
                external_id="program",
            ),
        )
        self.assertFalse(program_lead.eligible)

    def test_cover_letter_uses_only_resume_facts(self):
        profile = student()
        draft = draft_application(profile, posting(), ["Python", "SQL"])
        self.assertIn("Campus Planner", draft.cover_letter)
        self.assertIn("do not have full-time industry experience yet", draft.cover_letter)
        self.assertEqual(draft.answers["Years of experience"], "0")
        self.assertNotIn("Google", draft.cover_letter)
        self.assertNotIn("I worked at", draft.cover_letter)

        experienced = student(
            experience=[Experience(company="Campus Help Desk", title="Tutor", start="2024-01", end="2025-01", description="Tutored Python.")]
        )
        experienced_draft = draft_application(experienced, posting(), ["Python"])
        self.assertIn("Campus Help Desk", experienced_draft.cover_letter)
        self.assertNotIn("do not have full-time industry experience yet", experienced_draft.cover_letter)
        self.assertEqual(experienced_draft.answers["Years of experience"], "1.0")

    def test_required_questions_stay_blank_when_the_resume_does_not_answer_them(self):
        profile = student()
        draft = draft_application(
            profile,
            posting(),
            ["Python"],
            questions=[
                JobQuestion("Will you now or in the future require sponsorship?", required=True),
                JobQuestion("What is your GPA?", required=True),
                JobQuestion("How did you hear about us?", required=True),
            ],
        )
        self.assertEqual(draft.answers["Will you now or in the future require sponsorship?"], "No")
        self.assertIn("What is your GPA?", draft.unanswered_required)
        self.assertNotIn("GPA", draft.answers)

        profile.saved_answers = []
        from internship_assistant.models import SavedAnswer

        profile.saved_answers = [SavedAnswer("how did you hear", "Career fair")]
        answered = draft_application(
            profile,
            posting(),
            ["Python"],
            questions=[JobQuestion("How did you hear about us?", required=True)],
        )
        self.assertEqual(answered.answers["How did you hear about us?"], "Career fair")
        self.assertEqual(answered.unanswered_required, [])

    def test_resume_text_import_keeps_review_on(self):
        text = """
        Name: Sam Rivera
        Email: sam.rivera@university.edu
        School: State University
        Degree: B.S.
        Major: Computer Science
        Graduation: 2027-05
        Skills: Python, SQL
        Coursework: Data Structures, Algorithms
        Sponsorship: no
        Authorization: Authorized to work in the US

        Project: Campus Planner
        Technologies: Python, Flask
        Built a scheduler for exams.

        Experience:
        Role: Tutor
        Company: Campus Help Desk
        Dates: 2024-01 to 2025-01
        Helped students with Python.
        """
        profile = profile_from_resume_text(text)
        self.assertTrue(profile.needs_review)
        self.assertFalse(profile.example)
        self.assertEqual(profile.needs_sponsorship, False)
        self.assertEqual(profile.projects[0].name, "Campus Planner")
        self.assertEqual(profile.experience[0].company, "Campus Help Desk")
        self.assertEqual(years_experience(profile.experience), 1.0)


class DiscoveryTests(unittest.TestCase):
    def test_public_board_parsers_and_apply_email(self):
        greenhouse = parse_greenhouse(
            {
                "jobs": [
                    {
                        "id": 5,
                        "title": "Software Engineering Intern",
                        "absolute_url": "https://boards.greenhouse.io/acme/jobs/5",
                        "location": {"name": "Remote"},
                        "content": "<p>Please submit your resume to jobs@acme.test</p>",
                    }
                ]
            },
            "Acme",
            "acme",
        )
        self.assertEqual(greenhouse[0].company, "Acme")
        self.assertEqual(greenhouse[0].apply_email, "jobs@acme.test")
        self.assertNotIn("<p>", greenhouse[0].description)

        lever = parse_lever(
            [
                {
                    "id": "abc",
                    "text": "Software Engineer",
                    "categories": {"location": "Remote", "commitment": "Intern"},
                    "descriptionPlain": "Build tools.",
                    "hostedUrl": "https://jobs.lever.co/acme/abc",
                    "applyUrl": "https://jobs.lever.co/acme/abc/apply",
                }
            ],
            "Acme",
            "acme",
        )
        self.assertIn("Intern", lever[0].description)
        self.assertIn("Remote", lever[0].location)

        ashby = parse_ashby(
            {
                "jobs": [
                    {"id": "hidden", "title": "Secret Intern", "isListed": False, "employmentType": "Intern"},
                    {
                        "id": "shown",
                        "title": "Software Intern",
                        "employmentType": "Intern",
                        "isRemote": True,
                        "location": "New York",
                        "descriptionPlain": "Python internship.",
                        "jobUrl": "https://jobs.ashbyhq.com/acme/shown",
                    },
                ]
            },
            "Acme",
            "acme",
        )
        self.assertEqual([job.external_id for job in ashby], ["shown"])
        self.assertIn("Remote", ashby[0].location)

        feed = parse_feed(
            b"""<?xml version="1.0"?>
            <rss><channel><item>
              <title>Research Intern</title>
              <link>https://university.example/intern</link>
              <description>Summer research internship.</description>
              <guid>research-1</guid>
            </item></channel></rss>""",
            "Career center",
        )
        self.assertEqual(feed[0].title, "Research Intern")
        self.assertEqual(feed[0].external_id, "research-1")

        listed = parse_json_feed(
            {"jobs": [{"company": "Acme", "title": "Intern", "description": "mailto:jobs@acme.test", "id": "1"}]}
        )
        self.assertEqual(listed[0].apply_email, "jobs@acme.test")
        self.assertEqual(extract_apply_email("Questions? email hr@acme.test"), None)


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.resume = self.root / "resume.pdf"
        self.resume.write_bytes(b"%PDF-1.4 resume")
        self.store = Store(self.root / "applications.db")
        self.addCleanup(self.store.close)
        self.now = datetime(2026, 3, 2, 9, 0, 0)

    def jobs(self):
        return [
            posting(),
            posting(
                company="Packet Co",
                title="Software Engineering Intern",
                external_id="packet",
                apply_email=None,
                url="https://jobs.packet.test/intern",
                apply_url="https://jobs.packet.test/intern",
            ),
            posting(
                company="Contoso",
                title="Backend Intern",
                location="Remote",
                external_id="contoso",
                apply_email="jobs@contoso.test",
                description="Backend software engineering internship using Python and SQL.",
                url="https://jobs.contoso.test/intern",
            ),
            posting(
                company="Fabrikam",
                title="Senior Software Engineer",
                external_id="senior",
                description="Requires 5+ years of professional experience.",
                apply_email="jobs@fabrikam.test",
            ),
            posting(
                company="Litware",
                title="Marketing Intern",
                external_id="marketing",
                description="Social campaigns and event planning.",
                apply_email=None,
            ),
        ]

    def cycle(self, jobs, smtp, profile=None, cap=1, messages=None):
        profile = profile or student()
        return run_cycle(
            profile=profile,
            store=self.store,
            jobs=jobs,
            now=self.now,
            packet_dir=self.root / "packets",
            resume_path=str(self.resume),
            resume_exists=True,
            from_email=profile.email,
            auto_apply_email=True,
            min_match_score=40,
            daily_apply_cap=cap,
            require_intern_signal=True,
            exclude_title_keywords=["senior", "staff", "principal", "director"],
            smtp_send=smtp,
            inbox_messages=messages or [],
        )

    def test_sends_the_best_email_application_and_stops_at_the_cap(self):
        sent = []

        def smtp(message):
            sent.append(message)

        interview = InboundMail(
            sender="recruiting@northwind.test",
            subject="Northwind Labs interview invitation",
            body="We would like to invite you to interview next week.",
            received_at="Mon, 2 Mar 2026 15:00:00 +0000",
        )
        result = self.cycle(self.jobs(), smtp, messages=[interview])
        self.assertEqual(result.sent, 1)
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0]["To"], "jobs@northwind.test")
        body = sent[0].get_body(preferencelist=("plain",)).get_content()
        self.assertIn("Campus Planner", body)
        self.assertEqual(self.store.count_seen(), 5)
        applications = {item.company: item for item in self.store.list_applications()}
        self.assertEqual(set(applications), {"Northwind Labs", "Packet Co", "Contoso"})
        self.assertEqual(applications["Northwind Labs"].status, "interview")
        self.assertEqual(applications["Packet Co"].status, "ready_to_submit")
        self.assertIn("no apply-by-email", applications["Packet Co"].notes)
        self.assertIn("Daily cap", applications["Contoso"].notes)
        self.assertTrue((self.root / "packets" / f"{applications['Northwind Labs'].id}.txt").is_file())

        again = self.cycle(self.jobs(), smtp, messages=[interview])
        self.assertEqual(again.new_applications, 0)
        self.assertEqual(again.sent, 0)
        self.assertEqual(len(sent), 1)

    def test_sample_profile_and_example_addresses_are_not_emailed(self):
        sent = []
        placeholder = student(example=True, needs_review=True, email="you@example.com", full_name="Your Name")
        self.cycle([posting()], sent.append, profile=placeholder, cap=5)
        self.assertEqual(sent, [])
        saved = self.store.list_applications()[0]
        self.assertEqual(saved.status, "needs_input")

        real = student()
        self.cycle(
            [posting(company="Sample Co", external_id="sample", apply_email="jobs@sample.example")],
            sent.append,
            profile=real,
            cap=5,
        )
        self.assertEqual(sent, [])
        sample = self.store.get_by_job_key("listings:sample")
        self.assertIsNotNone(sample)
        self.assertEqual(sample.status, "needs_input")
        self.assertIn("example.com", sample.notes)

    def test_failed_send_can_be_retried_once(self):
        def boom(_message):
            raise RuntimeError("smtp down")

        first = self.cycle([posting()], boom, cap=5)
        self.assertEqual(first.sent, 0)
        failed = self.store.list_applications()[0]
        self.assertEqual(failed.status, "send_failed")

        sent = []
        second = self.cycle([posting()], sent.append, cap=5)
        self.assertEqual(second.sent, 1)
        self.assertEqual(self.store.get(failed.id).status, "applied")

    def test_counts_every_application(self):
        sent = []
        self.cycle(self.jobs(), sent.append, messages=[
            InboundMail(
                sender="recruiting@northwind.test",
                subject="Northwind Labs interview invitation",
                body="We invite you to interview.",
            )
        ])
        summary = summarize(self.store.list_applications(), self.store.count_seen())
        self.assertEqual(summary["seen"], 5)
        self.assertEqual(summary["tracked"], 3)
        self.assertEqual(summary["submitted"], 1)
        self.assertEqual(summary["interviews"], 1)
        self.assertEqual(summary["response_rate"], 100.0)
        self.assertEqual(summary["offers"], 0)
        report = render_html(summary, self.store.list_applications())
        self.assertIn("Northwind Labs", report)
        hostile = self.store.list_applications()[0]
        hostile.company = "<script>"
        page = render_html(summary, [hostile])
        self.assertIn("&lt;script&gt;", page)
        self.assertNotIn("<script>", page)


class MailAndSheetTests(unittest.TestCase):
    def test_classifier_prefers_rejection_over_the_word_interview(self):
        self.assertEqual(
            classify_message("Update", "We will not be moving forward with an interview."),
            "rejected",
        )
        self.assertEqual(
            classify_message("Hello", "We would like to invite you to interview on Friday."),
            "interview",
        )
        self.assertEqual(classify_message("Next step", "Please complete the CodeSignal assessment."), "assessment")
        self.assertEqual(classify_message("Offer", "We are pleased to offer you the internship."), "offer")
        self.assertIsNone(classify_message("Newsletter", "Our lab published a new paper."))

    def test_inbox_fetch_reads_rfc822(self):
        message = EmailMessage()
        message["From"] = "recruiting@northwind.test"
        message["Subject"] = "Northwind Labs interview invitation"
        message["Date"] = "Mon, 2 Mar 2026 15:00:00 +0000"
        message.set_content("We would like to invite you to interview.")
        raw = message.as_bytes()

        class FakeImap:
            def __init__(self, host, port):
                self.host = host

            def login(self, username, password):
                self.username = username

            def select(self, folder):
                return "OK", []

            def search(self, charset, *criteria):
                return "OK", [b"1"]

            def fetch(self, message_id, spec):
                return "OK", [(b"1 (RFC822)", raw)]

            def logout(self):
                return "OK", []

        messages = fetch_imap_messages(
            host="imap.test",
            port=993,
            username="sam@university.edu",
            password="app-password",
            connection_factory=FakeImap,
            now=datetime(2026, 3, 2),
        )
        self.assertEqual(len(messages), 1)
        self.assertEqual(classify_message(messages[0].subject, messages[0].body), "interview")
        parsed = parse_rfc822(raw)
        application = Application(
            id="abc",
            job_key="listings:northwind",
            company="Northwind Labs",
            title="Intern",
            location="",
            source="listings",
            url="",
            apply_email="",
            apply_url="",
            match_score=70,
            matched_skills="Python",
            missing_skills="",
            status="applied",
            submit_method="email",
            cover_letter="",
            answers_json="{}",
            needs_input="",
            email_evidence="",
            notes="",
            sheet_row=None,
            send_attempts=1,
            send_day="2026-03-02",
            found_at="2026-03-02T09:00:00",
            applied_at="2026-03-02T09:00:00",
            status_updated_at="2026-03-02T09:00:00",
        )
        self.assertEqual(match_application(parsed, [application]).id, "abc")

    def test_smtp_sender_uses_starttls(self):
        seen = {}

        class FakeSMTP:
            def __init__(self, host, port, timeout=30):
                seen["init"] = (host, port)

            def ehlo(self):
                seen.setdefault("ehlo", 0)
                seen["ehlo"] += 1

            def starttls(self):
                seen["starttls"] = True

            def login(self, username, password):
                seen["login"] = username

            def send_message(self, message):
                seen["to"] = message["To"]

            def quit(self):
                seen["quit"] = True

        message = build_application_message(
            from_email="sam@university.edu",
            to_email="jobs@northwind.test",
            full_name="Sam Rivera",
            role="Intern",
            company="Northwind Labs",
            cover_letter="Hello",
        )
        SmtpSender("smtp.test", 587, "sam@university.edu", "secret", factory=FakeSMTP).send(message)
        self.assertTrue(seen["starttls"])
        self.assertEqual(seen["login"], "sam@university.edu")
        self.assertEqual(seen["to"], "jobs@northwind.test")

    def test_csv_and_google_sheet_track_every_application(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "applications.db")
            application = Application(
                id="abc123",
                job_key="listings:1",
                company="Northwind Labs",
                title="Software Engineering Intern",
                location="Austin, TX",
                source="listings",
                url="https://jobs.northwind.test/intern",
                apply_email="jobs@northwind.test",
                apply_url="https://jobs.northwind.test/intern",
                match_score=73.3,
                matched_skills="Python, SQL",
                missing_skills="docker",
                status="applied",
                submit_method="email",
                cover_letter="Hello",
                answers_json="{}",
                needs_input="",
                email_evidence="",
                notes="Emailed the application with the resume attached.",
                sheet_row=None,
                send_attempts=1,
                send_day="2026-03-02",
                found_at="2026-03-02T09:00:00",
                applied_at="2026-03-02T09:00:00",
                status_updated_at="2026-03-02T09:00:00",
            )
            store.save(application)
            csv_path = Path(tmp) / "applications.csv"
            CsvTracker(csv_path).sync(store.list_applications())
            text = csv_path.read_text(encoding="utf-8")
            self.assertTrue(text.startswith(",".join(SHEET_HEADERS)))
            self.assertIn("Northwind Labs", text)
            self.assertEqual(len(application_row(application)), len(SHEET_HEADERS))

            class FakeHttp:
                def __init__(self):
                    self.calls = []
                    self.header = None

                def request_json(self, method, url, headers, body):
                    self.calls.append((method, url, body))
                    if ":batchUpdate" in url:
                        return 200, {}
                    if method == "GET":
                        return 200, {"values": [self.header] if self.header else []}
                    if method == "PUT" and "A1%3AR1" in url:
                        self.header = body["values"][0]
                        return 200, {"updatedRange": "Applications!A1:R1"}
                    if method == "POST" and ":append" in url:
                        return 200, {"updates": {"updatedRange": "Applications!A2:R2"}}
                    if method == "PUT":
                        return 200, {"updatedRange": "Applications!A2:R2"}
                    return 500, {"error": url}

            http = FakeHttp()
            tracker = GoogleSheetTracker("sheet-id", "Applications", "token", http)
            placed = tracker.sync([application])
            self.assertEqual(placed, [("abc123", 2)])
            self.assertEqual(application.sheet_row, 2)
            appends = [url for method, url, _body in http.calls if ":append" in url]
            self.assertEqual(len(appends), 1)
            tracker.sync([application])
            appends = [url for method, url, _body in http.calls if ":append" in url]
            self.assertEqual(len(appends), 1)
            self.assertEqual(row_from_updated_range("'Applications'!A12:R12"), 12)
            store.close()


class CliTests(unittest.TestCase):
    def test_init_run_show_and_mark_stay_local(self):
        with tempfile.TemporaryDirectory() as tmp:
            previous = os.getcwd()
            os.chdir(tmp)
            try:
                self.assertEqual(main(["init"]), 0)
                profile_path = Path("data/profile.json")
                original = profile_path.read_text(encoding="utf-8")
                profile = json.loads(original)
                profile["full_name"] = "Edited Name"
                profile_path.write_text(json.dumps(profile), encoding="utf-8")
                self.assertEqual(main(["init"]), 0)
                self.assertEqual(json.loads(profile_path.read_text(encoding="utf-8"))["full_name"], "Edited Name")

                self.assertEqual(main(["run"]), 0)
                report = Path("data/report.txt").read_text(encoding="utf-8")
                self.assertIn("Applications tracked: 2", report)
                self.assertIn("Waiting on you", report)
                csv_text = Path("data/applications.csv").read_text(encoding="utf-8")
                self.assertIn("Northwind Labs", csv_text)
                self.assertNotIn("Fabrikam", csv_text)

                application_id = report.split("[")[-2].split("]")[0]
                self.assertEqual(main(["show", application_id]), 0)
                self.assertEqual(main(["mark", application_id, "applied"]), 0)
                updated = Path("data/report.txt").read_text(encoding="utf-8")
                self.assertIn("Submitted: 1", updated)

                resume = Path("resume.txt")
                resume.write_text(
                    "Name: Sam Rivera\nEmail: sam.rivera@university.edu\nSkills: Python\n",
                    encoding="utf-8",
                )
                self.assertEqual(main(["import-resume", "resume.txt"]), 1)
                self.assertEqual(main(["import-resume", "resume.txt", "--force"]), 0)
                imported = load_profile("data/profile.json")
                self.assertEqual(imported.full_name, "Sam Rivera")
                self.assertTrue(imported.needs_review)
                config = load_config("data/config.json")
                self.assertFalse(config.auto_apply_email)
                self.assertEqual(config.daily_apply_cap, 8)
            finally:
                os.chdir(previous)


if __name__ == "__main__":
    unittest.main()
