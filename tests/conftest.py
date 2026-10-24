"""
Shared test setup.

The suite runs with no provider key of any kind: every model, search and speech call in
these tests is replaced by a fake before it is made, and `no_network` turns any call that
slips through into a failure instead of a request.
"""

import os
import socket

import pytest

from apu import config as _apu_config

# A client is only built when a role is called; fake, non-empty keys let it build, and the
# tests replace the call itself before it could leave.
os.environ[_apu_config.GEMINI_API_KEY_ENV] = "test-key-not-real-do-not-use"
# No test sends a trace to Arize, whatever .env holds (apu/observability.py).
os.environ[_apu_config.TRACING_SWITCH_ENV] = "0"


@pytest.fixture(autouse=True)
def library_key():
    """A signing key made for each test: the suite never writes the library's key to disk."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from learner.packages import signing

    signing.set_key(Ed25519PrivateKey.generate())
    yield
    signing.set_key(None)


class NetworkBlocked(Exception):
    """Raised when code under test tries to open an INET socket."""


_real_socket = socket.socket


@pytest.fixture
def no_network(monkeypatch):
    """Block outbound network. AF_UNIX stays open: asyncio needs a socketpair."""
    def guarded(family=socket.AF_INET, *a, **k):
        if family in (socket.AF_INET, socket.AF_INET6):
            raise NetworkBlocked(f"socket.socket(family={family!r})")
        return _real_socket(family, *a, **k)

    def blocked(*a, **k):
        raise NetworkBlocked("outbound connection attempt")

    monkeypatch.setattr(socket, "socket", guarded)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    return NetworkBlocked


def pytest_configure(config):
    """
    Refuse to run while scripts/mutate.py has a deliberate defect in the tree.

    The mutation runner sets URITHI_MUTATING for the suites it starts itself, so only a
    suite started by hand at the same time is stopped. That one would read a broken file and
    report a failure that is not real.
    """
    import pathlib

    lock = pathlib.Path(__file__).resolve().parents[1] / ".mutating"
    if lock.exists() and not os.environ.get("URITHI_MUTATING"):
        raise pytest.UsageError(
            "scripts/mutate.py is running and the source tree holds a deliberate defect. "
            "Wait for it to finish, or delete .mutating if it was killed.")


@pytest.fixture(autouse=True)
def default_stores(monkeypatch):
    """Each test that swaps a store gets the default back: no store leaks into the next test."""
    from apu import embeddings
    from apu.inference import llm
    from tests.support import WordEmbedder

    embeddings.set_embedder(WordEmbedder())
    monkeypatch.setattr(llm, "is_configured", lambda role="main": False)
    yield
    from apu.mmu.lance_driver import set_l3_store
    from apu.mmu.store import set_mmu_locks
    from guardian.memory.mmu import set_guardian_mmu
    from guardian.memory.store import set_maps, set_sessions
    from learner.memory.files import set_files
    from learner.memory.mmu import set_learner_mmu
    from learner.memory.progress import set_progress
    from library import reader

    with reader._KEPT_LOCK:
        reader._KEPT.clear()
    llm.set_client(None)
    embeddings.set_embedder(None)
    set_files(None)
    set_maps(None)
    set_sessions(None)
    set_progress(None)
    set_guardian_mmu(None)
    set_learner_mmu(None)
    set_l3_store(None)
    set_mmu_locks(None)


@pytest.fixture(autouse=True)
def counted(tmp_path):
    """Every costly call is metered (apu/meter.py): each test counts in its own place."""
    from apu import meter
    from apu.mmu import cache_l1, lance_driver
    from exchange.counters import SqliteCounters

    from guardian.memory.mmu import GuardianMmuStore, set_guardian_mmu
    from guardian.memory.working import SqliteWorkingMemories, set_working
    from learner.memory.answers import SqliteAnswers, set_answers
    from learner.memory.mmu import LearnerMmuStore, set_learner_mmu

    cache_l1.flush_all()
    lance_driver.reset_db()
    lance_driver.set_l3_store(None)
    meter.set_counters(SqliteCounters(str(tmp_path / "counters.sqlite3")))
    set_answers(SqliteAnswers(str(tmp_path / "answers.sqlite3")))
    set_working(SqliteWorkingMemories(str(tmp_path / "working.sqlite3")))
    set_guardian_mmu(GuardianMmuStore(tmp_path / "guardian_mmu"))
    set_learner_mmu(LearnerMmuStore(tmp_path / "learner_mmu"))
    from guardian.sources.store import LocalSources, set_archive, set_sources

    set_sources(LocalSources(str(tmp_path / "sources")))
    from learner.memory.notebook import SqliteLearnerMemory, set_learner_memory

    set_learner_memory(SqliteLearnerMemory(str(tmp_path / "notebook.sqlite3")))
    set_archive(KeptHere())
    yield
    cache_l1.flush_all()
    lance_driver.reset_db()
    lance_driver.set_l3_store(None)
    meter.set_counters(None)
    set_answers(None)
    set_working(None)
    set_sources(None)
    set_archive(None)
    set_learner_memory(None)
    set_guardian_mmu(None)
    set_learner_mmu(None)


class KeptHere:
    """The tests' archive: what would go to Cloud Storage, kept in a list; never the real bucket."""

    def __init__(self):
        self.put_paths = []

    def put(self, path, data, mime_type):
        self.put_paths.append(path)
        return f"test://{path}"

    def remove(self, where):
        self.put_paths.remove(where.removeprefix("test://"))
