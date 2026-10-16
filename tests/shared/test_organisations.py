"""
Organisations: the top level, and nothing read across them.

Target: library/access.py, exchange/questions.py, learner/memory/progress.py,
learner/renderings.py, the routes of both sides.

docs/decisions/0006 and .claude/skills/organisations: a person may belong to several
organisations with a role in each, from the registry only; every record carries its
organisation and every query filters on it. The library's own contract, the vector index
included, is in tests/shared/test_library.py, against memory and live Neo4j.
"""

import pytest

from learner.memory.progress import set_progress
from fastapi.testclient import TestClient

from apu import embeddings as embedder
from exchange.questions import Questions
from guardian.memory.store import set_maps
from learner.memory.progress import Progress
from library import access, store
from library.model import Body, Publication
from tests.support import BODY, WordEmbedder, community


# ── memberships, from the registry only ──────────────────────────────────────

def test_a_person_is_a_guardian_in_one_organisation_and_a_learner_in_another():
    """The project's own registry: Ezekias guards in urithi and learns in acme."""
    assert access.person("ezekias", "urithi").role == "guardian"
    learner = access.person("ezekias", "acme")
    assert learner.role == "learner" and learner.access == "community"
    assert access.require_guardian("ezekias", organisation="urithi").organisation == "urithi"
    with pytest.raises(PermissionError, match="not a guardian in acme"):
        access.require_guardian("ezekias", organisation="acme")


def test_an_organisation_one_does_not_belong_to_is_refused_not_defaulted():
    with pytest.raises(access.NotAMember):
        access.person("visitor", "acme")
    assert access.person("visitor").organisation == "urithi", "naming none acts in the first membership"


# ── the routes, each side in the organisation it acts in ─────────────────────

@pytest.fixture
def two_organisations(monkeypatch, tmp_path):
    from exchange import questions as questions_module
    from server import app

    embedder.set_embedder(WordEmbedder())
    lib = store.MemoryKnowledgeStore()
    lib.publish(community())                                   # in urithi
    acme = community()
    acme.body = Body(BODY, "Running a tech community", "Sabine", 1, "now", organisation="acme")
    acme.units = acme.units[:2]                                 # a smaller body, same id
    lib.publish(acme)
    store.set_store(lib)
    set_progress(Progress(str(tmp_path / "p.sqlite3")))
    questions_module.set_questions(Questions(str(tmp_path / "q.sqlite3")))
    yield TestClient(app), lib
    store.set_store(None)
    embedder.set_embedder(None)
    questions_module.set_questions(None)


def test_a_learner_reads_only_the_organisation_they_act_in(two_organisations):
    client, _ = two_organisations
    in_urithi = client.get(f"/api/learner/path/{BODY}", params={"person_id": "member"}).json()
    in_acme = client.get(f"/api/learner/path/{BODY}", params={"person_id": "ezekias", "organisation": "acme"}).json()
    assert in_urithi["body"]["guardian"] == "Ezekias" and len(in_urithi["units"]) == 4
    assert in_acme["body"]["guardian"] == "Sabine" and len(in_acme["units"]) == 2
    refused = client.get(f"/api/learner/path/{BODY}", params={"person_id": "member", "organisation": "acme"})
    assert refused.status_code == 403, "not a member of acme: refused, never read from urithi instead"


def test_progress_in_one_organisation_is_not_progress_in_another(two_organisations):
    client, _ = two_organisations
    unit_id = f"{BODY}:step-1"
    assert client.post("/api/learner/review", json={"person_id": "ezekias", "organisation": "acme",
                                                    "unit_id": unit_id, "rating": 4}).status_code == 200
    acme = client.get(f"/api/learner/unit/{unit_id}", params={"person_id": "ezekias", "organisation": "acme"}).json()
    urithi = client.get(f"/api/learner/unit/{unit_id}", params={"person_id": "ezekias", "organisation": "urithi"})
    assert acme["progress"]["state"] == "learned"
    # In urithi Ezekias is a guardian, not a learner: the same unit id there is another body's.
    assert urithi.status_code == 200 and urithi.json()["progress"]["state"] == "new"


def test_a_question_asked_in_one_organisation_reaches_only_that_inbox(tmp_path):
    box = Questions(str(tmp_path / "q.sqlite3"))
    box.ask_guardian("acme", BODY, "Asked in acme?", "en")
    assert box.open_questions("urithi", BODY) == []
    [question] = box.open_questions("acme", BODY)
    box.close_question("urithi", question["id"], "declined")
    assert box.open_questions("acme", BODY), "closed only from its own organisation"
    with pytest.raises(ValueError, match="organisation"):
        box.open_questions("", BODY)


def test_a_rendering_is_kept_under_its_organisation(tmp_path):
    from learner.memory.files import LocalFiles

    files = LocalFiles(str(tmp_path))
    files.write("acme", "a.webp", b"acme's")
    assert (tmp_path / "acme" / "a.webp").read_bytes() == b"acme's"
    assert files.read("urithi", "a.webp") is None, "another organisation's file is not this one's"
    for organisation, name in (("", "a.webp"), ("../urithi", "a.webp"), (".hidden", "a"), ("acme", "../x")):
        with pytest.raises(ValueError):
            files.write(organisation, name, b"x")


def test_a_signed_package_names_its_organisation(two_organisations):
    import json

    client, _ = two_organisations
    package = client.get(f"/api/learner/package/{BODY}", params={"person_id": "ezekias", "organisation": "acme"}).json()
    assert json.loads(package["manifest_json"])["organisation"] == "acme"


def test_a_guardian_publishes_only_in_the_organisation_of_the_map(two_organisations):
    """Sabine guards in both; her urithi map is published in urithi, whatever she names."""
    from guardian.engine.workmap import WorkMapStore
    from tests.guardian.test_publishing import confirmed_map

    import tempfile

    client, lib = two_organisations
    work_map = confirmed_map()                                   # Sabine's, in urithi
    with tempfile.TemporaryDirectory() as folder:
        maps = WorkMapStore(f"{folder}/w.sqlite3")
        maps.save(work_map)
        set_maps(maps)
        reply = client.post("/api/guardian/publish", json={"map_id": work_map.map_id, "person_id": "sabine"}).json()
    assert lib.version_of("urithi", reply["body_id"]) == 1
    assert lib.version_of("acme", reply["body_id"]) == 0


def test_no_store_method_reads_without_an_organisation():
    """The skill's rule, read from the code: every library store method names the organisation first."""
    import inspect

    for cls in (store.MemoryKnowledgeStore, store.Neo4jKnowledgeStore):
        for name in ("bodies_for", "search", "body_units", "version_of", "withdraw"):
            first = list(inspect.signature(getattr(cls, name)).parameters)[1]
            assert first == "organisation", f"{cls.__name__}.{name} takes {first!r} first"
    assert isinstance(Publication(body=Body("b", "n", "g", 1, "now")).body.organisation, str)


def test_every_neo4j_query_filters_on_the_organisation():
    """Read from the code, so it holds without a live database: each read and write names $org,
    and the vector search filters on it inside the index, before any ranking."""
    import inspect

    for name in ("bodies_for", "search", "body_units", "version_of", "withdraw", "_replace"):
        source = inspect.getsource(getattr(store.Neo4jKnowledgeStore, name))
        assert "$org" in source, name
    search = inspect.getsource(store.Neo4jKnowledgeStore.search)
    eligible = search[search.index("eligible = "):search.index("\n", search.index("eligible = "))]
    assert '"u.organisation = $org AND u.status = $published AND u.access IN $allowed"' in eligible
    # The one filter, inside the vector index, on what the words found, and on what is read for it.
    index_filter = search[search.index("VECTOR INDEX"):search.index("LIMIT $n")]
    assert '"WHERE " + eligible' in index_filter
    assert 'WHERE " + eligible' in search[search.index("UNWIND $ids"):]
    words = search[search.index('CALL () { MATCH (u:Unit)'):]
    assert words.index('WHERE " + eligible') < words.index("AS texts")
    assert "u.organisation" in inspect.getsource(store.Neo4jKnowledgeStore.ensure_schema)


def test_a_review_in_one_organisation_starts_from_nothing_in_another(tmp_path):
    """The same unit id, the same person: a card in acme is never continued in urithi."""
    progress = Progress(str(tmp_path / "p.sqlite3"))
    progress.review("acme", "ezekias", f"{BODY}:step-1", 4)
    progress.review("acme", "ezekias", f"{BODY}:step-1", 4)
    here = progress.review("urithi", "ezekias", f"{BODY}:step-1", 1)
    assert (here["reviews"], here["lapses"]) == (1, 1)
