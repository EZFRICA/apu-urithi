"""
The guardian's working memory, and a knowledge taught over several sessions.

Target: guardian/memory/working.py, the tell, debrief, rule, memory and contents routes.

Step 2 of docs/plan.md (docs/plan-done.md): what Urithi is in the middle of is kept by a store, so "Carry on
teaching" reopens it where it was left, the server restarted or not.
"""

import pytest

from guardian.memory.store import set_maps, set_sessions
from guardian.memory.working import MAX_BLOCKS, SqliteWorkingMemories, WorkingMemory
from tests.support import guardian_client


def test_the_list_keeps_recent_first_then_open_then_retained():
    memory = WorkingMemory()
    memory.put("retained", "rule-a", {"n": 1})
    memory.put("open", "question", {"n": 2})
    memory.put("recent", "said", {"n": 3})
    memory.put("open", "case-1", {"n": 4})
    assert [b["ref"] for b in memory.ordered()] == ["said", "case-1", "question", "rule-a"]
    memory.put("open", "question", {"n": 5})                     # touched again: front of its kind
    assert [b["ref"] for b in memory.ordered()] == ["said", "question", "case-1", "rule-a"]
    assert memory.drop("case-1") and not memory.find("case-1")
    links = memory.ordered()
    assert all(links[i]["next"] == links[i + 1]["id"] and links[i + 1]["prev"] == links[i]["id"]
               for i in range(len(links) - 1)), "linked both ways"


def test_past_the_bound_the_oldest_recent_go_and_nothing_open_is_lost():
    memory = WorkingMemory()
    memory.put("open", "question", {})
    for i in range(MAX_BLOCKS + 10):
        memory.put("recent", f"said-{i}", {})
    assert len(memory.blocks) == MAX_BLOCKS and memory.find("question")
    assert memory.find(f"said-{MAX_BLOCKS + 9}") and not memory.find("said-0")


def test_a_memory_is_one_organisations_one_knowledges(tmp_path):
    store = SqliteWorkingMemories(str(tmp_path / "w.sqlite3"))
    memory = WorkingMemory()
    memory.put("open", "question", {"text": "Why?"})
    store.save("acme", "m1", memory)
    assert store.load("acme", "m1").find("question")
    assert not store.load("urithi", "m1").find("question") and not store.load("acme", "m2").find("question")
    with pytest.raises(ValueError):
        store.load("", "m1")


@pytest.fixture
def teaching(tmp_path, monkeypatch):
    from guardian.api import routes
    from guardian.engine.workmap import WorkMapStore
    from server import app
    from tests.guardian.test_engine import taught_map

    maps = WorkMapStore(str(tmp_path / "w.sqlite3"))
    set_maps(maps)
    work_map = taught_map()
    maps.save(work_map)
    monkeypatch.setattr(routes, "_voiced", lambda text: {"audio": None, "words": []})
    return guardian_client(app), work_map


def test_a_debrief_survives_a_restart_of_the_server(teaching):
    """The cases still to test come back from the working memory when the session is gone."""
    client, work_map = teaching
    first = client.post("/api/guardian/debrief", json={"map_id": work_map.map_id}).json()["probe"]
    assert client.get(f"/api/guardian/memory/{work_map.map_id}").json()["cases"] >= 1
    set_sessions(None)                                                # what a restart forgets
    reply = client.post("/api/guardian/rule", json={"map_id": work_map.map_id, "probe_id": first["probe_id"],
                                                    "said": "Yes, it applies."}).json()
    assert "error" not in reply and reply["ruling"]["said"] == "Yes, it applies."


def test_the_contents_hold_every_step_once_and_make_a_draft(teaching):
    client, work_map = teaching
    ids = [s.step_id for s in work_map.steps]
    assert client.post("/api/guardian/contents", json={"map_id": work_map.map_id, "order": ids[:-1]}).status_code == 422
    assert client.post("/api/guardian/contents", json={"map_id": work_map.map_id, "order": ids + ["x"]}).status_code == 422
    reply = client.post("/api/guardian/contents", json={"map_id": work_map.map_id, "order": list(reversed(ids)),
                                                        "sections": [{"title": "All of it", "steps": ids}]})
    assert reply.status_code == 200
    seen = client.get(f"/api/guardian/map/{work_map.map_id}").json()
    assert seen["order"] == list(reversed(ids)) and seen["confirmed"] is False
    assert [s["section"] for s in seen["steps"]] == ["All of it"] * len(ids)


def test_confirming_keeps_the_version_that_is_then_published(teaching):
    """Validated through the route, then taught more: the preview publishes what was validated."""
    from guardian.engine.workmap import Step
    from guardian.memory.store import get_maps

    client, work_map = teaching
    client.get(f"/api/guardian/map/{work_map.map_id}/teach-back")
    assert client.post("/api/guardian/confirm", json={"map_id": work_map.map_id, "confirmed": True}).json()["confirmed"]
    later = get_maps().load(work_map.map_id)
    later.steps.append(Step(step_id="s9", number=9, title="Taught after", screen_moment=1.0, observed="o",
                            decision="d", reason="Said after the teach-back.", guardrail_ids=()))
    later.confirmed_at = None
    get_maps().save(later)
    seen = client.get(f"/api/guardian/map/{work_map.map_id}").json()
    assert seen["states"]["step:s9"] == "draft" and seen["validated"]
    preview = client.post("/api/guardian/preview", json={"map_id": work_map.map_id, "person_id": "sabine"}).json()
    assert "Taught after" not in {u["text"] for u in preview["units"]}


def test_what_a_class_captures_is_kept_and_is_a_draft(teaching, monkeypatch):
    """Step 4: the screen's change goes to the working memory; the guardian's answer becomes a
    draft step, validated later on the guardian's page."""
    from guardian.engine import questions, vision

    client, work_map = teaching
    client.get(f"/api/guardian/map/{work_map.map_id}/teach-back")
    client.post("/api/guardian/confirm", json={"map_id": work_map.map_id, "confirmed": True})
    monkeypatch.setattr(vision, "what_changed",
                        lambda frame, session, at: questions.Observation(at=at, changed="cost center changed to 0670"))
    monkeypatch.setattr(questions, "word_question", lambda *a, **k: "Why that cost center?")
    monkeypatch.setattr(absorb_module(), "find_guardrails", lambda said, **k: [])
    asked = None
    for at in (10.0, 20.0, 30.0, 40.0):
        reply = client.post("/api/guardian/observe", json={"map_id": work_map.map_id, "at": at, "frame": "x"}).json()
        asked = asked or reply.get("question")
    memory = client.get(f"/api/guardian/memory/{work_map.map_id}").json()
    assert any(b["ref"] == "saw" and "0670" in b["content"]["changed"] for b in memory["blocks"])
    assert asked == "Why that cost center?"
    ans = client.post("/api/guardian/answer", json={"map_id": work_map.map_id,
                                                    "said": "Equipment over five thousand is capex."}).json()
    step = client.post("/api/guardian/save", json={"map_id": work_map.map_id,
                                                   "proposal_id": ans["proposal"]["proposal_id"]}).json()["step"]
    seen = client.get(f"/api/guardian/map/{work_map.map_id}").json()
    assert seen["confirmed"] is False and seen["states"][f"step:s{step['number']}"] == "draft"


def absorb_module():
    from guardian.engine import absorb

    return absorb


def test_a_class_reads_a_frame_only_when_the_screen_changed_and_says_back_what_it_kept(teaching, monkeypatch):
    """Measured in a real class: the guardian worked in the window they shared, and Urithi, in
    a background tab, neither asked nor could be answered without going back to it. Now a frame
    is read only when the screen changed (guardian/ui/teach/capture.js), the pauses between are
    still counted, and the answer kept is said back aloud."""
    from guardian.api import routes
    from guardian.engine import questions, vision

    client, work_map = teaching
    read = []

    def seen(frame, session, at):
        read.append(at)
        return questions.Observation(at=at, changed="channel set to #announcements")

    monkeypatch.setattr(vision, "what_changed", seen)
    monkeypatch.setattr(questions, "word_question", lambda *a, **k: "Why the public channel?")
    monkeypatch.setattr(absorb_module(), "find_guardrails", lambda said, **k: [])
    monkeypatch.setattr(routes, "_voiced", lambda text: {"audio": f"spoken: {text}", "words": []})
    asked, saw = None, []
    for at, frame in ((10.0, "x"), (14.0, None), (18.0, None), (22.0, None), (26.0, None)):
        reply = client.post("/api/guardian/observe", json={"map_id": work_map.map_id, "at": at, "frame": frame}).json()
        asked = asked or reply.get("question")
        saw += [reply["change"]] if reply.get("change") else []
    assert saw == ["channel set to #announcements"], "what was seen reaches the notes, question or not"
    assert read == [10.0], "a screen nobody touched is not sent to be read"
    assert asked == "Why the public channel?", "the pause after the change is still seen"
    kept = client.post("/api/guardian/answer", json={"map_id": work_map.map_id,
                                                      "said": "Newcomers only see the public channel."}).json()
    # Said back as what it is, a proposal, never "as step N" before anything is saved (0016).
    assert kept["noted"] == f'Proposed: {kept["proposal"]["title"]}. Say "save this" to keep it.'
    assert kept["audio"] == f"spoken: {kept['noted']}", "said back aloud"


def test_a_class_begun_again_on_the_same_map_can_ask_again(teaching, monkeypatch):
    """Measured in a live run: a class ended with a question unanswered, a new one began on the
    same map with its clock at 0, and nothing was ever asked: the old question was still
    waiting, and the last question was still 12 s into a clock that had started again."""
    from guardian.api import routes
    from guardian.engine import questions, vision

    client, work_map = teaching
    monkeypatch.setattr(vision, "what_changed",
                        lambda frame, session, at: questions.Observation(at=at, changed="channel set to #announcements")
                        if frame else None)
    monkeypatch.setattr(questions, "word_question", lambda *a, **k: "Why the public channel?")
    monkeypatch.setattr(routes, "_voiced", lambda text: {"audio": None, "words": []})

    def a_class():
        asked = None
        for at, frame in ((6.0, "x"), (10.0, None), (14.0, None), (18.0, None)):
            reply = client.post("/api/guardian/observe", json={"map_id": work_map.map_id, "at": at, "frame": frame}).json()
            asked = asked or reply.get("question")
        return asked

    assert a_class() == "Why the public channel?", "the first class asks"
    assert a_class() == "Why the public channel?", "and so does the next, its clock begun again"


def test_a_recording_in_class_is_heard_before_it_is_routed(teaching, monkeypatch):
    """Measured in a live run: with no live words, "keep the information on the venue" went
    straight to be an answer. A recording is heard first, and its words decide where it goes."""
    import base64

    from apu.modality import voice

    client, work_map = teaching
    monkeypatch.setattr(voice, "transcribe", lambda audio, mime_type="audio/wav": "Keep the information on the venue.")
    heard = client.post("/api/guardian/hear", json={"map_id": work_map.map_id,
                                                    "audio": base64.b64encode(b"RIFF").decode()}).json()
    assert heard == {"said": "Keep the information on the venue."}
    memory = client.get(f"/api/guardian/memory/{work_map.map_id}").json()
    assert not any(b["ref"] == "said" for b in memory["blocks"]), "heard, not yet taught"
