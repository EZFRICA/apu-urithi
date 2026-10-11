"""
The apprentice: what it asks, what it learns, and whether what it learned is still true.

None of these touch the network. The model and the search backend are the two things that
cannot be relied on in a test, so they are the two things replaced here; everything between
them is this project's own and is run for real.
"""

import pathlib

import pytest

from guardian.memory.store import set_maps

from tests.support import as_guardian, guardian_client

from guardian.engine import absorb, jsonish, provenance, questions, tutor
from guardian.engine.sources import Source
from guardian.engine.workmap import Guardrail, Step, WorkMap, WorkMapError, WorkMapStore


@pytest.fixture
def store(tmp_path, monkeypatch):
    path = str(tmp_path / "workmap.sqlite3")
    monkeypatch.setattr("guardian.engine.workmap.WORKMAP_PATH", path)
    return WorkMapStore(path)


def rail(when="the supplier is unknown", then="stop and ask the controller",
         severity="stop", **extra) -> Guardrail:
    return Guardrail(guardrail_id=extra.pop("gid", "g1"), when=when, then=then,
                     quote=extra.pop("quote", "I stop and ask the controller."),
                     asked_at=195.0, severity=severity, **extra)


# ── when the apprentice speaks ───────────────────────────────────────────────

def test_a_pause_is_measured_rather_than_guessed():
    """The expert works in another window, so the only honest signal is a measured gap."""
    detector = questions.PauseDetector(pause_seconds=2.5)
    detector.update(questions.Activity(at=10.0, typing=True, talking=False, scrolling=False))

    assert not detector.is_pause(11.0), "one second after typing is mid-thought"
    assert detector.is_pause(13.0), "two and a half seconds of nothing is a pause"
    assert detector.paused_for(13.0) == pytest.approx(3.0)

    # Talking counts as busy: an apprentice that interrupts an explanation is worse than
    # one that stays quiet.
    detector.update(questions.Activity(at=13.0, typing=False, talking=True, scrolling=False))
    assert not detector.is_pause(14.0)


def test_the_question_closes_the_oldest_gap_first():
    """
    Which question is asked is a ledger of what is missing, never a model's curiosity, so
    the apprentice can always say why it asked that and not something else.
    """
    work_map = WorkMap(organisation="urithi", map_id="m", task="t", expert="e", created_at="now")
    seen = questions.Observation(at=1.0, changed="cost center changed", field="cost_center")

    # Nothing captured: the first thing missing is why anything was done.
    assert questions.next_kind(work_map, seen, []) is questions.QuestionKind.REASON

    work_map.steps.append(Step(step_id="s1", number=1, title="t", screen_moment=1.0,
                               observed="cost center changed", decision="d",
                               reason="because it is capex"))
    assert questions.next_kind(work_map, seen, []) is questions.QuestionKind.LIMIT

    work_map.guardrails.append(rail(severity="check"))
    assert questions.next_kind(work_map, seen, []) is questions.QuestionKind.ESCALATION

    work_map.guardrails.append(rail(gid="g2", severity="stop"))
    assert questions.next_kind(work_map, seen, []) is None, "nothing left that it needs"

    # Until she does something new. Measured on a real run: after one answer with a stop
    # rule in it, the next decision on screen was never asked about.
    new = questions.Observation(at=40.0, changed="account changed to 0420", field="account")
    assert questions.next_kind(work_map, new, []) is questions.QuestionKind.REASON

    # A field changed twice jumps the queue: that is where the exceptions live.
    assert questions.next_kind(work_map, seen, ["cost_center", "cost_center"]) \
        is questions.QuestionKind.EXCEPTION


def test_a_half_formed_question_is_never_spoken(monkeypatch):
    """
    Measured: a reasoning model spends its token budget before the first word, and returned
    "Why" and "If the rule". A truncated question sounds like an apprentice that lost its
    thread, so it is replaced by a whole one.
    """
    seen = questions.Observation(at=1.0, changed="cost center changed")
    for truncated in ("Why", "If the rule", "At what amount do you switch from", ""):
        monkeypatch.setattr(questions, "call_main_model", lambda *a, **k: truncated)
        asked = questions.word_question(questions.QuestionKind.REASON, seen, "task")
        assert asked == questions.FALLBACKS[questions.QuestionKind.REASON]
        assert asked.endswith("?")

    monkeypatch.setattr(questions, "call_main_model",
                        lambda *a, **k: '"Why capex rather than opex there?"')
    assert questions.word_question(questions.QuestionKind.REASON, seen, "t") \
        == "Why capex rather than opex there?"


# ── what it learns ───────────────────────────────────────────────────────────

def test_a_limit_keeps_the_sentence_it_came_from(monkeypatch):
    monkeypatch.setattr(absorb, "call_extraction_model", lambda *a, **k:
                        '{"guardrails":[{"when":"the supplier is unknown",'
                        '"then":"stop and ask the controller","severity":"stop"}]}')
    said = "If I do not recognise the supplier, I stop and ask the controller."
    [found] = absorb.find_guardrails(said, at=195.0)
    assert found.quote == said, "a rule nobody can trace to a person is one they work around"
    assert found.severity == "stop" and found.asked_at == 195.0


def test_no_limit_stated_invents_none(monkeypatch):
    monkeypatch.setattr(absorb, "call_extraction_model", lambda *a, **k: '{"guardrails":[]}')
    assert absorb.find_guardrails("I copy the number from the top of the page.", 1.0) == []


def test_an_unreadable_answer_loses_the_rule_and_not_the_step(monkeypatch):
    monkeypatch.setattr(absorb, "call_extraction_model", lambda *a, **k: "not json at all")
    assert absorb.find_guardrails("anything", 1.0) == [], "empty, not an exception"


def test_a_map_that_cannot_teach_says_so(store):
    work_map = store.new("Code an invoice", "Sabine", organisation="urithi")
    assert not work_map.is_teachable and "Nothing was captured" in work_map.why_not_teachable()

    work_map.steps.append(Step(step_id="s1", number=1, title="t", screen_moment=1.0,
                               observed="o", decision="d", reason="   "))
    work_map.guardrails.append(rail())
    # A step with no reason is a recording of a click. With a rail present, the only thing
    # standing between this map and teaching is the missing reason, so the verdict is what
    # has to be asserted, not only the message.
    assert not work_map.is_teachable, "a step with no reason must not teach"
    assert "No reason was given for step 1" in work_map.why_not_teachable()
    work_map.guardrails.clear()

    work_map.steps[0] = Step(step_id="s1", number=1, title="t", screen_moment=1.0,
                             observed="o", decision="d", reason="because it is capex")
    assert "No limit was stated" in work_map.why_not_teachable()

    work_map.guardrails.append(rail())
    assert work_map.is_teachable and work_map.why_not_teachable() == ""


def test_a_guardrail_needs_both_halves():
    with pytest.raises(WorkMapError):
        Guardrail("g", when="", then="stop", quote="q", asked_at=1.0)
    with pytest.raises(WorkMapError):
        Guardrail("g", when="x", then="y", quote="q", asked_at=1.0, severity="maybe")


def test_a_map_survives_being_written_down(store):
    work_map = store.new("Code an invoice", "Sabine", organisation="urithi")
    work_map.guardrails.append(rail(provenance={"verdict": "conflicted", "note": "moved"}))
    work_map.steps.append(Step(step_id="s1", number=1, title="t", screen_moment=1.0,
                               observed="o", decision="d", reason="r",
                               guardrail_ids=("g1",)))
    store.save(work_map)

    back = store.load(work_map.map_id)
    assert back.steps[0].reason == "r"
    assert isinstance(back.steps[0].guardrail_ids, tuple), "a frozen record holds no list"
    assert [g.guardrail_id for g in back.conflicts] == ["g1"]
    assert back.rails_for(back.steps[0])[0].then == "stop and ask the controller"


# ── what it teaches ──────────────────────────────────────────────────────────

def test_a_rule_the_tutor_cannot_decide_stops_the_save(monkeypatch):
    """
    Failing closed is the whole contract. A tutor that waves through what it does not
    understand is trusted exactly where the work is hard.
    """
    monkeypatch.setattr(tutor, "call_main_model", lambda *a, **k: "not json")
    work_map = WorkMap(organisation="urithi", map_id="m", task="t", expert="e", created_at="now",
                       guardrails=[rail()])
    result = tutor.review(work_map, {"supplier_known": True}, "book this")

    assert not result.allowed
    assert result.blocking is not None
    assert not result.blocking.certain
    assert "cannot tell" in result.blocking.says


def test_a_rule_that_does_not_apply_is_silent(monkeypatch):
    monkeypatch.setattr(tutor, "call_main_model", lambda *a, **k: '{"applies":"no"}')
    work_map = WorkMap(organisation="urithi", map_id="m", task="t", expert="e", created_at="now",
                       guardrails=[rail()])
    assert tutor.review(work_map, {"supplier_known": True}, "book this").allowed


def test_the_intervention_carries_the_expert_and_the_moment(monkeypatch):
    monkeypatch.setattr(tutor, "call_main_model", lambda *a, **k: '{"applies":"yes"}')
    work_map = WorkMap(organisation="urithi", map_id="m", task="t", expert="e", created_at="now",
                       guardrails=[rail()])
    [step] = tutor.review(work_map, {"supplier_known": False}, "book this").interventions

    assert step.quote == "I stop and ask the controller."
    assert step.replay_at == 195.0, "the second of screen to replay"
    assert "I stop and ask the controller." in step.says


def test_a_contradicted_rule_is_enforced_and_declared(monkeypatch):
    """
    A search result does not overrule twenty-four years. It is still enforced; the new hire
    is simply told to settle it with a person.
    """
    monkeypatch.setattr(tutor, "call_main_model", lambda *a, **k: '{"applies":"yes"}')
    flagged = rail(provenance={"verdict": "conflicted", "note": "the threshold moved"})
    work_map = WorkMap(organisation="urithi", map_id="m", task="t", expert="e", created_at="now",
                       guardrails=[flagged])
    result = tutor.review(work_map, {"supplier_known": False}, "book this")

    assert not result.allowed, "still enforced"
    assert "says something different" in result.interventions[0].says
    assert "controller" in result.interventions[0].says


def test_mastery_counts_what_was_tested_and_not_what_was_shown():
    work_map = WorkMap(organisation="urithi", map_id="m", task="t", expert="e", created_at="now",
                       guardrails=[rail(gid="a"), rail(gid="b", when="over 5000 euros",
                                                       then="capex", severity="check")])
    counted = tutor.mastery(work_map, seen={"a"})
    assert counted["covered"] == "1/2"
    assert [r["when"] for r in counted["to_practise"]] == ["over 5000 euros"]


# ── whether what it learned is still true ────────────────────────────────────

def source(domain="bundesfinanzministerium.de", text="The threshold is 800 euros.") -> Source:
    return Source(url=f"https://{domain}/page", title="Guidance", text=text,
                  backend="brightdata", retrieved_at="2026-10-04", published="2026-01-15")


def test_a_page_for_another_country_is_set_aside():
    """
    Measured on the first live run: asked about a German threshold, the search returned an
    American university's internal accounting manual and a conflict was raised on it. A
    rule flagged against the wrong country's law is worse than no flag.
    """
    assert provenance._applies_here("de", "de")
    assert provenance._applies_here("any", "de")
    assert provenance._applies_here("", "de")
    assert not provenance._applies_here("us", "de")


def test_a_rule_with_no_public_authority_is_a_house_rule(monkeypatch):
    """
    The distinction nobody writes down: which rules are law, and which are how we do it
    here. Both are real; a new hire needs to know which is which.
    """
    monkeypatch.setattr(provenance, "call_main_model", lambda *a, **k:
                        '{"query":"","public":false}')
    found = provenance.check(rail(), context="accounts payable")
    assert found.verdict is provenance.Verdict.HOUSE_RULE
    assert found.citations == []


def test_a_source_that_disagrees_is_a_flag_and_carries_both_sides(monkeypatch):
    calls = iter([
        '{"query":"German capitalisation threshold","public":true}',
        '{"relevant":true,"jurisdiction":"de","agrees":false,'
        '"says":"The threshold is 800 euros since 2018."}',
    ])
    monkeypatch.setattr(provenance, "call_main_model", lambda *a, **k: next(calls))
    monkeypatch.setattr(provenance, "get_backend", lambda country="de":
                        type("B", (), {"name": "brightdata",
                                       "search": lambda self, q, limit=4: [source()]})())

    found = provenance.check(rail(when="equipment is over 5000 euros", then="capex"),
                             context="accounts payable", country="de")
    assert found.verdict is provenance.Verdict.CONFLICTED and found.is_flag
    assert "800 euros" in found.note, "what the source says"
    assert "I stop and ask the controller." in found.note, "and what the expert said"
    assert found.citations[0].url.startswith("https://bundesfinanzministerium.de")


def test_no_backend_is_unchecked_and_never_corroborated(monkeypatch):
    """
    The one answer that must never be guessed. A lookup that did not happen is not a clean
    bill of health, and must not be shown as one.
    """
    from guardian.engine.sources import NoBackend

    monkeypatch.setattr(provenance, "call_main_model", lambda *a, **k:
                        '{"query":"anything","public":true}')

    def refuse(country="de"):
        raise NoBackend("no token")

    monkeypatch.setattr(provenance, "get_backend", refuse)
    found = provenance.check(rail(), context="t")
    assert found.verdict is provenance.Verdict.UNCHECKED
    assert "no token" in found.note


def test_a_stored_provenance_reads_back_or_is_nothing():
    original = provenance.Provenance(verdict=provenance.Verdict.CONFLICTED,
                                     checked_at="2026-10-04", note="n")
    assert provenance.from_dict(original.as_dict()).verdict is provenance.Verdict.CONFLICTED
    assert provenance.from_dict(None) is None
    assert provenance.from_dict({"verdict": "invented"}) is None, "not a silent default"


# ── reading a model that was asked for JSON ──────────────────────────────────

@pytest.mark.parametrize("raw, expected", [
    ('{"a":1}', {"a": 1}),
    ('```json\n{"a":1}\n```', {"a": 1}),
    ('Here you go: {"a":1} hope that helps', {"a": 1}),
    ('[{"when":"x"}]', [{"when": "x"}]),
])
def test_json_is_found_in_whatever_came_back(raw, expected):
    assert jsonish.loads(raw) == expected


def test_no_json_is_an_error_rather_than_a_default():
    with pytest.raises(ValueError):
        jsonish.loads("I am afraid I cannot do that")
    with pytest.raises(ValueError):
        jsonish.loads("")


def test_a_serp_zone_set_to_html_says_what_to_fix(caplog):
    from guardian.engine.sources import _organic

    assert _organic('{"organic":[{"link":"https://a"}]}') == [{"link": "https://a"}]
    assert _organic('[{"link":"https://b"}]') == [{"link": "https://b"}]
    with caplog.at_level("WARNING"):
        assert _organic("<html>not json</html>") == []
    assert "Full JSON" in caplog.text, "the message names the setting to change"


def test_the_readme_is_about_the_thing_this_repository_builds():
    readme = (pathlib.Path(__file__).resolve().parents[2] / "README.md").read_text(encoding="utf-8")
    assert "Urithi" in readme
    assert "uv run python -m server" in readme
    for page in ("localhost:8790/teach/", "localhost:8790/learn/", "localhost:8790/presentation/"):
        assert page in readme, page


# ── arithmetic is not a judgment call ────────────────────────────────────────

from guardian.engine import thresholds  # noqa: E402


@pytest.mark.parametrize("condition, value, above, inclusive", [
    ("equipment is over five thousand euros", 5000, True, False),
    ("the amount is above 5,000 EUR", 5000, True, False),
    ("net is at least 5.000 euros", 5000, True, True),       # a German thousands separator
    ("value under 800 euros", 800, False, False),
    ("invoices of 5k or more", 5000, True, True),
    ("over two hundred and fifty euros", 250, True, False),
    ("anything below 1,250.50 dollars", 1250.5, False, False),  # English: the dot is the decimal
    ("anything below 1.250,50 euros", 1250.5, False, False),    # German: the comma is
])
def test_the_number_a_rule_turns_on_is_read_however_it_was_said(condition, value, above, inclusive):
    found = thresholds.threshold_in(condition)
    assert found is not None
    assert found.value == pytest.approx(value)
    assert found.above is above and found.inclusive is inclusive


@pytest.mark.parametrize("condition", [
    "the supplier is not recognised",
    "the invoice comes from the Czech subsidiary",
    "over the moon",                                   # a comparison word, no number
])
def test_a_rule_with_no_number_is_left_to_the_model(condition):
    assert thresholds.decide(condition, {"amount_eur": 9999}) is None


@pytest.mark.parametrize("amount, applies", [(2400, False), (5000, False), (5001, True), (7480, True)])
def test_the_boundary_is_exact(amount, applies):
    """Five thousand is not over five thousand. Five thousand and one is."""
    assert thresholds.decide("equipment is over five thousand euros", {"amount_eur": amount}) is applies


def test_no_amount_in_the_case_is_no_answer_rather_than_a_guess():
    assert thresholds.decide("over five thousand euros", {"supplier": "x"}) is None
    assert thresholds.decide("over five thousand euros", {"amount_eur": True}) is None, \
        "a boolean is not an amount"
    assert thresholds.amount_in({"net_amount": "EUR 7.480"}) == 7480
    # How a German invoice actually prints its total.
    assert thresholds.amount_in({"net_amount": "7.480,00 EUR"}) == 7480


def test_a_numeric_rule_never_reaches_the_model(monkeypatch):
    """
    Measured: four runs of 2,400 against five thousand gave no, unsure, unsure, no. Unsure
    fails closed, so half the time a new hire was stopped by a rule that did not apply.
    """
    def must_not_be_called(*args, **kwargs):
        raise AssertionError("arithmetic was handed to the model")

    monkeypatch.setattr(tutor, "call_main_model", must_not_be_called)
    capex = rail(when="equipment is over five thousand euros", then="treat it as capex",
                 severity="check")
    assert tutor._rail_applies(capex, {"amount_eur": 2400}) == (False, True)
    assert tutor._rail_applies(capex, {"amount_eur": 7480}) == (True, True)


def test_uncertainty_is_said_for_every_rule_not_only_the_blocking_ones():
    """
    A "check" rule that fired because the tutor could not tell used to read exactly like
    one it was sure of. The new hire could not know which they were hearing.
    """
    check_rule = rail(severity="check")
    assert tutor._wording(check_rule, "book this", certain=False).startswith("I cannot tell")
    assert tutor._wording(check_rule, "book this", certain=True).startswith("Worth knowing")
    assert tutor._wording(rail(severity="stop"), "book this", certain=True).startswith("Hold on")


# ── the map, for someone who reads with their fingers ────────────────────────

from guardian.engine import braille as braille_map  # noqa: E402


def taught_map() -> WorkMap:
    work_map = WorkMap(organisation="urithi", map_id="m", task="Code a supplier invoice", expert="Sabine",
                       created_at="now")
    work_map.guardrails += [
        rail(gid="stop1", provenance={"verdict": "house_rule"}),
        rail(gid="check1", when="equipment is over five thousand euros",
             then="treat it as capex", severity="check",
             quote="Equipment over five thousand euros is always capex.",
             provenance={"verdict": "conflicted", "citations": [{"domain": "gofinto.com"}]}),
    ]
    work_map.steps.append(Step(step_id="s1", number=1, title="Code to a cost center",
                               screen_moment=192.0, observed="o", decision="d",
                               reason="Equipment over five thousand euros is always capex.",
                               guardrail_ids=("stop1", "check1")))
    return work_map


def test_the_printed_map_reads_in_order_for_a_reader_who_cannot_skim():
    text = braille_map.as_print(taught_map())
    order = [text.index(marker) for marker in
             ("Task:", "The steps.", "Step 1.", "Why:", "When to stop and ask.", "Worth knowing.")]
    assert order == sorted(order), "the order carries the structure a finger cannot skim"
    assert "In their words: I stop and ask the controller." in text


def test_a_screen_moment_is_not_printed_on_a_page_for_someone_without_the_screen():
    """'3:12' is an index into a recording, the one part a blind colleague was not given."""
    text = braille_map.as_print(taught_map())
    assert "3:12" not in text and "192" not in text


def test_a_disputed_rule_is_said_in_words_and_not_left_to_a_colour():
    """The screen marks a contradicted rule in amber. A colour is not a medium."""
    text = braille_map.as_print(taught_map())
    assert "a public source now says something different" in text
    assert "This is a house rule. No public source governs it." in text


def test_an_unfinished_map_says_so_on_the_page():
    work_map = WorkMap(organisation="urithi", map_id="m", task="t", expert="e", created_at="now")
    assert "This map is not finished." in braille_map.as_print(work_map)


def test_the_map_embosses_on_real_braille_paper():
    try:
        doc = braille_map.emboss(taught_map())
    except braille_map.BrailleUnavailable:
        pytest.skip("liblouis is not installed here")
    lines = doc.brf.replace("\f", "\n").split("\n")
    assert max(len(line) for line in lines) <= 40, "forty cells to a line, as paper holds them"
    assert doc.pages >= 1 and doc.grade == 2
    assert all(0x2800 <= ord(c) <= 0x28FF or c in " \n\f" for c in doc.unicode_braille)


def test_grade_one_is_longer_than_grade_two():
    """Grade 2 is contracted. If the two are the same length, contraction did not happen."""
    from apu.modality.braille.translator import BrailleGrade

    try:
        one = braille_map.emboss(taught_map(), grade=BrailleGrade.GRADE_1)
        two = braille_map.emboss(taught_map(), grade=BrailleGrade.GRADE_2)
    except braille_map.BrailleUnavailable:
        pytest.skip("liblouis is not installed here")
    assert len(one.brf) > len(two.brf)


def test_a_map_that_cannot_be_embossed_raises_rather_than_handing_over_a_blank_page(monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("liblouis is missing")

    monkeypatch.setattr(braille_map, "braille_sheet", broken)
    with pytest.raises(braille_map.BrailleUnavailable):
        braille_map.emboss(taught_map())
    assert braille_map.intervention_cells("anything") == "", "a warning without cells is still spoken"


def test_the_server_hands_out_the_map_in_braille(store, monkeypatch):

    from server import app

    set_maps(store)
    work_map = taught_map()
    work_map.map_id = store.new("t", "e", organisation="urithi").map_id
    store.save(work_map)

    client = guardian_client(app)
    reply = client.get(f"/api/guardian/map/{work_map.map_id}/braille?grade=2").json()
    if "error" in reply and "not available" in reply["error"]:
        pytest.skip("liblouis is not installed here")
    assert reply["grade"] == 2 and reply["pages"] >= 1 and reply["brf"]
    # The pages a screen shows are the embosser's pages, line for line: turned back into
    # Braille ASCII they are the BRF, character for character.
    from apu.modality.braille.translator import unicode_to_braille_ascii
    assert len(reply["pages_unicode"]) == reply["pages"]
    assert all(len(line) <= 40 for page in reply["pages_unicode"] for line in page)
    assert "\f".join("\n".join(unicode_to_braille_ascii(line) for line in page)
                     for page in reply["pages_unicode"]) == reply["brf"]
    assert client.get(f"/api/guardian/map/{work_map.map_id}/braille?grade=3").json() \
        == {"error": "Grade 1 or grade 2."}
    assert client.get("/api/guardian/map/nope/braille").json() == {"error": "No such map."}


def test_every_control_on_the_page_has_a_key():
    """
    The person teaching may not see the pointer. A button that has to be held with a mouse is
    a button a blind expert cannot hold: Space talks and lets go, Escape ends the class, and
    ? lists the keys of the page.
    """
    root = pathlib.Path(__file__).resolve().parents[2] / "guardian/ui/teach"
    page = (root / "index.html").read_text(encoding="utf-8")
    script = (root / "teach.js").read_text(encoding="utf-8")
    assert 'e.key === " "' in script and 'window.addEventListener("keyup"' in script, "push to talk releases on key up"
    assert '$("classroom").addEventListener("cancel"' in script, "Escape ends the class"
    assert "new KeyMap(" in script and 'aria-live="polite"' in page


# ── the debrief: the expert's rules tested like code ─────────────────────────

from guardian.engine import probe as probes  # noqa: E402
from guardian.engine.workmap import Ruling  # noqa: E402


def sabine_map(conflicted: bool = True) -> WorkMap:
    capex = rail(gid="capex", when="equipment is over five thousand euros",
                 then="treat it as capex", severity="check",
                 quote="Equipment over five thousand euros is always capex.",
                 provenance={"verdict": "conflicted", "citations": [{
                     "domain": "gofinto.com", "agrees": False, "url": "https://gofinto.com/x",
                     "says": "The immediate write-off threshold remains unchanged in 2026, "
                             "at 800 euros net per asset"}]} if conflicted else None)
    supplier = rail(gid="supplier", when="the supplier is not recognised",
                    then="stop and ask the controller")
    return WorkMap(organisation="urithi", map_id="m", task="Code a supplier invoice", expert="Sabine",
                   created_at="now", guardrails=[capex, supplier],
                   steps=[Step(step_id="s1", number=1, title="Cost center changed",
                               screen_moment=192.0, observed="o", decision="d",
                               reason="Equipment over five thousand euros is always capex.",
                               guardrail_ids=("capex", "supplier"))])


def ruling(kind, guardrail_id, case, said, applies, by="Sabine", **extra):
    return Ruling(ruling_id=extra.get("rid", f"{kind}-{guardrail_id}"), guardrail_id=guardrail_id,
                  kind=kind, case=case, question="q", said=said, applies=applies, by=by, at="now")


def test_the_debrief_asks_what_the_task_never_showed_built_by_code():
    """
    At least three follow-up questions the task did not answer. These three are computed,
    not generated, so what was asked can always be explained.
    """
    found = probes.probes_for(sabine_map(), use_model=False)
    assert [p.kind for p in found] == ["source", "boundary", "collision"], "most expensive first"
    assert all(p.built_by == "code" for p in found)
    assert len(found) >= probes.MIN_PROBES


def test_a_near_miss_goes_to_an_untested_rule_first_and_is_told_what_is_settled(monkeypatch):
    """Measured: a boundary settled at exactly 5,000 came back as a near miss about exactly 5,000."""
    work_map = sabine_map()
    work_map.rulings += [ruling("boundary", "capex", {"amount_eur": 5000}, "Five thousand is not over.", False),
                         ruling("source", "capex", {}, "We follow our own rule.", None),
                         ruling("boundary", "supplier", {}, "Unknown means stop.", True),
                         ruling("collision", "capex", {}, "Supplier first.", None)]
    work_map.guardrails.append(Guardrail(guardrail_id="credit", when="a credit note arrives",
                                         then="book it against the original invoice",
                                         quote="A credit note goes against the original invoice.", asked_at=300.0))
    prompts = []

    def model(messages, **kwargs):
        prompts.append(messages[1]["content"])
        return '{"case": "A credit note with no invoice number.", "question": "Do you still book it against an invoice?"}'

    monkeypatch.setattr(probes, "call_main_model", model)
    found = probes.probes_for(work_map)
    near = [p for p in found if p.kind == "near_miss"]
    assert near and near[0].guardrail_id == "credit", "the rule never put to the guardian first"
    [capex_prompt] = [x for x in prompts if "Five thousand is not over." in x]
    assert "do not ask about these again" in capex_prompt
    assert "do not ask" not in prompts[0], "nothing settled about the credit note rule"


def test_the_boundary_probe_is_the_exact_number_the_rule_turns_on():
    boundary = next(p for p in probes.probes_for(sabine_map(), use_model=False)
                    if p.kind == "boundary")
    assert boundary.case == {"amount_eur": 5000.0}
    assert "exactly 5,000" in boundary.question


def test_the_source_probe_sits_where_the_two_rules_disagree_and_not_on_the_year():
    """
    Measured: reading "unchanged in 2026, at 800 euros", the first number is the year, and
    the case was built around 2,026 euros. It must sit between 800 and 5,000.
    """
    source = probes.probes_for(sabine_map(), use_model=False)[0]
    assert source.kind == "source"
    assert 800 < source.case["amount_eur"] < 5000
    assert source.case["amount_eur"] == 2900
    assert source.case["public_threshold"] == 800


def test_money_is_read_beside_its_currency_and_never_from_a_year():
    assert thresholds.money_in("unchanged in 2026, at 800 euros net") == 800
    assert thresholds.money_in("A 2024 rule of 5k EUR") == 5000, "the k is part of the amount"
    assert thresholds.money_in("€1.250,50 from 2024") == 1250.5
    assert thresholds.money_in("The year 2026 only") is None


def test_a_rule_already_decided_is_not_asked_again():
    work_map = sabine_map()
    work_map.rulings.append(ruling("boundary", "capex", {"amount_eur": 5000}, "yes", True))
    assert "boundary" not in [p.kind for p in probes.probes_for(work_map, use_model=False)]


def test_the_reader_asks_what_she_would_do_not_whether_her_rule_applies(monkeypatch):
    """
    Asked "does the rule apply", a model reading "if the law says 800, then yes, three
    thousand is capex" answered no six times out of six, correctly: her rule says five
    thousand. What she would DO is the answer that matters, so that is what is asked.
    """
    seen = {}

    def model(messages, **kwargs):
        seen["system"], seen["user"] = messages[0]["content"], messages[1]["content"]
        return '{"would":"yes"}'

    monkeypatch.setattr(probes, "call_main_model", model)
    source = probes.probes_for(sabine_map(), use_model=False)[0]
    found = probes.rule_on(source, "If the law says 800, then yes, capex.", by="Sabine")

    assert found.applies is True
    assert "would take one action" in seen["system"]
    assert "The action: treat it as capex" in seen["user"]


def test_it_depends_stays_undecided(monkeypatch):
    monkeypatch.setattr(probes, "call_main_model", lambda *a, **k: '{"would":"unclear"}')
    found = probes.rule_on(probes.probes_for(sabine_map(), use_model=False)[1],
                           "Depends on the asset class.", by="Sabine")
    assert found.applies is None, "a person's 'it depends' is not ours to resolve"


def test_the_teach_back_says_only_what_the_map_holds():
    work_map = sabine_map()
    work_map.rulings.append(ruling("boundary", "capex", {"amount_eur": 5000},
                                   "Five thousand and up is capex.", True))
    text = probes.teach_back(work_map)
    assert "And at 5,000, it does apply." in text
    assert '"Five thousand and up is capex."' in text, "her words, not a paraphrase"
    assert text.endswith("Is that how it works?")


# ── precedent: the decided case outranks the rule ────────────────────────────

def test_her_answer_at_the_boundary_settles_every_case_at_the_boundary(monkeypatch):
    monkeypatch.setattr(tutor, "call_main_model", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("a settled question went to the model")))
    capex = sabine_map(conflicted=False).guardrails[0]
    settled = [ruling("boundary", "capex", {"amount_eur": 5000}, "yes, it counts", True)]
    assert tutor.decide(capex, {"amount_eur": 5000}, [])[0] is False, "as written: over, not at"
    assert tutor.decide(capex, {"amount_eur": 5000}, settled)[:2] == (True, True)


def test_one_ruling_against_a_public_source_moves_the_threshold_for_every_case():
    """
    She decided one invoice, 2,900 euros, and said she follows the law. That answer is the
    rule now: 1,500 is capex, 600 is not. She never had to rewrite her rule.
    """
    capex = sabine_map().guardrails[0]
    settled = [ruling("source", "capex", {"amount_eur": 2900, "public_threshold": 800},
                      "If the law says 800, we follow the law.", True)]
    assert tutor.decide(capex, {"amount_eur": 1500}, settled)[0] is True
    assert tutor.decide(capex, {"amount_eur": 600}, settled)[0] is False


def test_a_settled_source_is_said_as_her_decision_and_not_sent_back_to_be_settled(monkeypatch):
    # The supplier rule has no number, so it would go to the model; a unit test does not.
    monkeypatch.setattr(tutor, "call_main_model", lambda *a, **k: '{"applies":"no"}')
    work_map = sabine_map()
    work_map.rulings.append(ruling("source", "capex",
                                   {"amount_eur": 2900, "public_threshold": 800},
                                   "We follow the law.", True))
    [said] = tutor.review(work_map, {"amount_eur": 1500, "supplier_known": True},
                          "book this").interventions
    assert "decided this against a public source" in said.says
    assert "settle it with the controller" not in said.says
    assert "five thousand" not in said.says, "her old number is not repeated as if it held"


def test_two_rules_are_said_in_the_order_she_works(monkeypatch):
    monkeypatch.setattr(tutor, "call_main_model", lambda *a, **k: '{"applies":"yes"}')
    work_map = sabine_map(conflicted=False)
    work_map.rulings.append(ruling("collision", "capex",
                                   {"first": "supplier", "other": "supplier"},
                                   "The supplier check always comes first.", None))
    # The ruling names the pair as capex and supplier.
    work_map.rulings[-1] = Ruling(**{**work_map.rulings[-1].__dict__,
                                     "case": {"first": "supplier", "other": "supplier"}})
    work_map.rulings[-1] = Ruling(**{**work_map.rulings[-1].__dict__,
                                     "guardrail_id": "capex",
                                     "case": {"first": "supplier", "other": "supplier"}})
    order = tutor.review(work_map, {"amount_eur": 7480, "supplier_known": False},
                         "book this").interventions
    assert [i.guardrail.guardrail_id for i in order] == ["supplier", "capex"]


def test_the_map_keeps_learning_after_she_has_gone(monkeypatch):
    """
    The controller clears a supplier the tutor stopped. Same case again: it goes through,
    and the new hire is told who cleared it and why, rather than meeting a guardrail that
    seems to stop things at random.
    """
    monkeypatch.setattr(tutor, "call_main_model", lambda *a, **k: '{"applies":"yes"}')
    work_map = sabine_map(conflicted=False)
    case = {"supplier_known": False, "amount_eur": 1500}
    assert not tutor.review(work_map, case, "book this").allowed

    work_map.rulings.append(ruling("escalation", "supplier", case,
                                   "Novak is our new Czech partner. Fine to book.", False,
                                   by="Controller Weber"))
    again = tutor.review(work_map, case, "book this")
    assert again.allowed
    assert again.cleared[0].by == "Controller Weber"


def test_a_decided_case_is_matched_on_its_facts_not_its_words():
    assert tutor._same_case({"amount_eur": 5000}, {"amount_eur": 5000.0, "supplier": "x"})
    assert not tutor._same_case({"amount_eur": 5000}, {"amount_eur": 5001})
    assert not tutor._same_case({"supplier_known": False}, {"supplier_known": True})
    assert not tutor._same_case({"situation": "a laptop"}, {"situation": "a laptop"}), \
        "descriptions are not facts"


# ── the exam: the edges, set by the person who knows them ────────────────────

def test_the_exam_is_the_cases_she_decided_and_explains_every_mistake_in_her_words():
    work_map = sabine_map()
    work_map.rulings += [
        ruling("boundary", "capex", {"amount_eur": 5000}, "Five thousand counts.", True, rid="a"),
        ruling("near_miss", "capex", {"situation": "s"}, "No, not that one.", False, rid="b"),
        ruling("collision", "capex", {}, "Supplier first.", None, rid="c"),
    ]
    assert [i.ruling_id for i in probes.exam(work_map)] == ["a", "b"], \
        "an order is not a yes-or-no question"

    graded = probes.grade(work_map, {"a": True, "b": True})
    assert (graded.correct, graded.total) == (1, 2)
    [wrong] = [f for f in graded.feedback if not f["right"]]
    assert wrong["because"] == 'Sabine said: "No, not that one."'


# ── the corrections the runs above forced ────────────────────────────────────

def test_every_conditional_rule_is_extracted_not_only_the_ones_that_stop(monkeypatch):
    """
    Defined as "the cases where they stop or escalate", the extractor dropped the capex
    threshold in eight runs out of eight. The prompt now asks for every conditional rule.
    """
    assert "EVERY conditional rule" in absorb.EXTRACT_SYSTEM
    assert 'A classification rule is "check"' in absorb.EXTRACT_SYSTEM


def test_a_clause_starts_lower_case_except_the_word_i():
    assert absorb._clause("Treat it as capex.") == "treat it as capex"
    assert absorb._clause("I do not know") == "I do not know"
    assert absorb._clause("VAT is due") == "VAT is due"


def test_an_empty_search_is_unchecked_and_never_a_house_rule(monkeypatch):
    """
    "House rule" states that no public authority governs this. An empty response from the
    search proves nothing of the kind, and it used to be reported as one.
    """
    monkeypatch.setattr(provenance, "call_main_model", lambda *a, **k:
                        '{"query":"q","local_query":"","public":true}')
    monkeypatch.setattr(provenance, "get_backend", lambda country="de":
                        type("B", (), {"search": lambda self, q, limit=6: []})())
    found = provenance.check(rail(), context="t", country="de")
    assert found.verdict is provenance.Verdict.UNCHECKED


def test_a_rule_with_an_amount_is_always_looked_up(monkeypatch):
    """Judged "no external authority" in one run, contradicted by German law in the next."""
    calls = []
    monkeypatch.setattr(provenance, "call_main_model",
                        lambda *a, **k: '{"query":"","local_query":"","public":false}')
    monkeypatch.setattr(provenance, "get_backend", lambda country="de": type("B", (), {
        "search": lambda self, q, limit=6: calls.append(q) or []})())
    provenance.check(rail(when="equipment is over five thousand euros", then="capex"),
                     context="t", country="de")
    assert calls and "Germany" in calls[0]


def test_both_languages_are_searched_and_the_same_page_is_read_once(monkeypatch):
    searched = []
    monkeypatch.setattr(provenance, "call_main_model", lambda *a, **k:
                        '{"query":"capex threshold Germany",'
                        '"local_query":"Aktivierungsgrenze GWG","public":true}')
    monkeypatch.setattr(provenance, "_judge", lambda rail, s: None)
    monkeypatch.setattr(provenance, "get_backend", lambda country="de": type("B", (), {
        "search": lambda self, q, limit=6: searched.append(q) or [source()]})())
    found = provenance.check(rail(), context="t", country="de")
    assert searched == ["capex threshold Germany", "Aktivierungsgrenze GWG"]
    assert found.verdict is provenance.Verdict.HOUSE_RULE


def test_a_condition_the_question_settled_counts_as_met_and_no_other(monkeypatch):
    """
    "If the law says 800, then yes" was read as unclear twelve times in twelve, though the
    question had just quoted the law saying 800. The reader is told so. A condition the
    question did not settle, "if the auditor signs it off", must still stay unclear.
    """
    assert "A condition the question already settled counts as met" in probes.VERDICT_SYSTEM
    assert "Only a condition the question did not settle" in probes.VERDICT_SYSTEM


def test_the_most_expensive_question_is_asked_first_whatever_order_the_rules_were_learned_in():
    """
    On Sabine's map the order the probes are built in happens to be the right one, so a
    test there cannot tell sorting from luck. Here the rule with a threshold is learned
    first and the contradicted one second: built in that order, the boundary would come
    first. A rule the world contradicts is the most expensive to get wrong, so it leads.
    """
    plain = rail(gid="discount", when="the discount is over ten percent",
                 then="ask the sales director", severity="check")
    contradicted = sabine_map().guardrails[0]
    work_map = WorkMap(organisation="urithi", map_id="m", task="t", expert="e", created_at="now",
                       guardrails=[plain, contradicted])
    kinds = [p.kind for p in probes.probes_for(work_map, use_model=False)]
    assert kinds[0] == "source", kinds
    assert kinds.index("boundary") > kinds.index("source")


def test_an_action_is_an_instruction_because_it_is_read_back_after_you():
    """
    Extracted once as "it is always capex", the action produced "Do you it is always capex,
    or not?" on screen, in the exam a new hire was sitting. Every question and every
    teach-back line puts "you" in front of it, so it has to start with a verb.
    """
    assert "an instruction that starts with a verb" in absorb.EXTRACT_SYSTEM
    for probe_found in probes.probes_for(sabine_map(), use_model=False):
        assert "you it " not in probe_found.question and "Do you it" not in probe_found.question


# ── the exam out loud, for a new hire who cannot see the radio buttons ───────

@pytest.mark.parametrize("said, expected", [
    ("yes", True), ("Yes, it does.", True), ("oui", True), ("Ja, genau.", True),
    ("no", False), ("No, it does not.", False), ("non", False), ("Nein.", False),
    ("it does not apply", False),
    ("yes and no", None), ("I'm not sure", None), ("maybe", None), ("vielleicht", None),
    ("", None), ("the supplier is new", None),
])
def test_a_spoken_exam_answer_is_a_yes_a_no_or_asked_again(said, expected):
    """
    One word decides the grade, so code reads it, not a model. Hesitation, both words, or
    neither, are None: asked again, never graded as wrong.
    """
    from guardian.engine.probe import heard_yes_no

    assert heard_yes_no(said) is expected


def _exam_client(store, monkeypatch):

    from guardian.api import routes
    from server import app

    set_maps(store)
    monkeypatch.setattr(routes, "_voiced", lambda text: {"audio": "AUDIO", "words": []})
    work_map = taught_map()
    work_map.map_id = store.new("t", "e", organisation="urithi").map_id
    work_map.rulings.append(Ruling(
        ruling_id="r-boundary", guardrail_id=work_map.guardrails[0].guardrail_id,
        kind="boundary", case={"amount_eur": 5000}, question="Exactly 5,000. Does it apply?",
        said="At exactly five thousand, yes, it applies.", applies=True, by="Sabine",
        at="2026-10-04T10:00:00+00:00"))
    store.save(work_map)
    client = guardian_client(app)
    return client, work_map


def test_the_exam_answered_aloud_is_graded_in_the_experts_words(store, monkeypatch):
    client, work_map = _exam_client(store, monkeypatch)
    right = client.post("/api/guardian/exam/answer", json={
        "map_id": work_map.map_id, "ruling_id": "r-boundary", "said": "yes"}).json()
    assert right["understood"] and right["right"] is True
    assert right["says"] == "Right. Sabine said: At exactly five thousand, yes, it applies."
    assert right["audio"] == "AUDIO", "heard, not only shown"

    wrong = client.post("/api/guardian/exam/answer", json={
        "map_id": work_map.map_id, "ruling_id": "r-boundary", "said": "no"}).json()
    assert wrong["right"] is False and wrong["says"].startswith("Not quite. Sabine said:")


def test_an_unclear_spoken_answer_is_not_graded(store, monkeypatch):
    client, work_map = _exam_client(store, monkeypatch)
    reply = client.post("/api/guardian/exam/answer", json={
        "map_id": work_map.map_id, "ruling_id": "r-boundary", "said": "hmm, maybe"}).json()
    assert reply["understood"] is False and "right" not in reply
    assert "Say yes, or no" in reply["says"]


def test_a_spoken_answer_is_transcribed_before_it_is_read(store, monkeypatch):
    from guardian.api import routes

    client, work_map = _exam_client(store, monkeypatch)
    heard = []
    monkeypatch.setattr(routes.voice, "transcribe", lambda audio: heard.append(audio) or "Yes.")
    reply = client.post("/api/guardian/exam/answer", json={
        "map_id": work_map.map_id, "ruling_id": "r-boundary", "audio": "UklGRg=="}).json()
    assert heard == [b"RIFF"], "the recording itself went to the transcriber"
    assert reply["heard"] == "Yes." and reply["right"] is True


def test_an_exam_answer_for_a_case_that_is_not_in_the_exam_is_refused(store, monkeypatch):
    client, work_map = _exam_client(store, monkeypatch)
    assert client.post("/api/guardian/exam/answer", json={
        "map_id": work_map.map_id, "ruling_id": "nope", "said": "yes"}).json() \
        == {"error": "No such case in this exam."}


def test_say_reads_a_sentence_and_is_not_a_free_speech_service(store, monkeypatch):
    client, _ = _exam_client(store, monkeypatch)
    assert client.post("/api/guardian/say", json={"text": "The case."}).json() == {"audio": "AUDIO", "words": []}
    assert "error" in client.post("/api/guardian/say", json={"text": "  "}).json()
    assert "Longer than 600" in client.post("/api/guardian/say", json={"text": "x" * 601}).json()["error"]


def test_the_teach_back_route_says_what_the_expert_confirmed(store, monkeypatch):
    from guardian.engine.probe import teach_back

    client, work_map = _exam_client(store, monkeypatch)
    reply = client.get(f"/api/guardian/map/{work_map.map_id}/teach-back?spoken=true").json()
    assert reply["text"] == teach_back(store.load(work_map.map_id)), "built from the map, verbatim"
    assert "At exactly five thousand" in reply["text"]
    assert reply["audio"] == "AUDIO" and reply["expert"] == work_map.expert
    assert client.get(f"/api/guardian/map/{work_map.map_id}/teach-back").json()["audio"] is None


def test_a_company_suffix_does_not_end_a_step_title():
    from guardian.engine.absorb import title_for

    assert title_for("Novak Precision s.r.o. not found", "") == "Novak Precision s.r.o. not found"
    assert title_for("cost center changed. Then the account", "") == "cost center changed"



def test_a_lead_in_is_not_a_step_title():
    """Measured: "One more thing. When a word starts with a u that sounds like you, I write a"
    was taught in a real run, and the step a learner saw was called "One more thing"."""
    from guardian.engine.absorb import title_for

    said = ("One more thing. When a word starts with a u that sounds like you, like university, "
            "I write a.")
    assert title_for(said, "", limit=140).startswith("When a word starts with a u")
    assert title_for("Encore une chose. Quand un mot commence par un h muet, j'écris an.", "",
                     limit=140).startswith("Quand un mot")

def test_the_teach_back_puts_her_reason_inside_its_sentence():
    from guardian.engine.probe import teach_back

    text = teach_back(taught_map())
    assert ", because " in text
    assert not any(line.split(", because ")[1][:1].isupper() and not line.split(", because ")[1].startswith("I ")
                   for line in text.splitlines() if ", because " in line)


def test_a_map_exported_and_imported_is_the_same_map(store, tmp_path):
    from guardian.engine.workmap import WorkMapStore

    work_map = taught_map()
    work_map.map_id = store.new("t", "e", organisation="urithi").map_id
    store.save(work_map)
    other = WorkMapStore(str(tmp_path / "other.sqlite3"))
    copied = other.import_map(store.export(work_map.map_id))
    assert other.export(copied.map_id) == store.export(work_map.map_id)


def test_the_shipped_map_loads_and_is_teachable(tmp_path):
    import json

    from guardian.engine.workmap import WorkMapStore

    shipped = pathlib.Path(__file__).resolve().parents[2] / "deploy/sabine-workmap.json"
    loaded = WorkMapStore(str(tmp_path / "w.sqlite3")).import_map(json.loads(shipped.read_text()))
    assert loaded.is_teachable and loaded.confirmed_at and loaded.rulings


def test_a_deployment_is_seeded_only_when_it_holds_no_map(store, monkeypatch):
    import server

    set_maps(store)
    monkeypatch.setenv("GUARDIAN_SEED_MAP", str(pathlib.Path(__file__).resolve().parents[2]
                                                  / "deploy/sabine-workmap.json"))
    server.seed_an_empty_machine()
    assert len(store.list_maps()) == 1
    server.seed_an_empty_machine()
    assert len(store.list_maps()) == 1, "a store that holds maps is never touched"


def test_frames_observed_at_the_same_time_ask_one_question(store, monkeypatch):
    """
    Measured on a real run: a vision call is slower than the two seconds between frames, so
    two observations ran at once, both found nothing pending, and the same question was
    asked twice, two seconds apart. Deciding to ask is one step under a lock now.
    """
    import threading
    import time

    from guardian.api import routes
    from guardian.engine import questions, vision

    set_maps(store)
    monkeypatch.setattr(routes, "_voiced", lambda text: {"audio": None, "words": []})
    barrier = threading.Barrier(4)

    def slow_vision(frame, session_id, at):
        barrier.wait()                       # all four arrive together, as they did
        return questions.Observation(at=at, changed="cost center changed from 4711 to 0400")

    def wording(kind, observation, task, language="en"):
        time.sleep(0.05)                     # a model call: long enough for a race to show
        return "Why that cost center?"

    monkeypatch.setattr(vision, "what_changed", slow_vision)
    monkeypatch.setattr(questions, "word_question", wording)
    map_id = routes.start(routes.StartBody(task="t", expert="e"), as_guardian("sabine"))["map_id"]
    replies = []
    threads = [threading.Thread(target=lambda at=at: replies.append(routes.observe(
        routes.ObserveBody(map_id=map_id, at=at, frame="x"))))
        for at in (30.0, 30.1, 30.2, 30.3)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sum(1 for r in replies if r.get("question")) == 1


def test_typing_into_a_field_is_one_edit_not_two(store, monkeypatch):
    """Measured: "typed Brenn", then the full name, was asked about as a change of mind."""
    from guardian.api import routes
    from guardian.engine import questions, vision

    set_maps(store)
    monkeypatch.setattr(routes, "_voiced", lambda text: {"audio": None, "words": []})
    seen = iter([questions.Observation(4.0, 'typed "Brenn" into Supplier', "Supplier"),
                 questions.Observation(6.0, "Supplier changed to Brenner GmbH", "Supplier"),
                 questions.Observation(40.0, "Supplier changed to Brenner AG", "Supplier")])
    monkeypatch.setattr(vision, "what_changed", lambda frame, sid, at: next(seen))
    map_id = routes.start(routes.StartBody(task="t", expert="e"), as_guardian("sabine"))["map_id"]
    for at in (4.0, 6.0):
        routes.observe(routes.ObserveBody(map_id=map_id, at=at, frame="x"))
    assert routes._session(map_id)["fields"] == ["Supplier"]
    routes.observe(routes.ObserveBody(map_id=map_id, at=40.0, frame="x"))
    assert routes._session(map_id)["fields"] == ["Supplier", "Supplier"], \
        "changed again after a pause: that one is a second decision"


def test_teaching_by_conversation_turns_each_sentence_into_a_step_and_asks_the_next_gap(store, monkeypatch):
    """No screen: what the guardian says is the step, verbatim, and the ledger picks the follow-up."""
    from guardian.api import routes
    from guardian.engine import absorb, questions

    set_maps(store)
    monkeypatch.setattr(routes, "_voiced", lambda text: {"audio": None, "words": []})
    monkeypatch.setattr(absorb, "find_guardrails", lambda said, at, language="en", known=(): [])
    asked = []
    monkeypatch.setattr(questions, "word_question",
                        lambda kind, seen, task, language="en", **said: asked.append(kind) or "Where does that stop?")
    map_id = routes.start(routes.StartBody(task="Running a tech community", expert="Ezekias"), as_guardian("ezekias"))["map_id"]
    reply = routes.tell(routes.TellBody(map_id=map_id, said="I announce every meetup two weeks ahead."))
    assert reply["proposal"]["reason"] == "I announce every meetup two weeks ahead."
    assert reply["question"] == "Where does that stop?"
    assert asked == [questions.QuestionKind.LIMIT], "a reason is there; where it stops is not"
    routes.save_proposal(routes.SaveBody(map_id=map_id, proposal_id=reply["proposal"]["proposal_id"]))
    assert store.load(map_id).steps[0].title == "I announce every meetup two weeks ahead"
    assert routes.tell(routes.TellBody(map_id=map_id, said="  ")) == {"error": "Nothing was said."}


def test_teaching_more_after_confirming_needs_confirming_again(store, monkeypatch):
    """What was confirmed is no longer the whole of it: nothing new is published unheard."""
    from guardian.api import routes
    from guardian.engine import absorb, questions

    set_maps(store)
    monkeypatch.setattr(routes, "_voiced", lambda text: {"audio": None, "words": []})
    monkeypatch.setattr(absorb, "find_guardrails", lambda said, at, language="en", known=(): [])
    monkeypatch.setattr(questions, "word_question", lambda kind, seen, task, language="en", **said: "Why?")
    map_id = routes.start(routes.StartBody(task="Running a tech community", expert="Ezekias"), as_guardian("ezekias"))["map_id"]
    r1 = routes.tell(routes.TellBody(map_id=map_id, said="I announce every meetup two weeks ahead."))
    routes.save_proposal(routes.SaveBody(map_id=map_id, proposal_id=r1["proposal"]["proposal_id"]))
    routes.get_teach_back(map_id)
    assert routes.confirm(routes.ConfirmBody(map_id=map_id, confirmed=True))["confirmed"]
    r2 = routes.tell(routes.TellBody(map_id=map_id, said="Speakers are never paid, but they eat first."))
    routes.save_proposal(routes.SaveBody(map_id=map_id, proposal_id=r2["proposal"]["proposal_id"]))
    assert store.load(map_id).confirmed_at is None


def test_fewer_than_is_a_threshold_like_less_than():
    """Measured on a first conversation: "fewer than ten registered" got no boundary case."""
    found = thresholds.threshold_in("fewer than ten people have registered three days before")
    assert found == thresholds.Threshold(value=10.0, above=False, inclusive=False)


def test_collisions_are_asked_only_where_a_rule_says_to_stop_and_at_most_two():
    """Every pair of four rules was put to the guardian, including rules that never meet."""
    from guardian.engine import probe

    work_map = WorkMap(organisation="urithi", map_id="m", task="Running a community", expert="Ezekias", created_at="now")
    work_map.guardrails += [rail(gid=f"c{i}", when=f"case {i}", severity="check") for i in range(4)]
    assert not [p for p in probe.probes_for(work_map, use_model=False) if p.kind == "collision"]
    work_map.guardrails += [rail(gid="s1", when="a report involves an organiser", severity="stop")]
    collisions = [p for p in probe.probes_for(work_map, use_model=False) if p.kind == "collision"]
    assert len(collisions) == 2 and all("s1" in (p.guardrail_id, p.other_guardrail_id) for p in collisions)
    assert all("invoice" not in p.question for p in collisions), "the domain is not invoices any more"


def test_a_step_taught_in_conversation_is_said_once_in_the_teach_back():
    from guardian.engine.probe import teach_back

    work_map = WorkMap(organisation="urithi", map_id="m", task="Running a community", expert="Ezekias", created_at="now")
    said = "I announce every meetup two weeks ahead on the public channel, because people plan."
    work_map.steps.append(Step(step_id="s1", number=1, title=said[:60] + "...", screen_moment=1.0,
                               observed="o", decision="d", reason=said))
    line = teach_back(work_map).splitlines()[1]
    assert line == f"Step 1: {said.rstrip('.')}."
    assert line.count("announce every meetup") == 1


@pytest.mark.parametrize("asked, kept", [
    ("Should I still tie this credit note to an invoice, or is this the exception?", False),
    ("Faut-il le rattacher à une facture, ou est-ce l'exception ?", False),
    ("Do I still check with the controller before booking it?", True),
    ("Does the rule for numbers apply to Roman numerals like this?", False),
])
def test_a_near_miss_is_a_yes_or_no_question(monkeypatch, asked, kept):
    """Measured: a learner was asked "A, or B?" in the exam and could only say yes or no."""
    monkeypatch.setattr(probes, "call_main_model", lambda *a, **k: f'{{"case": "A case.", "question": "{asked}"}}')
    rail = Guardrail(guardrail_id="g", when="a credit note arrives", then="book it against the invoice",
                     quote="q", asked_at=1.0)
    assert (probes._near_miss(rail) is not None) is kept



def test_a_near_miss_is_asked_with_little_thinking_so_the_case_is_not_cut(monkeypatch):
    """Measured: left to think freely, the model spent 1,919 of 2,000 tokens thinking and the
    case came back cut, three times in three for one rule; thinking low, three in three."""
    asked = {}

    def model(messages, **options):
        asked.update(options)
        return '{"case": "A case.", "question": "Do I still check with the controller?"}'

    monkeypatch.setattr(probes, "call_main_model", model)
    rail = Guardrail(guardrail_id="g", when="a credit note arrives", then="book it against the invoice",
                     quote="q", asked_at=1.0)
    assert probes._near_miss(rail) is not None
    assert asked.get("thinking") == "low"

# ── search services that refuse ──────────────────────────────────────────────

class _Reply:
    def __init__(self, data):
        self.data = data
        self.text = __import__("json").dumps(data)

    def raise_for_status(self):
        pass

    def json(self):
        return self.data


def test_a_refused_search_is_said_as_refused_without_the_machines_address(monkeypatch):
    """Measured: an allow-list refusal read as "the search returned no results", rule after rule."""
    import httpx

    from guardian.engine import sources

    sent = []
    refusal = {"status_code": 407, "headers": {"proxy-status": 'brd.superproxy.io; error="http_request_denied"; '
               'details="client_10030: The IP address from which you are sending this request: 203.0.113.7 '
               'is not whitelisted in this zone\'s settings."'}, "body": ""}
    monkeypatch.setattr(httpx, "post", lambda url, **k: sent.append(k["json"]) or _Reply(refusal))
    monkeypatch.setenv(sources.BRIGHTDATA_TOKEN_ENV, "t")
    with pytest.raises(sources.SourceRefused) as refused:
        sources.BrightDataBackend().search("a or an")
    assert "407" in str(refused.value) and "not whitelisted" in str(refused.value)
    assert "203.0.113.7" not in str(refused.value), "the machine's address is not repeated"
    assert "country" not in sent[0], "no jurisdiction asked for: an empty one is a 400"


def test_a_refusing_service_hands_over_to_the_next(monkeypatch):
    from guardian.engine import sources

    class Refuses:
        name = "brightdata"

        def search(self, query, limit=4):
            raise sources.SourceRefused("not on the allow-list")

    class Answers:
        name = "tavily"

        def search(self, query, limit=4):
            return [sources.Source(url="https://dictionary.example/a-an", title="a or an", text="t",
                                   backend="tavily", retrieved_at="today")]

    both = sources.FallbackBackend([Refuses(), Answers()])
    assert both.search("a or an")[0].backend == "tavily" and both.name == "tavily"
    with pytest.raises(sources.SourceRefused, match="allow-list"):
        sources.FallbackBackend([Refuses()]).search("a or an")
    monkeypatch.setenv(sources.BRIGHTDATA_TOKEN_ENV, "t")
    monkeypatch.setenv(sources.TAVILY_TOKEN_ENV, "t")
    assert isinstance(sources.get_backend(), sources.FallbackBackend)


def test_knowledge_with_no_jurisdiction_keeps_every_source():
    assert provenance._applies_here("us", "") and provenance._applies_here("gb", "")
    assert not provenance._applies_here("us", "de"), "a country's rule still sets aside another's"


# ── the guardian takes back an answer, or a rule ─────────────────────────────

def _aan_map(store):
    from guardian.engine.workmap import Ruling

    vowel = Guardrail(guardrail_id="vowel", when="the next word starts with a vowel sound", then="write an",
                      quote="When the next word starts with a vowel sound, I write an.", asked_at=1.0)
    unsure = Guardrail(guardrail_id="unsure", when="you are not sure how a word is pronounced",
                       then="stop and check a dictionary", quote="If unsure, I check.", asked_at=2.0)
    work_map = WorkMap(organisation="urithi", map_id="aan", task="Choosing a or an", expert="Ezekias", created_at="now",
                       guardrails=[vowel, unsure], confirmed_at="then",
                       steps=[Step(step_id="s1", number=1, title="t", screen_moment=1.0, observed="o",
                                   decision="d", reason="r", guardrail_ids=("vowel", "unsure"))],
                       rulings=[Ruling(ruling_id="wrong", guardrail_id="vowel", kind="near_miss",
                                       case={"situation": "unique solution"},
                                       question="Does the rule to use 'an' apply to 'unique solution'?",
                                       said="Yes.", applies=True, by="Ezekias", at="now"),
                                Ruling(ruling_id="order", guardrail_id="unsure", kind="collision",
                                       case={"both_true": ["x", "y"], "first": "unsure", "other": "vowel"},
                                       question="Which first?", said="Check first.", applies=None,
                                       by="Ezekias", at="now")])
    store.save(work_map)
    return work_map


def test_a_case_answered_again_replaces_the_earlier_answer_only_once_answered(store, monkeypatch):
    """Measured: "an unique solution", answered yes in a hurry, would have reached every exam."""
    from guardian.api import routes

    set_maps(store)
    monkeypatch.setattr(routes, "_voiced", lambda text: {"audio": None, "words": []})
    _aan_map(store)
    asked = routes.reask(routes.ReaskBody(map_id="aan", ruling_id="wrong"))["probe"]
    assert asked["question"] == "Does the rule to use 'an' apply to 'unique solution'?"
    assert store.load("aan").confirmed_at is None, "heard back again before it is published"
    assert [r.ruling_id for r in store.load("aan").rulings] == ["wrong", "order"], "kept until answered"
    monkeypatch.setattr(probes, "call_main_model", lambda *a, **k: '{"would": "no"}')
    done = routes.rule(routes.RuleBody(map_id="aan", probe_id=asked["probe_id"],
                                       said="No, unique starts with a y sound: a unique solution."))
    saved = routes.save_proposal(routes.SaveBody(map_id="aan", proposal_id=done["proposal"]["proposal_id"]))
    rulings = store.load("aan").rulings
    assert [r.kind for r in rulings] == ["collision", "near_miss"] and rulings[1].applies is False
    assert "a unique solution" in saved["teach_back"] and "Does the rule to use 'an' apply" in saved["teach_back"]
    assert routes.reask(routes.ReaskBody(map_id="aan", ruling_id="nope")) == {"error": "No such answer."}


def test_a_rule_the_guardian_did_not_give_is_taken_out_with_what_tested_it(store, monkeypatch):
    from guardian.api import routes

    set_maps(store)
    _aan_map(store)
    assert routes.forget_rule(routes.ForgetRuleBody(map_id="aan", guardrail_id="vowel"))["removed"]
    work_map = store.load("aan")
    assert [g.guardrail_id for g in work_map.guardrails] == ["unsure"]
    assert work_map.rulings == [], "its own case, and the collision that named it, go too"
    assert work_map.steps[0].guardrail_ids == ("unsure",) and work_map.steps[0].reason == "r"
    assert work_map.confirmed_at is None
    assert routes.forget_rule(routes.ForgetRuleBody(map_id="aan", guardrail_id="vowel")) == {"error": "No such rule."}


def test_a_post_on_a_social_network_is_not_a_source(monkeypatch):
    """Measured: one garbled post made a textbook grammar rule "conflicted" against four references."""
    from guardian.engine.sources import Source

    pages = [Source(url="https://www.facebook.com/post/1", title="t", text="vowel sound (b, c, d)", backend="tavily",
                    retrieved_at="today"),
             Source(url="https://www.quillbot.com/a-an", title="t", text="an before a vowel sound", backend="tavily",
                    retrieved_at="today")]
    monkeypatch.setattr(provenance, "_query_for", lambda rail, context, country="": (["a or an"], True))
    monkeypatch.setattr(provenance, "get_backend", lambda country="": type("B", (), {
        "search": lambda self, q, limit=6: pages})())
    judged = []
    monkeypatch.setattr(provenance, "_judge", lambda rail, source: judged.append(source.domain) or provenance.Citation(
        url=source.url, title="t", domain=source.domain, says="an before a vowel sound", agrees=True))
    rail = Guardrail(guardrail_id="v", when="the next word starts with a vowel sound", then="write an",
                     quote="q", asked_at=1.0)
    found = provenance.check(rail)
    assert judged == ["quillbot.com"] and found.verdict == provenance.Verdict.CORROBORATED



def test_the_extractor_is_told_the_rules_already_noted(monkeypatch):
    """Measured: rules nobody stated, then the same rules again: nine rules for seven."""
    prompts = []
    monkeypatch.setattr(absorb, "call_extraction_model",
                        lambda messages, **k: prompts.append(messages[1]["content"]) or '{"guardrails": []}')
    known = [Guardrail(guardrail_id="v", when="the next word starts with a vowel sound", then="write an",
                       quote="q", asked_at=1.0)]
    absorb.find_guardrails("When it starts with a consonant sound, I write a.", 2.0, known=known)
    assert "Rules already noted" in prompts[0] and "when the next word starts with a vowel sound, write an" in prompts[0]
    absorb.find_guardrails("Anything.", 3.0)
    assert prompts[1] == "Anything.", "nothing noted, nothing added"
    assert "is not a rule either" in absorb.EXTRACT_SYSTEM


def test_a_title_is_cut_at_a_word_never_inside_one():
    """Measured: "...I stop and chec..." was the headline a learner read."""
    said = "When I am not sure how a word is pronounced, I stop and check its pronunciation in a dictionary first"
    short = absorb.title_for(said, "")
    assert short.endswith("...") and short[:-3] in said and said[len(short) - 3] == " "
    assert absorb.title_for(said, "", limit=140) == said, "a conversation step keeps its whole sentence"



def test_without_an_unlocker_zone_a_page_is_fetched_plainly_then_left_as_its_snippet(monkeypatch):
    """Measured: an Unlocker zone that did not exist made every page a 400, leaving a snippet."""
    import json

    import httpx

    from guardian.engine import sources

    monkeypatch.setenv(sources.BRIGHTDATA_TOKEN_ENV, "t")
    monkeypatch.delenv(sources.BRIGHTDATA_UNLOCKER_ZONE_ENV, raising=False)
    serp = {"status_code": 200, "body": json.dumps({"organic": [
        {"link": "https://owl.example.edu/a-an", "title": "A versus an", "description": "snippet one"},
        {"link": "https://closed.example.com/a-an", "title": "Closed", "description": "snippet two"}]})}
    zones = []
    monkeypatch.setattr(httpx, "post", lambda url, **k: zones.append(k["json"]["zone"]) or _Reply(serp))

    class Page:
        def __init__(self, ok):
            self.status_code, self.headers = (200 if ok else 403), {"content-type": "text/html"}
            self.text = "<html><body><p>Use an before a vowel sound.</p></body></html>"

    monkeypatch.setattr(httpx, "get", lambda url, **k: Page("owl" in url))
    found = sources.BrightDataBackend().search("a or an")
    assert len(zones) == 1, "the search only: no request to an Unlocker zone that is not set up"
    assert "Use an before a vowel sound." in found[0].text
    assert found[1].text == "snippet two"



def test_a_failure_on_the_far_side_is_tried_once_more_and_a_refusal_is_not(monkeypatch):
    import httpx

    from guardian.engine import sources

    monkeypatch.setenv(sources.BRIGHTDATA_TOKEN_ENV, "t")
    replies = [{"status_code": 502, "headers": {}, "body": ""},
               {"status_code": 200, "body": '{"organic": [{"link": "https://a.example/x", "description": "s"}]}'}]
    calls = []
    monkeypatch.setattr(httpx, "post", lambda url, **k: calls.append(1) or _Reply(replies.pop(0)))
    monkeypatch.setattr(sources, "_plain_fetch", lambda url: "")
    assert sources.BrightDataBackend().search("a or an")[0].text == "s" and len(calls) == 2
    calls.clear()
    monkeypatch.setattr(httpx, "post", lambda url, **k: calls.append(1) or _Reply({"status_code": 407, "headers": {}}))
    with pytest.raises(sources.SourceRefused):
        sources.BrightDataBackend().search("a or an")
    assert len(calls) == 1, "an allow-list refusal is not asked again"



def test_a_cut_snippet_may_agree_but_never_contradicts(monkeypatch):
    """Measured: a snippet ending "...begins with a ..." made Merriam-Webster disagree."""
    from guardian.engine.sources import Source

    pages = [Source(url="https://www.merriam-webster.com/grammar/a-or-an", title="t", text="begins with a ...",
                    backend="brightdata", retrieved_at="today", snippet_only=True),
             Source(url="https://owl.purdue.edu/a-an", title="t", text="full page", backend="brightdata",
                    retrieved_at="today")]
    monkeypatch.setattr(provenance, "_query_for", lambda rail, context, country="": (["a or an"], True))
    monkeypatch.setattr(provenance, "get_backend", lambda country="": type("B", (), {
        "search": lambda self, q, limit=6: pages})())
    monkeypatch.setattr(provenance, "_judge", lambda rail, source: provenance.Citation(
        url=source.url, title="t", domain=source.domain, says="x", agrees="owl" in source.url,
        snippet_only=source.snippet_only))
    rail = Guardrail(guardrail_id="v", when="the next word starts with a vowel sound", then="write an",
                     quote="q", asked_at=1.0)
    found = provenance.check(rail)
    assert found.verdict == provenance.Verdict.CORROBORATED
    assert [c.domain for c in found.citations] == ["owl.purdue.edu"], "the cut snippet is set aside"


# ── a guardian's routes, for that guardian ───────────────────────────────────

def test_a_draft_is_its_guardians_alone(store, monkeypatch):
    """Measured in the step 0 review: no guardian route asked who was there; a learner could
    read any draft and confirm it, which is what opens publishing."""
    from fastapi.testclient import TestClient

    from server import app

    set_maps(store)
    work_map = taught_map()
    store.save(work_map)
    client = TestClient(app)
    for person in (None, "visitor", "ezekias"):
        params = {"person_id": person} if person else {}
        assert client.get(f"/api/guardian/map/{work_map.map_id}", params=params).status_code == 403, person
        confirm = client.post("/api/guardian/confirm", params=params, json={"map_id": work_map.map_id, "confirmed": True})
        assert confirm.status_code == 403, person
    assert store.load(work_map.map_id).confirmed_at is None
    assert client.get(f"/api/guardian/map/{work_map.map_id}", params={"person_id": "sabine"}).status_code == 200


def test_who_teaches_is_who_asks_not_a_name_sent(store, monkeypatch):
    from guardian.api import routes

    set_maps(store)
    started = routes.start(routes.StartBody(task="t", expert="Sabine"), as_guardian("ezekias"))
    assert started["expert"] == "Ezekias"


def test_a_gap_the_guardian_answered_is_not_asked_again(store, monkeypatch):
    """Measured in a real class: "At what member count does that rule stop applying?" was
    answered "the size does not matter", and came back as "At what threshold does a community
    become too important?". Once asked, where a rule stops is not asked again."""
    from guardian.api import routes
    from guardian.engine import absorb, questions

    set_maps(store)
    monkeypatch.setattr(routes, "_voiced", lambda text: {"audio": None, "words": []})
    monkeypatch.setattr(absorb, "find_guardrails", lambda said, at, language="en", known=(): [])
    asked = []
    monkeypatch.setattr(questions, "word_question",
                        lambda kind, seen, task, language="en", **said: asked.append(kind) or "Asked?")
    map_id = routes.start(routes.StartBody(task="Organising a community event", expert="Ezekias"),
                          as_guardian("ezekias"))["map_id"]
    for said in ("I will show how an organiser creates an event.",
                 "It applies to any organiser, the size does not matter.",
                 "What matters is the structure we follow."):
        routes.tell(routes.TellBody(map_id=map_id, said=said))
    assert asked == [questions.QuestionKind.LIMIT, questions.QuestionKind.ESCALATION], \
        "each gap once; then Urithi listens"


def test_what_was_said_is_worded_as_said_never_as_a_change_on_screen(monkeypatch):
    """Measured in a real class: the guardian's introduction reached the model as a change on
    screen, and the question asked for a member count nobody had mentioned."""
    from guardian.engine import questions

    sent = []
    monkeypatch.setattr(questions, "call_main_model",
                        lambda messages, **k: sent.append(messages) or "What do you do first, and why?")
    heard = questions.Observation(at=3.0, changed="I will show how an organiser creates an event.")
    questions.word_question(questions.QuestionKind.LIMIT, heard, "Organising an event", said=True)
    questions.word_question(questions.QuestionKind.LIMIT, heard, "Organising an event")
    spoken, watched = sent
    assert "What they just said: I will show" in spoken[1]["content"]
    assert "never bring in a number" in spoken[0]["content"] and "what they do first" in spoken[0]["content"]
    assert "What just changed on screen" in watched[1]["content"] and "never bring in" not in watched[0]["content"]


def test_the_question_a_guardian_waits_on_has_its_own_model(monkeypatch):
    """Measured on the owner's words from a real class: 6 to 16 s a question with the main
    model. The question is worded by its own setting, the main model unless one is chosen."""
    from apu import config
    from guardian.engine import questions

    used = []
    monkeypatch.setattr(questions, "call_main_model", lambda messages, **k: used.append(k.get("model")) or "Why?")
    monkeypatch.setattr(config, "QUESTION_MODEL", "a-faster-model")
    questions.word_question(questions.QuestionKind.REASON, questions.Observation(at=1, changed="x"), "t")
    assert used == ["a-faster-model"]



def test_a_question_names_no_value_it_was_not_given(monkeypatch):
    """Measured in a live run: "Date and Announce in fields were filled" was asked as "Why July
    fourteenth for the date there?". The wording model is told to name only values it is given."""
    from guardian.engine import questions

    sent = []
    monkeypatch.setattr(questions, "call_main_model", lambda messages, **k: sent.append(messages) or "Why that date?")
    questions.word_question(questions.QuestionKind.REASON,
                            questions.Observation(at=6.0, changed="Date and Announce in fields were filled"), "t")
    assert "Name only values written in what you are given" in sent[0][0]["content"]


def test_a_rule_keeps_what_the_guardian_forbids_even_when_the_extractor_drops_it(monkeypatch):
    """Measured live: "we announce in #members only, never in #announcements" was saved as
    "announce in #members only": the prohibition, the half a new hire most needs, was gone."""
    said = "If the venue holds fewer than 40 seats, we announce in #members only, never in #announcements."
    monkeypatch.setattr(absorb, "call_extraction_model", lambda *a, **k: (
        '{"guardrails":[{"when":"the venue holds fewer than 40 seats",'
        '"then":"announce in #members only","severity":"check"}]}'))
    [rule] = absorb.find_guardrails(said, at=3.0)
    assert rule.when == "the venue holds fewer than 40 seats"
    assert "never in #announcements" in rule.then and "#members only" in rule.then
    monkeypatch.setattr(absorb, "call_extraction_model", lambda *a, **k: (
        '{"guardrails":[{"when":"the venue holds fewer than 40 seats",'
        '"then":"announce in #members only and never in #announcements","severity":"check"}]}'))
    [rule] = absorb.find_guardrails(said, at=3.0)
    assert rule.then == "announce in #members only and never in #announcements", "a whole reading is kept as read"
