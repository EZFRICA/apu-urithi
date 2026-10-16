"""
[B], the library: what is published, and who can read it.

Target: library/

The contract tests run against the memory store always, and against Neo4j when asked to
(URITHI_LIVE_NEO4J=1, with NEO4J_URI set): the same promises, held by both. The one that
matters most is the first: a unit a learner may not see is never returned, however close it
is to the question, because what is returned is what a model gets to read.
"""


import os
import uuid

import pytest

from apu import embeddings as embedder
from library import access, store
from library.model import (
    Body,
    Case,
    KnowledgeError,
    Link,
    Publication,
    Unit,
    levels_up_to,
)
from tests.support import DIM, WordEmbedder  # noqa: F401

ORG = "urithi"


@pytest.fixture(autouse=True)
def words(monkeypatch):
    embedder.set_embedder(WordEmbedder())
    yield
    embedder.set_embedder(None)


# ── the contract both stores hold ────────────────────────────────────────────

def _stores():
    yield pytest.param("memory", id="memory")
    yield pytest.param("neo4j", id="neo4j", marks=pytest.mark.skipif(
        not (os.environ.get("URITHI_LIVE_NEO4J") and os.environ.get("NEO4J_URI")),
        reason="set URITHI_LIVE_NEO4J=1 to hold Neo4j to the same contract"))


@pytest.fixture
def library(request):
    if request.param == "memory":
        yield store.MemoryKnowledgeStore(), "t"
        return
    embedder.set_embedder(None)      # the real model: the index has its dimensions
    live = store.Neo4jKnowledgeStore(os.environ["NEO4J_URI"], os.environ["NEO4J_USERNAME"],
                                     os.environ["NEO4J_PASSWORD"], os.environ.get("NEO4J_DATABASE"))
    prefix = f"test-{uuid.uuid4().hex[:8]}"
    yield live, prefix
    for b in live.bodies_for(ORG, ("public", "community", "restricted")):
        if b["body_id"].startswith(prefix):
            live.withdraw(ORG, b["body_id"])
    live.close()


def _publication(prefix: str, version: int = 1, secret_status: str = "published") -> Publication:
    body_id = f"{prefix}-community"
    unit = lambda name, text, level, status="published": Unit(  # noqa: E731
        unit_id=f"{body_id}:{name}", body_id=body_id, kind="limit", text=text, quote=text, at=1.0,
        access=level, status=status, version=version)
    units = [
        unit("open", "A meetup is announced two weeks ahead on the public channel.", "public"),
        unit("members", "Sponsors are thanked at the start, never given the stage.", "community"),
        unit("secret", "A code of conduct report about a speaker goes to two organisers only.",
             "restricted", secret_status),
    ]
    links = [Link(units[2].unit_id, units[0].unit_id, "PREREQUISITE_OF")]
    cases = [Case(case_id=f"{body_id}:case-1", body_id=body_id, kind="boundary",
                  question="A report about a sponsor?", said="Same: two organisers.", by="Ezekias",
                  applies=True, decides=(units[0].unit_id,), access="restricted"),
             # No yes or no: a collision. Neo4j stores no null, which broke the first live search.
             Case(case_id=f"{body_id}:case-2", body_id=body_id, kind="collision",
                  question="A sponsor and the code of conduct?", said="The code of conduct first.",
                  by="Ezekias", applies=None, decides=(units[1].unit_id,), access="community")]
    return Publication(body=Body(body_id=body_id, name="Running a tech community", guardian="Ezekias", organisation=ORG,
                                 version=version, published_at="now"),
                       units=units, links=links, cases=cases)


QUESTION = "who handles a code of conduct report about a speaker"


@pytest.mark.parametrize("library", list(_stores()), indirect=True)
def test_a_unit_a_learner_may_not_see_is_never_returned_however_close(library):
    lib, prefix = library
    lib.publish(_publication(prefix))
    body = f"{prefix}-community"
    public = lib.search(ORG, QUESTION, levels_up_to("public"), k=5, body_id=body)
    assert public and all(r["unit"]["access"] == "public" for r in public)
    assert not any("secret" in r["unit"]["unit_id"] for r in public)
    restricted = lib.search(ORG, QUESTION, levels_up_to("restricted"), k=1, body_id=body)
    assert restricted[0]["unit"]["unit_id"].endswith(":secret"), "it is the closest, for who may see it"


@pytest.mark.parametrize("library", list(_stores()), indirect=True)
def test_what_comes_with_a_unit_is_filtered_by_the_same_levels(library):
    lib, prefix = library
    lib.publish(_publication(prefix))
    body = f"{prefix}-community"
    open_unit = next(r for r in lib.search(ORG, "meetup announced public channel", levels_up_to("public"),
                                           k=3, body_id=body) if r["unit"]["unit_id"].endswith(":open"))
    assert open_unit["prerequisites"] == [], "its prerequisite is restricted"
    assert open_unit["cases"] == [], "its case is restricted"
    full = next(r for r in lib.search(ORG, "meetup announced public channel", levels_up_to("restricted"),
                                      k=3, body_id=body) if r["unit"]["unit_id"].endswith(":open"))
    assert [p["unit_id"].split(":")[1] for p in full["prerequisites"]] == ["secret"]
    assert [c["said"] for c in full["cases"]] == ["Same: two organisers."]
    assert "embedding" not in full["unit"]
    members = next(r for r in lib.search(ORG, "sponsors thanked stage", levels_up_to("community"),
                                         k=3, body_id=body) if r["unit"]["unit_id"].endswith(":members"))
    assert members["cases"] == [{"case_id": f"{body}:case-2", "kind": "collision", "applies": None,
                                 "question": "A sponsor and the code of conduct?",
                                 "said": "The code of conduct first.", "by": "Ezekias"}]


@pytest.mark.parametrize("library", list(_stores()), indirect=True)
def test_a_draft_is_never_read_by_anyone(library):
    lib, prefix = library
    lib.publish(_publication(prefix, secret_status="draft"))
    results = lib.search(ORG, QUESTION, levels_up_to("restricted"), k=5, body_id=f"{prefix}-community")
    assert not any(r["unit"]["unit_id"].endswith(":secret") for r in results)


@pytest.mark.parametrize("library", list(_stores()), indirect=True)
def test_a_new_version_replaces_the_old_one_entirely_and_a_withdrawal_removes_it(library):
    lib, prefix = library
    lib.publish(_publication(prefix, version=1))
    second = _publication(prefix, version=2)
    second.units = second.units[:1]
    second.links, second.cases = [], []
    lib.publish(second)
    body = f"{prefix}-community"
    ids = {r["unit"]["unit_id"] for r in lib.search(ORG, QUESTION, levels_up_to("restricted"), k=10, body_id=body)}
    assert ids == {f"{body}:open"}, "nothing of version 1 is left to be read"
    assert lib.version_of(ORG, body) == 2
    assert lib.stamp_of(ORG, body)[0] == 2, "the stamp a kept body is checked against (library/reader.py)"
    assert lib.withdraw(ORG, body)
    assert lib.search(ORG, QUESTION, levels_up_to("restricted"), k=10, body_id=body) == []
    assert lib.version_of(ORG, body) == 0
    assert lib.stamp_of(ORG, body) is None


@pytest.mark.parametrize("library", list(_stores()), indirect=True)
def test_when_and_in_which_language_a_unit_was_said_comes_back(library):
    """A date kept, a date unknown (Neo4j stores no null), and the language, in both stores."""
    from dataclasses import replace

    lib, prefix = library
    publication = _publication(prefix)
    publication.units[0] = replace(publication.units[0], said_at="2026-10-05T09:00:00+00:00", language="fr")
    lib.publish(publication)
    units = {u["unit_id"].split(":")[1]: u for u in lib.body_units(ORG, f"{prefix}-community", levels_up_to("community"))["units"]}
    assert units["open"]["said_at"] == "2026-10-05T09:00:00+00:00" and units["open"]["language"] == "fr"
    assert units["members"].get("said_at") is None


@pytest.mark.parametrize("library", list(_stores()), indirect=True)
def test_the_order_holds_across_a_part_one_may_not_see(library):
    """Measured: a step taught last came second, because the step before it was hidden."""
    lib, prefix = library
    body_id = f"{prefix}-order"
    unit = lambda name, level: Unit(unit_id=f"{body_id}:{name}", body_id=body_id, kind="step",  # noqa: E731
                                    text=f"Step {name}", quote=f"I do {name}.", at=1.0, access=level)
    units = [unit("first", "public"), unit("hidden", "community"), unit("last", "public")]
    links = [Link(units[0].unit_id, units[1].unit_id, "PREREQUISITE_OF"),
             Link(units[1].unit_id, units[2].unit_id, "PREREQUISITE_OF")]
    lib.publish(Publication(Body(body_id, "Order", "Ezekias", 1, "now", organisation=ORG), units, links, []))
    seen = lib.body_units(ORG, body_id, levels_up_to("public"))
    assert [(link["source_id"].split(":")[1], link["target_id"].split(":")[1]) for link in seen["links"]] == \
        [("first", "last")]
    assert "hidden" not in str(seen), "the bridge names no part the learner may not see"
    member = lib.body_units(ORG, body_id, levels_up_to("community"))["links"]
    assert len(member) == 2 and all(link["type"] == "PREREQUISITE_OF" for link in member)


@pytest.mark.parametrize("library", list(_stores()), indirect=True)
def test_the_same_knowledge_in_two_organisations_is_two_and_nothing_crosses(library):
    """docs/decisions/0006: every query filters on the organisation, the vector index included.
    The same body id, the same words, in two organisations: each reads, ranks, versions and
    withdraws only its own. Two organisations made for this run, so a live library's real
    bodies are neither read nor touched."""
    lib, prefix = library
    mine, other = f"{prefix}-org-a", f"{prefix}-org-b"
    body = f"{prefix}-community"
    ours, theirs = _publication(prefix), _publication(prefix, version=7)
    ours.body = Body(body_id=body, name="Running a tech community", guardian="Ezekias", organisation=mine,
                     version=1, published_at="now")
    theirs.body = Body(body_id=body, name="Running a tech community", guardian="Ezekias", organisation=other,
                       version=7, published_at="now")
    lib.publish(ours)
    lib.publish(theirs)
    try:
        assert lib.version_of(mine, body) == 1 and lib.version_of(other, body) == 7
        assert [b["version"] for b in lib.bodies_for(mine, levels_up_to("restricted"))] == [1]
        found = lib.search(mine, QUESTION, levels_up_to("restricted"), k=10)
        assert found and all(r["unit"]["body_id"] == body for r in found)
        assert len([r for r in found if r["unit"]["unit_id"].endswith(":secret")]) == 1, "one organisation's unit, once"
        assert lib.body_units(other, body, levels_up_to("restricted"))["body"]["version"] == 7
        assert lib.withdraw(other, body)
        assert lib.version_of(other, body) == 0 and lib.version_of(mine, body) == 1, "withdrawn there, kept here"
        assert lib.search(other, QUESTION, levels_up_to("restricted"), k=10) == []
    finally:
        lib.withdraw(mine, body)
        lib.withdraw(other, body)


@pytest.mark.parametrize("library", list(_stores())[:1], indirect=True)
def test_the_library_is_never_read_or_written_without_an_organisation(library):
    lib, prefix = library
    publication = _publication(prefix)
    publication.body = Body(body_id=publication.body.body_id, name="x", guardian="Ezekias", version=1, published_at="now")
    with pytest.raises(KnowledgeError, match="organisation"):
        lib.publish(publication)
    for read in (lambda: lib.search("", QUESTION, levels_up_to("public")), lambda: lib.bodies_for(None, ("public",)),
                 lambda: lib.body_units("", "b", ("public",)), lambda: lib.version_of("", "b"),
                 lambda: lib.withdraw(None, "b")):
        with pytest.raises(KnowledgeError, match="organisation"):
            read()


def test_a_search_with_no_access_level_or_an_unknown_one_is_refused():
    lib = store.MemoryKnowledgeStore()
    with pytest.raises(KnowledgeError):
        lib.search(ORG, "x", [])
    with pytest.raises(KnowledgeError):
        lib.search(ORG, "x", ["family"])


# ── who is asking: simulated, from the registry only ─────────────────────────

def test_levels_are_granted_from_the_most_open_up():
    assert levels_up_to("public") == ("public",)
    assert levels_up_to("restricted") == ("public", "community", "restricted")


def test_someone_not_in_the_registry_is_nobody_not_a_visitor():
    with pytest.raises(access.UnknownPerson):
        access.person("mallory")
    assert access.person("visitor").allowed == ("public",)




# ── words beside meaning (library/keywords.py) ───────────────────────────────

def _parts(prefix: str) -> Publication:
    body_id = f"{prefix}-tooling"
    unit = lambda name, text, level="public": Unit(  # noqa: E731
        unit_id=f"{body_id}:{name}", body_id=body_id, kind="limit", text=text, quote=text, at=1.0, access=level)
    units = [unit("order", "Order spare parts for the machines from the tooling supplier."),
             unit("check", "Check every machine part against the delivery note before installing it."),
             unit("store", "Store machine parts on the shelves by size, the heavy ones low."),
             unit("recall", "Part ZX9Q is recalled: never install a ZX9Q, send it back.", "community")]
    return Publication(body=Body(body_id=body_id, name="Machine parts", guardian="Ezekias", organisation=ORG,
                                 version=1, published_at="now", language="en"), units=units)


@pytest.mark.parametrize("library", list(_stores()), indirect=True)
def test_a_part_found_by_its_words_is_still_never_shown_to_who_may_not_read_it(library):
    """The words are searched under the same filter as the meaning: the full-text index is read
    after the vector one, and a part only it found was the way a closed part could slip out."""
    lib, prefix = library
    lib.publish(_parts(prefix))
    body = f"{prefix}-tooling"
    public = lib.search(ORG, "Can I install part ZX9Q?", levels_up_to("public"), k=4, body_id=body, lang="en")
    assert public and not any(r["unit"]["unit_id"].endswith(":recall") for r in public)
    members = lib.search(ORG, "Can I install part ZX9Q?", levels_up_to("community"), k=1, body_id=body, lang="en")
    assert members[0]["unit"]["unit_id"].endswith(":recall"), "for who may read it, its words bring it first"


@pytest.mark.parametrize("library", list(_stores()), indirect=True)
def test_asked_in_another_language_the_meaning_alone_ranks(library):
    """Measured on 2026-10-15: French questions on English knowledge matched short words by chance
    ("on", "a") and the fusion put the right part first 8 times in 12, against 10 by meaning alone."""
    lib, prefix = library
    lib.publish(_parts(prefix))
    body = f"{prefix}-tooling"
    ask = lambda lang: [r["unit"]["unit_id"] for r in lib.search(  # noqa: E731
        ORG, "Peut-on installer la pièce ZX9Q sur une machine ?", levels_up_to("community"), k=4, body_id=body, lang=lang)]
    assert ask("fr") == ask(None), "no keyword weighs across languages"


def _articles(prefix: str) -> Publication:
    body_id = f"{prefix}-articles"
    unit = lambda name, text: Unit(unit_id=f"{body_id}:{name}", body_id=body_id, kind="limit", text=text,  # noqa: E731
                                   quote=text, at=1.0, access="public")
    return Publication(body=Body(body_id=body_id, name="a or an", guardian="Ezekias", organisation=ORG, version=1,
                                 published_at="now", language="en"),
                       units=[unit("silent-h", "A silent h takes an: an hour, an heir, an honour."),
                              unit("you-sound", "A u that sounds like you takes a: a useful tool, a university."),
                              unit("vowel", "A vowel sound takes an: an apple, an egg, an idea."),
                              unit("consonant", "A consonant sound takes a: a dog, a cat, a house.")])


def test_the_question_s_own_words_lift_the_part_that_says_them():
    """Measured on 2026-10-15 on 38 labelled questions: by meaning alone the right part came first 30 times;
    with the question's words, in its own language, 32. One was the defect measured on "a or an before
    useful?", where the meaning put the silent H first: here the words lift the part on useful."""
    lib = store.MemoryKnowledgeStore()
    lib.publish(_articles("t"))
    ranked = lambda lang: [r["unit"]["unit_id"] for r in lib.search(  # noqa: E731
        ORG, "a or an before useful?", levels_up_to("public"), k=4, body_id="t-articles", lang=lang)]
    assert ranked(None).index("t-articles:you-sound") > ranked("en").index("t-articles:you-sound")


def test_fusion_and_word_scores():
    from library import keywords
    assert keywords.fuse(["a", "b", "c"], []) == ["a", "b", "c"], "no words: the meaning's order, unchanged"
    assert keywords.fuse(["a", "b", "c"], ["b"])[0] == "b", "second by meaning and first by words beats first by one"
    assert keywords.fuse(["a", "b"], ["b", "a"]) == ["a", "b"], "a tie keeps the meaning's order"
    scores = keywords.bm25("a or an before hour", ["When a word starts with a silent H, write an: an hour.",
                                                   "When a word starts with a consonant sound, write a."])
    assert scores[0] > scores[1] > 0, "no word left out: 'a' and 'an' count, the rare 'hour' most"
    assert keywords.same_language("en", "en-GB") and not keywords.same_language("fr", "en")
    assert not keywords.same_language(None, "en") and not keywords.same_language("en", None)


@pytest.mark.parametrize("library", list(_stores()), indirect=True)
def test_a_search_across_every_knowledge_ranks_by_meaning_alone(library):
    """Words were measured within one knowledge (the answer's search); across all of an organisation's,
    nothing was measured, so the ranking there is the meaning's, as it was. The same question that the
    words reorder within its knowledge (test above) is not reordered across them."""
    lib, prefix = library
    lib.publish(_articles(prefix))
    ask = lambda lang: [r["unit"]["unit_id"] for r in lib.search(  # noqa: E731
        ORG, "a or an before useful?", levels_up_to("public"), k=4, lang=lang)]
    assert ask("en") == ask(None)
