"""The local dashboard edits the same files the search run uses."""

from __future__ import annotations

import json
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from internship_assistant.cli import init_workspace
from internship_assistant.dashboard import serve_dashboard


def _request(url: str, payload: dict | None = None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    method = "GET" if payload is None else "POST"
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    last_error = None
    for _ in range(20):
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                body = response.read().decode("utf-8")
                if response.headers.get_content_type() == "application/json":
                    return response.status, json.loads(body)
                return response.status, body
        except urllib.error.HTTPError as exc:
            last_error = exc
            break
        except (ConnectionRefusedError, urllib.error.URLError) as exc:
            last_error = exc
            time.sleep(0.05)
    if isinstance(last_error, urllib.error.HTTPError):
        exc = last_error
        raw = exc.read().decode("utf-8")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = raw
        return exc.code, parsed
    if last_error:
        raise last_error
    raise RuntimeError("dashboard did not respond")


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        init_workspace(root)
        self.config_path = root / "data" / "config.json"
        self.server = serve_dashboard("127.0.0.1", 0, self.config_path, background=True)
        self.addCleanup(self.server.shutdown)
        self.addCleanup(self.server.server_close)
        port = self.server.server_address[1]
        self.base = f"http://127.0.0.1:{port}"

    def test_edit_profile_listings_run_and_mark(self):
        status, page = _request(self.base + "/")
        self.assertEqual(status, 200)
        self.assertIn("Run search", page)
        self.assertIn("Save profile", page)

        status, payload = _request(self.base + "/api/bootstrap")
        self.assertEqual(status, 200)
        self.assertTrue(payload["profile"]["example"])
        self.assertGreaterEqual(len(payload["listings"]), 2)

        profile = payload["profile"]
        profile["full_name"] = "Sam Rivera"
        profile["email"] = "sam.rivera@university.edu"
        profile["example"] = False
        profile["needs_review"] = False
        profile["work_authorization"] = "Authorized to work in the US"
        profile["needs_sponsorship"] = False
        status, saved = _request(self.base + "/api/profile", profile)
        self.assertEqual(status, 200, saved)
        self.assertEqual(saved["profile"]["full_name"], "Sam Rivera")
        on_disk = json.loads((self.config_path.parent / "profile.json").read_text(encoding="utf-8"))
        self.assertEqual(on_disk["full_name"], "Sam Rivera")
        self.assertFalse(on_disk["example"])

        listings = payload["listings"] + [
            {
                "company": "Initech",
                "title": "Software Engineering Intern",
                "location": "Austin, TX",
                "url": "https://jobs.initech.test/intern",
                "apply_email": "",
                "description": (
                    "Software engineering internship using Python and SQL. "
                    "Coursework in data structures and algorithms is relevant."
                ),
            }
        ]
        status, listed = _request(self.base + "/api/listings", {"jobs": listings})
        self.assertEqual(status, 200, listed)
        self.assertTrue(any(job["company"] == "Initech" for job in listed["listings"]))

        status, settings = _request(
            self.base + "/api/settings",
            {
                "auto_apply_email": False,
                "min_match_score": 40,
                "daily_apply_cap": 3,
                "spreadsheet_id": "",
                "imap_username": "sam.rivera@university.edu",
            },
        )
        self.assertEqual(status, 200, settings)
        self.assertEqual(settings["settings"]["daily_apply_cap"], 3)
        stored = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertEqual(stored["daily_apply_cap"], 3)
        self.assertEqual(stored["imap"]["username"], "sam.rivera@university.edu")
        self.assertIn("boards", stored)

        status, result = _request(self.base + "/api/run", {})
        self.assertEqual(status, 200, result)
        self.assertGreaterEqual(result["new_applications"], 1)
        self.assertEqual(result["sent"], 0)

        status, refreshed = _request(self.base + "/api/bootstrap")
        companies = {item["company"] for item in refreshed["applications"]}
        self.assertIn("Initech", companies)
        application = next(item for item in refreshed["applications"] if item["company"] == "Initech")

        status, detail = _request(self.base + "/api/applications/" + application["id"])
        self.assertEqual(status, 200, detail)
        self.assertIn("Course project name", detail["packet"])

        status, marked = _request(
            self.base + "/api/applications/" + application["id"],
            {"status": "applied", "notes": "Submitted the form myself."},
        )
        self.assertEqual(status, 200, marked)
        self.assertEqual(marked["application"]["status"], "applied")
        self.assertGreaterEqual(marked["summary"]["submitted"], 1)

        status, missing = _request(self.base + "/api/profile", {"full_name": ""})
        self.assertEqual(status, 400)
        self.assertIn("error", missing)

        status, bad_status = _request(
            self.base + "/api/applications/" + application["id"],
            {"status": "hired"},
        )
        self.assertEqual(status, 400)
        self.assertIn("error", bad_status)


if __name__ == "__main__":
    unittest.main()
