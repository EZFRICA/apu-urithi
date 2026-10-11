"""A confirmed Work Map, as the units, links, cases and sources of the library.

Done by code, field for field, with no model in between: the library holds what the
guardian said and confirmed, and a paraphrase written on the way in would change who the
learner is being taught by.

  a step            -> a "step" unit; its reason is the guardian's quote
  a rule (check)    -> a "limit" unit; a rule (stop) -> a "caution" unit
  step n, step n+1  -> PREREQUISITE_OF, because a procedure is learned in order
  a step and a rule -> PREREQUISITE_OF and LIMITS: a limit is not taught before what it limits
  two rules that met in the debrief -> MEETS, and the collision case decides both
  a ruling          -> a case that decides the unit(s) it was about
  a citation        -> a source that SUPPORTS or DISAGREES with the unit
"""

import re
from dataclasses import replace
from datetime import UTC, datetime

from guardian.engine import wording
from guardian.engine.workmap import WorkMap
from library.model import (
    Evidence,
    ACCESS_LEVELS,
    Body,
    Case,
    KnowledgeError,
    Link,
    Publication,
    SourceRef,
    Unit,
    check_access,
)


def body_id_for(work_map: WorkMap) -> str:
    """One body per guardian and task: teaching the same task again publishes a new version."""
    return f"{_slug(work_map.expert)}--{_slug(work_map.task)}"


def publication_from(work_map: WorkMap, *, version: int, access: dict[str, str] | None = None,
                     default_access: str = "public", language: str | None = None) -> Publication:
    """
    `access` maps a unit id (as returned in the publication) to its level; anything not
    named gets `default_access`. Only the validated version is published (docs/decisions/0002):
    what the guardian has not heard back and agreed to is not their knowledge yet, and a part
    taught since stays a draft, out of the library, until it is validated in its turn.
    """
    validated = work_map.as_validated()
    if validated is None:
        raise KnowledgeError("The guardian has not validated this map; it cannot be published.")
    work_map = validated
    if not work_map.is_teachable:
        raise KnowledgeError(work_map.why_not_teachable())
    check_access(default_access)
    language = wording.language_of(language or work_map.language)
    access = access or {}
    body_id = body_id_for(work_map)
    level = lambda unit_id: check_access(access.get(unit_id, default_access))  # noqa: E731

    body = Body(body_id=body_id, name=work_map.task, guardian=work_map.expert, version=version,
                published_at=datetime.now(UTC).isoformat(), language=language,
                organisation=work_map.organisation)
    publication = Publication(body=body)

    step_ids: list[str] = []
    # In the order of the contents the guardian set; the number stays each step's identity, so
    # reordering moves a part without changing it, nor a learner's progress on it.
    for step in work_map.ordered_steps():
        unit_id = f"{body_id}:step-{step.number}"
        publication.units.append(Unit(
            unit_id=unit_id, body_id=body_id, kind="step", text=step.title,
            quote=step.reason, at=step.screen_moment, access=level(unit_id),
            language=language, version=version, said_at=step.said_at,
            section=work_map.section_of(step.step_id)))
        if step_ids:
            publication.links.append(Link(step_ids[-1], unit_id, "PREREQUISITE_OF"))
        step_ids.append(unit_id)

    rail_units: dict[str, str] = {}
    for rail in work_map.guardrails:
        unit_id = f"{body_id}:rule-{_slug(rail.guardrail_id)}"
        rail_units[rail.guardrail_id] = unit_id
        publication.units.append(Unit(
            unit_id=unit_id, body_id=body_id,
            kind="caution" if rail.severity == "stop" else "limit",
            text=wording.say(language, "rule_text", when=rail.when, then=rail.then),
            quote=rail.quote, at=rail.asked_at,
            access=level(unit_id), language=language, version=version, said_at=rail.said_at))
        for citation in (rail.provenance or {}).get("citations", []):
            publication.sources.append(SourceRef(
                source_id=f"{unit_id}:source-{len(publication.sources) + 1}", body_id=body_id,
                url=citation.get("url", ""), domain=citation.get("domain", ""),
                says=citation.get("says", ""),
                relation="SUPPORTS" if citation.get("agrees") else "DISAGREES",
                unit_id=unit_id, jurisdiction=citation.get("jurisdiction", "")))

    for step in work_map.steps:
        for rail in work_map.rails_for(step):
            step_unit, rail_unit = f"{body_id}:step-{step.number}", rail_units[rail.guardrail_id]
            publication.links.append(Link(step_unit, rail_unit, "PREREQUISITE_OF"))
            publication.links.append(Link(rail_unit, step_unit, "LIMITS"))

    _raise_units_that_repeat_restricted_words(publication)

    # An access level for a unit that does not exist is a typo, and a typo here publishes
    # what was meant to be restricted as public. Refused, naming what was misspelt.
    unknown = sorted(set(access) - {u.unit_id for u in publication.units})
    if unknown:
        raise KnowledgeError(f"No such unit to set an access level on: {', '.join(unknown)}.")
    unit_access = {u.unit_id: u.access for u in publication.units}
    for ruling in work_map.rulings:
        if ruling.kind == "correction" or ruling.guardrail_id not in rail_units:
            continue   # a correction is about the map, not a case; it stays with the map
        decides = [rail_units[ruling.guardrail_id]]
        other = ruling.case.get("other") if ruling.kind == "collision" else None
        if other in rail_units:
            decides.append(rail_units[other])
            publication.links.append(Link(decides[0], decides[1], "MEETS"))
        publication.cases.append(Case(
            case_id=f"{body_id}:case-{_slug(ruling.ruling_id)}", body_id=body_id,
            kind=ruling.kind, question=ruling.question, said=ruling.said, by=ruling.by,
            applies=ruling.applies, decides=tuple(decides),
            # A case reveals the units it decides, so it is never more open than they are.
            access=_most_restricted(unit_access[u] for u in decides)))
    _raise_cases_that_name_restricted_words(publication)
    # The passages each part cites, as evidence a learner can open (step 3), at the part's own
    # level: an excerpt is never more open than the part it supports.
    by_unit = {u.unit_id: u for u in publication.units}
    for step in work_map.ordered_steps():
        _evidence(publication, by_unit[f"{body_id}:step-{step.number}"], step.cites)
    for rail in work_map.guardrails:
        _evidence(publication, by_unit[rail_units[rail.guardrail_id]], rail.cites)
    return publication


def _evidence(publication: Publication, unit, cites) -> None:
    for cite in cites or ():
        publication.evidence.append(Evidence(
            evidence_id=f"{unit.unit_id}:evidence-{len(publication.evidence) + 1}", body_id=unit.body_id,
            unit_id=unit.unit_id, name=cite.get("name", ""), where=cite.get("where", ""),
            excerpt=cite.get("text", "")[:600], access=unit.access))


def _words(text: str) -> set[str]:
    """
    The words that name something: an acronym ("MBA") or a long word ("abbreviation").
    Measured: with every word counted, "read", said only in the closed parts, raised a case
    about Roman numerals that had nothing closed in it.
    """
    found = re.findall(r"[A-Za-zÀ-ÿ0-9']+", text)
    return {w.lower() for w in found if (len(w) >= 2 and w.isupper()) or len(w) >= 7}


def _raise_cases_that_name_restricted_words(publication: Publication) -> None:
    """
    Measured: a near miss on the public rule "write a" asked "does it apply before an
    abbreviation like MBA?", and a visitor read in it, with the guardian's answer, what the
    guardian had kept to the community. A case that uses a word found only in more restricted
    parts ("abbreviation", "MBA") is raised to their level. Raising too much costs a case;
    raising too little opens what was closed.
    """
    words_at = {level: set() for level in ACCESS_LEVELS}
    for unit in publication.units:
        words_at[unit.access] |= _words(f"{unit.text} {unit.quote}")
    for i, case in enumerate(publication.cases):
        named = _words(f"{case.question} {case.said}")
        level = case.access
        for rank in range(ACCESS_LEVELS.index(case.access) + 1, len(ACCESS_LEVELS)):
            more_open = set().union(*(words_at[lvl] for lvl in ACCESS_LEVELS[:rank]))
            if named & (words_at[ACCESS_LEVELS[rank]] - more_open):
                level = ACCESS_LEVELS[rank]
        if level != case.access:
            publication.cases[i] = replace(case, access=level)


def _raise_units_that_repeat_restricted_words(publication: Publication) -> None:
    """
    Restricting a unit restricts its words, wherever else they were said. Measured on the
    first live search: a rule set to "community" was still read by a public visitor, word for
    word, in the quote of the step whose reason the guardian had given in the same sentence.
    So a unit whose quote holds another unit's quote is at least as restricted as that unit.
    """
    changed = True
    while changed:                         # until nothing moves: restrictions can chain
        changed = False
        for i, unit in enumerate(publication.units):
            stricter = [other.access for other in publication.units
                        if other is not unit and other.quote.strip()
                        and _norm(other.quote) in _norm(unit.quote)
                        and ACCESS_LEVELS.index(other.access) > ACCESS_LEVELS.index(unit.access)]
            if stricter:
                publication.units[i] = replace(unit, access=_most_restricted(stricter))
                changed = True


def _norm(text: str) -> str:
    return " ".join(text.lower().split()).rstrip(".")


def _most_restricted(levels) -> str:
    return max(levels, key=ACCESS_LEVELS.index)


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")
    return slug[:60] or "unnamed"
