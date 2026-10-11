"""
Teaching in French, and when each sentence was said.

Target: guardian/engine/ (thresholds, wording, probe, questions, absorb, routes),
guardian/publish.py

A guardian who teaches in French is asked, tested and read back in French, and their rule is
kept in their words. The arithmetic that decides a rule reads French numbers as well as
English ones. Models are faked: what is checked is what code builds.
"""

import sqlite3

import pytest

from guardian.memory.store import set_maps

from tests.support import as_guardian

from guardian.engine import absorb, probe, questions, thresholds, wording
from guardian.engine.workmap import Guardrail, Ruling, Step, WorkMap, WorkMapStore
from guardian.publish import publication_from


@pytest.mark.parametrize("condition, value, above, inclusive", [
    ("moins de dix personnes sont inscrites", 10, False, False),
    ("les achats dépassent 5 000 euros", 5000, True, False),
    ("plus de cinq mille euros", 5000, True, False),
    ("au moins vingt-cinq participants", 25, True, True),
    ("quatre-vingts inscrits ou plus", 80, True, True),
    ("plus de soixante-dix personnes", 70, True, False),
    ("vingt et un jours ou moins", 21, False, True),
    ("au-dessus de 1 250,50 euros", 1250.5, True, False),
    ("un sponsor demande plus de deux cents euros", 200, True, False),
    ("ten or more speakers", 10, True, True),
])
def test_a_french_threshold_is_read_by_arithmetic_like_an_english_one(condition, value, above, inclusive):
    found = thresholds.threshold_in(condition)
    assert (found.value, found.above, found.inclusive) == (value, above, inclusive)


def test_an_article_is_not_a_number():
    assert thresholds.threshold_in("un sponsor demande plus de place") is None


def test_amounts_are_written_the_way_each_language_writes_them():
    assert wording.money(5000, "en") == "5,000" and wording.money(5000, "fr") == "5 000"
    assert wording.money(1250.5, "fr") == "1 250,50"
    assert wording.language_of("de") == "en", "an unknown language falls back, never fails"


def french_map() -> WorkMap:
    small = Guardrail(guardrail_id="small", when="moins de dix personnes sont inscrites",
                      then="déplaces le meetup", quote="Sous dix inscrits, je déplace le meetup.",
                      asked_at=12.0, said_at="2026-10-05T09:00:00+00:00")
    report = Guardrail(guardrail_id="report", when="un signalement au code de conduite arrive",
                       then="le confies à deux organisateurs", quote="Un signalement va à deux organisateurs.",
                       asked_at=30.0, severity="stop", said_at="2026-10-05T09:01:00+00:00")
    step = Step(step_id="s1", number=1, title="J'annonce chaque meetup deux semaines avant",
                screen_moment=5.0, observed="o", decision="d",
                reason="J'annonce chaque meetup deux semaines avant, sur le canal public.",
                guardrail_ids=("small", "report"), said_at="2026-10-05T08:59:00+00:00")
    return WorkMap(organisation="urithi", map_id="fr", task="Animer une communauté tech", expert="Ezekias", created_at="now",
                   steps=[step], guardrails=[small, report], language="fr",
                   confirmed_at="2026-10-05T09:10:00+00:00")


def test_the_debrief_asks_in_french_with_french_numbers():
    found = {p.kind: p for p in probe.probes_for(french_map(), use_model=False)}
    assert found["boundary"].question == (
        "Prenons un cas à exactement 10. Tu as dit que quand moins de dix personnes sont inscrites, "
        "tu déplaces le meetup. Exactement 10, c'est en dessous, ou pas ?")
    assert found["collision"].question.startswith("Imagine que les deux arrivent en même temps")
    assert "Que fais-tu en premier ?" in found["collision"].question


def test_the_teach_back_is_in_french_and_still_built_from_the_map():
    work_map = french_map()
    work_map.rulings.append(Ruling(ruling_id="r", guardrail_id="small", kind="boundary",
                                   case={"amount_eur": 10}, question="q", said="Dix, ça suffit.",
                                   applies=False, by="Ezekias", at="now"))
    said = probe.teach_back(work_map)
    assert said.startswith("Voici comment je comprends « Animer une communauté tech ».")
    assert "Étape 1 : J'annonce chaque meetup deux semaines avant, sur le canal public." in said
    assert "Quand moins de dix personnes sont inscrites, tu déplaces le meetup." in said
    assert "Et à 10, elle ne s'applique pas. Tu as dit : « Dix, ça suffit. »" in said
    assert said.endswith("Est-ce que ça marche comme ça ?")


def test_an_english_map_is_read_back_as_before():
    work_map = french_map()
    work_map.language = "en"
    assert probe.teach_back(work_map).startswith("Here is how I understand animer une communauté tech.")


def test_a_french_rule_is_kept_in_french_with_when_it_was_said():
    publication = publication_from(french_map(), version=1)
    units = {u.unit_id.split(":")[1]: u for u in publication.units}
    assert units["rule-small"].text == "Quand moins de dix personnes sont inscrites, tu déplaces le meetup."
    assert all(u.language == "fr" for u in publication.units) and publication.body.language == "fr"
    assert units["step-1"].said_at == "2026-10-05T08:59:00+00:00"
    assert units["rule-report"].said_at == "2026-10-05T09:01:00+00:00"


def test_the_apprentice_falls_back_to_a_french_question(monkeypatch):
    def broken(*a, **k):
        raise RuntimeError("down")
    monkeypatch.setattr(questions, "call_main_model", broken)
    seen = questions.Observation(at=1.0, changed="x")
    assert questions.word_question(questions.QuestionKind.LIMIT, seen, "t", "fr") == \
        "Où est-ce que cette règle s'arrête de s'appliquer ?"
    asked = []
    monkeypatch.setattr(questions, "call_main_model", lambda messages, **k: asked.append(messages) or "Pourquoi dix ?")
    assert questions.word_question(questions.QuestionKind.REASON, seen, "t", "fr") == "Pourquoi dix ?"
    assert "in French" in asked[0][0]["content"]


def test_a_french_rule_is_extracted_in_french_conjugated_for_tu(monkeypatch):
    prompts = []

    def model(messages, **k):
        prompts.append(messages[0]["content"])
        return '{"guardrails": [{"when": "moins de dix inscrits", "then": "déplaces le meetup", "severity": "check"}]}'
    monkeypatch.setattr(absorb, "call_extraction_model", model)
    [rail] = absorb.find_guardrails("Sous dix inscrits, je déplace le meetup.", 3.0, language="fr")
    assert rail.then == "déplaces le meetup" and "conjugated" in prompts[0]
    absorb.find_guardrails("Under ten, I move it.", 3.0)
    assert "French" not in prompts[1], "an English guardian is not asked for French"


@pytest.mark.parametrize("said, heard", [
    ("Oui, on le déplace.", True), ("Non.", False), ("On ne le déplace pas.", False),
    ("Je ne sais pas.", None), ("Oui, enfin non.", None),
])
def test_a_spoken_french_yes_or_no(said, heard):
    assert probe.heard_yes_no(said) is heard


def test_teaching_by_conversation_stamps_the_time_and_keeps_the_language(tmp_path, monkeypatch):
    from guardian.api import routes

    store = WorkMapStore(str(tmp_path / "w.sqlite3"))
    set_maps(store)
    monkeypatch.setattr(routes, "_voiced", lambda text: {"audio": None, "words": []})
    languages = []
    monkeypatch.setattr(absorb, "find_guardrails", lambda said, at, language="en", known=(): languages.append(language) or (
        [Guardrail(guardrail_id="g", when="moins de dix inscrits", then="déplaces le meetup", quote=said,
                   asked_at=at, severity="check")] if "dix" in said else []))
    monkeypatch.setattr(questions, "word_question",
                        lambda kind, seen, task, language="en", **said: languages.append(language) or "Pourquoi ?")
    started = routes.start(routes.StartBody(task="Animer", expert="Ezekias", language="fr"), as_guardian("ezekias"))
    assert started["language"] == "fr"
    r_step = routes.tell(routes.TellBody(map_id=started["map_id"], said="J'annonce chaque rencontre deux semaines avant sur le salon."))
    routes.save_proposal(routes.SaveBody(map_id=started["map_id"], proposal_id=r_step["proposal"]["proposal_id"]))
    reply = routes.tell(routes.TellBody(map_id=started["map_id"], said="Sous dix inscrits, je déplace le meetup."))
    routes.save_proposal(routes.SaveBody(map_id=started["map_id"], proposal_id=reply["proposal"]["proposal_id"]))
    work_map = store.load(started["map_id"])
    assert work_map.language == "fr" and set(languages) == {"fr"}
    assert work_map.steps[0].said_at and work_map.guardrails[0].said_at
    assert routes.start(routes.StartBody(task="t", expert="e", language="xx"), as_guardian("sabine"))["language"] == "en"


def test_a_map_written_before_languages_still_loads_in_english(tmp_path):
    path = str(tmp_path / "old.sqlite3")
    with sqlite3.connect(path) as db:
        db.execute("""CREATE TABLE workmaps (map_id TEXT PRIMARY KEY, task TEXT NOT NULL,
            expert TEXT NOT NULL, created_at TEXT NOT NULL, confirmed_at TEXT,
            steps TEXT NOT NULL, guardrails TEXT NOT NULL, rulings TEXT NOT NULL DEFAULT '[]')""")
        db.execute("INSERT INTO workmaps VALUES ('old', 't', 'e', 'now', NULL, "
                   "'[{\"step_id\": \"s1\", \"number\": 1, \"title\": \"t\", \"screen_moment\": 1.0, "
                   "\"observed\": \"o\", \"decision\": \"d\", \"reason\": \"r\", \"guardrail_ids\": [], "
                   "\"confirmed\": false}]', '[]', '[]')")
    loaded = WorkMapStore(path).load("old")
    assert loaded.language == "en" and loaded.steps[0].said_at is None


def test_the_name_read_back_keeps_its_capitals_after_the_first_letter():
    """Measured: the teach-back read "Here is how I understand choosing a or an in english"."""
    work_map = french_map()
    work_map.language = "en"
    work_map.task = "Choosing a or an in English"
    assert probe.teach_back(work_map).startswith("Here is how I understand choosing a or an in English.")
