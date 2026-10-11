"""Reading and wording that both sides need, and that store nothing.

The guardian's side and the learner's side never import each other (docs/architecture.md).
What both need about language lives here: reading a spoken yes or no, putting a guardian's
debrief question to a learner, and telling which decided cases a learner can answer with yes
or no.
"""

import re

# What a new hire says to answer an exam case out loud, in the three languages the office
# works in. Read by code, not by a model: the answer is one word, and a model asked "is this
# a yes" would be one more thing that can be wrong about the only word that matters.
_UNSURE = re.compile(r"\b(not sure|don'?t know|no idea|maybe|perhaps|je ne sais pas|"
                     r"peut-être|peut-etre|weiß nicht|weiss nicht|vielleicht)\b", re.I)
_YES = re.compile(r"\b(yes|yeah|yep|yup|it does(?!n|\s+not)|it applies|oui|ja|genau)\b", re.I)
_NO = re.compile(r"\b(no|nope|not|doesn'?t|does not|non|pas|jamais|nein|nicht)\b", re.I)


def heard_yes_no(said: str) -> bool | None:
    """
    True for a yes, False for a no, None when it is not clearly one of them.

    None is the safe answer, and the page asks again: an exam answer guessed from "yes, no,
    wait" and graded as wrong teaches the new hire that they got the rule wrong when they
    never answered. So hesitation, both words, or neither, all come back as None.
    """
    said = (said or "").strip()
    if not said or _UNSURE.search(said):
        return None
    yes, no = bool(_YES.search(said)), bool(_NO.search(said))
    if yes == no:
        return None
    return yes


# A debrief question is put to the guardian: "You said that when...". The same case, put to a
# learner, is about what the guardian said, not what the learner said.
_YOU_SAID = re.compile(r"(^|(?<=[.?!»\"] ))(You said|Tu as dit)\b")


def for_learner(question: str, guardian: str) -> str:
    """The guardian's debrief question, as a learner reads it: "Sabine said that when..."."""
    return _YOU_SAID.sub(lambda m: f"{m.group(1)}{guardian} {'said' if m.group(2) == 'You said' else 'a dit'}",
                         question)


# What a learner answers with yes or no. A case the guardian settled by choosing between two
# readings ("which one is followed here?") is kept as precedent, but is not put to a learner
# as a yes-or-no question: measured, it reached the exam, where "yes" to "which one" means
# nothing.
_A_CHOICE = re.compile(r"(Which one is followed here\?|Laquelle des deux suit-on ici \?|,? or (is|are|do|does|should) )",
                       re.I)


def a_learner_can_answer(case: dict) -> bool:
    return case.get("applies") is not None and not _A_CHOICE.search(case.get("question", ""))
