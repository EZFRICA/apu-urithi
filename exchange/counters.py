"""The meter's counts: what each person and organisation spent, by capability and day.

The rules are apu/meter.py's; the numbers are kept here, the one place both sides share
besides the library and the question box. SQLite locally; a managed counter in production
passes the same contract (tests/shared/test_meter.py). No question, no answer and no word is
kept: only who, which capability, how much, and when.
"""

import os
import sqlite3
from datetime import datetime

from exchange import config


def _connect(path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute("""CREATE TABLE IF NOT EXISTS usage (
        organisation TEXT NOT NULL, person_id TEXT NOT NULL, role TEXT NOT NULL,
        capability TEXT NOT NULL, amount REAL NOT NULL, at TEXT NOT NULL)""")
    connection.execute("CREATE INDEX IF NOT EXISTS usage_by_who ON usage (capability, organisation, person_id, at)")
    return connection


class SqliteCounters:
    def __init__(self, path: str | None = None):
        self.path = path or config.COUNTERS_PATH

    def add(self, organisation: str, person_id: str, role: str, capability: str, amount: float,
            at: datetime) -> None:
        with _connect(self.path) as db:
            db.execute("INSERT INTO usage VALUES (?, ?, ?, ?, ?, ?)",
                       (organisation, person_id, role, capability, float(amount), at.isoformat()))

    def total(self, capability: str, *, since: datetime, organisation: str | None = None,
              person_id: str | None = None) -> float:
        query, params = "SELECT COALESCE(SUM(amount), 0) FROM usage WHERE capability = ? AND at >= ?", [
            capability, since.isoformat()]
        if organisation is not None:
            query += " AND organisation = ?"
            params.append(organisation)
        if person_id is not None:
            query += " AND person_id = ?"
            params.append(person_id)
        with _connect(self.path) as db:
            return float(db.execute(query, params).fetchone()[0])
