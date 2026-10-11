"""The learner's side of the question box: drop a question in, follow a ticket. Nothing else.

Reading the box, answering and declining are the guardian's (guardian/api/inbox_routes.py).
Measured in the step 0 review: the learner's routes held the whole box, so reading every open
question or closing one was a call away. tests/shared/test_boundaries.py refuses any other way
into exchange/ from learner/.
"""

from exchange.questions import get_questions


class Asking:
    """The box as a learner of one organisation reaches it."""

    __slots__ = ("_box", "_organisation")

    def __init__(self, box, organisation: str):
        if not organisation:
            raise ValueError("No organisation: a question is always asked in one.")
        self._box = box
        self._organisation = organisation

    def ask_guardian(self, body_id: str, question: str, language: str) -> str:
        """Keeps the question, not who asked it, and returns the asker's ticket."""
        return self._box.ask_guardian(self._organisation, body_id, question, language)

    def tickets(self, tickets: list[str]) -> list[dict]:
        """Where each question stands, for whoever holds its ticket."""
        return self._box.tickets(tickets)


def for_learners(organisation: str) -> Asking:
    return Asking(get_questions(), organisation)


def follow_tickets(tickets: list[str]) -> list[dict]:
    """Where each question stands, for whoever holds its ticket: a random secret, whatever the organisation."""
    return get_questions().tickets(tickets)
