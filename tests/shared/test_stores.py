"""
Every store behind an interface, and the contract each implementation must pass.

Target: guardian/memory/store.py, guardian/engine/workmap.py, learner/memory/progress.py,
learner/memory/files.py, exchange/questions.py

docs/decisions/0005 and .claude/skills/store-interfaces: SQLite and the local disk here,
managed services in production, the same tests for both. A production implementation is
accepted when it passes these, live, behind an environment flag. Records written before
organisations existed load into the one there was.
"""

import ast
import pathlib
import sqlite3

import pytest

from exchange.questions import Questions
from guardian.engine.workmap import WorkMap, WorkMapError, WorkMapStore
from guardian.memory.store import InProcessSessions, get_maps, set_maps
from learner.memory.files import LocalFiles
from learner.memory.progress import Progress, get_progress, set_progress

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _map_stores(tmp_path):
    yield WorkMapStore(str(tmp_path / "w.sqlite3"))


def test_a_map_is_always_some_organisations(tmp_path):
    for maps in _map_stores(tmp_path):
        with pytest.raises(TypeError):
            maps.new("t", "Sabine")                                    # no organisation: refused
        with pytest.raises(WorkMapError, match="organisation"):
            maps.save(WorkMap(map_id="m", task="t", expert="Sabine", created_at="now"))
        made = maps.new("t", "Sabine", organisation="acme")
        maps.save(made)
        assert maps.load(made.map_id).organisation == "acme"
        assert [m["map_id"] for m in maps.list_maps("acme")] == [made.map_id]
        assert maps.list_maps("urithi") == []
        again = WorkMapStore(str(tmp_path / "copy.sqlite3")).import_map(maps.export(made.map_id))
        assert again.organisation == "acme", "an exported map keeps its organisation"


def test_maps_written_before_organisations_belong_to_the_one_there_was(tmp_path):
    path = tmp_path / "old.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE workmaps (map_id TEXT PRIMARY KEY, task TEXT NOT NULL, expert TEXT NOT NULL, "
                   "created_at TEXT NOT NULL, confirmed_at TEXT, steps TEXT NOT NULL, guardrails TEXT NOT NULL)")
        db.execute("INSERT INTO workmaps VALUES ('old', 't', 'Sabine', 'then', NULL, '[]', '[]')")
    assert WorkMapStore(str(path)).load("old").organisation == "urithi"


def test_progress_from_before_organisations_is_kept_not_lost(tmp_path):
    path = tmp_path / "p.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE cards (person_id TEXT NOT NULL, unit_id TEXT NOT NULL, card TEXT NOT NULL, "
                   "reviews INTEGER NOT NULL DEFAULT 0, lapses INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (person_id, unit_id))")
    progress = Progress(str(path))
    progress.review("urithi", "ada", "u1", 3)
    assert progress.states("urithi", "ada", ["u1"])["u1"]["reviews"] == 1


def test_old_progress_rows_move_into_the_one_organisation_there_was(tmp_path):
    import json

    from fsrs import Card

    path = tmp_path / "p.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE cards (person_id TEXT NOT NULL, unit_id TEXT NOT NULL, card TEXT NOT NULL, "
                   "reviews INTEGER NOT NULL DEFAULT 0, lapses INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (person_id, unit_id))")
        db.execute("INSERT INTO cards VALUES ('ada', 'u1', ?, 4, 1)", (json.dumps(Card().to_dict()),))
    states = Progress(str(path)).states("urithi", "ada", ["u1"])
    assert (states["u1"]["reviews"], states["u1"]["lapses"]) == (4, 1)
    assert Progress(str(path)).states("acme", "ada", ["u1"])["u1"]["state"] == "new"


def test_questions_from_before_organisations_belong_to_the_one_there_was(tmp_path):
    path = tmp_path / "q.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE open_questions (id INTEGER PRIMARY KEY AUTOINCREMENT, body_id TEXT NOT NULL, "
                   "question TEXT NOT NULL, language TEXT NOT NULL, asked_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open')")
        db.execute("INSERT INTO open_questions (body_id, question, language, asked_at) VALUES ('b', 'Old?', 'en', 'then')")
    box = Questions(str(path))
    assert [q["question"] for q in box.open_questions("urithi", "b")] == ["Old?"]
    assert box.open_questions("acme", "b") == []


def test_a_session_is_made_once_and_dropped_whole():
    sessions, made = InProcessSessions(), []
    first = sessions.get("m", lambda: made.append(1) or {"n": 0})
    first["n"] += 1
    assert sessions.get("m", lambda: made.append(1) or {"n": 0})["n"] == 1 and made == [1]
    sessions.drop("m")
    assert sessions.get("m", lambda: {"n": 0})["n"] == 0


def test_a_file_is_written_whole_and_read_back(tmp_path):
    files = LocalFiles(str(tmp_path))
    assert files.read("urithi", "x.mp3") is None
    files.write("urithi", "x.mp3", b"abc")
    assert files.read("urithi", "x.mp3") == b"abc"
    assert not list(tmp_path.rglob("*.part")), "no half-written file is left behind"


def test_each_store_has_a_getter_and_a_setter():
    from apu.mmu.lance_driver import get_l3_store, set_l3_store
    from guardian.memory.mmu import get_guardian_mmu, set_guardian_mmu
    from learner.memory.mmu import get_learner_mmu, set_learner_mmu

    marker = object()
    set_maps(marker)
    set_progress(marker)
    set_guardian_mmu(marker)
    set_learner_mmu(marker)
    set_l3_store(marker)
    assert get_maps() is marker and get_progress() is marker
    assert get_guardian_mmu() is marker and get_learner_mmu() is marker and get_l3_store() is marker


def test_swapping_the_library_store_clears_the_reader_cache():
    from library import reader
    from library.store import MemoryKnowledgeStore, set_store

    reader._KEPT[(1, "urithi", "meetup", ("public",))] = ((1, "t"), {"body": {"body_id": "meetup"}, "units": []})
    set_store(MemoryKnowledgeStore())
    assert reader._KEPT == {}


# Where a database is opened or a file written: the stores, and three named exceptions.
STORE_MODULES = {
    "guardian/engine/workmap.py", "learner/memory/progress.py", "learner/memory/files.py",
    "learner/memory/answers.py", "guardian/memory/working.py", "guardian/sources/store.py", "learner/memory/notebook.py",
    "exchange/questions.py", "exchange/counters.py",
    "learner/packages/signing.py",                     # the signing key, on first use
    "apu/modality/braille/embosser_simulator.py",      # writes the .brf a person asked for
    "apu/logger.py",                                   # the log
}


def test_no_database_or_file_is_opened_outside_a_store():
    """.claude/skills/store-interfaces: no sqlite3, no open() on data, outside a store module."""
    for package in ("apu", "library", "exchange", "guardian", "learner"):
        for path in (ROOT / package).rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            relative = str(path.relative_to(ROOT))
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                opens = isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open"
                sql = isinstance(node, ast.Import) and any(a.name == "sqlite3" for a in node.names)
                if (opens or sql) and relative not in STORE_MODULES:
                    raise AssertionError(f"{relative} opens a database or a file outside a store")


def test_no_route_module_holds_mutable_state_at_module_level():
    """The state of a session in progress lives in a session store, never in a route module."""
    for path in list((ROOT / "guardian" / "api").glob("*.py")) + list((ROOT / "learner" / "api").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            value = node.value if isinstance(node, (ast.Assign, ast.AnnAssign)) else None
            if isinstance(value, (ast.Dict, ast.List, ast.Set)) or (
                    isinstance(value, ast.Call) and getattr(value.func, "id", "") in ("Progress", "WorkMapStore", "dict")):
                raise AssertionError(f"{path.relative_to(ROOT)}:{node.lineno} holds state at module level")


def test_the_server_makes_the_library_and_the_embedder_ready_and_a_failure_is_only_slower(monkeypatch):
    """Measured: the first question after a start took 8.7 s, the ones after 1.7 s; warmed, 3.3 s."""
    import server
    from apu import embeddings
    from library import store

    readied = []

    class Ready:
        def ensure_schema(self):
            readied.append("schema")

    class Embeds:
        def embed(self, texts):
            readied.append("embedder")
            return [[0.0]]

    monkeypatch.setattr(store, "get_store", lambda: Ready())
    monkeypatch.setattr(embeddings, "get_embedder", lambda: Embeds())
    server.warm_up()
    assert readied == ["schema", "embedder"]
    monkeypatch.setattr(embeddings, "get_embedder", lambda: (_ for _ in ()).throw(RuntimeError("no model")))
    server.warm_up()     # said in the log, never raised: the server starts all the same
