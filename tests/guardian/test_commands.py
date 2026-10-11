"""
P1: The guardian's classroom commands, understood by intent with QUESTION_MODEL,
and pointing at a part of the screen.
"""

import base64
import io

from PIL import Image
import pytest

from apu import config
from apu.modality import picture
from guardian.engine import absorb, commands, vision
from guardian.memory.store import get_maps, set_maps
from tests.support import guardian_client


def _two_half_jpeg() -> bytes:
    """A 200x100 JPEG: left half blue, right half red."""
    img = Image.new("RGB", (200, 100), (20, 40, 200))
    for x in range(100, 200):
        for y in range(100):
            img.putpixel((x, y), (220, 30, 30))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


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


def test_commands_are_classified_by_intent_with_the_question_model(monkeypatch):
    called_models = []

    def fake_model(messages, **kwargs):
        called_models.append(kwargs.get("model"))
        user = messages[-1]["content"].lower()
        if "common trap" in user:
            return '{"intent": "mistake", "what": "forgetting to lock the room first"}'
        if "concrete case" in user:
            return '{"intent": "example", "what": "the Friday release checklist"}'
        if "how this changed" in user:
            return '{"intent": "compare", "what": "the new header"}'
        if "scratch what i just said" in user:
            return '{"intent": "forget", "what": ""}'
        return '{"intent": "none", "what": ""}'

    monkeypatch.setattr("apu.inference.llm.is_configured", lambda role="main": True)
    monkeypatch.setattr(commands, "call_main_model", fake_model)

    c1 = commands.classify_command("Watch out, a common trap here is forgetting to lock the room first.")
    assert c1.intent == "mistake" and "lock the room" in c1.what
    assert called_models[-1] == config.QUESTION_MODEL

    c2 = commands.classify_command("Here is a concrete case: the Friday release checklist.")
    assert c2.intent == "example" and "Friday release" in c2.what

    c3 = commands.classify_command("Look at how this changed from the previous screen.")
    assert c3.intent == "compare"

    c4 = commands.classify_command("Wait, scratch what I just said.")
    assert c4.intent == "forget"

    habit = commands.classify_command("We keep this channel public for newcomers.")
    assert habit.intent == "none"


def test_ordinary_teaching_sentences_without_a_command_cue_do_not_call_the_model(monkeypatch):
    calls = []
    monkeypatch.setattr("apu.inference.llm.is_configured", lambda role="main": True)
    monkeypatch.setattr(commands, "call_main_model", lambda *a, **kw: calls.append(1) or '{"intent": "remember"}')
    res_en = commands.classify_command("First I open the main inlet valve slowly to equalise the line.")
    res_fr = commands.classify_command("J'annonce chaque rencontre deux semaines à l'avance sur le salon.")
    assert res_en.intent == "none"
    assert res_fr.intent == "none"
    assert calls == []


def test_a_pointed_region_of_the_screen_is_cropped_before_it_is_read(guardian, monkeypatch):
    client, work_map = guardian
    raw = _two_half_jpeg()
    cropped = commands.crop_region(raw, {"x": 0.5, "y": 0.0, "w": 0.5, "h": 1.0})
    with Image.open(io.BytesIO(cropped)) as img:
        assert img.size == (100, 100)
        r, g, b = img.getpixel((50, 50))
        assert r > 180 and b < 60

    seen_sizes = []

    def fake_describe(data, mime, **kwargs):
        with Image.open(io.BytesIO(data)) as im:
            seen_sizes.append(im.size)
        return "The pointed right half of the screen."

    monkeypatch.setattr(picture, "describe", fake_describe)
    res = client.post(
        "/api/guardian/remember",
        json={
            "map_id": work_map.map_id,
            "frame": base64.b64encode(raw).decode(),
            "said": "Remember this part on the right",
            "at": 12.0,
            "region": {"x": 0.5, "y": 0.0, "w": 0.5, "h": 1.0},
        },
    )
    assert res.status_code == 200
    assert seen_sizes == [(100, 100)]
    assert res.json()["proposal"]["cites"][0]["text"] == "The pointed right half of the screen."


def test_the_guardians_commands_create_examples_mistakes_comparisons_and_forget_the_last_step(
    guardian, monkeypatch
):
    client, work_map = guardian
    raw = _two_half_jpeg()
    frame_b64 = base64.b64encode(raw).decode()
    monkeypatch.setattr(picture, "describe", lambda data, mime, **k: "A form with a venue field.")
    monkeypatch.setattr(commands, "compare_frames", lambda before, now, focus="": "The venue changed to Room B.")
    vision._previous[work_map.map_id] = frame_b64

    def fake_classify(said, language="en"):
        low = said.lower()
        if "example" in low:
            return commands.Command("example", "booking Room B for Friday")
        if "mistake" in low:
            return commands.Command("mistake", "announcing before the speaker confirms")
        if "compare" in low:
            return commands.Command("compare", "the venue field")
        if "forget" in low:
            return commands.Command("forget", "")
        return commands.Command("none", "")

    monkeypatch.setattr(commands, "classify_command", fake_classify)
    initial_steps = len(get_maps().load(work_map.map_id).steps)

    ex = client.post(
        "/api/guardian/command",
        json={"map_id": work_map.map_id, "said": "This is an example: booking Room B for Friday", "frame": frame_b64, "at": 15.0},
    ).json()
    assert ex["intent"] == "example" and ex["proposal"]["title"].startswith("Example:")
    client.post("/api/guardian/save", json={"map_id": work_map.map_id, "proposal_id": ex["proposal"]["proposal_id"]})

    mi = client.post(
        "/api/guardian/command",
        json={"map_id": work_map.map_id, "said": "A common mistake is announcing before the speaker confirms", "frame": frame_b64, "at": 20.0},
    ).json()
    assert mi["intent"] == "mistake" and mi["proposal"]["title"].startswith("Common mistake:")
    client.post("/api/guardian/save", json={"map_id": work_map.map_id, "proposal_id": mi["proposal"]["proposal_id"]})

    cp = client.post(
        "/api/guardian/command",
        json={"map_id": work_map.map_id, "said": "Compare with before", "frame": frame_b64, "at": 25.0},
    ).json()
    assert cp["intent"] == "compare" and "Room B" in cp["comparison"]
    client.post("/api/guardian/save", json={"map_id": work_map.map_id, "proposal_id": cp["proposal"]["proposal_id"]})
    assert len(get_maps().load(work_map.map_id).steps) == initial_steps + 3

    fg = client.post(
        "/api/guardian/command",
        json={"map_id": work_map.map_id, "said": "Forget that", "at": 30.0},
    ).json()
    assert fg["intent"] == "forget" and fg["steps"] == initial_steps + 2
    assert len(get_maps().load(work_map.map_id).steps) == initial_steps + 2


def test_forget_that_only_undoes_a_step_captured_in_the_current_class_and_says_what_it_undid(
    guardian, monkeypatch
):
    client, work_map = guardian
    monkeypatch.setattr(picture, "describe", lambda data, mime, **k: "A form.")
    monkeypatch.setattr(
        commands,
        "classify_command",
        lambda said, language="en": (
            commands.Command("forget", "")
            if "forget" in said.lower()
            else commands.Command("example", "booking Room B")
        ),
    )
    initial_steps = len(get_maps().load(work_map.map_id).steps)
    assert initial_steps >= 1

    # Said at the start of a class: never deletes a step from an earlier session
    early = client.post(
        "/api/guardian/command",
        json={"map_id": work_map.map_id, "said": "Forget that", "at": 2.0},
    ).json()
    assert early["intent"] == "forget" and early["forgotten"] == ""
    assert len(get_maps().load(work_map.map_id).steps) == initial_steps

    # Capture and save one step in this class, then undo it: it is removed and named in noted
    ex1 = client.post(
        "/api/guardian/command",
        json={"map_id": work_map.map_id, "said": "Example: booking Room B", "at": 10.0},
    ).json()
    client.post("/api/guardian/save", json={"map_id": work_map.map_id, "proposal_id": ex1["proposal"]["proposal_id"]})
    assert len(get_maps().load(work_map.map_id).steps) == initial_steps + 1
    undone = client.post(
        "/api/guardian/command",
        json={"map_id": work_map.map_id, "said": "Forget that", "at": 12.0},
    ).json()
    assert undone["forgotten"].startswith("Example:") and undone["forgotten"] in undone["noted"]
    assert len(get_maps().load(work_map.map_id).steps) == initial_steps

    # Once validated, even a step captured in this class cannot be undone by "forget that"
    ex2 = client.post(
        "/api/guardian/command",
        json={"map_id": work_map.map_id, "said": "Example: booking Room B", "at": 15.0},
    ).json()
    client.post("/api/guardian/save", json={"map_id": work_map.map_id, "proposal_id": ex2["proposal"]["proposal_id"]})
    loaded = get_maps().load(work_map.map_id)
    loaded.confirmed_at = "2026-10-08T12:00:00Z"
    get_maps().save(loaded)
    refused = client.post(
        "/api/guardian/command",
        json={"map_id": work_map.map_id, "said": "Forget that", "at": 18.0},
    ).json()
    assert refused["forgotten"] == ""
    assert len(get_maps().load(work_map.map_id).steps) == initial_steps + 1


def test_a_compare_steps_reason_stays_the_guardians_words_verbatim_while_urithis_description_goes_to_observed_and_cites(
    guardian, monkeypatch
):
    client, work_map = guardian
    frame_b64 = base64.b64encode(_two_half_jpeg()).decode()
    vision._previous[work_map.map_id] = frame_b64
    monkeypatch.setattr(
        commands,
        "classify_command",
        lambda said, language="en": commands.Command("compare", "the channel field"),
    )
    monkeypatch.setattr(
        commands,
        "compare_frames",
        lambda before, now, focus="": "The channel changed from #general to #announcements.",
    )
    said = "Compare with before: we switched to the public announcement channel."
    res = client.post(
        "/api/guardian/command",
        json={"map_id": work_map.map_id, "said": said, "frame": frame_b64, "at": 22.0},
    ).json()
    assert res["intent"] == "compare"
    assert res["proposal"]["reason"] == said
    assert res["proposal"]["cites"][0]["text"] == "The channel changed from #general to #announcements."
    client.post("/api/guardian/save", json={"map_id": work_map.map_id, "proposal_id": res["proposal"]["proposal_id"]})
    saved_step = get_maps().load(work_map.map_id).steps[-1]
    assert saved_step.reason == said
    assert saved_step.observed == "The channel changed from #general to #announcements."


def test_compare_uses_the_frame_before_the_last_change_instead_of_comparing_the_screen_with_itself(
    guardian, monkeypatch
):
    client, work_map = guardian
    vision.forget(work_map.map_id)

    img_before = Image.new("RGB", (60, 40), (10, 20, 200))
    buf_before = io.BytesIO()
    img_before.save(buf_before, format="JPEG", quality=90)
    raw_before = buf_before.getvalue()
    b64_before = base64.b64encode(raw_before).decode()

    img_after = Image.new("RGB", (60, 40), (200, 20, 10))
    buf_after = io.BytesIO()
    img_after.save(buf_after, format="JPEG", quality=90)
    raw_after = buf_after.getvalue()
    b64_after = base64.b64encode(raw_after).decode()

    # Frame 1 (before) is observed at t=0; Frame 2 (after) is observed at t=4 and triggers a change.
    assert vision.what_changed(b64_before, work_map.map_id, 0.0) is None

    class _FakeResp:
        text = '{"changed": "Switched channel to #announcements", "field": "channel", "decision": true}'
        usage_metadata = None

    class _FakeModels:
        def generate_content(self, **kwargs):
            return _FakeResp()

    class _FakeClient:
        models = _FakeModels()

    from apu.modality import voice

    monkeypatch.setattr(voice, "get_client", lambda: _FakeClient())
    obs = vision.what_changed(b64_after, work_map.map_id, 4.0)
    assert obs is not None and "announcements" in obs.changed

    # Now vision._previous[map_id] is b64_after, while _before_change[map_id] is b64_before.
    # When the guardian says "Compare with before" while the screen is still b64_after,
    # compare_frames receives raw_before (NOT raw_after).
    compared_pairs: list[tuple[bytes | None, bytes]] = []

    def fake_compare(before, now, *, focus=""):
        compared_pairs.append((before, now))
        return "Channel changed from #general (blue) to #announcements (red)."

    monkeypatch.setattr(vision, "compare_frames", fake_compare)
    monkeypatch.setattr(
        commands,
        "classify_command",
        lambda said, language="en": commands.Command("compare", "the channel"),
    )
    res = client.post(
        "/api/guardian/command",
        json={"map_id": work_map.map_id, "said": "Compare with before", "frame": b64_after, "at": 6.0},
    ).json()
    assert res["intent"] == "compare"
    assert len(compared_pairs) == 1
    assert compared_pairs[0][0] == raw_before
    assert compared_pairs[0][1] == raw_after
    assert compared_pairs[0][0] != compared_pairs[0][1]


def test_a_question_addressed_to_urithi_is_classified_as_ask_pupil_never_becomes_a_step_and_is_answered_from_known_facts(
    guardian, monkeypatch
):
    client, _ = guardian
    work_map = get_maps().new("Run a community tech meetup", "Sabine", "en", organisation="urithi")
    get_maps().save(work_map)
    monkeypatch.setattr(commands, "_command_model_ready", lambda: False)

    for phrase in (
        "did you see my screen?",
        "what rule are you talking about?",
        "give me the rule",
        "I said rule, not room.",
    ):
        cmd = commands.classify_command(phrase)
        assert cmd.intent == "ask_pupil", phrase

    # Before anything was seen or noted, Urithi says "I have not seen that yet." and adds no step.
    r1 = client.post(
        "/api/guardian/tell",
        json={"map_id": work_map.map_id, "said": "did you see my screen?"},
    ).json()
    assert r1["intent"] == "ask_pupil"
    assert r1["step"] is None
    assert r1["question"] is None
    assert r1["answer"] == "I have not seen that yet."
    assert len(get_maps().load(work_map.map_id).steps) == 0

    # Asking for a rule when none is noted yet says so simply and recalls the last question.
    from guardian.api import routes
    from guardian.engine import questions
    from guardian.engine.workmap import Guardrail

    session = routes._session(work_map.map_id)
    session["last_question_text"] = "Why announce in that channel?"
    r2 = client.post(
        "/api/guardian/tell",
        json={"map_id": work_map.map_id, "said": "what rule are you talking about?"},
    ).json()
    assert r2["intent"] == "ask_pupil"
    assert r2["step"] is None
    assert "not cited any rule" in r2["answer"].lower() or "no rule" in r2["answer"].lower()
    assert "Why announce in that channel?" in r2["answer"]
    assert len(get_maps().load(work_map.map_id).steps) == 0

    # Five different questions about the rule receive five distinct answers grounded in known facts.
    session["observations"].append(
        questions.Observation(
            at=2.0,
            changed="Organiser's Desk: Venue Dockside Room B, Format Two talks",
            field="Venue",
        )
    )
    five_questions = [
        "what rule are you talking about?",
        "give me the rule",
        "which rule did you mean?",
        "what is the rule?",
        "I said rule, not room, what rule?",
    ]
    five_answers = []
    for q in five_questions:
        ans = client.post(
            "/api/guardian/tell",
            json={"map_id": work_map.map_id, "said": q},
        ).json()["answer"]
        assert "not cited any rule" in ans.lower() or "no rule" in ans.lower()
        assert "Why announce in that channel?" in ans or "Dockside Room B" in ans
        five_answers.append(ans)
    assert len(set(five_answers)) == 5

    # Even if the question model repeats the exact same text, _ensure_distinct_answer differentiates it.
    monkeypatch.setattr(commands, "_command_model_ready", lambda: True)
    monkeypatch.setattr(
        commands,
        "call_main_model",
        lambda messages, **k: (
            '{"intent": "ask_pupil", "what": ""}'
            if "Classify" in messages[0]["content"] or "intent" in messages[0]["content"]
            else "I have not cited any rule yet; I asked: Why announce in that channel?"
        ),
    )
    a_first = client.post(
        "/api/guardian/tell",
        json={"map_id": work_map.map_id, "said": "tell me what rule you mean?"},
    ).json()["answer"]
    a_second = client.post(
        "/api/guardian/tell",
        json={"map_id": work_map.map_id, "said": "can you state the rule please?"},
    ).json()["answer"]
    assert a_first != a_second
    monkeypatch.setattr(commands, "_command_model_ready", lambda: False)

    # Once a rule is saved, Urithi answers strictly from those facts.
    loaded = get_maps().load(work_map.map_id)
    loaded.guardrails.append(
        Guardrail(
            guardrail_id="g-1",
            when="fewer than ten people register",
            then="move the meetup to the smaller room",
            quote="When fewer than ten people register, move the meetup to the smaller room.",
            asked_at=3.0,
        )
    )
    get_maps().save(loaded)

    r3 = client.post(
        "/api/guardian/tell",
        json={"map_id": work_map.map_id, "said": "did you see my screen?"},
    ).json()
    assert r3["intent"] == "ask_pupil"
    assert r3["step"] is None
    assert "Dockside Room B" in r3["answer"]

    r4 = client.post(
        "/api/guardian/tell",
        json={"map_id": work_map.map_id, "said": "give me the rule"},
    ).json()
    assert r4["intent"] == "ask_pupil"
    assert r4["step"] is None
    assert "fewer than ten people register" in r4["answer"]
    assert len(get_maps().load(work_map.map_id).steps) == 0


def test_an_answer_to_the_guardian_is_one_short_sentence_that_never_reads_a_note_back_whole(monkeypatch):
    """Measured live: answers took 3.9 to 6.2 s, two sentences each, one reading a whole note
    back and another counting "2 item(s)"; the voice, which reads the whole answer, took most of it."""
    work_map = get_maps().new("Organiser desk", "Sabine", "en", organisation="urithi")
    note = ("Uh, the information I want to share is what you need to have when you want to create "
            "your community tech event, who is mandatory and who is important for your event")
    from guardian.engine import questions
    seen = [questions.Observation(at=4.0, changed="Date set to Thu 22 Oct", scene="The Organiser's Desk.")]
    monkeypatch.setattr(commands, "_command_model_ready", lambda: True)
    monkeypatch.setattr(commands, "call_main_model", lambda *a, **k:
                        "I saw the Organiser's Desk with the date set. My last question was what we do first.")
    answer = commands.answer_pupil_question(work_map, "did you see my screen?", observations=seen)
    assert answer == "I saw the Organiser's Desk with the date set."
    monkeypatch.setattr(commands, "_command_model_ready", lambda: False)
    for asked in ("what is the organizer role you're talking about?", "did you see my screen?"):
        answer = commands.answer_pupil_question(work_map, asked, observations=seen, notes=[{"text": note}],
                                                last_question="What do we do first, and why?")
        assert "(s)" not in answer
        assert "who is mandatory and who is important for your event" not in answer


def test_forget_that_last_step_drops_the_proposal_just_made_not_a_saved_step(guardian, monkeypatch):
    """Measured live: "Forget that last step." left the scratch proposal it meant (the word "step"
    was read as the saved kind), and the proposal was saved later as knowledge."""
    client, work_map = guardian
    monkeypatch.setattr(picture, "describe", lambda data, mime, **k: "A form.")
    monkeypatch.setattr(commands, "classify_command", lambda said, language="en": (
        commands.Command("forget", "") if "forget" in said.lower() else commands.Command("example", "a scratch note")))
    saved_before = len(get_maps().load(work_map.map_id).steps)
    made = client.post("/api/guardian/command",
                       json={"map_id": work_map.map_id, "said": "Example: a scratch note", "at": 10.0}).json()
    pid = made["proposal"]["proposal_id"]
    undone = client.post("/api/guardian/command",
                         json={"map_id": work_map.map_id, "said": "Forget that last step.", "at": 12.0}).json()
    assert undone["dropped_proposal"] == pid
    left = client.get(f"/api/guardian/map/{work_map.map_id}").json()["proposals"]
    assert pid not in [p["proposal_id"] for p in left]
    assert len(get_maps().load(work_map.map_id).steps) == saved_before


def test_a_spoken_answer_is_cut_to_about_twenty_five_words_at_a_comma(monkeypatch):
    """Measured live in a shared-screen class: one-sentence answers of thirty words and more,
    listing every field on the screen, took past 3 s to be said."""
    long_one = ("I saw the Venue Dockside Library, room 2 with sixty seats, the format with two talks "
                "and discussion, that forty-eight came last time out of seventy-one who said yes, and today.")
    short = commands._spoken_length(long_one)
    assert len(short.split()) <= 25 and short.endswith(".")
    assert short.startswith("I saw the Venue Dockside Library")
    assert commands._spoken_length("I saw the Organiser's Desk.") == "I saw the Organiser's Desk."
