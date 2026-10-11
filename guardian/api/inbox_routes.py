"""The guardian's side of the question box: reading what learners asked, and closing it.

Guardian actions, on the guardian's side (.claude/skills/boundary-check). The box itself is
`exchange/`; nothing here imports the learner's code. Everything happens in the organisation
the guardian acts in: a question asked in another one is not in this inbox.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from exchange.questions import get_questions
from library import access
from library.store import get_store

router = APIRouter(prefix="/api/guardian")
EVERY_LEVEL = ("public", "community", "restricted")


def _as_guardian_of(body_id: str, person_id: str, organisation: str | None) -> access.Person:
    try:
        who = access.require_guardian(person_id, organisation=organisation)
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    found = get_store().body_units(who.organisation, body_id, EVERY_LEVEL)
    if found is None:
        raise HTTPException(status_code=404, detail="No such body of knowledge.")
    if found["body"]["guardian"] != who.name:
        raise HTTPException(status_code=403, detail=f"This knowledge is {found['body']['guardian']}'s, not {who.name}'s.")
    return who


@router.get("/questions/{body_id}")
def open_questions(body_id: str, person_id: str, organisation: str | None = None) -> dict:
    """What learners asked that the library had no answer to, for its guardian only."""
    who = _as_guardian_of(body_id, person_id, organisation)
    return {"questions": get_questions().open_questions(who.organisation, body_id), "simulated": access.SIMULATED}


class CloseBody(BaseModel):
    person_id: str
    ids: list[int]
    organisation: str | None = None


@router.post("/questions/{body_id}/answered")
def answered(body_id: str, body: CloseBody) -> dict:
    """
    The guardian taught the answer and published it. The questions are closed against the
    version now in the library, read here, not taken from the page: a learner holding the
    ticket is told the answer is in that version, so it has to be.
    """
    who = _as_guardian_of(body_id, body.person_id, body.organisation)
    version = get_store().version_of(who.organisation, body_id)
    box = get_questions()
    closed = [i for i in body.ids[:100] if box.body_of_question(who.organisation, i) == body_id]
    for question_id in closed:
        box.close_question(who.organisation, question_id, "answered", version)
    return {"closed": len(closed), "version": version, "simulated": access.SIMULATED}


@router.post("/questions/{body_id}/declined")
def declined(body_id: str, body: CloseBody) -> dict:
    """Not something this guardian teaches. Said to the learner, rather than left waiting."""
    who = _as_guardian_of(body_id, body.person_id, body.organisation)
    box = get_questions()
    closed = [i for i in body.ids[:100] if box.body_of_question(who.organisation, i) == body_id]
    for question_id in closed:
        box.close_question(who.organisation, question_id, "declined")
    return {"closed": len(closed), "simulated": access.SIMULATED}
