"""
Decision 0016, after the review of 2026-10-14: only the guardian's explicit word saves, a saved step
holds only its own rules, what is forgotten or ignored stays aside, a change before saving is what
is saved, and two requests on one working memory never undo each other.
"""

import itertools

import pytest

from guardian.api import routes
from guardian.engine import absorb, commands, questions
from guardian.engine.commands import Command
from guardian.engine.workmap import Guardrail
from guardian.memory.store import get_maps, set_maps
from guardian.memory.working import SqliteWorkingMemories, get_working
from tests.support import guardian_client


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
    monkeypatch.setattr(routes, "_voiced", lambda text: {"audio": None, "words": []})
    monkeypatch.setattr(questions, "judge_learner_gap", lambda *a, **k: questions.PupilJudgment(None, 0, "", ""))
    return guardian_client(app), work_map


def _propose(work_map, proposal: dict) -> None:
    memory = get_working().load(work_map.organisation, work_map.map_id)
    memory.put("open", f"proposal-{proposal['proposal_id']}", proposal)
    get_working().save(work_map.organisation, work_map.map_id, memory)


def _step(pid: str, reason: str, rules=()) -> dict:
    return {"proposal_id": pid, "kind": "step", "origin": "teach", "title": reason, "reason": reason,
            "observed": reason, "decision": reason, "at": 1.0, "said_at": "", "rules": list(rules), "cites": []}


def _proposals(client, work_map) -> list[dict]:
    return client.get(f"/api/guardian/map/{work_map.map_id}").json()["proposals"]


def test_a_step_saved_without_a_rule_holds_none_and_forgetting_it_keeps_every_rule(guardian, monkeypatch):
    """Found in the review of 2026-10-14: a step saved with no rule was given every rule of the knowledge,
    and "forget that" after the save deleted all of them and their cases."""
    client, work_map = guardian
    _propose(work_map, _step("p1", "Two talks fill the evening, so every yes is also a no to someone."))
    saved = client.post("/api/guardian/save", json={"map_id": work_map.map_id, "proposal_id": "p1"}).json()
    after = get_maps().load(work_map.map_id)
    assert saved["saved_kind"] == "step" and after.steps[-1].guardrail_ids == ()
    assert after.rails_for(after.steps[-1]) == []

    monkeypatch.setattr(commands, "classify_command", lambda said, **k: Command(intent="forget", what=said))
    gone = client.post("/api/guardian/command", json={"map_id": work_map.map_id, "said": "Forget the saved step."}).json()
    left = get_maps().load(work_map.map_id)
    assert gone["removed_number"] == 2 and len(left.steps) == 1
    assert {g.guardrail_id for g in left.guardrails} == {"stop1", "check1"}, "no rule went with the step"


def test_forgetting_a_saved_step_keeps_a_rule_another_step_holds(guardian, monkeypatch):
    client, work_map = guardian
    said = "2026-10-14T10:00:00+00:00"
    held = {"guardrail_id": "stop1", "when": "w", "then": "t", "quote": "q", "at": 1.0, "step_said_at": said}
    own = {"guardrail_id": "g-own", "when": "a slot is asked for pizza", "then": "never trade it", "quote": "q",
           "at": 1.0, "severity": "stop", "step_said_at": said}
    _propose(work_map, {**_step("p2", "Check the sponsor first.", rules=[held, own]), "said_at": said})
    client.post("/api/guardian/save", json={"map_id": work_map.map_id, "proposal_id": "p2"})
    monkeypatch.setattr(commands, "classify_command", lambda said, **k: Command(intent="forget", what=said))
    client.post("/api/guardian/command", json={"map_id": work_map.map_id, "said": "Forget the saved step."})
    ids = {g.guardrail_id for g in get_maps().load(work_map.map_id).guardrails}
    assert "stop1" in ids and "check1" in ids, "held by step 1, so kept"
    assert "g-own" not in ids, "said with the forgotten step alone, so gone with it"


def test_a_forgotten_rule_is_not_proposed_again(guardian, monkeypatch):
    """Found in the review of 2026-10-14: "forget that" dropped a rule's proposal and kept the rule in
    the notes, and the next look at the notes proposed it again."""
    client, work_map = guardian
    ids = itertools.count(1)
    monkeypatch.setattr(absorb, "find_guardrails", lambda said, **k: [Guardrail(
        guardrail_id=f"g-{next(ids)}", when="a sponsor pays for the pizza", then="never trade a slot",
        quote=said, asked_at=1.0)] if said.startswith("When") else [])
    client.post("/api/guardian/tell", json={"map_id": work_map.map_id,
                                             "said": "When a sponsor pays for the pizza, never trade a slot."})
    rule = next(p for p in _proposals(client, work_map) if p["kind"] == "rule")
    monkeypatch.setattr(commands, "classify_command", lambda said, **k: Command(intent="forget", what=said))
    client.post("/api/guardian/command", json={"map_id": work_map.map_id, "said": "Forget that."})
    # The judge reads the same notes again and offers the rule, as a model would.
    monkeypatch.setattr(absorb, "judge_proposals", lambda *a, **k: [dict(rule)])
    monkeypatch.setattr(commands, "classify_command", lambda said, **k: Command(intent="none"))
    client.post("/api/guardian/tell", json={"map_id": work_map.map_id, "said": "Speakers confirm a week before."})
    assert rule["guardrail_id"] not in {p.get("guardrail_id") for p in _proposals(client, work_map)}
    memory = get_working().load(work_map.organisation, work_map.map_id)
    assert memory.find(f"rule-{rule['guardrail_id']}") is None, "not kept as a noted rule either"


def test_a_rule_changed_before_saving_is_saved_in_its_new_words(guardian, monkeypatch):
    """Found in the review of 2026-10-14: the guardian corrected a proposed rule, the page showed the
    correction, and the rule saved was the first wording."""
    client, work_map = guardian
    rule = {"guardrail_id": "g-pizza", "when": "pizza is offered", "then": "say thanks", "quote": "q", "at": 1.0}
    _propose(work_map, {**_step("rule-g-pizza", "q", rules=[rule]), "kind": "rule", "origin": "rule",
                        "guardrail_id": "g-pizza", "when": rule["when"], "then": rule["then"]})
    monkeypatch.setattr(absorb, "find_guardrails", lambda said, **k: [Guardrail(
        guardrail_id="fresh", when="a sponsor asks for a slot for pizza", then="never trade the slot",
        quote=said, asked_at=1.0)])
    words = "When a sponsor asks for a slot for pizza, never trade the slot."
    changed = client.post("/api/guardian/proposal/change", json={"map_id": work_map.map_id,
                          "proposal_id": "rule-g-pizza", "reason": words}).json()["proposal"]
    assert changed["then"] == "never trade the slot" and changed["guardrail_id"] == "g-pizza"
    client.post("/api/guardian/save", json={"map_id": work_map.map_id, "proposal_id": "rule-g-pizza"})
    saved = get_maps().load(work_map.map_id).guardrail("g-pizza")
    assert (saved.when, saved.then, saved.quote) == ("a sponsor asks for a slot for pizza", "never trade the slot", words)


def test_a_changed_step_stays_proposed_when_the_judge_picks_another_note(guardian, monkeypatch):
    client, work_map = guardian
    memory = get_working().load(work_map.organisation, work_map.map_id)
    memory.put("recent", "note-n1", {"note_id": "n1", "kind": "tell", "text": "We announce two weeks ahead.", "rules": []})
    memory.put("open", "proposal-n1", {**_step("n1", "We announce two weeks ahead."), "origin": "tell"})
    get_working().save(work_map.organisation, work_map.map_id, memory)
    client.post("/api/guardian/proposal/change", json={"map_id": work_map.map_id, "proposal_id": "n1",
                                                       "reason": "We announce at least 14 days ahead."})
    monkeypatch.setattr(absorb, "judge_proposals", lambda *a, **k: [_step("n2", "Another note.")])
    memory = get_working().load(work_map.organisation, work_map.map_id)
    routes._refresh_proposals(get_maps().load(work_map.map_id), memory, use_model=False)
    get_working().save(work_map.organisation, work_map.map_id, memory)
    reasons = {p["reason"] for p in _proposals(client, work_map)}
    assert "We announce at least 14 days ahead." in reasons


def test_a_save_made_while_a_frame_is_judged_is_not_undone(tmp_path):
    """Found in the review of 2026-10-14: a frame being judged held the list it had loaded for seconds,
    then wrote it back whole, and a proposal just saved came back as waiting."""
    store = SqliteWorkingMemories(str(tmp_path / "w.sqlite3"))
    first = store.load("urithi", "m")
    first.put("open", "proposal-p1", {"proposal_id": "p1"})
    first.put("open", "proposal-p2", {"proposal_id": "p2"})
    store.save("urithi", "m", first)

    judging = store.load("urithi", "m")             # the frame, about to call the model
    saving = store.load("urithi", "m")              # the guardian, saying "save this"
    saving.drop("proposal-p1")
    saving.put("retained", "ignored-p2", {"proposal_id": "p2"})
    store.save("urithi", "m", saving)
    with judging.derived():                          # proposals judged again from the old list
        judging.put("open", "proposal-p1", {"proposal_id": "p1"})
    judging.put("recent", "saw", {"changed": "Date set"})
    store.save("urithi", "m", judging)

    now = store.load("urithi", "m")
    assert now.find("proposal-p1") is None, "the save stands"
    assert now.find("ignored-p2") is not None, "the ignore stands"
    assert now.find("saw") is not None, "what the frame saw is kept all the same"


def test_a_frame_judged_during_a_save_through_the_routes_does_not_bring_the_proposal_back(guardian, monkeypatch):
    client, work_map = guardian
    memory = get_working().load(work_map.organisation, work_map.map_id)
    memory.put("recent", "note-n1", {"note_id": "n1", "kind": "tell", "text": "Two talks fill the evening.", "rules": []})
    memory.put("open", "proposal-n1", {**_step("n1", "Two talks fill the evening."), "origin": "tell"})
    get_working().save(work_map.organisation, work_map.map_id, memory)

    def judged_while_saved(*a, **k):
        routes.save_proposal(routes.SaveBody(map_id=work_map.map_id, proposal_id="n1"))
        return [{**_step("n1", "Two talks fill the evening."), "origin": "tell"}]

    monkeypatch.setattr(absorb, "judge_proposals", judged_while_saved)
    memory = get_working().load(work_map.organisation, work_map.map_id)
    routes._refresh_proposals(get_maps().load(work_map.map_id), memory)
    get_working().save(work_map.organisation, work_map.map_id, memory)
    assert all(p["proposal_id"] != "n1" for p in _proposals(client, work_map))
    assert len(get_maps().load(work_map.map_id).steps) == 2, "saved once"


def test_a_command_saves_only_on_the_guardians_explicit_words(guardian, monkeypatch):
    """Found in the review of 2026-10-14: every line said in class reaches /command first, and there a
    model answering "save" was enough to write knowledge."""
    client, work_map = guardian
    _propose(work_map, _step("p3", "Check the venue a week before."))
    monkeypatch.setattr(commands, "classify_command", lambda said, **k: Command(intent="save", what="the venue"))
    guessed = client.post("/api/guardian/command", json={"map_id": work_map.map_id,
                          "said": "Saving the agenda early helps newcomers."}).json()
    assert guessed["intent"] == "none" and len(get_maps().load(work_map.map_id).steps) == 1
    said = client.post("/api/guardian/command", json={"map_id": work_map.map_id, "said": "Save this."}).json()
    assert said["saved_kind"] == "step" and len(get_maps().load(work_map.map_id).steps) == 2


def test_what_save_this_names_is_never_the_models_reading(monkeypatch):
    monkeypatch.setattr(commands, "_command_model_ready", lambda: True)
    monkeypatch.setattr(commands, "call_main_model", lambda *a, **k: '{"intent": "save", "what": "the rule about pizza"}')
    assert commands.classify_command("Save this.") == Command(intent="save", what="")
    assert commands.classify_command("Save the step about the venue.").what == "the step about the venue"


def test_a_judge_answering_none_proposes_no_step(monkeypatch):
    """Found in the review of 2026-10-14: "none" was read as a note's id, and the latest note was
    proposed anyway."""
    from tests.guardian.test_engine import taught_map

    monkeypatch.setattr(absorb, "_proposal_model_ready", lambda: True)
    monkeypatch.setattr(absorb, "call_main_model", lambda *a, **k: '{"step_note_id": "none", "rule_id": ""}')
    notes = [{"note_id": "n1", "text": "We always announce in #announcements two weeks ahead, so newcomers plan.",
              "kind": "tell", "rules": []}]
    assert absorb.judge_proposals(taught_map(), notes) == []


def test_a_follow_up_asked_in_class_is_the_one_question_waiting(guardian, monkeypatch):
    """Found in the review of 2026-10-14: a follow-up asked after something said in class was left
    unmarked, so the screen asked a second question over it and it could not be passed."""
    client, work_map = guardian
    session = routes._session(work_map.map_id)
    session["last_at"] = 30.0
    monkeypatch.setattr(questions, "judge_learner_gap", lambda *a, **k: questions.PupilJudgment(
        questions.QuestionKind.REASON, 5, "why", "Why two talks?"))
    monkeypatch.setattr(questions, "should_ask", lambda *a, **k: True)
    reply = client.post("/api/guardian/tell", json={"map_id": work_map.map_id, "said": "Two talks fill the evening."}).json()
    assert reply["question"] == "Why two talks?"
    assert session["pending"]["question"] == "Why two talks?" and session["last_question_at"] == 30.0
    passed = client.post("/api/guardian/pass", json={"map_id": work_map.map_id}).json()
    assert passed["passed"] is True


def test_the_class_page_shows_a_follow_up_with_pass_like_any_question():
    from pathlib import Path

    teach = (Path(__file__).resolve().parents[2] / "guardian/ui/teach/teach.js").read_text(encoding="utf-8")
    tell_branch = teach[teach.index('post("/api/guardian/tell"'):teach.index("async refreshMap()")]
    assert "if (reply.question) {" in tell_branch and "this.classroom.onQuestion(reply);" in tell_branch


def test_a_saved_step_forgotten_does_not_come_back_as_a_proposal(guardian, monkeypatch):
    """Measured live on 2026-10-14: "Forget the saved step." removed it, and the next look at the notes
    proposed the same words again, its note judged anew once the step was gone."""
    client, work_map = guardian
    words = "We announce every meetup in #announcements at least 14 days ahead, so newcomers can plan."
    memory = get_working().load(work_map.organisation, work_map.map_id)
    memory.put("recent", "note-n9", {"note_id": "n9", "kind": "answer", "text": words, "title": words, "rules": []})
    memory.put("open", "proposal-n9", {**_step("n9", words), "origin": "answer"})
    get_working().save(work_map.organisation, work_map.map_id, memory)
    client.post("/api/guardian/save", json={"map_id": work_map.map_id, "proposal_id": "n9"})
    monkeypatch.setattr(commands, "classify_command", lambda said, **k: Command(intent="forget", what=said))
    client.post("/api/guardian/command", json={"map_id": work_map.map_id, "said": "Forget the saved step."})
    memory = get_working().load(work_map.organisation, work_map.map_id)
    routes._refresh_proposals(get_maps().load(work_map.map_id), memory, use_model=False)
    get_working().save(work_map.organisation, work_map.map_id, memory)
    assert all(p.get("reason") != words for p in _proposals(client, work_map))



def test_a_proposal_said_while_the_screen_changes_is_kept(guardian, monkeypatch):
    """Found in the second review of 2026-10-14: a frame noting what it saw meanwhile counted as a conflict,
    and the step just proposed to the guardian was dropped: "Proposed: ..." said, nothing waiting."""
    client, work_map = guardian
    words = "We announce every meetup in #announcements at least 14 days ahead, so newcomers can plan."
    real_judge = absorb.judge_proposals

    def judged_while_a_frame_saw(*a, **k):
        frame = get_working().load(work_map.organisation, work_map.map_id)
        frame.put("recent", "saw", {"changed": "Date set", "at": 9.0})
        get_working().save(work_map.organisation, work_map.map_id, frame)
        return real_judge(*a, **{**k, "use_model": False})

    monkeypatch.setattr(absorb, "judge_proposals", judged_while_a_frame_saw)
    reply = client.post("/api/guardian/tell", json={"map_id": work_map.map_id, "said": words}).json()
    assert reply["noted"].startswith("Proposed: ")
    assert any(p.get("reason") == words for p in _proposals(client, work_map)), "said as proposed, so waiting"
    assert get_working().load(work_map.organisation, work_map.map_id).find("saw") is not None


def test_an_unrelated_write_keeps_what_was_judged_and_a_deleted_list_stays_deleted(tmp_path):
    store = SqliteWorkingMemories(str(tmp_path / "w.sqlite3"))
    first = store.load("urithi", "m")
    first.put("recent", "note-n1", {"note_id": "n1", "text": "t"})
    store.save("urithi", "m", first)
    judging, frame = store.load("urithi", "m"), store.load("urithi", "m")
    frame.put("recent", "saw", {"changed": "x"})
    store.save("urithi", "m", frame)
    with judging.derived():
        judging.put("open", "proposal-n1", {"proposal_id": "n1"})
    store.save("urithi", "m", judging)
    assert store.load("urithi", "m").find("proposal-n1") is not None

    late = store.load("urithi", "m")
    store.forget("urithi", "m")                      # the knowledge deleted while a request held it
    late.put("recent", "saw", {"changed": "y"})
    store.save("urithi", "m", late)
    assert store.load("urithi", "m").find("note-n1") is None, "not written back"


@pytest.mark.parametrize("said", ["Can you save this?", "Could you save this one please?", "Peux-tu garder ça ?",
                                  "Tu peux sauvegarder la proposition ?"])
def test_a_polite_request_to_save_still_saves(guardian, monkeypatch, said):
    """Found in the second review of 2026-10-14: once /command needed the guardian's words, "Can you save
    this?" was no longer a save, and became a note."""
    client, work_map = guardian
    _propose(work_map, _step("p5", "Check the venue a week before."))
    monkeypatch.setattr(commands, "_command_model_ready", lambda: True)
    monkeypatch.setattr(commands, "call_main_model", lambda *a, **k: '{"intent": "ask_pupil", "what": ""}')
    reply = client.post("/api/guardian/command", json={"map_id": work_map.map_id, "said": said}).json()
    assert reply.get("saved_kind") == "step" and len(get_maps().load(work_map.map_id).steps) == 2


def test_sauvegarder_names_what_follows_it():
    m = commands._SAVE_RE.match("Tu peux sauvegarder la règle ?")
    assert commands._extract_save_what(m) == "la règle"


def test_a_rule_saved_on_its_own_stays_when_the_step_before_it_is_forgotten(guardian, monkeypatch):
    """Found in the second review of 2026-10-14: a rule saved alone is attached to the step before it,
    and forgetting that step deleted the rule the guardian had saved for itself."""
    client, work_map = guardian
    _propose(work_map, {**_step("p6", "Two talks fill the evening."), "said_at": "2026-10-14T10:00:00+00:00"})
    client.post("/api/guardian/save", json={"map_id": work_map.map_id, "proposal_id": "p6"})
    alone = {"guardrail_id": "g-alone", "when": "a sponsor wants a slot", "then": "decline", "quote": "q",
             "severity": "stop", "at": 2.0, "step_said_at": "2026-10-14T10:05:00+00:00"}
    _propose(work_map, {**_step("rule-g-alone", "q", rules=[alone]), "kind": "rule", "origin": "rule",
                        "guardrail_id": "g-alone", "said_at": alone["step_said_at"]})
    client.post("/api/guardian/save", json={"map_id": work_map.map_id, "proposal_id": "rule-g-alone"})
    assert "g-alone" in get_maps().load(work_map.map_id).steps[-1].guardrail_ids, "attached to the step before it"
    monkeypatch.setattr(commands, "classify_command", lambda said, **k: Command(intent="forget", what=said))
    client.post("/api/guardian/command", json={"map_id": work_map.map_id, "said": "Forget the saved step."})
    after = get_maps().load(work_map.map_id)
    assert len(after.steps) == 1 and after.guardrail("g-alone") is not None


def test_save_this_never_saves_a_note_just_ignored(guardian):
    """Found in the second review of 2026-10-14: with nothing else waiting, "save this" saved the latest note,
    the one the guardian had just ignored."""
    client, work_map = guardian
    memory = get_working().load(work_map.organisation, work_map.map_id)
    memory.put("recent", "note-n7", {"note_id": "n7", "kind": "tell", "text": "Hello everyone, welcome.", "rules": []})
    memory.put("open", "proposal-n7", {**_step("n7", "Hello everyone, welcome."), "origin": "tell"})
    get_working().save(work_map.organisation, work_map.map_id, memory)
    client.post("/api/guardian/proposal/ignore", json={"map_id": work_map.map_id, "proposal_id": "n7"})
    reply = client.post("/api/guardian/save", json={"map_id": work_map.map_id})
    assert reply.status_code == 404 and len(get_maps().load(work_map.map_id).steps) == 1


def test_a_step_reworded_before_saving_and_forgotten_does_not_come_back(guardian, monkeypatch):
    client, work_map = guardian
    memory = get_working().load(work_map.organisation, work_map.map_id)
    first = "We always announce in #announcements two weeks ahead, so newcomers can plan their evening."
    memory.put("recent", "note-n8", {"note_id": "n8", "kind": "tell", "text": first, "rules": []})
    memory.put("open", "proposal-n8", {**_step("n8", first), "origin": "tell"})
    get_working().save(work_map.organisation, work_map.map_id, memory)
    client.post("/api/guardian/save", json={"map_id": work_map.map_id, "proposal_id": "n8",
                                            "reason": "We announce at least 14 days ahead."})
    monkeypatch.setattr(commands, "classify_command", lambda said, **k: Command(intent="forget", what=said))
    client.post("/api/guardian/command", json={"map_id": work_map.map_id, "said": "Forget the saved step."})
    memory = get_working().load(work_map.organisation, work_map.map_id)
    routes._refresh_proposals(get_maps().load(work_map.map_id), memory, use_model=False)
    get_working().save(work_map.organisation, work_map.map_id, memory)
    assert not _proposals(client, work_map), "its note went aside with it"
    assert absorb.is_teaching_note(first, has_rules=False), "a note the judge would offer again"


def test_a_rule_corrected_into_two_rules_keeps_both(guardian, monkeypatch):
    client, work_map = guardian
    rule = {"guardrail_id": "g-two", "when": "w", "then": "t", "quote": "q", "at": 1.0, "severity": "check"}
    _propose(work_map, {**_step("rule-g-two", "q", rules=[rule]), "kind": "rule", "origin": "rule", "guardrail_id": "g-two"})
    monkeypatch.setattr(absorb, "find_guardrails", lambda said, **k: [
        Guardrail(guardrail_id="x1", when="a sponsor asks for a slot", then="decline", quote=said, asked_at=1.0),
        Guardrail(guardrail_id="x2", when="a report names an organiser", then="send it to two others", quote=said, asked_at=1.0)])
    client.post("/api/guardian/save", json={"map_id": work_map.map_id, "proposal_id": "rule-g-two",
                                            "reason": "Decline sponsor slots, and send a report naming an organiser to two others."})
    saved = get_maps().load(work_map.map_id)
    assert saved.guardrail("g-two").when == "a sponsor asks for a slot" and saved.guardrail("x2") is not None


def test_a_rule_said_with_two_steps_stays_while_one_of_them_holds_it(guardian, monkeypatch):
    client, work_map = guardian
    said = "2026-10-14T11:00:00+00:00"
    shared = {"guardrail_id": "g-shared", "when": "a slot is asked for pizza", "then": "never trade it", "quote": "q",
              "at": 1.0, "severity": "stop", "step_said_at": said}
    for pid, words in (("pa", "Check the sponsor first."), ("pb", "Then answer the sponsor in a day.")):
        _propose(work_map, {**_step(pid, words, rules=[shared]), "said_at": said})
        client.post("/api/guardian/save", json={"map_id": work_map.map_id, "proposal_id": pid})
    monkeypatch.setattr(commands, "classify_command", lambda said, **k: Command(intent="forget", what=said))
    client.post("/api/guardian/command", json={"map_id": work_map.map_id, "said": "Forget the saved step."})
    after = get_maps().load(work_map.map_id)
    assert len(after.steps) == 2 and after.guardrail("g-shared") is not None, "the step before still holds it"


def _teach_js() -> str:
    from pathlib import Path

    return (Path(__file__).resolve().parents[2] / "guardian/ui/teach/teach.js").read_text(encoding="utf-8")


def test_the_class_page_sends_a_polite_save_as_a_save():
    """Measured live in the second review of 2026-10-14: "Can you save this?" went to "remember this screen",
    which dropped the question waiting and said nothing back."""
    import re

    line = next(row for row in _teach_js().splitlines() if row.startswith("const SAVE_COMMAND = /"))
    pattern = re.compile(line[len("const SAVE_COMMAND = /"):line.rindex("/i;")], re.IGNORECASE)
    for said in ("Save this.", "Can you save this?", "Could you save the rule please?", "Peux-tu garder ça ?",
                 "Tu peux sauvegarder la règle ?"):
        assert pattern.match(said), said
    for said in ("Can you see my screen?", "What would you save?", "We save the slides before every talk."):
        assert not pattern.match(said), said


def test_remembering_a_screen_keeps_the_question_waiting_unless_another_is_asked():
    teach = _teach_js()
    body = teach[teach.index("async rememberScreen("):teach.index("async float()")]
    assert "if (asked && !this.classroom.pending && !reply.question) {" in body
    assert 'reply.intent === "save"' in body, "a save made from there is said back"


def test_save_this_with_the_latest_note_set_aside_saves_no_older_note(guardian):
    client, work_map = guardian
    memory = get_working().load(work_map.organisation, work_map.map_id)
    memory.put("recent", "note-old", {"note_id": "old", "kind": "tell", "rules": [],
                                      "text": "We always announce in #announcements two weeks ahead, so newcomers plan."})
    memory.put("recent", "note-new", {"note_id": "new", "kind": "tell", "text": "Hello everyone, welcome.", "rules": []})
    memory.put("open", "proposal-new", {**_step("new", "Hello everyone, welcome."), "origin": "tell"})
    get_working().save(work_map.organisation, work_map.map_id, memory)
    client.post("/api/guardian/proposal/ignore", json={"map_id": work_map.map_id, "proposal_id": "new"})
    reply = client.post("/api/guardian/save", json={"map_id": work_map.map_id})
    assert reply.status_code == 404 and len(get_maps().load(work_map.map_id).steps) == 1


def test_a_rule_without_a_severity_is_saved_as_a_check(guardian):
    """Found while fixing the review of 2026-10-14: the default severity, "warning", is refused by the map,
    so a rule proposed without one could not be saved at all."""
    client, work_map = guardian
    rule = {"guardrail_id": "g-nosev", "when": "a sponsor wants a slot", "then": "decline", "quote": "q", "at": 1.0}
    _propose(work_map, {**_step("rule-g-nosev", "q", rules=[rule]), "kind": "rule", "origin": "rule", "guardrail_id": "g-nosev"})
    reply = client.post("/api/guardian/save", json={"map_id": work_map.map_id, "proposal_id": "rule-g-nosev"})
    assert reply.status_code == 200 and get_maps().load(work_map.map_id).guardrail("g-nosev").severity == "check"


def test_save_naming_an_ignored_note_never_saves_it(guardian):
    client, work_map = guardian
    words = "We always check the venue checklist two days before the meetup."
    memory = get_working().load(work_map.organisation, work_map.map_id)
    memory.put("recent", "note-n10", {"note_id": "n10", "kind": "tell", "text": words, "rules": []})
    memory.put("open", "proposal-n10", {**_step("n10", words), "origin": "tell"})
    get_working().save(work_map.organisation, work_map.map_id, memory)
    client.post("/api/guardian/proposal/ignore", json={"map_id": work_map.map_id, "proposal_id": "n10"})
    client.post("/api/guardian/save", json={"map_id": work_map.map_id, "what": "the venue checklist"})
    assert all(s.reason != words for s in get_maps().load(work_map.map_id).steps), "set aside, so never saved"


def test_with_no_model_urithi_says_what_it_knows_whatever_the_question(monkeypatch):
    """Found in the review of 2026-10-15: answers were picked by lists of words met live ("room", "role",
    "whole", "give me"), and a fluent answer from the model was refused when it lacked listed words."""
    from tests.guardian.test_engine import taught_map

    work_map = taught_map()
    work_map.guardrails = []
    monkeypatch.setattr(commands, "_command_model_ready", lambda: False)
    note = "Uh, the information I want to share is what you need to have when you create your community event"
    answers = {q: commands.answer_pupil_question(work_map, q, notes=[{"text": note}], last_question="Why that date?")
               for q in ("what rule are you talking about?", "I said rule, not room.", "tell me about the venue")}
    for answer in answers.values():
        assert answer.startswith("No rule is noted yet") and "Why that date?" in answer
        assert note not in answer and "the information I want to share" in answer, "named in a few words"


def test_a_fluent_model_answer_is_kept_whatever_words_it_uses(monkeypatch):
    from tests.guardian.test_engine import taught_map

    work_map = taught_map()
    work_map.guardrails = []
    monkeypatch.setattr(commands, "_command_model_ready", lambda: True)
    monkeypatch.setattr(commands, "call_main_model", lambda *a, **k: "Nothing like that came up so far, sorry.")
    assert commands.answer_pupil_question(work_map, "what rule are you talking about?",
                                          last_question="Why that date?") == "Nothing like that came up so far, sorry."


def test_the_teach_back_says_a_labelled_step_once_and_keeps_a_screen_title_with_its_reason():
    """Measured on 2026-10-10: "Step 3: Common mistake: accepting a sponsor's sales pitch because they pay
    for the pizza, because a common mistake is accepting a sponsor's sales pitch because they pay..." """
    from guardian.engine import probe
    from guardian.engine.workmap import Step, WorkMap

    work_map = WorkMap(organisation="urithi", map_id="m-tb", task="Lead a tech community", expert="Ezekias",
                       created_at="now")
    said = "A common mistake is accepting a sponsor's sales pitch because they pay for the pizza."
    work_map.steps = [
        Step(step_id="s1", number=1, title="Common mistake: accepting a sponsor's sales pitch because they pay for the pizza",
             screen_moment=1.0, observed="o", decision="mistake", reason=said),
        Step(step_id="s2", number=2, title="Date set to Thu 22 Oct", screen_moment=2.0, observed="o", decision="d",
             reason="We announce at least 14 days ahead so newcomers can plan."),
    ]
    text = probe.teach_back(work_map)
    assert "Step 1: " + said.rstrip(".") + "." in text and text.count("sales pitch") == 1
    assert "Step 2: Date set to Thu 22 Oct, because we announce at least 14 days ahead" in text


def test_a_map_saved_from_an_older_copy_is_refused_and_an_import_replaces_it(tmp_path):
    """Found in the review of 2026-10-14: a map was written back whole, so the last of two writers undid
    the other's change."""
    from guardian.engine.workmap import MapChanged, WorkMapStore

    store = WorkMapStore(str(tmp_path / "maps.sqlite3"))
    work_map = store.new("Lead a tech community", "Ezekias", organisation="urithi")
    store.save(work_map)
    first, second = store.load(work_map.map_id), store.load(work_map.map_id)
    first.task = "Lead a tech community, first change"
    store.save(first)
    second.task = "Lead a tech community, second change"
    with pytest.raises(MapChanged):
        store.save(second)
    assert store.load(work_map.map_id).task.endswith("first change") and store.load(work_map.map_id).version == 2
    store.import_map({**store.export(work_map.map_id), "task": "Imported"})
    assert store.load(work_map.map_id).task == "Imported"


def test_two_saves_at_once_both_land(guardian, monkeypatch):
    import threading
    import time as clock

    client, work_map = guardian
    rule = {"guardrail_id": "g-race", "when": "w", "then": "t", "quote": "q", "at": 1.0, "severity": "check"}
    _propose(work_map, {**_step("rule-g-race", "q", rules=[rule]), "kind": "rule", "origin": "rule", "guardrail_id": "g-race"})
    _propose(work_map, _step("p-race", "Two talks fill the evening."))
    other: list = []

    def reading_while_another_saves(said, **k):
        thread = threading.Thread(target=lambda: other.append(
            routes.save_proposal(routes.SaveBody(map_id=work_map.map_id, proposal_id="p-race"))))
        thread.start()
        clock.sleep(0.3)                          # the other save runs as far as it can meanwhile
        other.append(thread)
        return [Guardrail(guardrail_id="x", when="a sponsor asks", then="decline", quote=said, asked_at=1.0)]

    monkeypatch.setattr(absorb, "find_guardrails", reading_while_another_saves)
    reply = client.post("/api/guardian/save", json={"map_id": work_map.map_id, "proposal_id": "rule-g-race",
                                                     "reason": "When a sponsor asks, decline."})
    other[-1].join(5)
    after = get_maps().load(work_map.map_id)
    assert reply.status_code == 200 and after.guardrail("g-race") is not None
    assert any(s.reason == "Two talks fill the evening." for s in after.steps), "the other save is not undone"


def test_a_map_changed_by_another_process_is_said_not_overwritten(guardian, monkeypatch):
    client, work_map = guardian
    rule = {"guardrail_id": "g-elsewhere", "when": "w", "then": "t", "quote": "q", "at": 1.0, "severity": "check"}
    _propose(work_map, {**_step("rule-g-elsewhere", "q", rules=[rule]), "kind": "rule", "origin": "rule",
                        "guardrail_id": "g-elsewhere"})

    def saved_elsewhere_meanwhile(said, **k):
        elsewhere = get_maps().load(work_map.map_id)
        elsewhere.task = "Renamed elsewhere"
        get_maps().save(elsewhere)
        return []

    monkeypatch.setattr(absorb, "find_guardrails", saved_elsewhere_meanwhile)
    reply = client.post("/api/guardian/save", json={"map_id": work_map.map_id, "proposal_id": "rule-g-elsewhere",
                                                     "reason": "When a sponsor asks, decline."})
    assert reply.status_code == 409 and "changed meanwhile" in reply.json()["detail"]
    assert get_maps().load(work_map.map_id).task == "Renamed elsewhere"


def test_the_migration_takes_off_only_the_rules_a_step_was_given_by_mistake(tmp_path):
    """The knowledge taught on 2026-10-10: step 1 saved, the pizza rule saved alone (attached to step 1),
    step 2 saved with no rule (given the pizza rule by mistake), two rules saved alone (attached to step 2
    by design), then steps 3 and 4 with their own rules."""
    import importlib.util
    from pathlib import Path

    from guardian.engine.workmap import Step, WorkMapStore

    spec = importlib.util.spec_from_file_location(
        "migrate_step_rules", Path(__file__).resolve().parents[2] / "scripts/migrate_step_rules.py")
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    t = lambda m, s: f"2026-10-10T19:{m:02d}:{s:02d}+00:00"  # noqa: E731
    rule = lambda gid, at: Guardrail(guardrail_id=gid, when=f"w {gid}", then=f"t {gid}", quote="q",  # noqa: E731
                                     asked_at=1.0, said_at=at)
    step = lambda n, at, ids: Step(step_id=f"s{n}", number=n, title=f"Step {n}", screen_moment=1.0,  # noqa: E731
                                   observed="o", decision="d", reason=f"Reason {n}.", said_at=at, guardrail_ids=ids)
    store = WorkMapStore(str(tmp_path / "maps.sqlite3"))
    work_map = store.new("Lead a tech community", "Ezekias", organisation="urithi")
    work_map.guardrails = [rule("pizza", t(20, 26)), rule("report", t(21, 48)), rule("speaker", t(20, 17))]
    work_map.steps = [step(1, t(19, 38), ("pizza",)), step(2, t(20, 36), ("pizza", "report", "speaker")),
                      step(3, t(20, 26), ("pizza",)), step(4, t(20, 17), ("speaker",))]
    work_map.validated = work_map.snapshot()
    store.save(work_map)

    assert migration.migrate(store, apply=False) == 1 and store.load(work_map.map_id).steps[1].guardrail_ids == (
        "pizza", "report", "speaker"), "a dry run changes nothing"
    assert migration.migrate(store, apply=True) == 1
    after = store.load(work_map.map_id)
    assert [s.guardrail_ids for s in after.steps] == [("pizza",), ("report", "speaker"), ("pizza",), ("speaker",)]
    assert len(after.guardrails) == 3 and set(after.states().values()) == {"validated"}
    assert migration.migrate(store, apply=True) == 0, "run again, nothing more to do"


def test_the_pupils_prompt_lets_the_facts_decide_not_a_list_of_cases():
    """Measured live on 2026-10-15: with two rules saved, "I said rule, not room." was answered "I have not
    cited or noted any rule yet"; the prompt carried the cases met live ("room", "role", "my deck")."""
    prompt = commands.PUPIL_ANSWER_SYSTEM
    for case in ("room", "'role'", "my deck", "organized desk", "whole to talk", "I said rule"):
        assert case not in prompt, case
    assert "The facts decide what you say" in prompt and "closest thing the facts do hold" in prompt


def test_an_answer_told_apart_keeps_its_capital_i():
    told_apart = commands._ensure_distinct_answer("I have not seen that yet.", "what role?", "en",
                                                  [("what rule?", "I have not seen that yet.")])
    assert told_apart == 'About "what role": I have not seen that yet.'


def test_a_rule_removed_from_the_map_is_not_proposed_again(guardian, monkeypatch):
    """Measured live on 2026-10-15: a rule removed with "remove a rule" came back as a proposal, and "save
    this" then asked which one instead of saving the step just said."""
    client, work_map = guardian
    monkeypatch.setattr(absorb, "find_guardrails", lambda said, **k: [Guardrail(
        guardrail_id="g-rain", when="it rains", then="bring umbrellas", quote=said, asked_at=1.0)]
        if "rains" in said else [])
    told = client.post("/api/guardian/tell", json={"map_id": work_map.map_id, "said": "When it rains, we bring umbrellas."}).json()
    client.post("/api/guardian/save", json={"map_id": work_map.map_id, "proposal_id": told["proposal"]["proposal_id"]})
    client.post("/api/guardian/forget-rule", json={"map_id": work_map.map_id, "guardrail_id": "g-rain"})
    rule = {"proposal_id": "rule-g-rain", "kind": "rule", "origin": "rule", "guardrail_id": "g-rain", "when": "it rains",
            "then": "bring umbrellas", "title": "When it rains, bring umbrellas.", "reason": "q", "rules": []}
    monkeypatch.setattr(absorb, "judge_proposals", lambda *a, **k: [dict(rule)])   # read again, as a model would
    client.post("/api/guardian/tell", json={"map_id": work_map.map_id, "said": "Each talk lasts twenty minutes."})
    assert all(p.get("guardrail_id") != "g-rain" for p in _proposals(client, work_map))
    memory = get_working().load(work_map.organisation, work_map.map_id)
    assert memory.find("rule-g-rain") is None, "not kept as a noted rule either"
