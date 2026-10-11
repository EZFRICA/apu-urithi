"""The Work Map as something a blind colleague can read with their fingers.

A screen recording cannot be inherited by a blind new hire. Neither can a task-mining log,
which is a list of coordinates. This is the argument for the Work Map that nobody makes
about screen capture tools: **a Work Map is already language.** A step, a reason in the
expert's words, a condition and what to do about it. None of it needs a screen, so none of
it needs eyes.

Two things follow, and the second is the one worth building.

**A blind expert can teach.** They work with their screen reader, the apprentice listens
and watches, and their judgment is captured exactly as a sighted expert's would be.

**A blind new hire can be taught.** Where a sighted one replays a second of screen, this
one reads the same step in braille, at their own pace, as many times as they like.

And there is a reason to emboss a guardrail rather than only speak it, which applies to
everyone. A spoken warning is linear and gone: you hear it once, at the speed the voice
chose, while under time pressure. A braille line stays under the finger. The sighted new
hire glances back at the screen; this one re-reads the cells. The rule persists either way,
which is the whole point of a rule.
"""

from dataclasses import dataclass

from apu.logger import get_logger
from apu.modality.braille.sheet import BrailleSheet, braille_sheet
from apu.modality.braille.translator import BrailleGrade
from guardian.engine.workmap import WorkMap

logger = get_logger(__name__)


class BrailleUnavailable(RuntimeError):
    """liblouis is not installed, so nothing here can be produced."""


@dataclass(frozen=True)
class BrailleWorkMap:
    print_text: str          # what was embossed, in print, so a sighted colleague can check
    unicode_braille: str     # the same cells, for a screen or a screen reader
    brf: str                 # for an embosser
    pages: int
    grade: int
    pages_unicode: tuple[tuple[str, ...], ...] = ()   # the embosser's pages, line for line


def as_print(work_map: WorkMap) -> str:
    """
    The Work Map as a document meant to be read start to finish.

    Laid out for a reader who cannot skim. A sighted reader's eye jumps to the bold line; a
    finger cannot, so the order carries the structure instead: what the task is, what to do
    in sequence, and the limits last, because they are what gets re-read.

    Timestamps are left out. A screen moment is an index into a recording, and a recording
    is the one part of this a blind colleague cannot use; printing "3:12" on their page
    would be printing a reference to something they were not given.
    """
    lines = [
        f"Task: {work_map.task}",
        f"Taught by: {work_map.expert}",
        "",
        "The steps.",
        "",
    ]
    for step in work_map.steps:
        lines.append(f"Step {step.number}. {step.title}")
        lines.append(f"Why: {step.reason.strip()}")
        rails = work_map.rails_for(step)
        if rails:
            lines.append("Limits on this step: "
                         + "; ".join(f"when {r.when}, {r.then}" for r in rails))
        lines.append("")

    stops = [g for g in work_map.guardrails if g.severity == "stop"]
    checks = [g for g in work_map.guardrails if g.severity != "stop"]

    if stops:
        lines += ["When to stop and ask.", ""]
        for rail in stops:
            lines.append(f"When {rail.when}, {rail.then}.")
            lines.append(f"In their words: {rail.quote.strip()}")
            lines.append(_provenance_line(rail))
            lines.append("")
    if checks:
        lines += ["Worth knowing.", ""]
        for rail in checks:
            lines.append(f"When {rail.when}, {rail.then}.")
            lines.append(_provenance_line(rail))
            lines.append("")

    if not work_map.is_teachable:
        lines += ["This map is not finished.", work_map.why_not_teachable(), ""]

    return "\n".join(line for line in lines if line is not None)


def _provenance_line(rail) -> str:
    """
    Where the rule came from, said in words rather than shown as a colour.

    The screen marks a contradicted rule in amber. A colour is not a medium, so the same
    fact is a sentence here, and a reader who cannot see the badge is not the last to know
    that the rule they are learning is disputed.
    """
    found = rail.provenance or {}
    verdict = found.get("verdict")
    if verdict == "conflicted":
        return ("Note: a public source now says something different about this. "
                "Settle it with a person before relying on it.")
    if verdict == "corroborated":
        sources = ", ".join(c.get("domain", "") for c in found.get("citations", [])[:2])
        return f"This matches a public source{f' ({sources})' if sources else ''}."
    if verdict == "house_rule":
        return "This is a house rule. No public source governs it."
    return "This has not been checked against any source."


def emboss(work_map: WorkMap, grade: BrailleGrade = BrailleGrade.GRADE_2,
           language: str = "en") -> BrailleWorkMap:
    """
    The whole map, translated and laid out on paper.

    Grade 2 by default because that is what a fluent adult reads and what an embosser
    produces; grade 1 is there for a learner. Raises rather than returning an empty
    document: a blank page handed to someone who cannot see it is blank is the worst
    possible failure here.
    """
    text = as_print(work_map)
    try:
        sheet: BrailleSheet = braille_sheet(text, grade=grade, language=language)
    except Exception as error:
        logger.warning("The map could not be embossed: %s", error)
        raise BrailleUnavailable(str(error)) from error

    return BrailleWorkMap(print_text=sheet.text, unicode_braille=sheet.unicode_braille,
                          brf=sheet.brf, pages=sheet.pages, grade=int(grade),
                          pages_unicode=sheet.pages_unicode)


def intervention_pages(says: str, grade: BrailleGrade = BrailleGrade.GRADE_2,
                       language: str = "en") -> list[list[str]]:
    """The same warning laid out by the embosser, as a slip to keep on the desk. Empty if
    braille is unavailable: the spoken warning is still given."""
    try:
        return [list(page) for page in braille_sheet(says, grade=grade,
                                                     language=language).pages_unicode]
    except Exception as error:
        logger.info("No slip for an intervention: %s", error)
        return []


def intervention_cells(says: str, grade: BrailleGrade = BrailleGrade.GRADE_2,
                       language: str = "en") -> str:
    """
    One spoken intervention, as cells ready to emboss.

    The tutor says this at the moment of a save. Spoken, it is gone in four seconds and the
    new hire is still holding the decision. On paper it stays on the desk while they think.
    """
    try:
        return braille_sheet(says, grade=grade, language=language).unicode_braille
    except Exception as error:
        logger.info("No cells for an intervention: %s", error)
        return ""
