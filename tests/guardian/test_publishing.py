"""
Publishing: from a guardian's confirmed Work Map to the library, and the guardian's routes.

Target: guardian/publish.py, guardian/api/library_routes.py

What is published is the guardian's words, field for field, at the levels the guardian chose;
only the map's own guardian publishes or withdraws it.
"""



import pytest

from guardian.memory.store import set_maps
from fastapi.testclient import TestClient

import guardian.publish as fw
from apu import embeddings as embedder
from guardian.engine.workmap import Guardrail, Ruling, Step, WorkMap
from guardian.publish import body_id_for, publication_from
from library import access, store
from library.model import (
    KnowledgeError,
)
from tests.support import DIM, WordEmbedder  # noqa: F401


@pytest.fixture(autouse=True)
def words(monkeypatch):
    embedder.set_embedder(WordEmbedder())
    yield
    embedder.set_embedder(None)



def confirmed_map() -> WorkMap:
    work_map = WorkMap(organisation="urithi", map_id="m1", task="Code a supplier invoice", expert="Sabine", created_at="now",
                       confirmed_at="2026-10-05T08:00:00+00:00")
    work_map.guardrails += [
        Guardrail(guardrail_id="stop1", when="the supplier is not recognised",
                  then="stop and ask the controller", quote="If I do not recognise the supplier, I stop.",
                  asked_at=74.0, severity="stop"),
        Guardrail(guardrail_id="check1", when="equipment is over five thousand euros",
                  then="treat it as capex", quote="Equipment over five thousand euros is always capex.",
                  asked_at=192.0, severity="check",
                  provenance={"verdict": "conflicted", "citations": [
                      {"url": "https://norman.finance", "domain": "norman.finance",
                       "says": "above EUR 800 must be capitalized", "agrees": False, "jurisdiction": "DE"}]}),
    ]
    work_map.steps += [
        Step(step_id="s1", number=1, title="Look the supplier up", screen_moment=74.0, observed="o1",
             decision="d1", reason="Every supplier we pay is in the vendor master.", guardrail_ids=("stop1",)),
        Step(step_id="s2", number=2, title="Code to a cost center", screen_moment=192.0, observed="o2",
             decision="d2", reason="Equipment over five thousand euros is always capex.",
             guardrail_ids=("check1",)),
    ]
    work_map.rulings += [
        Ruling(ruling_id="r1", guardrail_id="check1", kind="boundary", case={"amount_eur": 5000},
               question="Exactly 5,000?", said="Exactly five thousand counts.", applies=True,
               by="Sabine", at="t"),
        Ruling(ruling_id="r2", guardrail_id="stop1", kind="collision",
               case={"first": "stop1", "other": "check1"}, question="Both at once?",
               said="The supplier first, always.", applies=None, by="Sabine", at="t"),
        Ruling(ruling_id="r3", guardrail_id="", kind="correction", case={}, question="Right?",
               said="Yes.", applies=None, by="Sabine", at="t"),
    ]
    return work_map


# ── from a Work Map to the library ───────────────────────────────────────────

def test_only_a_validated_map_is_published():
    work_map = confirmed_map()
    work_map.confirmed_at = None
    with pytest.raises(KnowledgeError, match="not validated"):
        publication_from(work_map, version=1)


# ── the three states: draft, validated, published (docs/decisions/0002) ─────

def test_a_part_taught_after_validation_is_a_draft_and_is_not_published():
    """Validating keeps the version heard back; what is taught after it waits, unpublished."""
    from guardian.engine.workmap import Step

    work_map = confirmed_map()
    work_map.validated = work_map.snapshot()
    work_map.steps.append(Step(step_id="s3", number=3, title="A new step", screen_moment=300.0, observed="o",
                               decision="d", reason="Said after the teach-back.", guardrail_ids=()))
    work_map.confirmed_at = None                     # as /tell leaves it
    states = work_map.states()
    assert states["step:s3"] == "draft" and states["step:s1"] == "validated"
    published = publication_from(work_map, version=2)
    assert "A new step" not in {u.text for u in published.units}, "a draft is never published"
    assert len([u for u in published.units if u.kind == "step"]) == 2


def test_a_part_changed_after_validation_is_a_draft_again():
    work_map = confirmed_map()
    work_map.validated = work_map.snapshot()
    rail = work_map.guardrails[0]
    work_map.guardrails[0] = type(rail)(**{**{f: getattr(rail, f) for f in rail.__dataclass_fields__},
                                            "then": "call the controller instead"})
    assert work_map.states()[f"rule:{rail.guardrail_id}"] == "draft"
    published = publication_from(work_map, version=2)
    assert any("stop and ask the controller" in u.text for u in published.units), "the validated wording is published"


def test_the_learners_path_follows_the_contents_the_guardian_set():
    """Step 2 of the plan: the guardian orders the knowledge and groups it into sections."""
    work_map = confirmed_map()
    work_map.order = ["s2", "s1"]
    work_map.sections = [{"title": "Coding it", "steps": ["s2"]}, {"title": "Checking it", "steps": ["s1"]}]
    work_map.validated = work_map.snapshot()
    published = publication_from(work_map, version=1)
    steps = [u for u in published.units if u.kind == "step"]
    assert [u.unit_id.split(":")[1] for u in steps] == ["step-2", "step-1"], "the order set, the ids unchanged"
    assert [u.section for u in steps] == ["Coding it", "Checking it"]
    first, second = steps[0].unit_id, steps[1].unit_id
    assert any(link.source_id == first and link.target_id == second and link.type == "PREREQUISITE_OF"
               for link in published.links)


def test_what_is_published_is_the_guardians_words_field_for_field():
    pub = publication_from(confirmed_map(), version=1)
    units = {u.unit_id.split(":")[1]: u for u in pub.units}
    assert units["step-1"].quote == "Every supplier we pay is in the vendor master."
    assert units["rule-check1"].text == "When equipment is over five thousand euros, treat it as capex."
    assert units["rule-check1"].quote == "Equipment over five thousand euros is always capex."
    assert units["rule-stop1"].kind == "caution" and units["rule-check1"].kind == "limit"
    assert units["rule-check1"].at == 192.0


def test_a_procedure_is_learned_in_order_and_a_limit_after_what_it_limits():
    pub = publication_from(confirmed_map(), version=1)
    links = {(link.source_id.split(":")[1], link.target_id.split(":")[1], link.type) for link in pub.links}
    assert ("step-1", "step-2", "PREREQUISITE_OF") in links
    assert ("step-2", "rule-check1", "PREREQUISITE_OF") in links
    assert ("rule-check1", "step-2", "LIMITS") in links
    assert ("rule-stop1", "rule-check1", "MEETS") in links, "two rules that met in the debrief"


def test_rulings_become_cases_and_a_correction_does_not():
    pub = publication_from(confirmed_map(), version=1)
    kinds = sorted(c.kind for c in pub.cases)
    assert kinds == ["boundary", "collision"]
    collision = next(c for c in pub.cases if c.kind == "collision")
    assert len(collision.decides) == 2, "a collision decides both rules"


def test_a_case_is_never_more_open_than_the_units_it_decides():
    body = body_id_for(confirmed_map())
    pub = publication_from(confirmed_map(), version=1, access={f"{body}:rule-check1": "restricted"})
    for case in pub.cases:
        assert case.access == "restricted", case.kind


def test_restricting_a_rule_restricts_its_words_wherever_else_they_were_said():
    """
    Measured live: the caution was set to "community", and a public visitor still read it,
    word for word, in the reason of the step it was said with.
    """
    work_map = confirmed_map()
    work_map.steps[0] = Step(step_id="s1", number=1, title="Look the supplier up", screen_moment=74.0,
                             observed="o1", decision="d1", guardrail_ids=("stop1",),
                             reason="I look it up first. If I do not recognise the supplier, I stop.")
    body = body_id_for(work_map)
    pub = publication_from(work_map, version=1, access={f"{body}:rule-stop1": "community"})
    units = {u.unit_id.split(":")[1]: u for u in pub.units}
    assert units["rule-stop1"].access == "community"
    assert units["step-1"].access == "community", "its reason holds the restricted sentence"
    assert units["step-2"].access == "public", "a step that does not repeat it stays open"


def test_a_source_that_disagrees_is_kept_as_disagreeing():
    pub = publication_from(confirmed_map(), version=1)
    assert [(s.domain, s.relation, s.jurisdiction) for s in pub.sources] == [("norman.finance", "DISAGREES", "DE")]


def test_a_misspelt_unit_in_the_access_levels_is_refused_not_published_as_public():
    with pytest.raises(KnowledgeError, match="No such unit"):
        publication_from(confirmed_map(), version=1, access={"sabine--code:rule-x": "restricted"})


def test_an_unknown_access_level_is_refused_not_guessed():
    with pytest.raises(KnowledgeError):
        publication_from(confirmed_map(), version=1, default_access="family")


@pytest.fixture
def client(monkeypatch, tmp_path):
    from guardian.engine.workmap import WorkMapStore
    from server import app

    maps = WorkMapStore(str(tmp_path / "w.sqlite3"))
    maps.save(confirmed_map())
    set_maps(maps)
    store.set_store(store.MemoryKnowledgeStore())
    yield TestClient(app)
    store.set_store(None)


def test_only_the_maps_own_guardian_publishes_it(client):
    assert client.post("/api/guardian/publish", json={"map_id": "m1", "person_id": "visitor"}).status_code == 403
    assert client.post("/api/guardian/publish", json={"map_id": "m1", "person_id": "ezekias"}).status_code == 403
    assert client.post("/api/guardian/publish", json={"map_id": "m1", "person_id": "mallory"}).status_code == 403
    first = client.post("/api/guardian/publish", json={"map_id": "m1", "person_id": "sabine"}).json()
    assert first["version"] == 1 and first["units"] == 4 and first["simulated"] is True
    again = client.post("/api/guardian/publish", json={"map_id": "m1", "person_id": "sabine"}).json()
    assert again["version"] == 2, "teaching it again is a new version"


def test_a_learner_reads_what_their_level_allows_and_is_told_it_is_simulated(client):
    body = body_id_for(confirmed_map())
    client.post("/api/guardian/publish", json={
        "map_id": "m1", "person_id": "sabine",
        "access": {f"{body}:rule-stop1": "community"}})
    visitor = client.get("/api/learner/search", params={"q": "supplier not recognised", "person_id": "visitor"}).json()
    member = client.get("/api/learner/search", params={"q": "supplier not recognised", "person_id": "member"}).json()
    assert visitor["simulated"] is True and visitor["access"] == "public"
    assert not any(r["unit"]["unit_id"].endswith("rule-stop1") for r in visitor["results"])
    assert any(r["unit"]["unit_id"].endswith("rule-stop1") for r in member["results"])
    assert client.get("/api/learner/search", params={"q": "x", "person_id": "mallory"}).status_code == 403


def test_only_its_guardian_withdraws_a_body(client):
    client.post("/api/guardian/publish", json={"map_id": "m1", "person_id": "sabine"})
    body = body_id_for(confirmed_map())
    assert client.delete(f"/api/guardian/body/{body}", params={"person_id": "ezekias"}).status_code == 403
    assert client.delete(f"/api/guardian/body/{body}", params={"person_id": "sabine"}).json()["withdrawn"]
    assert client.get("/api/guardian/bodies", params={"person_id": "sabine"}).json()["bodies"] == []


def test_a_learner_is_not_a_guardian_even_with_the_same_name(tmp_path, monkeypatch):
    """The role is checked on its own: a name is not a role."""
    import json

    from library import config

    registry = tmp_path / "people.json"
    registry.write_text(json.dumps({
        "organisations": [{"organisation": "urithi", "name": "Urithi"}],
        "people": [{"person_id": "sabine-learner", "name": "Sabine"}],
        "memberships": [{"person_id": "sabine-learner", "organisation": "urithi", "role": "learner",
                         "access": "public"}]}))
    monkeypatch.setattr(config, "PEOPLE_PATH", str(registry))
    with pytest.raises(PermissionError, match="not a guardian"):
        access.require_guardian("sabine-learner", "Sabine")


def test_the_preview_shows_the_level_each_unit_will_really_get_and_writes_nothing(client):
    body = body_id_for(confirmed_map())
    reply = client.post("/api/guardian/preview", json={
        "map_id": "m1", "person_id": "sabine", "access": {f"{body}:rule-stop1": "community"}}).json()
    units = {u["unit_id"].split(":")[1]: u for u in reply["units"]}
    assert units["rule-stop1"]["access"] == "community" and not units["rule-stop1"]["raised"]
    assert units["step-1"]["access"] == "public", "its reason does not repeat the caution's words"
    assert client.get("/api/guardian/bodies", params={"person_id": "sabine"}).json()["bodies"] == []
    assert client.post("/api/guardian/preview", json={"map_id": "m1", "person_id": "ezekias"}).status_code == 403


def test_a_case_that_names_what_was_kept_closed_is_raised_with_it():
    """Measured: "does 'a' apply before an abbreviation like MBA?" reached a visitor with its answer."""
    work_map = confirmed_map()
    body = body_id_for(work_map)
    work_map.rulings.append(Ruling(ruling_id="names", guardrail_id="check1", kind="near_miss",
                                   case={"situation": "x"}, question="Is a laptop checked with the controller first?",
                                   said="No.", applies=False, by="Sabine", at="now"))
    work_map.rulings.append(Ruling(ruling_id="plain", guardrail_id="check1", kind="near_miss",
                                   case={"situation": "y"}, question="Does it apply to a printer?",
                                   said="Yes.", applies=True, by="Sabine", at="now"))
    publication = publication_from(work_map, version=1, access={f"{body}:rule-stop1": "community"})
    cases = {c.case_id.split(":")[1]: c.access for c in publication.cases}
    assert cases["case-names"] == "community", "'controller' is said only in the closed rule"
    assert cases["case-plain"] == "public"
    assert "read" not in fw._words("When it is read as a word, like NASA") and "nasa" in fw._words("like NASA")
    open_publication = publication_from(work_map, version=1)
    assert {c.access for c in open_publication.cases} == {"public"}, "nothing closed, nothing raised"


def test_a_guardian_sees_one_map_per_body_the_latest_and_what_is_published(client):
    from guardian.memory.store import get_maps

    older = WorkMap(organisation="urithi", map_id="m0", task="Code a supplier invoice", expert="Sabine", created_at="before")
    get_maps().save(older)
    get_maps().save(WorkMap(organisation="urithi", map_id="e1", task="Something else", expert="Ezekias", created_at="now"))
    client.post("/api/guardian/publish", json={"map_id": "m1", "person_id": "sabine"})
    reply = client.get("/api/guardian/knowledge", params={"person_id": "sabine"}).json()
    assert [(m["map_id"], m["published"], m["steps"]) for m in reply["maps"]] == [("m1", 1, 2)]
    assert reply["maps"][0]["body_id"] == body_id_for(confirmed_map()) and reply["simulated"] is True
    assert client.get("/api/guardian/knowledge", params={"person_id": "visitor"}).status_code == 403
    assert client.get("/api/guardian/knowledge", params={"person_id": "mallory"}).status_code == 403


def test_teaching_a_body_again_keeps_the_levels_its_parts_already_have(client):
    """Measured: the preview of a body taught again showed parts kept to the community as public."""
    body = body_id_for(confirmed_map())
    client.post("/api/guardian/publish", json={
        "map_id": "m1", "person_id": "sabine", "access": {f"{body}:rule-stop1": "community"}})
    again = client.post("/api/guardian/preview", json={"map_id": "m1", "person_id": "sabine"}).json()
    units = {u["unit_id"].split(":")[1]: u for u in again["units"]}
    assert units["rule-stop1"]["access"] == "community" and not units["rule-stop1"]["raised"]
    client.post("/api/guardian/publish", json={"map_id": "m1", "person_id": "sabine"})
    visitor = client.get("/api/learner/search", params={"q": "supplier not recognised", "person_id": "visitor"}).json()
    assert not any(r["unit"]["unit_id"].endswith("rule-stop1") for r in visitor["results"])
    opened = client.post("/api/guardian/preview", json={
        "map_id": "m1", "person_id": "sabine", "access": {f"{body}:rule-stop1": "public"}}).json()
    assert {u["unit_id"].split(":")[1]: u["access"] for u in opened["units"]}["rule-stop1"] == "public", \
        "the guardian still decides"



def test_a_body_withdrawn_and_published_again_keeps_what_was_closed(client):
    """The levels live in the library; once it is withdrawn, the guardian's map remembers them."""
    body = body_id_for(confirmed_map())
    client.post("/api/guardian/publish", json={
        "map_id": "m1", "person_id": "sabine", "access": {f"{body}:rule-stop1": "community"}})
    assert client.delete(f"/api/guardian/body/{body}", params={"person_id": "sabine"}).json()["withdrawn"]
    again = client.post("/api/guardian/preview", json={"map_id": "m1", "person_id": "sabine"}).json()
    assert {u["unit_id"].split(":")[1]: u["access"] for u in again["units"]}["rule-stop1"] == "community"
