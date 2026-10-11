"""
P2: The expert pupil. What is missing for a learner judged by importance (the why, a limit,
a term never explained, a step skipped, no example, a risk); asked only when important, at a
pause; passable; a silent mode keeping questions for the debrief; the guardian's threshold
learned from what they pass.
"""

import pytest

from guardian.api import routes
from guardian.engine import absorb, commands, probe, questions, vision
from guardian.engine.workmap import Guardrail, Step, WorkMap
from guardian.memory.store import get_maps, set_maps
from guardian.memory.working import get_working
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
    return guardian_client(app), work_map


def test_learner_gaps_are_judged_by_importance_and_only_asked_when_above_threshold():
    wm = WorkMap(organisation="urithi", map_id="m-pupil", task="t", expert="e", created_at="now")
    obs = questions.Observation(at=5.0, changed="Date set to Friday")
    kind, imp = questions.find_learner_gap(wm, obs, [])
    assert kind == questions.QuestionKind.REASON and imp == 5

    wm.steps.append(
        Step(step_id="s1", number=1, title="Date", screen_moment=5.0, observed="Date set to Friday",
             decision="Date", reason="Because people plan ahead.")
    )
    wm.guardrails.append(
        Guardrail(guardrail_id="g1", when="announcing", then="post two weeks ahead", quote="q", asked_at=5.0, severity="stop")
    )
    # Acronym COC never explained in earlier steps -> TERM gap of importance 3
    obs_term = questions.Observation(at=10.0, changed="Date set to Friday", field="")
    wm.steps[-1] = Step(
        step_id="s1", number=1, title="Date", screen_moment=5.0, observed="Date set to Friday",
        decision="Date", reason="Always check the COC escalation path."
    )
    kind_term, imp_term = questions.find_learner_gap(
        wm, obs_term, [], asked=(questions.QuestionKind.LIMIT, questions.QuestionKind.ESCALATION)
    )
    assert kind_term == questions.QuestionKind.TERM and imp_term == 3

    # Example gap when guardrails exist and no example step is present
    wm.steps[-1] = Step(
        step_id="s1", number=1, title="Date", screen_moment=5.0, observed="Date set to Friday",
        decision="Date", reason="Because people plan ahead."
    )
    kind_ex, imp_ex = questions.find_learner_gap(
        wm, obs_term, [], asked=(questions.QuestionKind.LIMIT, questions.QuestionKind.ESCALATION, questions.QuestionKind.TERM)
    )
    assert kind_ex == questions.QuestionKind.EXAMPLE and imp_ex == 2
    assert not questions.should_ask(kind_ex, imp_ex, None), "importance 2 is below default threshold 3"


def test_passing_a_question_prevents_the_next_question_of_the_same_kind_and_same_importance(guardian, monkeypatch):
    client, work_map = guardian
    monkeypatch.setattr(
        vision, "what_changed", lambda frame, sid, at: questions.Observation(at=at, changed="Channel set to #members")
    )
    monkeypatch.setattr(questions, "word_question", lambda *a, **k: "Why choose #members?")

    r1 = client.post("/api/guardian/observe", json={"map_id": work_map.map_id, "at": 10.0, "frame": "x"}).json()
    assert r1["question"] == "Why choose #members?" and r1["importance"] == 5

    passed = client.post("/api/guardian/pass", json={"map_id": work_map.map_id}).json()
    assert passed["passed"] is True and passed["kind"] == "reason"
    assert passed["threshold"] == 6

    # Next observation of the same kind (reason, importance 5) is prevented by the raised threshold (6)
    r2 = client.post("/api/guardian/observe", json={"map_id": work_map.map_id, "at": 30.0, "frame": "x"}).json()
    assert "question" not in r2

    # Passing a second question raises the guardian's threshold further
    memory = get_working().load(work_map.organisation, work_map.map_id)
    questions.record_pass(memory, "limit", 4)
    get_working().save(work_map.organisation, work_map.map_id, memory)
    level, by_kind = questions.threshold_for(get_working().load(work_map.organisation, work_map.map_id))
    assert level >= 4 and by_kind["limit"] == 5
    assert not questions.should_ask(questions.QuestionKind.LIMIT, 4, memory)
    assert not questions.should_ask(questions.QuestionKind.REASON, 5, memory)



def test_silent_mode_keeps_classroom_questions_for_the_debrief_instead_of_asking_aloud(guardian, monkeypatch):
    client, work_map = guardian
    monkeypatch.setattr(
        vision, "what_changed", lambda frame, sid, at: questions.Observation(at=at, changed="Venue set to Room 2")
    )
    monkeypatch.setattr(questions, "word_question", lambda *a, **k: "Why choose Room 2?")
    monkeypatch.setattr(probe, "probes_for", lambda wm: [])

    s = client.post("/api/guardian/silent", json={"map_id": work_map.map_id, "silent": True}).json()
    assert s == {"silent": True}

    obs = client.post(
        "/api/guardian/observe", json={"map_id": work_map.map_id, "at": 12.0, "frame": "x", "silent": True}
    ).json()
    assert "question" not in obs
    assert obs["watching"] is True and obs["deferred"] == "Why choose Room 2?"

    debrief = client.post("/api/guardian/debrief", json={"map_id": work_map.map_id}).json()
    assert len(debrief["deferred_questions"]) == 1
    assert debrief["deferred_questions"][0]["question"] == "Why choose Room 2?"
    assert debrief["probe"]["question"] == "Why choose Room 2?"


def test_expert_pupil_judges_by_model_in_one_json_call_keeps_why_in_notes_and_memory_and_refuses_invented_values(
    guardian, monkeypatch
):
    client, work_map = guardian
    calls = []
    responses = iter([
        '{"kind": "limit", "importance": 4, "why": "A learner needs to know when the relief valve opens.", '
        '"question": "At what pressure does the relief valve open?"}',
        '{"kind": "none", "importance": 0, "why": "Already clear.", "question": ""}',
        '{"kind": "reason", "importance": 5, "why": "The gauge changed.", '
        '"question": "Why did you set the relief valve to 75 bar?"}',
    ])
    monkeypatch.setattr("apu.inference.llm.is_configured", lambda role="main": role == "main")
    monkeypatch.setattr(
        questions,
        "call_main_model",
        lambda messages, **k: calls.append((messages, k)) or next(responses),
    )
    obs_seq = iter([
        questions.Observation(at=2.0, changed="Relief valve selected"),
        questions.Observation(at=10.0, changed="Relief valve selected"),
        questions.Observation(at=35.0, changed="Status banner updated"),
        questions.Observation(at=60.0, changed="Relief valve armed"),
    ])
    monkeypatch.setattr(vision, "what_changed", lambda frame, sid, at: next(obs_seq))

    # 1. Busy frame (typing=True): no pause, so zero model calls
    busy = client.post(
        "/api/guardian/observe",
        json={"map_id": work_map.map_id, "at": 2.0, "frame": "x", "typing": True},
    ).json()
    assert "question" not in busy and len(calls) == 0

    # 2. Pause after change (at=10.0): exactly ONE JSON call to QUESTION_MODEL
    asked = client.post(
        "/api/guardian/observe",
        json={"map_id": work_map.map_id, "at": 10.0, "frame": "x"},
    ).json()
    assert len(calls) == 1
    assert calls[0][1].get("response_format") == {"type": "json_object"}
    assert asked["kind"] == "limit" and asked["importance"] == 4
    assert asked["why"] == "A learner needs to know when the relief valve opens."
    assert asked["question"] == "At what pressure does the relief valve open?"

    # "why" is kept in working memory and in the guardian's MMU
    wm_mem = get_working().load(work_map.organisation, work_map.map_id)
    open_q = wm_mem.find("question")
    assert open_q is not None and open_q["content"]["why"] == asked["why"]
    from guardian.memory.mmu import get_guardian_mmu

    dll = get_guardian_mmu().load_dll(work_map.organisation, work_map.expert)
    assert "relief valve opens" in dll["nodes"]["current_class"]["content"]
    assert "relief valve opens" in dll["nodes"]["active_knowledge"]["content"]

    # Clear pending question by passing so we can test "none" and invented-value refusal
    client.post("/api/guardian/pass", json={"map_id": work_map.map_id})

    # 3. Model returns {"kind": "none"}: asks nothing, and an idle frame in the same pause does not call again
    none_reply = client.post(
        "/api/guardian/observe",
        json={"map_id": work_map.map_id, "at": 35.0, "frame": "x"},
    ).json()
    assert "question" not in none_reply and len(calls) == 2
    idle_reply = client.post(
        "/api/guardian/observe",
        json={"map_id": work_map.map_id, "at": 37.0, "frame": None},
    ).json()
    assert "question" not in idle_reply and len(calls) == 2

    # 4. Model invents "75 bar" which was never seen or said: grounded check replaces it with the safe fallback
    ungrounded = client.post(
        "/api/guardian/observe",
        json={"map_id": work_map.map_id, "at": 60.0, "frame": "x"},
    ).json()
    assert len(calls) == 3
    assert "75" not in ungrounded["question"]
    assert ungrounded["question"] == questions.FALLBACKS[questions.QuestionKind.REASON]


def test_a_second_class_in_silent_mode_keeps_earlier_deferred_questions_for_the_debrief(
    guardian, monkeypatch
):
    client, work_map = guardian
    obs_seq = iter([
        questions.Observation(at=10.0, changed="Selected Room A"),
        questions.Observation(at=12.0, changed="Selected catering tier"),
    ])
    monkeypatch.setattr(vision, "what_changed", lambda frame, sid, at: next(obs_seq))

    # Class 1 in silent mode at t=10.0 -> defers question 1
    r1 = client.post(
        "/api/guardian/observe",
        json={"map_id": work_map.map_id, "at": 10.0, "frame": "x", "silent": True},
    ).json()
    assert r1.get("deferred")

    # Simulate a new class session where `asked` starts empty again (`at` resets to 0.0 then 12.0)
    from guardian.api import routes

    routes._session(work_map.map_id)["asked"] = []
    r2 = client.post(
        "/api/guardian/observe",
        json={"map_id": work_map.map_id, "at": 35.0, "frame": "x", "silent": True},
    ).json()
    assert r2.get("deferred")

    debrief = client.post("/api/guardian/debrief", json={"map_id": work_map.map_id}).json()
    deferred = debrief.get("deferred_questions", [])
    assert len(deferred) == 2
    assert {d["about"] for d in deferred} == {"Selected Room A", "Selected catering tier"}


def test_the_expert_pupil_receives_the_vision_description_screen_fields_and_guardians_recent_words(
    guardian, monkeypatch
):
    client, work_map = guardian
    client.post(
        "/api/guardian/tell",
        json={"map_id": work_map.map_id, "said": "We book the dockside room before announcing."},
    )
    prompts = []
    monkeypatch.setattr("apu.inference.llm.is_configured", lambda role="main": role == "main")
    monkeypatch.setattr(
        questions,
        "call_main_model",
        lambda messages, **k: prompts.append(messages[-1]["content"])
        or '{"kind": "reason", "importance": 4, '
        '"why": "The event was marked Done with 16 days notice.", '
        '"question": "Why schedule 16 days ahead in \\"#announcements\\"?"}',
    )
    monkeypatch.setattr(
        vision,
        "what_changed",
        lambda frame, sid, at: questions.Observation(
            at=at,
            changed='November meetup Event set to "Done"',
            field="November meetup",
            scene="The Organiser's Desk shows November meetup marked Done after scheduling.",
            screen_fields=(
                "Date: Thu 22 Oct, 18:30 · in 16 days",
                "Announce in: #announcements (public, everyone)",
            ),
        ),
    )

    reply = client.post(
        "/api/guardian/observe",
        json={"map_id": work_map.map_id, "at": 10.0, "frame": "x"},
    ).json()
    assert len(prompts) == 1
    user_prompt = prompts[0]
    assert "Vision description of the screen: The Organiser's Desk shows November meetup marked Done" in user_prompt
    assert "Fields read on screen: Date: Thu 22 Oct, 18:30 · in 16 days; Announce in: #announcements" in user_prompt
    assert "Guardian's recent words: We book the dockside room before announcing." in user_prompt
    assert reply["question"] == 'Why schedule 16 days ahead in "#announcements"?'
    assert reply["importance"] == 4


def test_a_whole_class_without_a_save_leaves_the_knowledge_empty(
    guardian, monkeypatch
):
    """Decision 0016: the twelve sentences of the Organiser's Desk class (hesitations, questions
    to Urithi, teaching sentences, and screen observations) leave work_map empty until the
    guardian explicitly asks to save."""
    client, _ = guardian
    work_map = get_maps().new("Run a community tech meetup", "Sabine", "en", organisation="urithi")
    get_maps().save(work_map)
    monkeypatch.setattr(commands, "_command_model_ready", lambda: False)
    monkeypatch.setattr(
        vision,
        "what_changed",
        lambda frame, sid, at: questions.Observation(
            at=at,
            changed="Organiser's Desk: November meetup, Venue Dockside Room B, Format Two talks",
            field="Venue",
            scene="Organiser's Desk showing November meetup in Dockside Room B",
            screen_fields=("Venue: Dockside Room B", "Format: Two talks", "Last meetup: 18 attendees"),
        ),
    )
    client.post("/api/guardian/observe", json={"map_id": work_map.map_id, "at": 2.0, "frame": "x"})

    class_sentences = (
        "Uh, especially about leadership in community is important to, uh",
        "[inhales] Hello. So, um, I want to, to share, uh",
        "did you see my screen?",
        "so I want to share",
        "Uh, the information I want to share is like what is different information you need to have when you want to, mm, to, to create or to have your event",
        "what rule are you talking about?",
        "give me the rule",
        "I said rule, not room.",
        "what rule are you talking about?",
        "Ok, I remember about, uh, November meetup, uh, venue, format, last meetup and today.",
        "I want you to keep the information on the venue, the format, the last meetup, and today.",
        "what would you save?",
    )
    replies = []
    for said in class_sentences:
        r = client.post("/api/guardian/tell", json={"map_id": work_map.map_id, "said": said}).json()
        assert r.get("step") is None, said
        replies.append((said, r))

    loaded = get_maps().load(work_map.map_id)
    assert loaded.steps == [], "0 steps saved in the knowledge when the guardian never asked to save"
    assert loaded.guardrails == [], "0 rules saved in the knowledge when the guardian never asked to save"
    assert loaded.rulings == []

    by_said = dict(replies)
    assert "Dockside Room B" in by_said["did you see my screen?"]["answer"]
    assert "no rule has been noted so far" in by_said["what rule are you talking about?"]["answer"]
    assert "venue" in by_said["what would you save?"]["answer"].lower()

    view = client.get(f"/api/guardian/map/{work_map.map_id}").json()
    assert view["steps"] == [] and view["guardrails"] == []
    assert len(view["notes"]) >= 1 and len(view["proposals"]) >= 1


def test_no_route_saves_to_the_knowledge_without_the_guardians_request(
    guardian, monkeypatch
):
    """Decision 0016: /tell, /answer, /remember, /command (remember, example, mistake, compare),
    /sources/propose, and /rule record notes and proposals in working memory; none writes to work_map."""
    import base64
    import io
    from PIL import Image
    from apu.modality import picture

    client, work_map = guardian
    initial_steps = len(work_map.steps)
    initial_rails = len(work_map.guardrails)
    initial_rulings = len(work_map.rulings)

    buf = io.BytesIO()
    Image.new("RGB", (40, 40), (30, 60, 120)).save(buf, format="JPEG")
    frame_b64 = base64.b64encode(buf.getvalue()).decode()

    monkeypatch.setattr(picture, "describe", lambda data, mime, **k: "Venue: Dockside Room B")
    import itertools
    rule_ids = itertools.count(1)   # each sentence read gives its own rule, as the extractor does
    monkeypatch.setattr(
        absorb,
        "find_guardrails",
        lambda said, **k: [
            Guardrail(
                guardrail_id=f"g-unsaved-{next(rule_ids)}",
                when="fewer than ten people register",
                then="move to the smaller room",
                quote=said,
                asked_at=1.0,
            )
        ],
    )

    # 1. /tell
    r_tell = client.post(
        "/api/guardian/tell",
        json={"map_id": work_map.map_id, "said": "When fewer than ten people register, move to the smaller room."},
    ).json()
    assert r_tell["step"] is None and r_tell["guardrails"] == [] and r_tell["proposal"] is not None

    # 2. /observe + /answer
    monkeypatch.setattr(
        vision, "what_changed", lambda frame, sid, at: questions.Observation(at=at, changed="Channel set to #public")
    )
    monkeypatch.setattr(questions, "word_question", lambda *a, **k: "Why #public?")
    client.post("/api/guardian/observe", json={"map_id": work_map.map_id, "at": 10.0, "frame": "x"})
    r_ans = client.post(
        "/api/guardian/answer",
        json={"map_id": work_map.map_id, "said": "Because newcomers only see #public."},
    ).json()
    assert r_ans["step"] is None and r_ans["guardrails"] == [] and r_ans["proposal"] is not None

    # 3. /remember
    r_rem = client.post(
        "/api/guardian/remember",
        json={"map_id": work_map.map_id, "frame": frame_b64, "at": 15.0, "said": "Remember the venue field."},
    ).json()
    assert r_rem["step"] is None and r_rem["guardrails"] == [] and r_rem["proposal"] is not None

    # 4. /command (example, mistake, compare)
    vision._previous[work_map.map_id] = frame_b64
    monkeypatch.setattr(commands, "compare_frames", lambda b, n, focus="": "Changed to Room B.")
    for intent_name, phrase in (
        ("example", "Example: booking Room B"),
        ("mistake", "Mistake: forgetting the projector"),
        ("compare", "Compare with before"),
    ):
        monkeypatch.setattr(
            commands, "classify_command", lambda s, language="en", i=intent_name, p=phrase: commands.Command(i, p)
        )
        r_cmd = client.post(
            "/api/guardian/command",
            json={"map_id": work_map.map_id, "said": phrase, "frame": frame_b64, "at": 20.0},
        ).json()
        assert r_cmd.get("step") is None and r_cmd["proposal"] is not None

    # 5. /sources/propose
    r_prop = client.post(
        "/api/guardian/sources/propose",
        json={
            "map_id": work_map.map_id,
            "source_id": r_rem["source"]["source_id"],
            "passage": 1,
            "said": "Always check the venue capacity first.",
        },
    ).json()
    assert r_prop["proposal"] is not None

    # 6. /debrief + /rule
    deb = client.post("/api/guardian/debrief", json={"map_id": work_map.map_id}).json()
    if deb.get("probe"):
        monkeypatch.setattr(probe, "call_main_model", lambda *a, **k: '{"would": "yes"}')
        r_rule = client.post(
            "/api/guardian/rule",
            json={"map_id": work_map.map_id, "probe_id": deb["probe"]["probe_id"], "said": "Yes, it counts."},
        ).json()
        assert r_rule["proposal"]["kind"] == "case"

    loaded = get_maps().load(work_map.map_id)
    assert len(loaded.steps) == initial_steps
    assert len(loaded.guardrails) == initial_rails
    assert len(loaded.rulings) == initial_rulings

    # Ignoring a proposal removes it without touching work_map
    pid = r_tell["proposal"]["proposal_id"]
    ig = client.post("/api/guardian/proposal/ignore", json={"map_id": work_map.map_id, "proposal_id": pid}).json()
    assert ig["ignored"] is True and ig["proposal_id"] == pid
    assert len(get_maps().load(work_map.map_id).steps) == initial_steps


def test_a_saved_proposal_keeps_the_guardians_words_and_saves_step_and_rule_on_save_this(
    guardian, monkeypatch
):
    """Decision 0016: proposals replace previous ones instead of piling up, non-teaching notes stay
    notes, a limit is proposed as kind='rule' (when/then), 'what would you save?' previews them,
    'save this' saves both step and rule in the guardian's words, and publishing requires a rule."""
    from guardian.publish import KnowledgeError, publication_from

    client, _ = guardian
    work_map = get_maps().new("Run a community tech meetup", "Sabine", "en", organisation="urithi")
    get_maps().save(work_map)
    monkeypatch.setattr(commands, "_command_model_ready", lambda: False)

    # 1. A filler greeting remains a note and creates no proposal.
    r_hello = client.post(
        "/api/guardian/tell",
        json={"map_id": work_map.map_id, "said": "Hello everyone."},
    ).json()
    assert r_hello["step"] is None
    assert r_hello["proposal"] is None
    assert r_hello["note"]["text"] == "Hello everyone."
    assert (r_hello.get("question") or r_hello.get("answer") or r_hello.get("noted"))

    # 2. Two teaching steps replace the previous step proposal instead of piling up.
    first_step = "We check the venue, the format, the last meetup, and today's registrations."
    second_step = "I want you to keep the information on the venue, the format, the last meetup, and today."
    r1 = client.post("/api/guardian/tell", json={"map_id": work_map.map_id, "said": first_step}).json()
    assert r1["proposal"]["kind"] == "step" and r1["proposal"]["reason"] == first_step
    r2 = client.post("/api/guardian/tell", json={"map_id": work_map.map_id, "said": second_step}).json()
    assert r2["proposal"]["kind"] == "step" and r2["proposal"]["reason"] == second_step
    state_after_steps = client.get(f"/api/guardian/map/{work_map.map_id}").json()
    assert len(state_after_steps["proposals"]) == 1
    assert state_after_steps["proposals"][0]["reason"] == second_step

    # 3. Guardian can change the step proposal wording before saving.
    pid = r2["proposal"]["proposal_id"]
    changed = client.post(
        "/api/guardian/proposal/change",
        json={
            "map_id": work_map.map_id,
            "proposal_id": pid,
            "title": "The venue, the format, the last meetup, and today",
            "reason": second_step,
        },
    ).json()
    assert changed["proposal"]["title"] == "The venue, the format, the last meetup, and today"

    # 4. A limit stated by the guardian is proposed as a rule (when / then), keeping at most 2 proposals.
    rule_said = "If the venue holds fewer than 40 seats, we announce in #members only, never in #announcements."
    monkeypatch.setattr(
        absorb,
        "find_guardrails",
        lambda said, at=0.0, **k: [
            Guardrail(
                guardrail_id="g-40-seats",
                when="the venue holds fewer than 40 seats",
                then="announce in #members only, never in #announcements",
                quote=said,
                asked_at=at,
                severity="stop",
            )
        ]
        if "40 seats" in said
        else [],
    )
    r_rule = client.post("/api/guardian/tell", json={"map_id": work_map.map_id, "said": rule_said}).json()
    assert r_rule["proposal"]["kind"] == "rule"
    assert "40 seats" in r_rule["proposal"]["when"]
    assert "#members" in r_rule["proposal"]["then"]
    state_with_rule = client.get(f"/api/guardian/map/{work_map.map_id}").json()
    assert len(state_with_rule["proposals"]) == 2
    assert {p["kind"] for p in state_with_rule["proposals"]} == {"step", "rule"}
    assert get_maps().load(work_map.map_id).steps == []
    assert get_maps().load(work_map.map_id).guardrails == []

    # 5. Asking "what would you save?" previews the step and the rule without adding a note or proposal.
    preview = client.post(
        "/api/guardian/tell",
        json={"map_id": work_map.map_id, "said": "what would you save?"},
    ).json()
    assert preview["intent"] == "ask_pupil"
    # Named, not read whole (measured live: whole proposals read back took past a minute of speech).
    assert "the step" in preview["answer"] and "the venue, the format" in preview["answer"].lower()
    assert second_step not in preview["answer"]
    assert "40 seats" in preview["answer"]

    # 6. A map with a step but no saved guardrail is not teachable and cannot be published.
    map_without_rule = get_maps().new("Incomplete meetup", "Sabine", "en", organisation="urithi")
    map_without_rule.steps.append(
        Step(
            step_id="s1",
            number=1,
            title="Check venue",
            screen_moment=0.0,
            observed="Check venue",
            decision="Check venue",
            reason=second_step,
        )
    )
    map_without_rule.guardian_confirmed = True
    with pytest.raises(KnowledgeError):
        publication_from(map_without_rule, version=1)

    # 7. With two pending proposals, bare "save this" asks which one and saves nothing.
    ambig = client.post("/api/guardian/tell", json={"map_id": work_map.map_id, "said": "save this"}).json()
    assert ambig["intent"] == "save"
    assert ambig["ambiguous"] is True
    assert ambig["step"] is None and ambig["guardrails"] == []
    assert "Which one should I save?" in ambig["question"]
    assert get_maps().load(work_map.map_id).steps == []
    assert get_maps().load(work_map.map_id).guardrails == []

    # 8. "save the rule" saves only the rule, leaving the step proposal pending.
    saved_rule = client.post("/api/guardian/tell", json={"map_id": work_map.map_id, "said": "save the rule"}).json()
    assert saved_rule["intent"] == "save"
    assert saved_rule["saved_kind"] == "rule"
    assert saved_rule["step"] is None
    assert len(saved_rule["guardrails"]) == 1 and "40 seats" in saved_rule["guardrails"][0]["when"]
    loaded_after_rule = get_maps().load(work_map.map_id)
    assert loaded_after_rule.steps == []
    assert len(loaded_after_rule.guardrails) == 1 and "40 seats" in loaded_after_rule.guardrails[0].when

    # 9. Now only the step proposal remains: "save this" saves that single step in the guardian's words.
    saved = client.post("/api/guardian/tell", json={"map_id": work_map.map_id, "said": "save this"}).json()
    assert saved["intent"] == "save"
    assert saved["step"]["reason"] == second_step
    assert saved["guardrails"] == []
    loaded = get_maps().load(work_map.map_id)
    assert len(loaded.steps) == 1 and loaded.steps[0].reason == second_step
    assert len(loaded.guardrails) == 1 and "40 seats" in loaded.guardrails[0].when
    assert loaded.is_teachable is True

    # 10. Confirming before the teach-back is refused (Decision 0002); after teach-back it succeeds.
    refused_conf = client.post("/api/guardian/confirm", json={"map_id": work_map.map_id, "confirmed": True})
    assert refused_conf.status_code == 409
    assert refused_conf.json()["confirmed"] is False
    assert "teach-back" in refused_conf.json()["error"].lower()

    tb = client.get(f"/api/guardian/map/{work_map.map_id}/teach-back").json()
    assert second_step in tb["text"]
    conf = client.post("/api/guardian/confirm", json={"map_id": work_map.map_id, "confirmed": True}).json()
    assert conf["confirmed"] is True
    pub = publication_from(get_maps().load(work_map.map_id), version=1)
    assert any(u.quote == second_step for u in pub.units if u.kind == "step")
    assert any("40 seats" in u.text and u.quote == rule_said for u in pub.units if u.kind in ("caution", "limit"))

    # Saving a new step changes the map: confirming is refused again until a new teach-back is produced.
    client.post(
        "/api/guardian/tell",
        json={"map_id": work_map.map_id, "said": "Then we lock the registration form because late RSVPs exceed capacity."},
    )
    client.post("/api/guardian/tell", json={"map_id": work_map.map_id, "said": "save this"})
    refused_again = client.post("/api/guardian/confirm", json={"map_id": work_map.map_id, "confirmed": True})
    assert refused_again.status_code == 409
    assert refused_again.json()["confirmed"] is False


def test_proposals_are_judged_by_question_model_with_deterministic_fallback_and_questions_never_repeat_or_stay_silent(
    guardian, monkeypatch
):
    """Decision 0016: judge_proposals calls QUESTION_MODEL once and falls back deterministically;
    notes count as answered so Urithi never repeats a question already asked, and every spoken
    sentence receives a question or a spoken acknowledgement."""
    from apu import config
    from guardian.engine import absorb

    client, _ = guardian
    work_map = get_maps().new("Run a community tech meetup", "Sabine", "en", organisation="urithi")
    get_maps().save(work_map)

    # 1. judge_proposals calls QUESTION_MODEL to pick the substantive step and rule, with fallback on error.
    calls: list[str] = []

    def _fake_proposal_llm(messages, **kwargs):
        calls.append(str(kwargs.get("model") or ""))
        return '{"step_note_id": "n1", "rule_id": "g1"}'

    monkeypatch.setattr(absorb, "_proposal_model_ready", lambda: True)
    monkeypatch.setattr(absorb, "call_main_model", _fake_proposal_llm)
    notes = [
        {"note_id": "n2", "text": "And then we also check the catering.", "title": "Check catering", "at": 2.0},
        {"note_id": "n1", "text": "First we check the venue capacity because fire safety caps the room.", "title": "Check venue capacity", "at": 1.0},
    ]
    noted_rules = [
        {"guardrail_id": "g0", "when": "a field is blank", "then": "fill it first", "quote": "Fill blank fields first.", "severity": "check"},
        {"guardrail_id": "g1", "when": "fewer than 40 seats", "then": "announce in #members only", "quote": "If fewer than 40 seats, announce in #members only.", "severity": "stop"},
    ]
    judged = absorb.judge_proposals(work_map, notes, noted_rules, use_model=True)
    assert calls == [config.QUESTION_MODEL]
    assert len(judged) == 2
    assert judged[0]["proposal_id"] == "n1" and judged[0]["kind"] == "step"
    assert judged[1]["kind"] == "rule" and judged[1]["guardrail_id"] == "g1"
    assert len(judged[1]["rules"]) == 1 and judged[1]["rules"][0]["guardrail_id"] == "g1"

    def _boom_proposal(messages, **kwargs):
        raise RuntimeError("proposal model offline")

    monkeypatch.setattr(absorb, "call_main_model", _boom_proposal)
    fallback_judged = absorb.judge_proposals(work_map, notes, noted_rules, use_model=True)
    assert len(fallback_judged) == 2
    assert {p["kind"] for p in fallback_judged} == {"step", "rule"}

    # 2. Notes count as answered and a question already asked in the session is never repeated.
    monkeypatch.setattr(questions, "_question_model_ready", lambda: True)
    monkeypatch.setattr(
        questions,
        "call_main_model",
        lambda messages, **k: '{"kind": "limit", "importance": 4, "why": "Boundary.", "question": "Where does that 40 seats rule stop applying?"}',
    )
    r_first = client.post(
        "/api/guardian/tell",
        json={
            "map_id": work_map.map_id,
            "said": "We check the venue capacity of 40 seats before opening registrations.",
        },
    ).json()
    assert r_first["question"] == "Where does that 40 seats rule stop applying?"

    # Even if the model tries to return the exact same question or kind again on the next sentence,
    # Urithi suppresses the repeat and still gives a non-silent acknowledgement.
    r_second = client.post(
        "/api/guardian/tell",
        json={
            "map_id": work_map.map_id,
            "said": "When the room has fewer than 40 seats, we cap the RSVP list at 40.",
        },
    ).json()
    assert r_second["question"] is None
    # Said as what it is: the rule from these words is proposed, never "noted" in silence (live).
    assert r_second["answer"].startswith("Proposed: ") and r_second["answer"].endswith('to keep it.')
    assert r_second["noted"] == r_second["answer"]



def test_an_answer_is_about_what_the_guardian_did_since_the_question_and_said_back_as_a_proposal(guardian, monkeypatch):
    """Measured live: the question came when the meetup was opened; the guardian then chose the date
    and the channel and answered with the reason. The proposal was titled "Opened: November meetup",
    and was said back "Noted, as step 1" though nothing was saved."""
    client, work_map = guardian
    monkeypatch.setattr(absorb, "find_guardrails", lambda said, **k: [])
    monkeypatch.setattr(questions, "judge_learner_gap", lambda *a, **k: questions.PupilJudgment(None, 0, "", ""))
    session = routes._session(work_map.map_id)
    asked = questions.Observation(at=5.0, changed="Opened: November meetup")
    session["observations"] = [asked, questions.Observation(at=9.0, changed='Date set to "in 16 days", Announce in set to "#announcements"')]
    session["pending"] = {"kind": "reason", "observation": asked, "asked_at": 5.0, "question": "Why November first?",
                          "source": "screen", "cites": ()}
    reply = client.post("/api/guardian/answer", json={"map_id": work_map.map_id,
                        "said": "We announce in #announcements at least 14 days ahead."}).json()
    assert "#announcements" in reply["proposal"]["title"]      # the guardian's words name it
    assert reply["proposal"]["observed"].startswith("Date set") # what was done since the question
    assert reply["noted"].startswith("Proposed: ") and "as step" not in reply["noted"]
    assert len(get_maps().load(work_map.map_id).steps) == len(work_map.steps), "nothing saved"



def test_every_rule_stated_is_proposed_and_an_ignored_one_never_comes_back(guardian, monkeypatch):
    """Measured live: a second rule said replaced the first one's proposal, and a rule said after a
    passed question was only noted; an ignored proposal came back at the next look at the notes."""
    import itertools
    client, work_map = guardian
    ids = itertools.count(1)
    monkeypatch.setattr(absorb, "find_guardrails", lambda said, **k: [Guardrail(
        guardrail_id=f"g-{next(ids)}", when=said.split(",")[0].removeprefix("When ").lower(), then="stop", quote=said, asked_at=1.0)])
    monkeypatch.setattr(questions, "judge_learner_gap", lambda *a, **k: questions.PupilJudgment(None, 0, "", ""))
    for said in ("When a sponsor pays for the pizza, never trade a slot.", "When a report names an organiser, never send it to them."):
        client.post("/api/guardian/tell", json={"map_id": work_map.map_id, "said": said})
    rules = [p for p in client.get(f"/api/guardian/map/{work_map.map_id}").json()["proposals"] if p["kind"] == "rule"]
    assert {r["guardrail_id"] for r in rules} == {"g-1", "g-2"}
    client.post("/api/guardian/proposal/ignore", json={"map_id": work_map.map_id, "proposal_id": rules[0]["proposal_id"]})
    # The judge offers the ignored rule again, as a model reading the same notes would.
    ignored_again = dict(rules[0])
    monkeypatch.setattr(absorb, "judge_proposals", lambda *a, **k: [ignored_again])
    client.post("/api/guardian/tell", json={"map_id": work_map.map_id, "said": "When a newcomer asks in #help, answer within a day."})
    left = {p["guardrail_id"] for p in client.get(f"/api/guardian/map/{work_map.map_id}").json()["proposals"] if p["kind"] == "rule"}
    assert rules[0]["guardrail_id"] not in left and len(left) == 2
