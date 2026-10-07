"""SQLite record of every listing considered and every application prepared."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from internship_assistant.models import Application

_APPLICATION_COLUMNS = (
    "id",
    "job_key",
    "company",
    "title",
    "location",
    "source",
    "url",
    "apply_email",
    "apply_url",
    "match_score",
    "matched_skills",
    "missing_skills",
    "status",
    "submit_method",
    "cover_letter",
    "answers_json",
    "needs_input",
    "email_evidence",
    "notes",
    "sheet_row",
    "send_attempts",
    "send_day",
    "found_at",
    "applied_at",
    "status_updated_at",
)


def _application_from_row(row: sqlite3.Row) -> Application:
    data = {column: row[column] for column in _APPLICATION_COLUMNS}
    return Application(**data)


class Store:
    def __init__(self, path: str | Path):
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(destination)
        self.conn.row_factory = sqlite3.Row
        self._init()

    def close(self) -> None:
        self.conn.close()

    def _init(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS jobs_seen (
                job_key TEXT PRIMARY KEY,
                company TEXT NOT NULL,
                title TEXT NOT NULL,
                score REAL NOT NULL,
                reason TEXT NOT NULL,
                first_seen TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS applications (
                id TEXT PRIMARY KEY,
                job_key TEXT UNIQUE NOT NULL,
                company TEXT NOT NULL,
                title TEXT NOT NULL,
                location TEXT NOT NULL,
                source TEXT NOT NULL,
                url TEXT NOT NULL,
                apply_email TEXT NOT NULL,
                apply_url TEXT NOT NULL,
                match_score REAL NOT NULL,
                matched_skills TEXT NOT NULL,
                missing_skills TEXT NOT NULL,
                status TEXT NOT NULL,
                submit_method TEXT NOT NULL,
                cover_letter TEXT NOT NULL,
                answers_json TEXT NOT NULL,
                needs_input TEXT NOT NULL,
                email_evidence TEXT NOT NULL,
                notes TEXT NOT NULL,
                sheet_row INTEGER,
                send_attempts INTEGER NOT NULL DEFAULT 0,
                send_day TEXT NOT NULL DEFAULT '',
                found_at TEXT NOT NULL,
                applied_at TEXT NOT NULL DEFAULT '',
                status_updated_at TEXT NOT NULL
            );
            """
        )
        self.conn.commit()

    def upsert_seen(self, job_key: str, company: str, title: str, score: float, reason: str, seen_at: str) -> None:
        self.conn.execute(
            """
            INSERT INTO jobs_seen (job_key, company, title, score, reason, first_seen)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(job_key) DO UPDATE SET
                score=excluded.score,
                reason=excluded.reason
            """,
            (job_key, company, title, score, reason, seen_at),
        )
        self.conn.commit()

    def get_by_job_key(self, job_key: str) -> Application | None:
        row = self.conn.execute("SELECT * FROM applications WHERE job_key = ?", (job_key,)).fetchone()
        return _application_from_row(row) if row else None

    def get(self, application_id: str) -> Application | None:
        row = self.conn.execute(
            "SELECT * FROM applications WHERE id = ? OR job_key = ?",
            (application_id, application_id),
        ).fetchone()
        return _application_from_row(row) if row else None

    def save(self, application: Application) -> None:
        placeholders = ", ".join("?" for _ in _APPLICATION_COLUMNS)
        columns = ", ".join(_APPLICATION_COLUMNS)
        updates = ", ".join(f"{column}=excluded.{column}" for column in _APPLICATION_COLUMNS if column != "id")
        values = [getattr(application, column) for column in _APPLICATION_COLUMNS]
        self.conn.execute(
            f"""
            INSERT INTO applications ({columns}) VALUES ({placeholders})
            ON CONFLICT(id) DO UPDATE SET {updates}
            """,
            values,
        )
        self.conn.commit()

    def list_applications(self) -> list[Application]:
        rows = self.conn.execute(
            "SELECT * FROM applications ORDER BY match_score DESC, found_at ASC"
        ).fetchall()
        return [_application_from_row(row) for row in rows]

    def list_status(self, status: str) -> list[Application]:
        rows = self.conn.execute("SELECT * FROM applications WHERE status = ?", (status,)).fetchall()
        return [_application_from_row(row) for row in rows]

    def count_seen(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) AS n FROM jobs_seen").fetchone()["n"])

    def seen_rows(self) -> list[sqlite3.Row]:
        return list(self.conn.execute("SELECT * FROM jobs_seen").fetchall())

    def claim_for_send(self, application_id: str, day: str, cap: int, updated_at: str) -> bool:
        """Reserve one daily send slot. A crash leaves status 'sending' so it is not sent twice."""
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            row = self.conn.execute(
                "SELECT status, send_attempts FROM applications WHERE id = ?",
                (application_id,),
            ).fetchone()
            if row is None or row["status"] not in {"ready_to_submit", "drafted", "send_failed"}:
                self.conn.execute("ROLLBACK")
                return False
            if int(row["send_attempts"]) >= 2:
                self.conn.execute("ROLLBACK")
                return False
            used = self.conn.execute(
                """
                SELECT COUNT(*) AS n FROM applications
                WHERE send_day = ?
                  AND status IN ('sending', 'applied', 'assessment', 'interview', 'rejected', 'offer')
                """,
                (day,),
            ).fetchone()["n"]
            if int(used) >= cap:
                self.conn.execute("ROLLBACK")
                return False
            self.conn.execute(
                """
                UPDATE applications
                SET status = 'sending', send_attempts = send_attempts + 1, send_day = ?, status_updated_at = ?
                WHERE id = ?
                """,
                (day, updated_at, application_id),
            )
            self.conn.commit()
            return True
        except Exception:
            self.conn.execute("ROLLBACK")
            raise

    def sends_used(self, day: str) -> int:
        row = self.conn.execute(
            """
            SELECT COUNT(*) AS n FROM applications
            WHERE send_day = ?
              AND status IN ('sending', 'applied', 'assessment', 'interview', 'rejected', 'offer')
            """,
            (day,),
        ).fetchone()
        return int(row["n"])
