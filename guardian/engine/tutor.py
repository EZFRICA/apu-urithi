"""The tutor: what the apprentice learned, taught to the next person.

The hardest part is here. A new hire meets a case the expert never showed, and the tutor
has to catch a wrong decision **before it is saved** and explain it using the reasoning the
expert gave. Catching it afterwards is a report; catching it before
is an apprentice standing at your shoulder.

Three properties make that honest rather than lucky.

**It fails closed.** A rail the checker cannot decide on is treated as breached, not as
clear. A tutor that waves through what it does not understand is worse than no tutor: the
new hire learns to trust it and it is wrong exactly where the work is hard.

**It never speaks for itself.** Every intervention carries the expert's own sentence and the
second of screen it was said at. The new hire is being taught by Sabine, through this; the
tutor that cannot name who said a rule is making it up.

**It teaches rather than blocks.** A breach is raised as a question with the reason behind
it, and the person still decides. Nothing here acts on the user's behalf.
"""

import json
from dataclasses import dataclass

from apu.inference.llm import call_main_model
from apu.logger import get_logger
from guardian.engine import jsonish, thresholds
from guardian.engine.workmap import Guardrail, Ruling, WorkMap

logger = get_logger(__name__)


@dataclass(frozen=True)
class Intervention:
    """What the tutor says when it steps in, and what it stands on."""

    guardrail: Guardrail
    says: str
    replay_at: float          # the screen moment to show: the expert saying this
    certain: bool             # False when the tutor stopped because it could not tell
    precedent: Ruling | None = None   # the decided case this one matched, when there is one

    @property
    def quote(self) -> str:
        return self.guardrail.quote


@dataclass(frozen=True)
class Review:
    allowed: bool
    interventions: tuple[Intervention, ...] = ()
    cleared: tuple[Ruling, ...] = ()     # decisions that are why a rule did not fire

    @property
    def blocking(self) -> Intervention | None:
        return next((i for i in self.interventions if i.guardrail.severity == "stop"), None)


CHECK_SYSTEM = (
    "You decide whether one stated limit applies to one case. Nothing else.\n"
    "Return JSON only: {\"applies\": \"yes\" | \"no\" | \"unsure\", \"because\": \"...\"}\n"
    "- \"yes\": the case clearly meets the condition.\n"
    "- \"no\": the case clearly does not.\n"
    "- \"unsure\": the case does not say enough to tell. Use this rather than guessing; "
    "the cost of a wrong \"no\" is a rule broken that nobody noticed."
)


def _same_case(decided: dict, case: dict) -> bool:
    """
    Whether a new case is one a person already decided.

    Compared on the facts that can be compared exactly, numbers and yes-or-no fields, and
    only on the ones both cases state. Descriptions are left out: two invoices described in
    different words are not thereby different invoices.
    """
    def facts(d: dict) -> dict:
        return {k: v for k, v in d.items()
                if isinstance(v, (bool, int, float)) and k != "public_threshold"}

    ours, theirs = facts(decided), facts(case)
    shared = set(ours) & set(theirs)
    if not shared:
        return False
    for key in shared:
        a, b = ours[key], theirs[key]
        if isinstance(a, bool) or isinstance(b, bool):
            if a is not b:
                return False
        elif abs(float(a) - float(b)) > 0.005:
            return False
    return True


def decide(rail: Guardrail, case: dict, rulings: list[Ruling]) -> tuple[bool, bool, Ruling | None]:
    """
    (applies, certain, precedent), consulting what people decided before the rule itself.

    In this order, because it is the order of authority. A person's decision on this exact
    case outranks everything. Then what their decisions at the rule's edge settled for every
    case: whether the boundary counts, and which threshold the company follows. Then
    arithmetic on the rule as stated. Then, for what is not arithmetic, the model.
    """
    settled = [r for r in rulings if r.applies is not None]

    for ruling in settled:
        if ruling.kind != "collision" and _same_case(ruling.case, case):
            return ruling.applies, True, ruling

    inclusive = next((r.applies for r in settled if r.kind == "boundary"), None)
    value = next((r.case.get("public_threshold") for r in settled
                  if r.kind == "source" and r.applies and r.case.get("public_threshold")), None)
    if inclusive is not None or value is not None:
        decided = thresholds.decide(rail.when, case, inclusive=inclusive, value=value)
        if decided is not None:
            source = next(r for r in settled if r.kind in ("boundary", "source"))
            return decided, True, source

    applies, certain = _rail_applies(rail, case)
    return applies, certain, None


def _rail_applies(rail: Guardrail, case: dict) -> tuple[bool, bool]:
    """
    (applies, certain). An error or an unreadable answer is "applies, not certain".

    A rule that turns on a number is decided by arithmetic first. Asked whether 2,400
    euros is over five thousand, the model said no twice and "unsure" twice in four runs,
    and unsure fails closed: half the time a new hire was stopped by a rule that did not
    apply. The model is still asked everything that is not arithmetic.
    """
    decided = thresholds.decide(rail.when, case)
    if decided is not None:
        return decided, True
    try:
        raw = call_main_model([
            {"role": "system", "content": CHECK_SYSTEM},
            {"role": "user", "content":
                f"The limit: when {rail.when}, {rail.then}\n"
                f"The case: {json.dumps(case, ensure_ascii=False)}"},
        ], temperature=0.0, response_format={"type": "json_object"}, max_tokens=200)
        parsed = jsonish.loads(raw)
        verdict = str(parsed.get("applies", "unsure") if isinstance(parsed, dict)
                      else "unsure").lower()
    except Exception as error:
        logger.warning("Could not check the limit %r: %s", rail.when[:50], error)
        return True, False
    if verdict == "no":
        return False, True
    if verdict == "yes":
        return True, True
    return True, False


def review(work_map: WorkMap, case: dict, about_to: str) -> Review:
    """
    Check what the new hire is about to do against everything the expert said.

    Called before the save, not after it. Only "stop" rails block; a "check" rail is raised
    as something to be aware of and the person carries on.
    """
    interventions = []
    cleared = []
    for rail in work_map.guardrails:
        applies, certain, precedent = decide(rail, case, work_map.rulings_for(rail.guardrail_id))
        if not applies:
            if precedent is not None and precedent.kind in ("escalation", "near_miss"):
                cleared.append(precedent)
            continue
        interventions.append(Intervention(
            guardrail=rail,
            says=_wording(rail, about_to, certain, precedent),
            replay_at=rail.asked_at,
            certain=certain,
            precedent=precedent,
        ))

    interventions = _in_the_experts_order(interventions, work_map)
    blocking = any(i.guardrail.severity == "stop" for i in interventions)
    return Review(allowed=not blocking, interventions=tuple(interventions),
                  cleared=tuple(cleared))


def _in_the_experts_order(interventions: list, work_map: WorkMap) -> list:
    """
    When two rules fire together, say them in the order the expert said she works.

    Asked what comes first when an unknown supplier sends five thousand euros of equipment,
    Sabine said the supplier check, always, before anything is coded. The tutor used to
    announce the capex note first because that rule happened to be learned first. The order
    a new hire hears is the order they will act in, so it is hers, not the list's.
    """
    fired = {i.guardrail.guardrail_id for i in interventions}
    rank: dict[str, int] = {}
    for ruling in work_map.rulings:
        if ruling.kind != "collision":
            continue
        first = ruling.case.get("first")
        pair = {ruling.guardrail_id, ruling.case.get("other", "")}
        if first and pair <= fired:
            for rail_id in pair:
                rank[rail_id] = 0 if rail_id == first else 1
    return sorted(interventions, key=lambda i: rank.get(i.guardrail.guardrail_id, 1))


def _wording(rail: Guardrail, about_to: str, certain: bool,
             precedent: Ruling | None = None) -> str:
    """
    What the new hire hears. The expert's sentence does the work; the tutor only frames it.

    No model call: this is said at the moment of a click, and a sentence that has to wait
    for a network round trip arrives after the save it was meant to prevent.
    """
    # The expert's sentence is quoted whole and set apart, rather than folded into one of
    # the tutor's own: "then" is a clause the expert spoke, and inlining it produced
    # sentences like "this is a stop and ask the controller".
    # Uncertainty is said for every rail, not only the blocking ones. It used to be dropped
    # for a "check" rule, so one that fired because the tutor could not tell read exactly
    # like one it was sure of, and a new hire had no way to know which they were hearing.
    if not certain:
        lead = "I cannot tell whether this one applies, so before you "
    elif rail.severity == "stop":
        lead = "Hold on before you "
    else:
        lead = "Worth knowing before you "
    said = (f"{lead}{about_to}. "
            f"{rail.quote.strip()} "
            f"Here that means: {rail.then.rstrip('.').strip()}.")

    # A decided case is cited like a judgment: who decided, and what they said. It is the
    # strongest thing the tutor can say, because it is not the tutor saying it.
    if precedent is not None and precedent.kind == "source":
        # Settled against a public source: what she decided is the rule now, so it leads,
        # and her original sentence, which states the old number, is not repeated as if it
        # still held.
        return (f"{lead}{about_to}. {precedent.by} decided this against a public source: "
                f"\"{precedent.said}\" Here that means: {rail.then.rstrip('.').strip()}.")
    if precedent is not None:
        said += (f" {precedent.by} decided a case like this one: \"{precedent.said}\"")

    # A rule a public source contradicts is still enforced, because the expert said it and
    # a search result does not overrule twenty-four years. But the new hire is told, so the
    # person who can settle it is the one who does. Only while it is unsettled: once
    # someone has decided it, sending the new hire to decide it again is noise.
    if (rail.provenance or {}).get("verdict") == "conflicted" and precedent is None:
        said += (" One more thing: a public source now says something different about "
                 "this, so settle it with the controller rather than taking it from me.")
    return said


def mastery(work_map: WorkMap, seen: set[str]) -> dict:
    """
    What the new hire has met and what is still ahead of them.

    Shown at the end of a case. It counts rails they actually hit, not steps they scrolled
    past: a tutor that reports mastery of what was never tested is a certificate, not a
    teacher.
    """
    rails = work_map.guardrails
    met = [r for r in rails if r.guardrail_id in seen]
    return {
        "met": [{"when": r.when, "then": r.then} for r in met],
        "to_practise": [{"when": r.when, "then": r.then}
                        for r in rails if r.guardrail_id not in seen],
        "covered": f"{len(met)}/{len(rails)}" if rails else "0/0",
    }
