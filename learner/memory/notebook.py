"""The learner's notebook, and the session they are in: both theirs, kept apart from the guardian's.

  notebook   what the learner keeps: an answer whole, its key points, or an excerpt, with the
             guardian's words it cites; a revision sheet is made of it, on screen or in braille.
  session    the learner's working memory for one knowledge: the part they were on, what they
             asked, what they found hard (rated again or hard, or answered wrong).

Persistent progress (FSRS) is learner/memory/progress.py. These are kept per organisation and
person, behind interfaces (.claude/skills/store-interfaces); nothing here is ever read by the
guardian's side, which has its own working memory (guardian/memory/working.py).
"""

import json
import os
import sqlite3
import uuid
from datetime import UTC, datetime
from typing import Protocol

from learner import config

KINDS = ("whole", "key_points", "excerpt")
MAX_SESSION_EVENTS = 50


def _who(organisation: str, person_id: str) -> tuple[str, str]:
    if not organisation or not person_id:
        raise ValueError("A notebook and a session are one person's, in one organisation.")
    return organisation, person_id


class Notebook(Protocol):
    def keep(self, organisation: str, person_id: str, entry: dict) -> dict: ...
    def entries(self, organisation: str, person_id: str, body_id: str | None = None) -> list[dict]: ...
    def forget(self, organisation: str, person_id: str, entry_id: str) -> bool: ...


class Sessions(Protocol):
    def load(self, organisation: str, person_id: str, body_id: str) -> dict: ...
    def save(self, organisation: str, person_id: str, body_id: str, session: dict) -> None: ...


class SqliteLearnerMemory:
    """Both, in one file of the learner's side: the notebook's entries and the sessions."""

    def __init__(self, path: str | None = None):
        self.path = path or os.path.join(config.DATA_DIR, "notebook.sqlite3")

    def _connect(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.execute("CREATE TABLE IF NOT EXISTS notebook (organisation TEXT NOT NULL, person_id TEXT NOT NULL, "
                           "entry_id TEXT NOT NULL, body_id TEXT, entry TEXT NOT NULL, kept_at TEXT NOT NULL, "
                           "PRIMARY KEY (organisation, person_id, entry_id))")
        connection.execute("CREATE TABLE IF NOT EXISTS sessions (organisation TEXT NOT NULL, person_id TEXT NOT NULL, "
                           "body_id TEXT NOT NULL, session TEXT NOT NULL, PRIMARY KEY (organisation, person_id, body_id))")
        return connection

    # the notebook
    def keep(self, organisation: str, person_id: str, entry: dict) -> dict:
        organisation, person_id = _who(organisation, person_id)
        if entry.get("kind") not in KINDS:
            raise ValueError("An entry is kept whole, as key points, or as an excerpt.")
        entry = {**entry, "entry_id": uuid.uuid4().hex[:12], "kept_at": datetime.now(UTC).isoformat()}
        with self._connect() as db:
            db.execute("INSERT INTO notebook VALUES (?, ?, ?, ?, ?, ?)",
                       (organisation, person_id, entry["entry_id"], entry.get("body_id"),
                        json.dumps(entry, ensure_ascii=False), entry["kept_at"]))
        return entry

    def entries(self, organisation: str, person_id: str, body_id: str | None = None) -> list[dict]:
        organisation, person_id = _who(organisation, person_id)
        query, params = "SELECT entry FROM notebook WHERE organisation = ? AND person_id = ?", [organisation, person_id]
        if body_id:
            query += " AND body_id = ?"
            params.append(body_id)
        with self._connect() as db:
            return [json.loads(r[0]) for r in db.execute(query + " ORDER BY kept_at", params)]

    def forget(self, organisation: str, person_id: str, entry_id: str) -> bool:
        organisation, person_id = _who(organisation, person_id)
        with self._connect() as db:
            return db.execute("DELETE FROM notebook WHERE organisation = ? AND person_id = ? AND entry_id = ?",
                              (organisation, person_id, entry_id)).rowcount > 0

    # the session
    def load(self, organisation: str, person_id: str, body_id: str) -> dict:
        organisation, person_id = _who(organisation, person_id)
        with self._connect() as db:
            row = db.execute("SELECT session FROM sessions WHERE organisation = ? AND person_id = ? AND body_id = ?",
                             (organisation, person_id, body_id)).fetchone()
        return json.loads(row[0]) if row else {"on": None, "asked": [], "hard": []}

    def save(self, organisation: str, person_id: str, body_id: str, session: dict) -> None:
        organisation, person_id = _who(organisation, person_id)
        session = {**session, "asked": session.get("asked", [])[-MAX_SESSION_EVENTS:],
                   "hard": session.get("hard", [])[-MAX_SESSION_EVENTS:]}
        with self._connect() as db:
            db.execute("INSERT OR REPLACE INTO sessions VALUES (?, ?, ?, ?)",
                       (organisation, person_id, body_id, json.dumps(session, ensure_ascii=False)))


_memory: SqliteLearnerMemory | None = None


def get_learner_memory() -> SqliteLearnerMemory:
    global _memory
    if _memory is None:
        _memory = SqliteLearnerMemory()
    return _memory


def set_learner_memory(store: SqliteLearnerMemory | None) -> None:
    global _memory
    _memory = store
