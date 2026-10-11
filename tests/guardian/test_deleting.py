"""
A guardian deletes a knowledge they teach: asked by the owner, who had no way to.

Target: guardian/api/library_routes.py (delete_knowledge), guardian/engine/workmap.py (delete),
guardian/sources/store.py (Archive.remove), guardian/ui/teach/teach.js (deleteButton).
"""

import pytest

from guardian.engine.workmap import Step, WorkMapStore
from guardian.memory.store import set_maps
from guardian.memory.working import WorkingMemory, get_working
from guardian.sources.store import get_archive, get_sources
from library import store
from tests.guardian.test_engine import rail
from tests.support import ORG, guardian_client


def _map(maps, task, expert="Ezekias", organisation=ORG):
    work_map = maps.new(task, expert, organisation=organisation)
    work_map.steps.append(Step(step_id="s1", number=1, title="t", screen_moment=0.0, observed="o",
                               decision="d", reason="Announce it two weeks ahead.", guardrail_ids=("stop1",)))
    work_map.guardrails.append(rail(gid="stop1"))
    maps.save(work_map)
    return work_map


@pytest.fixture
def deleting(tmp_path):
    from server import app

    maps = WorkMapStore(str(tmp_path / "w.sqlite3"))
    set_maps(maps)
    library = store.MemoryKnowledgeStore()
    store.set_store(library)
    yield guardian_client(app, "ezekias"), maps, library
    store.set_store(None)
    set_maps(None)


def test_deleting_a_knowledge_leaves_nothing_of_it(deleting):
    """Every map of it (an older one would come back in its place), its working memory, its
    documents and their archived copies, and the library; nothing else."""
    client, maps, library = deleting
    older = _map(maps, "Organise tech community")
    latest = _map(maps, "Organise tech community")
    other = _map(maps, "Choosing a or an in English")
    get_working().save(ORG, latest.map_id, WorkingMemory())
    kept = get_sources().save(ORG, latest.map_id, {"name": "screen.jpg", "mime": "image/jpeg"}, b"jpg")
    kept["archived"] = get_archive().put(f"{ORG}/x/screen.jpg", b"jpg", "image/jpeg")
    get_sources().update(ORG, latest.map_id, kept)
    from guardian.publish import publication_from

    latest.confirmed_at = "2026-10-07T00:00:00+00:00"
    maps.save(latest)
    library.publish(publication_from(latest, version=1))
    assert any(b["body_id"].endswith("organise-tech-community") for b in library.bodies_for(ORG, ("restricted",)))

    reply = client.delete(f"/api/guardian/map/{latest.map_id}", params={"organisation": ORG})
    assert reply.status_code == 200 and reply.json()["deleted"] == 2 and reply.json()["documents"] == 1
    assert maps.load(latest.map_id) is None and maps.load(older.map_id) is None
    assert maps.load(other.map_id) is not None, "another knowledge is untouched"
    assert get_sources().list(ORG, latest.map_id) == [] and get_archive().put_paths == []
    assert get_working().load(ORG, latest.map_id).blocks == {}
    tasks = [m["task"] for m in client.get("/api/guardian/knowledge", params={"organisation": ORG}).json()["maps"]]
    assert tasks == ["Choosing a or an in English"]
    assert not any(b["body_id"].endswith("organise-tech-community") for b in library.bodies_for(ORG, ("restricted",)))


def test_only_its_own_guardian_deletes_a_knowledge(deleting):
    client, maps, _ = deleting
    theirs = _map(maps, "Code a supplier invoice", expert="Sabine")
    elsewhere = _map(maps, "Writing a clear email subject", organisation="acme")
    assert client.delete(f"/api/guardian/map/{theirs.map_id}", params={"organisation": ORG}).status_code == 403
    assert client.delete(f"/api/guardian/map/{elsewhere.map_id}", params={"organisation": ORG}).status_code == 404
    assert maps.load(theirs.map_id) is not None and maps.load(elsewhere.map_id) is not None
