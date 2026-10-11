"""[D], the learner's memory: what each person knows, and when to review it.

One FSRS card per person and unit (py-fsrs): a review moves the card, and its due date is
when that unit should come back. Kept in SQLite on this machine, never in the library.

The question box is not here: it is the one place both sides share, in exchange/.

A card is a person's in one organisation: the same person learning in two organisations has
two progressions, and nothing of one is read in the other.
"""

import json
import os
import sqlite3
from datetime import UTC, datetime
from typing import Protocol

from fsrs import Card, Rating, Scheduler

from apu import config as shared_config
from learner import config

RATINGS = {1: Rating.Again, 2: Rating.Hard, 3: Rating.Good, 4: Rating.Easy}


def _path() -> str:
    return config.PROGRESS_PATH


def _connect(path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    connection = sqlite3.connect(path)
    columns = {row[1] for row in connection.execute("PRAGMA table_info(cards)")}
    if columns and "organisation" not in columns:
        # Cards made before organisations existed belong to the one there was: rebuilt with
        # the organisation in the key, so the same unit in two organisations is two cards.
        connection.execute("ALTER TABLE cards RENAME TO cards_before_organisations")
    connection.execute("""CREATE TABLE IF NOT EXISTS cards (
        organisation TEXT NOT NULL, person_id TEXT NOT NULL, unit_id TEXT NOT NULL, card TEXT NOT NULL,
        reviews INTEGER NOT NULL DEFAULT 0, lapses INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (organisation, person_id, unit_id))""")
    if columns and "organisation" not in columns:
        connection.execute("INSERT INTO cards SELECT ?, person_id, unit_id, card, reviews, lapses "
                           "FROM cards_before_organisations", (shared_config.LEGACY_ORGANISATION,))
        connection.execute("DROP TABLE cards_before_organisations")
    return connection


def _org(organisation: str) -> str:
    if not organisation:
        raise ValueError("No organisation: progress is never read across organisations.")
    return organisation


class Progress:
    def __init__(self, path: str | None = None):
        self.path = path or _path()
        self.scheduler = Scheduler()

    def review(self, organisation: str, person_id: str, unit_id: str, rating: int,
               now: datetime | None = None) -> dict:
        """One review: 1 again, 2 hard, 3 good, 4 easy. Returns when the unit is next due."""
        if rating not in RATINGS:
            raise ValueError("A rating is 1 (again), 2 (hard), 3 (good) or 4 (easy).")
        now = now or datetime.now(UTC)
        with _connect(self.path) as db:
            row = db.execute("SELECT card, reviews, lapses FROM cards WHERE organisation=? AND person_id=? "
                             "AND unit_id=?", (_org(organisation), person_id, unit_id)).fetchone()
            card = Card.from_dict(json.loads(row[0])) if row else Card()
            card, _ = self.scheduler.review_card(card, RATINGS[rating], review_datetime=now)
            reviews, lapses = (row[1] if row else 0) + 1, (row[2] if row else 0) + (rating == 1)
            db.execute("INSERT OR REPLACE INTO cards VALUES (?, ?, ?, ?, ?, ?)",
                       (organisation, person_id, unit_id, json.dumps(card.to_dict()), reviews, lapses))
        return {"unit_id": unit_id, "due": card.due.isoformat(), "reviews": reviews, "lapses": lapses}

    def states(self, organisation: str, person_id: str, unit_ids: list[str],
               now: datetime | None = None) -> dict[str, dict]:
        """For each unit: never seen, due, or learned until a date."""
        now = now or datetime.now(UTC)
        with _connect(self.path) as db:
            rows = {r[0]: r for r in db.execute(
                f"SELECT unit_id, card, reviews, lapses FROM cards WHERE organisation=? AND person_id=? "
                f"AND unit_id IN ({','.join('?' * len(unit_ids))})",
                (_org(organisation), person_id, *unit_ids))} if unit_ids else {}
        found = {}
        for unit_id in unit_ids:
            if unit_id not in rows:
                found[unit_id] = {"state": "new", "due": None, "reviews": 0, "lapses": 0}
                continue
            card = Card.from_dict(json.loads(rows[unit_id][1]))
            found[unit_id] = {"state": "due" if card.due <= now else "learned",
                              "due": card.due.isoformat(), "reviews": rows[unit_id][2],
                              "lapses": rows[unit_id][3]}
        return found


class ProgressStore(Protocol):
    """What the learner's side needs of progress; SQLite locally, a managed store in production."""

    def review(self, organisation: str, person_id: str, unit_id: str, rating: int,
               now: datetime | None = None) -> dict: ...
    def states(self, organisation: str, person_id: str, unit_ids: list[str],
               now: datetime | None = None) -> dict[str, dict]: ...


_progress: ProgressStore | None = None


def get_progress() -> ProgressStore:
    global _progress
    if _progress is None:
        _progress = Progress()
    return _progress


def set_progress(store: ProgressStore | None) -> None:
    """For tests, and for a deployment that keeps progress elsewhere."""
    global _progress
    _progress = store
