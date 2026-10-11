"""The question box: what learners asked that the library had no answer to.

The one place the two sides meet besides the library (docs/architecture.md). A learner's side
drops a question in; the guardian's side reads it and closes it. The question is kept, the
person who asked it is not: the guardian needs to know what is missing, not who did not know
it. The asker gets a ticket instead, a random string kept on their own device: with it, and
only with it, they can see that the guardian answered (in which version of the knowledge) or
said it is not something they teach.

Every question names its organisation, and the box is read and closed one organisation at a
time: the same knowledge name in two organisations is two inboxes.
"""

import os
import secrets
import sqlite3
from datetime import UTC, datetime

from apu import config as shared_config
from exchange import config

# The organisation questions asked before organisations existed belong to: there was one.
LEGACY_ORGANISATION = shared_config.LEGACY_ORGANISATION

STATUSES = ("open", "answered", "declined")


def _connect(path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute("""CREATE TABLE IF NOT EXISTS open_questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, body_id TEXT NOT NULL, question TEXT NOT NULL,
        language TEXT NOT NULL, asked_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open')""")
    # Columns added after the first boxes were made.
    columns = {row[1] for row in connection.execute("PRAGMA table_info(open_questions)")}
    for name, kind in (("ticket", "TEXT"), ("version", "INTEGER"), ("organisation", "TEXT")):
        if name not in columns:
            connection.execute(f"ALTER TABLE open_questions ADD COLUMN {name} {kind}")
    connection.execute("UPDATE open_questions SET organisation = ? WHERE organisation IS NULL", (LEGACY_ORGANISATION,))
    return connection


def _org(organisation: str) -> str:
    if not organisation or not str(organisation).strip():
        raise ValueError("No organisation: the question box is never read across organisations.")
    return str(organisation)


class Questions:
    def __init__(self, path: str | None = None):
        self.path = path or config.QUESTIONS_PATH

    def ask_guardian(self, organisation: str, body_id: str, question: str, language: str) -> str:
        """Keeps the question, not who asked it, and returns the asker's ticket."""
        ticket = secrets.token_urlsafe(16)
        with _connect(self.path) as db:
            db.execute(
                "INSERT INTO open_questions (organisation, body_id, question, language, asked_at, ticket) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (_org(organisation), body_id, question.strip()[:500], language, datetime.now(UTC).isoformat(), ticket))
        return ticket

    def open_questions(self, organisation: str, body_id: str) -> list[dict]:
        with _connect(self.path) as db:
            rows = db.execute("SELECT id, question, language, asked_at FROM open_questions "
                              "WHERE organisation=? AND body_id=? AND status='open' ORDER BY id",
                              (_org(organisation), body_id)).fetchall()
        return [{"id": r[0], "question": r[1], "language": r[2], "asked_at": r[3]} for r in rows]

    def body_of_question(self, organisation: str, question_id: int) -> str | None:
        with _connect(self.path) as db:
            row = db.execute("SELECT body_id FROM open_questions WHERE organisation=? AND id=?",
                             (_org(organisation), question_id)).fetchone()
        return row[0] if row else None

    def close_question(self, organisation: str, question_id: int, status: str = "answered",
                       version: int | None = None) -> None:
        """Answered in a published version, or declined: not something this guardian teaches."""
        if status not in STATUSES[1:]:
            raise ValueError("A question is closed as answered or declined.")
        with _connect(self.path) as db:
            db.execute("UPDATE open_questions SET status=?, version=? WHERE organisation=? AND id=? AND status='open'",
                       (status, version, _org(organisation), question_id))

    def tickets(self, tickets: list[str]) -> list[dict]:
        """Where each question stands, for whoever holds its ticket. Unknown tickets are left out."""
        wanted = [t for t in dict.fromkeys(tickets) if isinstance(t, str) and t][:50]
        if not wanted:
            return []
        with _connect(self.path) as db:
            rows = db.execute(f"SELECT ticket, body_id, status, version FROM open_questions "
                              f"WHERE ticket IN ({','.join('?' * len(wanted))})", wanted).fetchall()
        return [{"ticket": r[0], "body_id": r[1], "status": r[2], "version": r[3]} for r in rows]


_questions: Questions | None = None


def get_questions() -> Questions:
    global _questions
    if _questions is None:
        _questions = Questions()
    return _questions


def set_questions(questions: Questions | None) -> None:
    """For tests, and for a deployment that keeps the box elsewhere."""
    global _questions
    _questions = questions
