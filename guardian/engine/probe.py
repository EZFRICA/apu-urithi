"""The debrief: the apprentice tests the expert's rules the way an engineer tests code.

Software engineering has known for fifty years where programs break: at their boundaries,
where two conditions meet, and where the specification disagrees with the world. Boundary
value analysis, pairwise testing and property-based testing all come from that. Nobody
applies them to what a person knows, and a person's rules break in exactly the same places.

Sabine said "equipment over five thousand euros is always capex". Writing the code that
checks it meant deciding whether exactly five thousand counts. She never said. Her rule has
a hole at its own edge, and nobody will find it until an invoice for 5,000.00 lands on a
new hire's desk after she has retired.

So the debrief does not ask "is anything unclear?", which an expert always answers no. It
builds the cases where the rules are least clear, puts each one to her as a concrete
invoice, and asks her to decide. Four kinds, most of them built by code rather than by a
model, so what gets asked can be explained:

- **source**: a public source contradicts her rule. A case between the two thresholds, where
  her rule and the source disagree, and she decides which this company follows.
- **boundary**: the exact number her rule turns on. Does it count?
- **collision**: two of her rules apply to the same case. What comes first?
- **near miss**: a case that is almost, but not quite, the condition. The model proposes the
  variation; it never answers it.

Every answer is kept as a Ruling, verbatim. The tutor then cites them as precedent, and the
cases she decided become the exam a new hire sits.
"""

import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from itertools import combinations

from apu.inference.llm import call_main_model
from apu.language import (
    heard_yes_no,  # noqa: F401  (the guardian's exam reads answers with it)
)
from apu.logger import get_logger
from guardian.engine import absorb, jsonish, thresholds, wording
from guardian.engine.workmap import Guardrail, Ruling, WorkMap

logger = get_logger(__name__)

# At least three follow-up questions the task did not answer, or a debrief proves little. More than
# six and an expert at the end of a working day starts answering without thinking.
MIN_PROBES = 3
MAX_PROBES = 6

# Order of value: a rule the world contradicts is the most expensive to get wrong.
ORDER = {"source": 0, "boundary": 1, "collision": 2, "near_miss": 3}


@dataclass(frozen=True)
class Probe:
    probe_id: str
    kind: str
    guardrail_id: str
    question: str            # what is said to the expert
    case: dict               # the concrete case it is about
    built_by: str            # "code" or "model": a reader can tell which questions were computed
    action: str = ""         # what the rule tells them to do, which is what the answer is about
    other_guardrail_id: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def _money(value: float, language: str = "en") -> str:
    return wording.money(value, language)


def _boundary(rail: Guardrail, language: str = "en") -> Probe | None:
    """The exact number the rule turns on. "Over five thousand": is five thousand over?"""
    found = thresholds.threshold_in(rail.when)
    if found is None:
        return None
    side = wording.say(language, "over" if found.above else "under")
    return Probe(
        probe_id=str(uuid.uuid4()), kind="boundary", guardrail_id=rail.guardrail_id,
        question=wording.say(language, "boundary", n=_money(found.value, language), when=rail.when,
                             then=rail.then, side=side),
        case={"amount_eur": found.value}, built_by="code", action=rail.then)


def _source(rail: Guardrail, language: str = "en") -> Probe | None:
    """
    A public source disagrees. The case is chosen where the two rules give opposite answers,
    so the question cannot be answered by agreeing with both.
    """
    found = rail.provenance or {}
    if found.get("verdict") != "conflicted":
        return None
    citations = [c for c in found.get("citations", []) if not c.get("agrees")]
    if not citations:
        return None
    citation = citations[0]
    theirs = thresholds.threshold_in(rail.when)
    public = thresholds.money_in(citation.get("says", ""))

    if theirs and public and public != theirs.value:
        low, high = sorted((public, theirs.value))
        between = round((low + high) / 2, -2) or (low + high) / 2
        return Probe(
            probe_id=str(uuid.uuid4()), kind="source", guardrail_id=rail.guardrail_id,
            question=wording.say(language, "source_amount",
                                 domain=citation.get("domain") or wording.say(language, "a_source"),
                                 says=citation.get("says", "").strip(),
                                 theirs=_money(theirs.value, language),
                                 between=_money(between, language), then=rail.then),
            case={"amount_eur": between, "source": citation.get("url", ""),
                  "public_threshold": public},
            built_by="code", action=rail.then)

    return Probe(
        probe_id=str(uuid.uuid4()), kind="source", guardrail_id=rail.guardrail_id,
        question=wording.say(language, "source_quote",
                             domain=citation.get("domain") or wording.say(language, "a_source"),
                             says=citation.get("says", "").strip(), quote=rail.quote.strip()),
        case={"source": citation.get("url", "")}, built_by="code", action=rail.then)


def _collision(first: Guardrail, second: Guardrail, language: str = "en") -> Probe:
    """Both rules at once. Each says what to do; neither says what to do first."""
    case: dict = {}
    for rail in (first, second):
        found = thresholds.threshold_in(rail.when)
        if found:
            case["amount_eur"] = found.value * (1.5 if found.above else 0.5)
    case["both_true"] = [first.when, second.when]
    return Probe(
        probe_id=str(uuid.uuid4()), kind="collision", guardrail_id=first.guardrail_id,
        other_guardrail_id=second.guardrail_id,
        question=wording.say(language, "collision", w1=first.when, w2=second.when,
                             t1=first.then, t2=second.then),
        case=case, built_by="code")


NEAR_MISS_SYSTEM = (
    "You help an apprentice find the edge of a workplace rule. Given one rule, describe ONE "
    "concrete case that is almost, but not quite, the rule's condition: the kind of case "
    "where a newcomer would not know whether the rule applies.\n"
    'Return JSON only: {"case": "...", "question": "..."}\n'
    '- "case": one sentence describing the concrete situation.\n'
    '- "question": one spoken sentence asking the expert whether their rule applies to it. '
    "It must end with a question mark, and be answered by yes or no: never 'A, or B?'. It "
    "must stand on its own, naming the case in it: the expert only hears the question, so "
    "never 'like this' or 'this case'.\n"
    "Never answer the question yourself."
)

# Measured: "should I still tie this credit note to an invoice, or is this the exception?" was
# put to a learner in the exam, answered with yes or no. A yes to "A, or B?" says nothing. The
# model is asked for a yes-or-no question, and one that offers a choice is not asked.
# Measured: "does the rule for numbers apply to Roman numerals like this?", and the guardian
# never saw what "this" was. A question that points at a case it does not name is not asked.
_POINTS_AWAY = re.compile(r"\b(like this|this case|this one|such a case|in this situation|comme ça|ce cas)\b", re.I)
_A_OR_B = re.compile(r",? or (is|are|do|does|should|can|would|will) |, ou (est-ce|faut-il|dois|doit) ", re.I)


def _near_miss(rail: Guardrail, decided: list[Ruling] = (), language: str = "en") -> Probe | None:
    rule = f"The rule: when {rail.when}, {rail.then}."
    if wording.language_of(language) != "en":
        rule += f"\nWrite the case and the question in {wording.LANGUAGE_NAMES[wording.language_of(language)]}."
    if decided:
        # Measured: a rule whose boundary the guardian had settled at exactly 5,000 came back
        # as a near miss asking about exactly 5,000. What is settled is said, so it is not asked.
        rule += "\nAlready decided by the expert, do not ask about these again:\n" + "\n".join(
            f"- {r.question} They said: \"{r.said}\"" for r in decided)
    try:
        found = jsonish.loads(call_main_model([
            {"role": "system", "content": NEAR_MISS_SYSTEM},
            {"role": "user", "content": rule},
        ], temperature=0.4, max_tokens=2000, thinking="low"))
        # Measured on a real run: left to think freely, the model spent 1,919 of the 2,000
        # tokens thinking and the case came back cut, three times in three for one rule; with
        # the thinking low, three valid cases in three.
    except Exception as error:
        logger.info("No near miss for %r: %s", rail.when[:40], error)
        return None
    if not isinstance(found, dict):
        return None
    question = str(found.get("question", "")).strip()
    described = str(found.get("case", "")).strip()
    # The same rule as for the apprentice's questions: a half-formed one is never asked.
    if (len(question) < 12 or not question.endswith("?") or not described or _A_OR_B.search(question)
            or _POINTS_AWAY.search(question)):
        return None
    return Probe(probe_id=str(uuid.uuid4()), kind="near_miss",
                 guardrail_id=rail.guardrail_id, question=question,
                 case={"situation": described}, built_by="model", action=rail.then)


MAX_COLLISIONS = 2


def probes_for(work_map: WorkMap, use_model: bool = True) -> list[Probe]:
    """
    The cases worth putting to the expert before they leave, most expensive first.

    Rules that already have a ruling of the same kind are not asked again: a debrief that
    repeats a question the expert answered last week teaches them to stop answering.
    """
    asked = {(r.guardrail_id, r.kind) for r in work_map.rulings}
    found: list[Probe] = []

    for rail in work_map.guardrails:
        for build in (_source, _boundary):
            probe = build(rail, work_map.language)
            if probe and (probe.guardrail_id, probe.kind) not in asked:
                found.append(probe)

    # Only pairs where one rule says to stop: that is where the order matters, since one of
    # the two actions must wait for the other. Measured on a first real conversation: every
    # pair of four rules was put to the guardian, "announce the meetup" against "a code of
    # conduct report", six questions about rules that never meet.
    collisions = [(first, second) for first, second in combinations(work_map.guardrails, 2)
                  if "stop" in (first.severity, second.severity)
                  and (first.guardrail_id, "collision") not in asked]
    for first, second in collisions[:MAX_COLLISIONS]:
        found.append(_collision(first, second, work_map.language))

    found.sort(key=lambda p: ORDER[p.kind])

    if use_model and len(found) < MIN_PROBES:
        # Rules never put to the guardian first: one already tested is the least unclear.
        tested = {r.guardrail_id for r in work_map.rulings}
        for rail in sorted(work_map.guardrails, key=lambda g: g.guardrail_id in tested):
            if len(found) >= MIN_PROBES:
                break
            if (rail.guardrail_id, "near_miss") in asked:
                continue
            probe = _near_miss(rail, work_map.rulings_for(rail.guardrail_id), work_map.language)
            if probe:
                found.append(probe)

    return found[:MAX_PROBES]


# Measured as well: "if the law says 800, then yes, that is capex" was read as unclear
# twelve times in twelve, because it is phrased as a condition. The question had just quoted
# the law saying 800 to her; the condition was met before she spoke. So the reader is told
# that a condition the question settled counts as met.
#
# What is asked is the question the expert was asked: would you do this, on this case. It
# used to be "does the rule apply", and measured six times out of six, a model reading
# "if the law says 800 then yes, three thousand is capex, we follow the law" answered no,
# correctly: her rule as stated says five thousand, so her rule does not apply; the law
# does. The question was wrong, not the answer. What matters is what she would do.
VERDICT_SYSTEM = (
    "An expert was asked whether they would take one action on one concrete case. Read "
    "their answer and report only what they said they would do.\n"
    'Return JSON only: {"would": "yes" | "no" | "unclear"}\n'
    '- "yes": they said they would take the action on this case, for whatever reason, '
    "including because a law or a source says so.\n"
    '- "no": they said they would not.\n'
    '- "unclear": anything else, including "it depends". Do not resolve it for them.\n'
    "A condition the question already settled counts as met. If the question quoted a "
    'source saying 800 and they answer "if the law says 800, then yes", the law was just '
    'quoted to them, so that is a "yes". Only a condition the question did not settle '
    'makes the answer "unclear".'
)


def _applies_from(said: str, probe: Probe) -> bool | None:
    """Whether the answer was a yes or a no. "It depends" stays unresolved, on purpose."""
    try:
        verdict = jsonish.loads(call_main_model([
            {"role": "system", "content": VERDICT_SYSTEM},
            {"role": "user", "content":
                f"The action: {probe.action or 'what the rule says'}\n"
                f"The case they were shown: {probe.question}\nThey said: {said}"},
        ], temperature=0.0, max_tokens=2000))
    except Exception as error:
        logger.info("Could not read the ruling: %s", error)
        return None
    value = str(verdict.get("would", "unclear") if isinstance(verdict, dict) else "").lower()
    return {"yes": True, "no": False}.get(value)


ORDER_SYSTEM = (
    "An expert was asked which of two rules comes first when both apply. Read their answer.\n"
    'Return JSON only: {"first": "A" | "B" | "unclear"}\n'
    "Report what they said, never what seems sensible."
)


def _first_of(probe: Probe, said: str, first_when: str, second_when: str) -> str:
    """Which rule they said comes first, as a guardrail id, or "" when they did not say."""
    try:
        found = jsonish.loads(call_main_model([
            {"role": "system", "content": ORDER_SYSTEM},
            {"role": "user", "content":
                f"Rule A: when {first_when}\nRule B: when {second_when}\nThey said: {said}"},
        ], temperature=0.0, max_tokens=2000))
    except Exception as error:
        logger.info("Could not read the order: %s", error)
        return ""
    answer = str(found.get("first", "") if isinstance(found, dict) else "").upper()
    return {"A": probe.guardrail_id, "B": probe.other_guardrail_id}.get(answer, "")


def rule_on(probe: Probe, said: str, by: str) -> Ruling:
    """The expert's answer to one probe, kept verbatim, as precedent."""
    case = dict(probe.case)
    if probe.kind == "collision":
        whens = case.get("both_true", ["", ""])
        # Which rule goes first, so the tutor can say them in the order the expert works.
        case["first"] = _first_of(probe, said, whens[0], whens[1])
        case["other"] = probe.other_guardrail_id
    return Ruling(
        ruling_id=str(uuid.uuid4()), guardrail_id=probe.guardrail_id, kind=probe.kind,
        case=case, question=probe.question, said=said.strip(),
        # A collision is not a yes or a no about one rule; its answer is the order, which
        # lives in what they said.
        applies=None if probe.kind == "collision" else _applies_from(said, probe),
        by=by, at=datetime.now(UTC).isoformat())


def teach_back(work_map: WorkMap) -> str:
    """
    The apprentice explains the process back, so the expert can say "yes, that is how it
    works", or correct it.

    Built from the map, not written by a model. A teach-back that paraphrases freely can
    sound right and be wrong, and an expert at the end of a long day will confirm a fluent
    paragraph. This one can only say what the map holds.
    """
    language = work_map.language
    say = wording.say
    task = work_map.task.rstrip(".")
    # Inside a sentence the name starts lower case, and only its first letter: measured,
    # lowering all of it read back "choosing a or an in english".
    lines = [say(language, "tb_intro", task=absorb._clause(task) if language == "en" else task)]
    for step in work_map.steps:
        # Her words, inside a sentence: "because equipment over...", not "because Equipment".
        title = step.title.rstrip(". ").removesuffix("...")
        if step.reason.strip().lower().startswith(title.lower()):
            # Taught in conversation: the step is the sentence itself, said once.
            lines.append(say(language, "tb_step_said", n=step.number, said=step.reason.strip().rstrip(".")))
        else:
            lines.append(say(language, "tb_step", n=step.number, title=step.title,
                             reason=absorb._clause(step.reason)))
    for rail in work_map.guardrails:
        lines.append(say(language, "tb_rule", when=rail.when, then=rail.then))
        for ruling in work_map.rulings_for(rail.guardrail_id):
            if ruling.kind in ("boundary", "source") and ruling.applies is not None:
                amount = thresholds.amount_in(ruling.case)
                where = (say(language, "tb_at", amount=_money(amount, language)) if amount is not None
                         else say(language, "tb_case"))
                lines.append(say(language, "tb_applies", where=where, said=ruling.said,
                                 does=say(language, "does" if ruling.applies else "does_not")))
            # The case is said with the answer. Measured: "close to it, but not it: yes" hid
            # a wrong answer ("an unique solution") that the guardian could not have spotted.
            elif ruling.kind == "collision":
                other = work_map.guardrail(ruling.case.get("other", ""))
                lines.append(say(language, "tb_collision", said=ruling.said,
                                 other=other.when if other else (ruling.case.get("both_true") or ["", ""])[-1]))
            elif ruling.kind == "near_miss":
                lines.append(say(language, "tb_near", said=ruling.said, question=ruling.question))
    lines.append(say(language, "tb_end"))
    return "\n".join(lines)


@dataclass
class ExamItem:
    ruling_id: str
    case: dict
    question: str


@dataclass
class ExamResult:
    correct: int
    total: int
    feedback: list[dict] = field(default_factory=list)


def exam(work_map: WorkMap) -> list[ExamItem]:
    """
    The cases the expert decided, without their answers.

    These are the hard ones by construction: the boundary, the source the expert overruled,
    the case almost but not quite inside the rule. A new hire who gets them right has
    learned the edges, which is the part that was never written down.
    """
    return [ExamItem(ruling_id=r.ruling_id, case=r.case, question=r.question)
            for r in work_map.rulings if r.applies is not None]


def grade(work_map: WorkMap, answers: dict[str, bool]) -> ExamResult:
    """Each answer against the ruling, explained in the words of the person who ruled."""
    by_id = {r.ruling_id: r for r in work_map.rulings if r.applies is not None}
    result = ExamResult(correct=0, total=len(by_id))
    for ruling_id, ruling in by_id.items():
        given = answers.get(ruling_id)
        right = given is not None and given == ruling.applies
        result.correct += right
        result.feedback.append({
            "ruling_id": ruling_id, "right": right, "answered": given,
            "expected": ruling.applies,
            "because": f"{ruling.by} said: \"{ruling.said}\"",
        })
    return result
