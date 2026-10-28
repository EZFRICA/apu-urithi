"""
A library out of reach (library/model.py LibraryUnavailable): said as such, never as a server error.

Measured on 2026-10-24 with the Aura instance paused, then with a port refused and a name that does
not resolve: five library routes in six answered 500 "Internal Server Error", the learner's page said
"nothing published", the guardian's page lost the maps it was teaching, and the server's log named
the library's address five times. The incident runbook says otherwise: learners continue from kept
packages, publishing waits, and it is said.
"""

import logging
from dataclasses import asdict

import pytest
from fastapi.testclient import TestClient
from neo4j.exceptions import AuthError, ServiceUnavailable, SessionExpired

from guardian.memory.store import get_maps, set_maps
from library import store
from library.model import LibraryUnavailable
from tests.guardian.test_publishing import confirmed_map

ADDRESS = "secret-host.example:7687"


class _Driver:
    """A driver whose library is out of reach: on opening a session, or on the query in it."""

    def __init__(self, error, at: str):
        self.error, self.at = error, at

    def session(self, database=None):
        if self.at == "session":
            raise self.error
        error = self.error

        class Session:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def execute_read(self, work):
                raise error

            def execute_write(self, work):
                raise error

            def run(self, *args, **kwargs):
                raise error
        return Session()


@pytest.mark.parametrize("kind", [ServiceUnavailable, SessionExpired, AuthError])
@pytest.mark.parametrize("at", ["session", "query"])
def test_a_library_out_of_reach_is_said_by_its_kind_never_by_its_address(kind, at, caplog):
    library = store.Neo4jKnowledgeStore.__new__(store.Neo4jKnowledgeStore)
    library.driver, library.database, library._schema_ready = _Driver(kind(f"Couldn't connect to {ADDRESS}"), at), None, False
    for read in (lambda: library.bodies_for("urithi", ["public"]), lambda: library.version_of("urithi", "b1"),
                 lambda: library.withdraw("urithi", "b1"), library.ensure_schema):
        with caplog.at_level(logging.WARNING), pytest.raises(LibraryUnavailable) as raised:
            read()
        assert str(raised.value) == LibraryUnavailable.SAID
        assert raised.value.__cause__ is None and raised.value.__suppress_context__, "the driver's message stays out"
    assert ADDRESS not in caplog.text and kind.__name__ in caplog.text


class _Down:
    """A library every read and write of which is out of reach."""

    def __getattr__(self, name):
        def down(*args, **kwargs):
            raise LibraryUnavailable()
        return down


@pytest.fixture
def down(tmp_path):
    from guardian.engine.workmap import WorkMapStore
    from server import app

    maps = WorkMapStore(str(tmp_path / "w.sqlite3"))
    maps.save(confirmed_map())
    set_maps(maps)
    store.set_store(_Down())
    yield TestClient(app)
    store.set_store(None)


@pytest.mark.parametrize("method,path,body", [
    ("GET", "/api/learner/bodies", None),
    ("GET", "/api/learner/path/sabine--code-a-supplier-invoice", None),
    ("GET", "/api/learner/search", {"q": "capex"}),
    ("POST", "/api/learner/ask", {"person_id": "visitor", "body_id": "sabine--code-a-supplier-invoice",
                                  "question": "When is equipment capex?"}),
])
def test_a_learners_route_says_the_library_is_out_of_reach_so_the_page_opens_what_it_keeps(down, method, path, body):
    asked = {"json": body} if method == "POST" else {"params": {"person_id": "visitor", **(body or {})}}
    reply = down.request(method, path, **asked)
    assert reply.status_code == 503, "a 500 says only that something broke"
    assert reply.json() == {"detail": LibraryUnavailable.SAID, "unavailable": "library"}


def test_the_guardian_keeps_the_maps_being_taught_and_publishing_waits(down):
    reply = down.get("/api/guardian/knowledge", params={"person_id": "sabine"})
    assert reply.status_code == 200, "the maps are the guardian's, kept here, not the library's"
    listed = reply.json()
    assert [(m["map_id"], m["published"]) for m in listed["maps"]] == [("m1", None)]
    assert listed["unavailable"] == "library" and listed["detail"] == LibraryUnavailable.SAID
    before = asdict(get_maps().load("m1"))
    published = down.post("/api/guardian/publish", json={"map_id": "m1", "person_id": "sabine"})
    assert published.status_code == 503 and published.json()["unavailable"] == "library"
    assert asdict(get_maps().load("m1")) == before, "nothing was changed by a publication that did not happen"
