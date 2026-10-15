"""The guardian's stores, behind interfaces (docs/decisions/0005, .claude/skills/store-interfaces).

  maps      the work maps: what a guardian taught, as it stands. SQLite locally
            (guardian.engine.workmap.WorkMapStore); a managed database in production passes
            the same contract tests (tests/shared/test_stores.py).
  sessions  the state of a teaching session in progress: what Urithi is waiting on, the
            pause detector, the questions pending. Never a dictionary in a route module.
            Locally, held in this process; a session holds live objects (a detector, a lock),
            so a shared implementation keeps what can be written down and rebuilds the rest.

Each has a getter and a setter: the code that uses a store never knows which one it is.
"""

import threading
from collections.abc import Callable
from typing import Protocol

from guardian.engine.workmap import WorkMap, WorkMapStore


class MapStore(Protocol):
    def new(self, task: str, expert: str, language: str = "en", *, organisation: str) -> WorkMap: ...
    def save(self, work_map: WorkMap) -> None: ...
    def load(self, map_id: str) -> WorkMap | None: ...
    def list_maps(self, organisation: str | None = None) -> list[dict]: ...
    def export(self, map_id: str) -> dict | None: ...
    def import_map(self, data: dict) -> WorkMap: ...
    def delete(self, map_id: str) -> bool: ...


class SessionStore(Protocol):
    def get(self, map_id: str, make: Callable[[], dict]) -> dict: ...
    def drop(self, map_id: str) -> None: ...


class InProcessSessions:
    """Sessions in this process: one server, one place. Lost on a restart, which the
    working memory (step 2) is there to survive."""

    def __init__(self):
        self._held: dict[str, dict] = {}
        self._lock = threading.Lock()

    def get(self, map_id: str, make: Callable[[], dict]) -> dict:
        with self._lock:
            if map_id not in self._held:
                self._held[map_id] = make()
            return self._held[map_id]

    def drop(self, map_id: str) -> None:
        with self._lock:
            self._held.pop(map_id, None)


_maps: MapStore | None = None
_sessions: SessionStore | None = None
_map_locks: dict[str, threading.RLock] = {}
_map_locks_guard = threading.Lock()


def map_lock(map_id: str) -> threading.RLock:
    """One writer of a map at a time in this process, held from loading the map to saving it; the map
    store's version refuses a stale save from another process (guardian.engine.workmap.MapChanged)."""
    with _map_locks_guard:
        return _map_locks.setdefault(map_id, threading.RLock())


def get_maps() -> MapStore:
    global _maps
    if _maps is None:
        _maps = WorkMapStore()
    return _maps


def set_maps(store: MapStore | None) -> None:
    """For tests, and for a deployment that keeps the maps elsewhere."""
    global _maps
    _maps = store


def get_sessions() -> SessionStore:
    global _sessions
    if _sessions is None:
        _sessions = InProcessSessions()
    return _sessions


def set_sessions(store: SessionStore | None) -> None:
    global _sessions
    _sessions = store
