"""The guardian's working memory, one per knowledge: what Urithi holds while it is being taught.

The map is what the guardian taught; this is what Urithi is in the middle of: the question it
asked and is waiting on, the cases it still has to test, what was said last, what it retained. Kept by a store, so "Carry on teaching" reopens it where it was left,
the server restarted or not (docs/plan.md, docs/plan-done.md, step 2), where the session store forgets.

A doubly linked list of memory blocks, as in the school tutor's memory of this line:
what is recent at the head, what is in progress after it, what is retained before the tail, read
head to tail; a block touched again moves to the front of its kind; past a bound, the oldest
recent blocks are let go first. One list per (organisation, map): nothing of one knowledge or one
organisation is read in another.

Kinds:  recent    what was just said or asked                 at the head
        open      a question waiting on the guardian, a case   after the head
        retained  what Urithi keeps for the whole knowledge    before the tail
"""

import json
import os
import sqlite3
import uuid
from typing import Protocol

from guardian import config

KINDS = ("recent", "open", "retained")
MAX_BLOCKS = 200


class WorkingMemory:
    """The list itself, in plain data: {"head", "tail", "blocks": {id: block}}."""

    def __init__(self, data: dict | None = None):
        self.data = data or {"head": None, "tail": None, "blocks": {}}

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
        return block

    def drop(self, ref: str) -> bool:
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
            self.drop(recent[-1]["ref"])


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
        with self._connect() as db:
            db.execute("INSERT OR REPLACE INTO memories VALUES (?, ?, ?)",
                       (organisation, map_id, json.dumps(memory.data, ensure_ascii=False)))

    def forget(self, organisation: str, map_id: str) -> None:
        with self._connect() as db:
            db.execute("DELETE FROM memories WHERE organisation = ? AND map_id = ?", (organisation, map_id))


_memories: WorkingMemories | None = None


def get_working() -> WorkingMemories:
    global _memories
    if _memories is None:
        _memories = SqliteWorkingMemories()
    return _memories


def set_working(store: WorkingMemories | None) -> None:
    global _memories
    _memories = store
