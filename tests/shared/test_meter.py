"""
The meter: no costly call without a budget, quotas per role and period, four ceilings, and
the step-down before a refusal.

Target: apu/meter.py, exchange/counters.py, apu/inference/llm.py, apu/modality/voice.py,
learner/api/routes.py (the ask route), learner/memory/answers.py

docs/decisions/0007 and .claude/skills/metering-and-cost. Every model is faked; what is checked
is what code decides: whether a call reaches the provider at all, what is counted, what the
person is told, and which step is taken.
"""

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from apu import config, meter
from apu.inference import llm
from exchange.counters import SqliteCounters
from learner.tutor import answer as answering
from learner.tutor import guard
from tests.support import BODY, WordEmbedder, community

LEARNER = meter.Principal("urithi", "member", "learner")
NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)


@pytest.fixture
def policy(tmp_path, monkeypatch):
    """A small policy, so limits are reached in a few calls; acme narrows it, and tries to widen it."""
    found = {
        "quotas": {"learner": {"questions": {"period": "day", "warn": 2, "stop": 3}}},
        "ceilings": {"request": 0.5, "person_day": 1.0, "organisation_month": 10.0, "platform_day": 100.0},
        "organisations": {"acme": {"quotas": {"learner": {"questions": {"stop": 1, "warn": 1000}}},
                                   "ceilings": {"person_day": 50.0}}},
    }
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(found))
    monkeypatch.setattr(config, "POLICY_PATH", str(path))
    monkeypatch.setattr(config, "MODEL_PRICES", {"main": {"input": 1.0, "output": 10.0},
                                                 "extraction": {"input": 1.0, "output": 10.0}})
    return found


class FakeModels:
    def __init__(self, text="Two organisers handle it [1].", prompt=1000, total=21000):
        self.text, self.calls = text, []
        self.usage = SimpleNamespace(prompt_token_count=prompt, candidates_token_count=10,
                                     thoughts_token_count=total - prompt - 10, total_token_count=total)

    def generate_content(self, model, contents, config):
        self.calls.append(model)
        return SimpleNamespace(text=self.text, usage_metadata=self.usage,
                               candidates=[SimpleNamespace(finish_reason="STOP")])


@pytest.fixture
def models():
    fake = FakeModels()
    llm.set_client(SimpleNamespace(models=fake))
    yield fake
    llm.set_client(None)


# ── the rules ────────────────────────────────────────────────────────────────

def test_a_quota_warns_then_refuses_in_the_persons_own_words(policy):
    m = meter.meter()
    for _ in range(2):
        m.record(m.grant("questions", 1, LEARNER, NOW), now=NOW)
    third = m.grant("questions", 1, LEARNER, NOW)
    assert third.warning.startswith("You are close to your limit")
    m.record(third, now=NOW)
    with pytest.raises(meter.Refused) as refused:
        m.grant("questions", 1, LEARNER, NOW)
    assert refused.value.reason == ("You have reached your limit for questions to the tutor today. "
                                    "It starts again tomorrow.")
    assert m.grant("questions", 1, LEARNER, NOW + timedelta(days=1)), "a new day, a new quota"
    other = meter.Principal("urithi", "visitor", "learner")
    assert m.grant("questions", 1, other, NOW), "one person's quota is theirs"


def test_an_organisation_narrows_the_platforms_limits_and_never_widens_them(policy):
    acme = meter.Principal("acme", "ezekias", "learner")
    assert meter.quota(acme, "questions") == {"period": "day", "warn": 2, "stop": 1}
    assert meter.ceilings(acme)["person_day"] == 1.0, "50 asked, 1 allowed by the platform"
    m = meter.meter()
    m.record(m.grant("questions", 1, acme, NOW), now=NOW)
    with pytest.raises(meter.Refused):
        m.grant("questions", 1, acme, NOW)


def test_a_model_call_is_costed_from_what_was_billed_thinking_included(policy, models):
    with meter.acting_as(LEARNER):
        llm.call_main_model([{"role": "user", "content": "x" * 400}], max_tokens=30000)
    spent = SqliteCounters(meter.meter().counters.path).total("model_cost", since=NOW - timedelta(days=3650),
                                                              person_id="member")
    # 1000 tokens in at 1 per million, 20000 out (answer and thinking) at 10 per million.
    assert spent == pytest.approx(0.201)


def test_no_call_reaches_the_provider_past_a_ceiling(policy, models):
    m = meter.meter()
    m.counters.add("urithi", "member", "learner", "model_cost", 1.0, datetime.now(UTC))   # the day's budget, spent
    with meter.acting_as(LEARNER), pytest.raises(meter.Refused, match="answers worded by a model today"):
        llm.call_main_model([{"role": "user", "content": "hi"}], max_tokens=100)
    assert models.calls == [], "refused before the provider is reached"


def test_the_guard_is_counted_and_never_refused(policy, models):
    """A reply to distress is never stopped by a quota: the guard must read every message."""
    meter.meter().counters.add("urithi", "member", "learner", "model_cost", 1.0, datetime.now(UTC))
    with meter.acting_as(LEARNER):
        llm.call_extraction_model([{"role": "user", "content": "I can't cope any more"}], max_tokens=30000, always=True)
    assert models.calls, "the guard's call went through"


def test_a_request_too_costly_on_its_own_is_refused(policy, models):
    with meter.acting_as(LEARNER), pytest.raises(meter.Refused, match="one request"):
        llm.call_main_model([{"role": "user", "content": "x"}], max_tokens=100_000)


def test_the_level_says_how_near_the_ceiling_is(policy):
    m = meter.meter()
    assert m.level(LEARNER, NOW) == "ok"
    m.counters.add("urithi", "member", "learner", "model_cost", 0.85, NOW)
    assert m.level(LEARNER, NOW) == "near"
    m.counters.add("urithi", "member", "learner", "model_cost", 0.2, NOW)
    assert m.level(LEARNER, NOW) == "stop"


def test_counters_count_by_who_and_when(tmp_path):
    counters = SqliteCounters(str(tmp_path / "c.sqlite3"))
    counters.add("acme", "a", "learner", "questions", 2, NOW)
    counters.add("acme", "b", "learner", "questions", 3, NOW)
    counters.add("urithi", "a", "learner", "questions", 5, NOW - timedelta(days=2))
    assert counters.total("questions", since=NOW - timedelta(hours=1), organisation="acme") == 5
    assert counters.total("questions", since=NOW - timedelta(hours=1), organisation="acme", person_id="a") == 2
    assert counters.total("questions", since=NOW - timedelta(days=3)) == 10


# ── the step-down, at the ask route ──────────────────────────────────────────

@pytest.fixture
def asking(monkeypatch, tmp_path, policy):
    from apu import embeddings as embedder
    from exchange.questions import Questions, set_questions
    from library import store
    from server import app

    embedder.set_embedder(WordEmbedder())
    lib = store.MemoryKnowledgeStore()
    lib.publish(community())
    store.set_store(lib)
    set_questions(Questions(str(tmp_path / "q.sqlite3")))
    labels = {"label": "TOPIC"}
    monkeypatch.setattr(guard, "call_extraction_model", lambda *a, **k: labels["label"])
    words = []
    monkeypatch.setattr(answering, "call_main_model",
                        lambda *a, **k: words.append(k.get("model")) or "You move it under ten registrations [1].")
    yield TestClient(app), words, labels
    store.set_store(None)
    embedder.set_embedder(None)
    set_questions(None)


def _ask(client, question="When fewer than ten people register, do you move the meetup?"):
    return client.post("/api/learner/ask", json={"person_id": "member", "body_id": BODY, "question": question})


def test_the_same_question_on_the_same_version_is_answered_from_the_cache(asking):
    client, words, _ = asking
    first, second = _ask(client).json(), _ask(client).json()
    assert first["kind"] == "worded" and second["text"] == first["text"] and second["cached"]
    assert len(words) == 1, "worded once, for everyone who may see the same parts"


def test_near_a_ceiling_a_cheaper_model_words_it_when_one_is_set(asking, monkeypatch):
    client, words, _ = asking
    monkeypatch.setattr(config, "MAIN_MODEL_CHEAPER", "the-cheaper-one")
    meter.meter().counters.add("urithi", "member", "learner", "model_cost", 0.85, datetime.now(UTC))
    assert _ask(client).json()["kind"] == "worded"
    assert words == ["the-cheaper-one"]


def test_a_learners_answer_is_worded_by_its_own_model(asking, monkeypatch):
    """Measured on a real question: 8 to 17 s a worded answer with the main model. The answer has
    its own setting, the main model unless one is chosen; near a ceiling the cheaper one still wins."""
    client, words, _ = asking
    monkeypatch.setattr(config, "ANSWER_MODEL", "the-answer-model")
    assert _ask(client).json()["kind"] == "worded"
    assert words == ["the-answer-model"]


def test_at_a_ceiling_the_guardians_own_words_cost_nothing(asking):
    client, words, _ = asking
    meter.meter().counters.add("urithi", "member", "learner", "model_cost", 1.0, datetime.now(UTC))
    reply = _ask(client).json()
    assert reply["kind"] == "extractive" and reply["stepped_down"] == "guardian_words"
    assert words == [], "no model at all"


def test_at_a_ceiling_a_new_illustration_is_deferred_and_said(asking):
    client, _, _ = asking
    meter.meter().counters.add("urithi", "member", "learner", "model_cost", 1.0, datetime.now(UTC))
    reply = client.get(f"/api/learner/unit/{BODY}:step-1/picture", params={"person_id": "member"}).json()
    assert reply["deferred"] and "paused" in reply["detail"]


def test_past_the_quota_the_refusal_is_plain_and_distress_is_still_answered(asking):
    client, _, labels = asking
    for _ in range(3):
        _ask(client, question=f"When fewer than ten people register, do you move the meetup, case {_}?")
    refused = _ask(client)
    assert refused.status_code == 429 and refused.json()["refused"] == "questions"
    assert "your limit" in refused.json()["detail"] and "member" not in refused.json()["detail"]
    labels["label"] = "WELFARE"
    cared = _ask(client, question="I can't do this any more, I want to give up")
    assert cared.status_code == 200 and cared.json()["kind"] == "welfare"


def test_the_learners_guard_reads_a_message_past_every_ceiling(policy, monkeypatch):
    """The real guard, past the person's ceiling: distress is still recognised and answered."""
    fake = FakeModels(text="WELFARE", prompt=100, total=120)
    llm.set_client(SimpleNamespace(models=fake))
    try:
        meter.meter().counters.add("urithi", "member", "learner", "model_cost", 5.0, datetime.now(UTC))
        with meter.acting_as(LEARNER):
            verdict = guard.check("I can't do this any more", body_id=BODY, body_name="b", covers=[])
        assert verdict.outcome.value == "welfare" and verdict.reply
    finally:
        llm.set_client(None)


def test_a_ceiling_met_on_the_way_is_a_step_down_not_a_failure(asking, monkeypatch):
    """Measured live: the estimate alone passed the platform's ceiling; the answer fell back to
    the guardian's words but did not say it had stepped down."""
    client, _, _ = asking

    def refused(*a, **k):
        raise meter.Refused("model_cost", "The service has reached its spending limit for today.")

    monkeypatch.setattr(answering, "call_main_model", refused)
    reply = _ask(client).json()
    assert reply["kind"] == "extractive" and reply["stepped_down"] == "guardian_words"


def test_the_guardians_words_quote_the_passage_that_shares_the_questions_words():
    """Measured live: "a or an before useful?" quoted the silent H, ranked first, rather than
    the passage that says "a useful tip", ranked second."""
    citations = [
        {"n": 1, "guardian": "Ezekias", "text": "Silent H, write an.", "quote": "Hour or heir: an."},
        {"n": 2, "guardian": "Ezekias", "text": "A you sound, write a.", "quote": "A university, a useful tip."},
    ]
    said = answering.extractive(citations, "en", "Do I write a or an before useful?")
    assert "a useful tip" in said and said.endswith("[2]")
    assert answering.extractive(citations, "en", "Something unrelated").endswith("[1]"), "the vector rank, between equals"
    # Measured live: "One more: an FBI agent?" quoted a step that began "One more thing."
    lead_in = [{"n": 1, "guardian": "E", "text": "Letter by letter.", "quote": "An FBI agent, an MBA."},
               {"n": 2, "guardian": "E", "text": "A you sound.", "quote": "One more thing. A useful tip."}]
    assert answering.extractive(lead_in, "en", "One more: an FBI agent?").endswith("[1]")


def test_only_a_worded_answer_is_kept_for_the_next_asker(asking, monkeypatch):
    """Measured live: answers given in the guardian's words while the model was refused were
    cached, and served again after it came back, one quoting the wrong passage."""
    client, words, _ = asking

    def refused(*a, **k):
        raise meter.Refused("model_cost", "The service has reached its spending limit for today.")

    monkeypatch.setattr(answering, "call_main_model", refused)
    assert _ask(client).json()["kind"] == "extractive"
    monkeypatch.setattr(answering, "call_main_model", lambda *a, **k: "You move it under ten registrations [1].")
    again = _ask(client).json()
    assert again["kind"] == "worded" and not again.get("cached"), "worded now that the model is back"
