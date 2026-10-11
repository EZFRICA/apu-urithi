"""Answers already given, per version of a knowledge and per access level.

The first step down from a ceiling (docs/decisions/0007), and the reason cost follows the
knowledge rather than the number of people: the same question, on the same version, by
someone who may see the same parts, gets the answer already worded and checked, at no cost.
A new version of the knowledge is a new key, so an answer never outlives what it rests on.

Behind an interface (.claude/skills/store-interfaces): SQLite here. No person is kept: only
the organisation, the knowledge, its version, the levels, the question and the answer. An
answer worded with a person's MMU memory is never put in or served from this shared cache, so
one learner's memory never reaches another.
"""

import hashlib
import json
import os
import sqlite3
from typing import Protocol

from learner import config


def _key(organisation: str, body_id: str, version: int, allowed, question: str, language: str) -> str:
    asked = " ".join(question.lower().split()).strip(" ?!.")
    raw = json.dumps([organisation, body_id, version, sorted(allowed), asked, language])
    return hashlib.sha256(raw.encode()).hexdigest()


class AnswerCache(Protocol):
    def get(self, organisation: str, body_id: str, version: int, allowed, question: str,
            language: str) -> dict | None: ...
    def put(self, organisation: str, body_id: str, version: int, allowed, question: str,
            language: str, answer: dict, *, memory_context: str = "") -> None: ...


class SqliteAnswers:
    def __init__(self, path: str | None = None):
        self.path = path or os.path.join(config.DATA_DIR, "answers.sqlite3")

    def _connect(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.execute("CREATE TABLE IF NOT EXISTS answers (key TEXT PRIMARY KEY, organisation TEXT NOT NULL, "
                           "answer TEXT NOT NULL)")
        return connection

    def get(self, organisation, body_id, version, allowed, question, language):
        with self._connect() as db:
            row = db.execute("SELECT answer FROM answers WHERE key = ?",
                             (_key(organisation, body_id, version, allowed, question, language),)).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, organisation, body_id, version, allowed, question, language, answer, *,
            memory_context: str = ""):
        if memory_context.strip():
            return
        with self._connect() as db:
            db.execute("INSERT OR REPLACE INTO answers VALUES (?, ?, ?)",
                       (_key(organisation, body_id, version, allowed, question, language), organisation,
                        json.dumps(answer, ensure_ascii=False)))


_answers: AnswerCache | None = None


def get_answers() -> AnswerCache:
    global _answers
    if _answers is None:
        _answers = SqliteAnswers()
    return _answers


def set_answers(store: AnswerCache | None) -> None:
    global _answers
    _answers = store

