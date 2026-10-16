"""The guardian's working memory, one per knowledge: what Urithi holds while it is being taught.

The map is what the guardian taught; this is what Urithi is in the middle of: the question it
asked and is waiting on, the cases it still has to test, what was said last, what it retained. Kept by a store, so "Carry on teaching" reopens it where it was left,
the server restarted or not (docs/plan.md, docs/plan-done.md, step 2), where the session store forgets.

A doubly linked list of memory blocks, as in the school tutor's memory of this line:
what is recent at the head, what is in progress after it, what is retained before the tail, read
head to tail; a block touched again moves to the front of its kind; past a bound, the oldest
recent blocks are let go first. One list per (organisation, map): nothing of one knowledge or one
organisation is read in another.

Two requests may hold the same list at once: a class frame is being judged (seconds of model calls)
while the guardian saves, ignores or says something. Measured in the review of 2026-10-14: the
later save wrote back the whole list it had loaded, and a proposal just saved came back as
waiting, an ignored one was offered again, a note was lost. So a memory keeps what it changed,
and a store that finds the list written meanwhile replays those changes on the newer list. What
is only recomputed from the rest (proposals judged again from the notes) is marked derived and
dropped only when what it was judged from (notes, proposals, rules, what was set aside) changed
meanwhile: a frame noting what it saw does not undo a proposal (measured in the second review the
same day). A list deleted meanwhile is not written again.

Kinds:  recent    what was just said or asked                 at the head
        open      a question waiting on the guardian, a case   after the head
        retained  what Urithi keeps for the whole knowledge    before the tail
"""

import json
import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from typing import Protocol

from guardian import config

KINDS = ("recent", "open", "retained")
MAX_BLOCKS = 200
JUDGED_FROM = ("note-", "proposal-", "ignored-", "rule-", "saved-")   # what derived changes are judged from


def _judged_from(data: dict | None) -> str:
    """What derived changes were computed from, as one comparable string."""
    blocks = (data or {}).get("blocks") or {}
    kept = {b["ref"]: b.get("content") for b in blocks.values() if b["ref"].startswith(JUDGED_FROM)}
    return json.dumps(kept, sort_keys=True, ensure_ascii=False)


class WorkingMemory:
    """The list itself, in plain data: {"head", "tail", "blocks": {id: block}}."""

    def __init__(self, data: dict | None = None):
        self.data = data or {"head": None, "tail": None, "blocks": {}}
        self.base_version = int(self.data.get("version", 0))
        self.base_judged_from = _judged_from(self.data)
        self.journal: list[tuple] = []
        self._derived = 0

    @contextmanager
    def derived(self):
        """Changes recomputed from the rest of the list: kept only when nothing was written meanwhile."""
        self._derived += 1
        try:
            yield self
        finally:
            self._derived -= 1

    def replay(self, journal: list[tuple], *, derived: bool = False) -> None:
        """Another request's changes, on this newer list; what was derived only when asked."""
        for op in journal:
            if op[-1] and not derived:
                continue
            if op[0] == "put":
                self.put(op[1], op[2], json.loads(json.dumps(op[3])))
            else:
                self.drop(op[1])

    @property
    def blocks(self) -> dict:
        return self.data["blocks"]

    def ordered(self) -> list[dict]:
        """Head to tail, guarded against a broken link."""
        out, current, seen = [], self.data["head"], set()
        while current and current not in seen:
            seen.add(current)
            out.append(self.blocks[current])
            current = self.blocks[current]["next"]
        return out

    def find(self, ref: str) -> dict | None:
        return next((b for b in self.blocks.values() if b["ref"] == ref), None)

    def _unlink(self, block: dict) -> None:
        prev, nxt = block["prev"], block["next"]
        if prev:
            self.blocks[prev]["next"] = nxt
        if nxt:
            self.blocks[nxt]["prev"] = prev
        if self.data["head"] == block["id"]:
            self.data["head"] = nxt
        if self.data["tail"] == block["id"]:
            self.data["tail"] = prev
        block["prev"] = block["next"] = None

    def _link_after(self, block: dict, after: str | None) -> None:
        """After `after`, or at the head when None."""
        if after is None:
            block["next"], block["prev"] = self.data["head"], None
            if self.data["head"]:
                self.blocks[self.data["head"]]["prev"] = block["id"]
            self.data["head"] = block["id"]
            if self.data["tail"] is None:
                self.data["tail"] = block["id"]
            return
        nxt = self.blocks[after]["next"]
        block["prev"], block["next"] = after, nxt
        self.blocks[after]["next"] = block["id"]
        if nxt:
            self.blocks[nxt]["prev"] = block["id"]
        else:
            self.data["tail"] = block["id"]

    def _place(self, block: dict) -> None:
        ordered = self.ordered()
        if block["kind"] == "recent":
            self._link_after(block, None)
        elif block["kind"] == "open":
            recent = [b for b in ordered if b["kind"] == "recent"]
            self._link_after(block, recent[-1]["id"] if recent else None)
        else:   # retained: before the tail's retained run ends, i.e. after the last open
            earlier = [b for b in ordered if b["kind"] != "retained"]
            self._link_after(block, earlier[-1]["id"] if earlier else None)

    def put(self, kind: str, ref: str, content: dict) -> dict:
        """One block per ref: put again, it is replaced and moved to the front of its kind."""
        if kind not in KINDS:
            raise ValueError(f"Unknown kind of memory {kind!r}.")
        old = self.find(ref)
        if old:
            self._unlink(old)
            del self.blocks[old["id"]]
        block = {"id": uuid.uuid4().hex[:12], "kind": kind, "ref": ref, "content": content,
                 "prev": None, "next": None}
        self.blocks[block["id"]] = block
        self._place(block)
        self._bound()
        self.journal.append(("put", kind, ref, content, bool(self._derived)))
        return block

    def drop(self, ref: str) -> bool:
        self.journal.append(("drop", ref, bool(self._derived)))
        return self._drop(ref)

    def _drop(self, ref: str) -> bool:
        block = self.find(ref)
        if not block:
            return False
        self._unlink(block)
        del self.blocks[block["id"]]
        return True

    def of_kind(self, kind: str, prefix: str = "") -> list[dict]:
        return [b for b in self.ordered() if b["kind"] == kind and b["ref"].startswith(prefix)]

    def _bound(self) -> None:
        """Past the bound, the oldest recent blocks go first; what is open or retained stays."""
        while len(self.blocks) > MAX_BLOCKS:
            recent = self.of_kind("recent")
            if not recent:
                break
            self._drop(recent[-1]["ref"])


class WorkingMemories(Protocol):
    def load(self, organisation: str, map_id: str) -> WorkingMemory: ...
    def save(self, organisation: str, map_id: str, memory: WorkingMemory) -> None: ...
    def forget(self, organisation: str, map_id: str) -> None: ...


class SqliteWorkingMemories:
    def __init__(self, path: str | None = None):
        self.path = path or os.path.join(config.DATA_DIR, "working.sqlite3")

    def _connect(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.execute("CREATE TABLE IF NOT EXISTS memories (organisation TEXT NOT NULL, map_id TEXT NOT NULL, "
                           "data TEXT NOT NULL, PRIMARY KEY (organisation, map_id))")
        return connection

    def load(self, organisation: str, map_id: str) -> WorkingMemory:
        if not organisation:
            raise ValueError("No organisation: a working memory is always one organisation's.")
        with self._connect() as db:
            row = db.execute("SELECT data FROM memories WHERE organisation = ? AND map_id = ?",
                             (organisation, map_id)).fetchone()
        return WorkingMemory(json.loads(row[0]) if row else None)

    def save(self, organisation: str, map_id: str, memory: WorkingMemory) -> None:
        """Written as loaded when nobody wrote meanwhile; otherwise its changes on the newer list."""
        with _lock_for(organisation, map_id), self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT data FROM memories WHERE organisation = ? AND map_id = ?",
                             (organisation, map_id)).fetchone()
            stored = json.loads(row[0]) if row else None
            if stored is None and memory.base_version > 0:
                memory.journal = []          # the list was deleted meanwhile, with its knowledge
                return
            version = int((stored or {}).get("version", 0))
            if stored is not None and version != memory.base_version:
                newer = WorkingMemory(stored)
                newer.replay(memory.journal, derived=_judged_from(stored) == memory.base_judged_from)
                memory.data = newer.data
            memory.data["version"] = version + 1
            db.execute("INSERT OR REPLACE INTO memories VALUES (?, ?, ?)",
                       (organisation, map_id, json.dumps(memory.data, ensure_ascii=False)))
        memory.base_version = memory.data["version"]
        memory.base_judged_from = _judged_from(memory.data)
        memory.journal = []

    def forget(self, organisation: str, map_id: str) -> None:
        with self._connect() as db:
            db.execute("DELETE FROM memories WHERE organisation = ? AND map_id = ?", (organisation, map_id))


_locks: dict[tuple[str, str], threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock_for(organisation: str, map_id: str) -> threading.Lock:
    """One writer at a time per list in this process; BEGIN IMMEDIATE covers other processes."""
    with _locks_guard:
        return _locks.setdefault((organisation, map_id), threading.Lock())


_memories: WorkingMemories | None = None


def get_working() -> WorkingMemories:
    global _memories
    if _memories is None:
        _memories = SqliteWorkingMemories()
    return _memories


def set_working(store: WorkingMemories | None) -> None:
    global _memories
    _memories = store
