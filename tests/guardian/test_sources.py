"""
Sources: what a guardian deposits, read into passages, made into cited steps, archived when cited.

Target: guardian/sources/, guardian/api/source_routes.py, the archive at validation, the
evidence a learner opens (library, learner).

Step 3 of docs/plan.md (docs/plan-steps-3-to-8.md) and docs/decisions/0004. Models and speech are faked; a real PDF is
read. What is checked is what the code decides: a passage is the document's text and where it
is, a step cites it, a document no validated part cites is never uploaded, and an excerpt is
never more open than the part it supports.
"""

import base64

import pytest

from apu.modality import picture, voice
from guardian.engine import absorb
from guardian.memory.store import set_maps
from guardian.sources import passages
from guardian.sources.store import LocalSources
from tests.support import guardian_client


def tiny_pdf(pages: list[str]) -> bytes:
    """A real PDF, written by hand: one text line per page."""
    objects = ["<< /Type /Catalog /Pages 2 0 R >>", None, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids = []
    for text in pages:
        stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
        objects.append(f"<< /Length {len(stream)} >>\nstream\n{stream.decode()}\nendstream")
        content = len(objects)
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {content} 0 R "
                       f"/Resources << /Font << /F1 3 0 R >> >> >>")
        kids.append(len(objects))
    objects[1] = f"<< /Type /Pages /Kids [{' '.join(f'{k} 0 R' for k in kids)}] /Count {len(kids)} >>"
    out, offsets = b"%PDF-1.4\n", []
    for i, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{body}\nendobj\n".encode()
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{o:010d} 00000 n \n" for o in offsets).encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    return out


PDF = tiny_pdf(["Every subject starts with the action.", "A deadline goes in the subject line."])


def test_a_pdf_is_read_page_by_page():
    found = passages.read(PDF, "application/pdf")
    assert [(p["where"], p["text"]) for p in found] == [
        ("page 1", "Every subject starts with the action."), ("page 2", "A deadline goes in the subject line.")]


def test_a_recording_is_cut_at_its_sentences_with_their_moments(monkeypatch):
    words = [{"word": w, "start": i * 0.5, "end": i * 0.5 + 0.4} for i, w in
             enumerate("I write the date. Then I send it.".split())]
    monkeypatch.setattr(voice, "transcribe_timed", lambda data, mime: ("", words))
    found = passages.read(b"RIFF", "audio/wav")
    assert [(p["where"], p["text"]) for p in found] == [("0:00–0:01", "I write the date."), ("0:02–0:03", "Then I send it.")]


def test_an_image_is_described_and_said_to_be_urithis_words(monkeypatch):
    monkeypatch.setattr(picture, "describe", lambda data, mime: "A form with a red STOP stamp.")
    [found] = passages.read(b"\x89PNG", "image/png")
    assert found["described"] and found["where"] == "the image"


def test_a_guardian_names_a_passage_by_its_page_or_its_moment():
    pdf = passages.read(PDF, "application/pdf")
    assert passages.find("make a step of page 2", pdf)["page"] == 2
    timed = [{"n": 1, "where": "1:00–1:20", "start": 60.0, "end": 80.0, "text": "x"}]
    assert passages.find("take what I said at 1:10", timed)["n"] == 1
    assert passages.find("nothing named", pdf) is None
    with pytest.raises(passages.Unreadable):
        passages.kind_of("application/zip")


def test_sources_are_kept_per_organisation_and_map(tmp_path):
    store = LocalSources(str(tmp_path))
    record = store.save("acme", "m1", {"name": "a.pdf"}, b"pdf")
    assert store.data("acme", "m1", record["source_id"]) == b"pdf"
    assert store.list("urithi", "m1") == [] and store.list("acme", "m2") == []
    with pytest.raises(ValueError):
        store.save("../urithi", "m1", {"name": "x"}, b"x")


# ── the routes, end to end ───────────────────────────────────────────────────

@pytest.fixture
def guardian(tmp_path, monkeypatch):
    from guardian.engine.workmap import WorkMapStore
    from server import app
    from tests.guardian.test_engine import taught_map

    maps = WorkMapStore(str(tmp_path / "w.sqlite3"))
    set_maps(maps)
    work_map = taught_map()
    maps.save(work_map)
    monkeypatch.setattr(absorb, "find_guardrails", lambda said, **k: [])
    return guardian_client(app), work_map


def _deposit(client, work_map, data=PDF, mime="application/pdf", name="subjects.pdf"):
    return client.post("/api/guardian/sources", json={"map_id": work_map.map_id, "name": name, "mime": mime,
                                                      "data": base64.b64encode(data).decode()})


def test_a_passage_becomes_a_step_that_cites_it_and_is_a_draft(guardian):
    client, work_map = guardian
    source = _deposit(client, work_map).json()["source"]
    proposal = client.post("/api/guardian/sources/propose", json={
        "map_id": work_map.map_id, "source_id": source["source_id"], "said": "make a step of page 2"}).json()["proposal"]
    assert proposal["reason"] == "A deadline goes in the subject line." and proposal["cites"][0]["where"] == "page 2"
    memory = client.get(f"/api/guardian/memory/{work_map.map_id}").json()
    assert any(b["ref"] == f"proposal-{proposal['proposal_id']}" for b in memory["blocks"]), "kept until accepted"
    step = client.post("/api/guardian/sources/accept", json={"map_id": work_map.map_id,
                                                             "proposal_id": proposal["proposal_id"]}).json()["step"]
    seen = client.get(f"/api/guardian/map/{work_map.map_id}").json()
    assert seen["states"][f"step:s{step['number']}"] == "draft" and step["cites"][0]["name"] == "subjects.pdf"


def test_an_image_needs_the_guardians_own_words(guardian, monkeypatch):
    client, work_map = guardian
    monkeypatch.setattr(picture, "describe", lambda data, mime: "A form with a stamp.")
    source = _deposit(client, work_map, data=b"\x89PNG", mime="image/png", name="form.png").json()["source"]
    asked = {"map_id": work_map.map_id, "source_id": source["source_id"], "passage": 1}
    assert client.post("/api/guardian/sources/propose", json=asked).status_code == 422
    proposal = client.post("/api/guardian/sources/propose", json={**asked, "said": "A stamped form is never paid."}).json()
    assert proposal["proposal"]["reason"] == "A stamped form is never paid.", "the guardian's words, never the description"


def test_only_cited_documents_are_archived_and_the_rest_purged(guardian):
    """docs/decisions/0004: saving uploads only what a validated part cites."""
    from apu import meter  # noqa: F401
    from guardian.sources.store import get_archive, get_sources

    client, work_map = guardian
    cited = _deposit(client, work_map).json()["source"]
    unused = _deposit(client, work_map, name="unused.pdf").json()["source"]
    proposal = client.post("/api/guardian/sources/propose", json={
        "map_id": work_map.map_id, "source_id": cited["source_id"], "passage": 1}).json()["proposal"]
    client.post("/api/guardian/sources/accept", json={"map_id": work_map.map_id, "proposal_id": proposal["proposal_id"]})
    client.get(f"/api/guardian/map/{work_map.map_id}/teach-back")
    assert client.post("/api/guardian/confirm", json={"map_id": work_map.map_id, "confirmed": True}).json()["confirmed"]
    archived = get_archive().put_paths
    assert len(archived) == 1 and archived[0].startswith(f"urithi/guardian/sabine/{work_map.map_id}/{cited['source_id']}")
    left = {s["source_id"] for s in get_sources().list("urithi", work_map.map_id)}
    assert left == {cited["source_id"]}, "the document no part cites is purged"
    assert unused["source_id"] not in left


def test_a_deposit_past_the_quota_is_refused(guardian, tmp_path, monkeypatch):
    import json

    from apu import config

    path = tmp_path / "policy.json"
    path.write_text(json.dumps({"quotas": {"guardian": {"deposited_bytes": {"period": "month", "stop": 100}}}}))
    monkeypatch.setattr(config, "POLICY_PATH", str(path))
    client, work_map = guardian
    reply = _deposit(client, work_map)
    assert reply.status_code == 429 and reply.json()["refused"] == "deposited_bytes"


def test_an_excerpt_is_never_more_open_than_the_part_it_supports():
    from guardian.publish import body_id_for, publication_from
    from tests.guardian.test_publishing import confirmed_map

    work_map = confirmed_map()
    step = work_map.steps[0]
    work_map.steps[0] = type(step)(**{**{f: getattr(step, f) for f in step.__dataclass_fields__},
                                      "cites": ({"source_id": "x", "name": "vendors.pdf", "where": "page 4",
                                                 "text": "Unknown suppliers are never paid."},)})
    unit = f"{body_id_for(work_map)}:step-{step.number}"
    published = publication_from(work_map, version=1, access={unit: "community"})
    [found] = published.evidence
    assert (found.unit_id, found.where, found.access) == (unit, "page 4", "community")


def test_a_learner_opens_the_evidence_of_a_part_they_may_see_and_only_that(monkeypatch):
    from fastapi.testclient import TestClient

    from apu import embeddings
    from guardian.publish import body_id_for, publication_from
    from library import store
    from server import app
    from tests.guardian.test_publishing import confirmed_map
    from tests.support import WordEmbedder

    embeddings.set_embedder(WordEmbedder())
    work_map = confirmed_map()
    for i, step in enumerate(work_map.steps):
        work_map.steps[i] = type(step)(**{**{f: getattr(step, f) for f in step.__dataclass_fields__},
                                          "cites": ({"source_id": "x", "name": "doc.pdf", "where": f"page {i + 1}",
                                                     "text": f"Passage {i + 1}."},)})
    body = body_id_for(work_map)
    lib = store.MemoryKnowledgeStore()
    lib.publish(publication_from(work_map, version=1, access={f"{body}:step-2": "restricted"}))
    store.set_store(lib)
    try:
        client = TestClient(app)
        seen = client.get(f"/api/learner/unit/{body}:step-1", params={"person_id": "visitor"}).json()
        assert seen["evidence"] == [{"unit_id": f"{body}:step-1", "name": "doc.pdf", "where": "page 1", "excerpt": "Passage 1."}]
        path = client.get(f"/api/learner/path/{body}", params={"person_id": "visitor"}).json()
        assert all(u["unit_id"] != f"{body}:step-2" for u in path["units"])
        assert client.get(f"/api/learner/unit/{body}:step-2", params={"person_id": "visitor"}).status_code == 404
    finally:
        store.set_store(None)
        embeddings.set_embedder(None)


def test_a_package_carries_no_excerpt_of_a_part_its_learner_may_not_see():
    """The package carries every excerpt the library hands it: the library hands only those visible."""
    import json

    from apu import embeddings
    from guardian.publish import body_id_for, publication_from
    from learner.packages import package
    from library import store
    from tests.guardian.test_publishing import confirmed_map
    from tests.support import WordEmbedder

    embeddings.set_embedder(WordEmbedder())
    try:
        work_map = confirmed_map()
        for i, step in enumerate(work_map.steps):
            work_map.steps[i] = type(step)(**{**{f: getattr(step, f) for f in step.__dataclass_fields__},
                                              "cites": ({"source_id": "x", "name": "doc.pdf", "where": f"page {i + 1}",
                                                         "text": f"Passage {i + 1}."},)})
        body = body_id_for(work_map)
        lib = store.MemoryKnowledgeStore()
        lib.publish(publication_from(work_map, version=1, access={f"{body}:step-2": "restricted"}))
        found = lib.body_units("urithi", body, ("public",))
        assert [e["where"] for e in found["evidence"]] == ["page 1"]
        built = package.build(found, person_id="visitor", organisation="urithi", allowed=("public",))
        assert "Passage 2." not in built["content_json"] and "Passage 1." in json.loads(built["content_json"])["evidence"][0]["excerpt"]
    finally:
        embeddings.set_embedder(None)



def test_an_archive_that_fails_does_not_undo_the_validation(guardian):
    """Measured live: the bucket did not exist, and validating failed whole with a 500."""
    from guardian.sources.store import get_sources, set_archive

    class Down:
        def put(self, path, data, mime_type):
            raise RuntimeError("The specified bucket does not exist.")

    client, work_map = guardian
    cited = _deposit(client, work_map).json()["source"]
    proposal = client.post("/api/guardian/sources/propose", json={
        "map_id": work_map.map_id, "source_id": cited["source_id"], "passage": 1}).json()["proposal"]
    client.post("/api/guardian/sources/accept", json={"map_id": work_map.map_id, "proposal_id": proposal["proposal_id"]})
    client.get(f"/api/guardian/map/{work_map.map_id}/teach-back")
    set_archive(Down())
    reply = client.post("/api/guardian/confirm", json={"map_id": work_map.map_id, "confirmed": True})
    assert reply.status_code == 200 and reply.json()["confirmed"]
    [kept] = get_sources().list("urithi", work_map.map_id)
    assert "bucket does not exist" in kept["archive_pending"] and not kept.get("archived")


def test_a_document_left_archive_pending_is_sent_at_the_next_validation(guardian):
    """A document that stayed archive_pending is uploaded at the next validation and cleared."""
    from guardian.sources.store import get_sources, set_archive

    class Down:
        def put(self, path, data, mime_type):
            raise RuntimeError("The specified bucket does not exist.")

    class Up:
        def __init__(self):
            self.uploaded = []

        def put(self, path, data, mime_type):
            self.uploaded.append((path, len(data), mime_type))
            return f"gs://archive/{path}"

    client, work_map = guardian
    cited = _deposit(client, work_map).json()["source"]
    proposal = client.post("/api/guardian/sources/propose", json={
        "map_id": work_map.map_id, "source_id": cited["source_id"], "passage": 1}).json()["proposal"]
    client.post("/api/guardian/sources/accept", json={"map_id": work_map.map_id, "proposal_id": proposal["proposal_id"]})
    client.get(f"/api/guardian/map/{work_map.map_id}/teach-back")
    set_archive(Down())
    client.post("/api/guardian/confirm", json={"map_id": work_map.map_id, "confirmed": True})
    [pending] = get_sources().list("urithi", work_map.map_id)
    assert "archive_pending" in pending and not pending.get("archived")

    up = Up()
    set_archive(up)
    reply = client.post("/api/guardian/confirm", json={"map_id": work_map.map_id, "confirmed": True})
    assert reply.status_code == 200 and reply.json()["confirmed"]
    [archived] = get_sources().list("urithi", work_map.map_id)
    assert archived["archived"].startswith("gs://archive/urithi/guardian/sabine/")
    assert "archive_pending" not in archived
    assert len(up.uploaded) == 1


SCREEN = base64.b64encode(b"\xff\xd8\xff screen").decode()


def test_a_screen_remembered_with_words_is_a_step_citing_it(guardian, monkeypatch):
    """Asked by the owner after a real class: "remember this" about what is on the screen. The
    screen is kept as a source, read by the class's fast model, and the guardian's words are the
    step; Urithi's description is never the step."""
    from apu import config
    from guardian.api import routes

    client, work_map = guardian
    read_by = []
    monkeypatch.setattr(picture, "describe",
                        lambda data, mime, model=None, focus="": read_by.append((model, focus)) or "Announce in: #members")
    monkeypatch.setattr(routes, "_voiced", lambda text: {"audio": None, "words": []})
    monkeypatch.setattr(absorb, "find_guardrails", lambda said, **k: [])
    kept = client.post("/api/guardian/remember", json={
        "map_id": work_map.map_id, "frame": SCREEN, "at": 166.5,
        "said": "Members only is for the second reminder, never the first announcement."}).json()
    assert read_by == [(config.CLASS_VISION_MODEL, "Members only is for the second reminder, never the first announcement.")], \
        "the part the guardian names is the part read"
    proposal = kept["proposal"]
    step = client.post("/api/guardian/save", json={"map_id": work_map.map_id, "proposal_id": proposal["proposal_id"]}).json()["step"]
    assert step["reason"].startswith("Members only is for the second reminder")
    assert step["cites"][0]["where"] == "the screen at 2:46" and "#members" in step["cites"][0]["text"]
    stored = next(s for s in get_maps_of(work_map) if s.number == step["number"])
    assert stored.cites[0]["where"] == "the screen at 2:46", "the step kept in the map cites the screen"
    seen = client.get(f"/api/guardian/map/{work_map.map_id}").json()
    assert seen["confirmed"] is False and seen["states"][f"step:s{step['number']}"] == "draft"
    sources = client.get(f"/api/guardian/sources/{work_map.map_id}").json()["sources"]
    assert [s["name"] for s in sources] == ["screen-2m46.jpg"]


def test_a_screen_remembered_without_words_is_asked_about_and_the_answer_cites_it(guardian, monkeypatch):
    from guardian.api import routes

    client, work_map = guardian
    monkeypatch.setattr(picture, "describe", lambda data, mime, model=None, focus="": "A date picker on Thu 15 Oct.")
    monkeypatch.setattr(routes, "_voiced", lambda text: {"audio": None, "words": []})
    monkeypatch.setattr(absorb, "find_guardrails", lambda said, **k: [])
    asked = client.post("/api/guardian/remember", json={"map_id": work_map.map_id, "frame": SCREEN, "at": 75.0}).json()
    assert asked["question"] == "What should I remember about this screen?" and "step" not in asked
    answered = client.post("/api/guardian/answer", json={
        "map_id": work_map.map_id, "said": "The meetup is always announced two weeks ahead."}).json()
    saved = client.post("/api/guardian/save", json={
        "map_id": work_map.map_id, "proposal_id": answered["proposal"]["proposal_id"]}).json()
    stored = next(s for s in get_maps_of(work_map) if s.number == saved["step"]["number"])
    assert stored.title == "The meetup is always announced two weeks ahead", "named by what was said"
    assert stored.cites[0]["where"] == "the screen at 1:15"


def get_maps_of(work_map):
    from guardian.memory.store import get_maps

    return get_maps().load(work_map.map_id).steps


@pytest.mark.parametrize("said, title", [
    ("I want you to keep the information on the venue, the format, and the last meetup.",
     "The venue, the format, and the last meetup"),
    ("Okay, so I want you to keep the information on the part from November meetup",
     "The part from November meetup"),
    ("Je veux que tu gardes les informations sur le lieu et le format", "Le lieu et le format"),
    ("Members only is for the second reminder.", "Members only is for the second reminder"),
])
def test_a_screen_kept_is_named_by_what_to_keep_not_by_the_request(said, title):
    """Measured in a live run: the step was titled "I want you to keep the information on the
    venue...". The request is taken off the title; the step's words stay the guardian's, whole."""
    from guardian.api import source_routes
    from guardian.engine import absorb

    assert absorb.title_for(source_routes._named(said), "", limit=140) == title


def test_a_step_kept_from_the_screen_carries_the_named_title_and_the_whole_words(guardian, monkeypatch):
    from guardian.api import routes

    client, work_map = guardian
    monkeypatch.setattr(picture, "describe", lambda data, mime, model=None, focus="": "Venue: Dockside Library")
    monkeypatch.setattr(routes, "_voiced", lambda text: {"audio": None, "words": []})
    said = "I want you to keep the information on the venue and the format."
    proposal = client.post("/api/guardian/remember", json={"map_id": work_map.map_id, "frame": SCREEN, "at": 35.0,
                                                           "said": said}).json()["proposal"]
    step = client.post("/api/guardian/save", json={"map_id": work_map.map_id, "proposal_id": proposal["proposal_id"]}).json()["step"]
    assert step["title"] == "The venue and the format" and step["reason"] == said
