"""The learner's HTTP surface.

Every unit is read through the person's access levels. A unit they may not see is answered
404, the same as one that does not exist: refusing it by name would tell them it is there.
Identities are simulated (library.access), and every reply that depends on one says so.
"""

import base64
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, HTTPException, WebSocket
from pydantic import BaseModel

from apu.language import a_learner_can_answer, for_learner, heard_yes_no
from apu import meter
from apu.logger import get_logger
from apu.modality import picture as pictures
from apu.modality import live, voice
from exchange.asking import follow_tickets, for_learners
from learner import renderings
from learner.memory.answers import get_answers
from learner.memory.mmu import get_learner_mmu
from learner.memory.notebook import get_learner_memory
from learner.memory.progress import get_progress
from learner.packages import package as packaging
from learner.packages import signing
from learner.tutor import answer as answering
from learner.tutor import guard
from learner.tutor.path import ordered
from library import access
from library.reader import get_reader

logger = get_logger("learning")
router = APIRouter(prefix="/api/learner")


def _who(person_id: str | None, organisation: str | None = None) -> access.Person:
    """The person's membership in the organisation named, or their first; from the registry only."""
    try:
        who = access.person(person_id, organisation)
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    meter.act_as(meter.Principal(who.organisation, who.person_id, who.role))
    return who


def _body(body_id: str, who: access.Person) -> dict:
    found = get_reader(who.organisation).body_units(body_id, who.allowed)
    if found is None:
        raise HTTPException(status_code=404, detail="No such body of knowledge.")
    return found


def _unlearned_before(body: dict, unit_ids: list[str], who: access.Person) -> list[dict]:
    """The parts these rest on that this person has not learned yet: reminded, never enforced
    (docs/decisions/0003), when an answer rests on them and at the exam."""
    by_id = {u["unit_id"]: u for u in body["units"]}
    before = {link["source_id"] for link in body["links"]
              if link["type"] == "PREREQUISITE_OF" and link["target_id"] in unit_ids} - set(unit_ids)
    states = get_progress().states(who.organisation, who.person_id, sorted(before))
    return [{"unit_id": uid, "text": by_id[uid]["text"]} for uid in sorted(before)
            if uid in by_id and states[uid]["state"] != "learned"]


def _remember(who: access.Person, body_id: str, **changes) -> None:
    """The learner's working memory for this knowledge (learner/memory/notebook.py and mmu.py)."""
    memory = get_learner_memory()
    session = memory.load(who.organisation, who.person_id, body_id)
    if "on" in changes:
        session["on"] = changes["on"]
    for key in ("asked", "hard"):
        if changes.get(key):
            session.setdefault(key, []).append({**changes[key], "at": datetime.now(UTC).isoformat()})
    memory.save(who.organisation, who.person_id, body_id, session)
    get_learner_mmu().record_session_event(
        who.organisation,
        who.person_id,
        body_id,
        on=changes.get("on"),
        asked=changes.get("asked"),
        hard=changes.get("hard"),
    )


def _unit(unit_id: str, who: access.Person) -> tuple[dict, dict]:
    body = _body(unit_id.split(":", 1)[0], who)
    unit = next((u for u in body["units"] if u["unit_id"] == unit_id), None)
    if unit is None:
        raise HTTPException(status_code=404, detail="No such unit.")
    return unit, body


@router.websocket("/listen")
async def listen_live(ws: WebSocket, person_id: str = "", organisation: str | None = None) -> None:
    """The learner's microphone, live: their words on the teleprompter as they say them."""
    try:
        who = access.person(person_id, organisation)
    except PermissionError:
        await ws.close(code=4403)
        return
    await live.relay(ws, meter.Principal(who.organisation, who.person_id, who.role))


@router.get("/people")
def list_people() -> dict:
    """Who one can be, in simulation."""
    return {"simulated": access.SIMULATED, "people": [access.as_listed(p) for p in access.memberships()]}


@router.get("/search")
def search(q: str, person_id: str, k: int = 5, body_id: str | None = None, organisation: str | None = None,
           lang: str | None = None) -> dict:
    """What this person may see that is closest to the question, with what it rests on; the question's
    own words count too when it is asked in the knowledge's language (library/keywords.py)."""
    who = _who(person_id, organisation)
    if not q.strip():
        raise HTTPException(status_code=422, detail="Nothing to search for.")
    results = get_reader(who.organisation).search(q, who.allowed, k=max(1, min(k, 20)), body_id=body_id, lang=lang)
    return {"results": results, "as": who.name, "access": who.access, "simulated": access.SIMULATED}


@router.get("/bodies")
def bodies(person_id: str, organisation: str | None = None) -> dict:
    who = _who(person_id, organisation)
    return {"bodies": [b for b in get_reader(who.organisation).bodies_for(who.allowed) if b["units"]],
            "as": who.name, "access": who.access, "simulated": access.SIMULATED}


@router.get("/path/{body_id}")
def path(body_id: str, person_id: str, organisation: str | None = None) -> dict:
    """The units in learning order, each with where this person stands on it."""
    who = _who(person_id, organisation)
    body = _body(body_id, who)
    units, cycle = ordered(body["units"], body["links"])
    states = get_progress().states(who.organisation, who.person_id, [u["unit_id"] for u in units])
    quizzes = {}
    for case in body["cases"]:
        if a_learner_can_answer(case):
            for uid in case["decides"]:
                quizzes[uid] = quizzes.get(uid, 0) + 1
    return {"body": body["body"], "cycle_broken": cycle, "simulated": access.SIMULATED, "as": who.name,
            "units": [{**u, "progress": states[u["unit_id"]], "quizzes": quizzes.get(u["unit_id"], 0)}
                      for u in units],
            # Between units this person may see, both ends: what the "see" form draws from.
            "links": body["links"],
            "cases": sum(1 for c in body["cases"] if a_learner_can_answer(c)),
            "due": sum(1 for s in states.values() if s["state"] == "due")}


@router.get("/key")
def key() -> dict:
    """The library's public key: a device keeps it, and checks every package with it, offline."""
    return signing.public_key()


@router.get("/package/{body_id}")
def package(body_id: str, person_id: str, lang: str = "en", audio: bool = False, organisation: str | None = None) -> dict:
    """The body as this person may see it, to keep and learn from offline."""
    who = _who(person_id, organisation)
    found = _body(body_id, who)
    deferred = audio and meter.meter().level() != "ok"   # audio is heavy work: deferred near a ceiling
    built = packaging.build(found, person_id=who.person_id, organisation=who.organisation, allowed=who.allowed,
                            language=lang, with_audio=audio and not deferred)
    return {**built, "audio_deferred": deferred, "simulated": access.SIMULATED}


class SyncBody(BaseModel):
    person_id: str
    organisation: str | None = None
    reviews: list[dict]      # [{"unit_id", "rating", "at"}], made offline, in order


@router.post("/sync")
def sync(body: SyncBody) -> dict:
    """Reviews made offline, applied in the order and at the time they were made."""

    who = _who(body.person_id, body.organisation)
    applied, refused = 0, []
    for entry in body.reviews[:500]:
        try:
            when = datetime.fromisoformat(entry["at"])
            _unit(entry["unit_id"], who)
            get_progress().review(who.organisation, who.person_id, entry["unit_id"], int(entry["rating"]), when)
            applied += 1
        except (HTTPException, KeyError, ValueError) as error:
            refused.append({"unit_id": entry.get("unit_id"), "why": str(getattr(error, "detail", error))})
    return {"applied": applied, "refused": refused, "simulated": access.SIMULATED}


@router.get("/unit/{unit_id:path}/listen")
def listen(unit_id: str, person_id: str, lang: str = "en", organisation: str | None = None) -> dict:
    who = _who(person_id, organisation)
    unit, body = _unit(unit_id, who)
    try:
        return renderings.audio(unit, body["body"]["guardian"], lang, organisation=who.organisation)
    except voice.VoiceUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.get("/unit/{unit_id:path}/braille")
def braille(unit_id: str, person_id: str, grade: int = 2, lang: str = "en", organisation: str | None = None) -> dict:
    if grade not in (1, 2):
        raise HTTPException(status_code=422, detail="Grade 1 or grade 2.")
    who = _who(person_id, organisation)
    unit, body = _unit(unit_id, who)
    try:
        return renderings.braille(unit, body["body"]["guardian"], grade, lang)
    except Exception as error:
        raise HTTPException(status_code=503, detail=f"Braille is not available here: {error}") from error


@router.get("/unit/{unit_id:path}/picture")
def picture(unit_id: str, person_id: str, organisation: str | None = None) -> dict:
    """
    An illustration drawn from the unit's words, as a memory aid. Drawn once per version of
    the unit, and only if it holds no writing (apu/modality/picture.py).
    """
    who = _who(person_id, organisation)
    found, _ = _unit(unit_id, who)
    kept = renderings.picture_kept(found, organisation=who.organisation)
    if kept:
        return {**kept, "cached": True}
    if meter.meter().level() != "ok":
        # Heavy work deferred near a ceiling (docs/decisions/0007): said, not failed.
        return {"deferred": True, "detail": "Illustrations are paused for now; the words are all here."}
    try:
        return renderings.picture(found, organisation=who.organisation)
    except pictures.PictureUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.get("/unit/{unit_id:path}")
def unit(unit_id: str, person_id: str, organisation: str | None = None) -> dict:
    """A unit, what it rests on, its sources, and its quiz questions without their answers."""
    who = _who(person_id, organisation)
    found, body = _unit(unit_id, who)
    by_id = {u["unit_id"]: u for u in body["units"]}
    prerequisites = [by_id[link["source_id"]] for link in body["links"]
                     if link["type"] == "PREREQUISITE_OF" and link["target_id"] == unit_id]
    quiz = [{"case_id": c["case_id"], "question": for_learner(c["question"], c["by"]), "kind": c["kind"]}
            for c in body["cases"] if unit_id in c["decides"] and a_learner_can_answer(c)]
    _remember(who, body["body"]["body_id"], on=unit_id)
    return {"unit": found, "guardian": body["body"]["guardian"], "body": body["body"],
            "prerequisites": [{"unit_id": p["unit_id"], "text": p["text"]} for p in prerequisites],
            "sources": [s for s in body["sources"] if s["unit_id"] == unit_id], "quiz": quiz,
            # The passages of the guardian's own documents this part rests on, at its level.
            "evidence": [e for e in body.get("evidence", []) if e["unit_id"] == unit_id],
            "progress": get_progress().states(who.organisation, who.person_id, [unit_id])[unit_id],
            "picture": renderings.picture_kept(found, organisation=who.organisation) is not None, "simulated": access.SIMULATED}


class QuizBody(BaseModel):
    person_id: str
    organisation: str | None = None
    case_id: str
    answer: bool | None = None      # a key or a button
    said: str | None = None         # typed or transcribed
    audio: str | None = None        # a recording, transcribed here


@router.post("/quiz")
def quiz(body: QuizBody) -> dict:
    """One case, answered. Graded by code against the guardian's decision, in their words."""
    who = _who(body.person_id, body.organisation)
    found = _body(body.case_id.split(":", 1)[0], who)
    case = next((c for c in found["cases"] if c["case_id"] == body.case_id and a_learner_can_answer(c)), None)
    if case is None:
        raise HTTPException(status_code=404, detail="No such question.")
    given, heard = body.answer, body.said
    if given is None:
        if not heard and body.audio:
            try:
                heard = voice.transcribe(base64.b64decode(body.audio))
            except voice.VoiceUnavailable as error:
                raise HTTPException(status_code=503, detail=str(error)) from error
        given = heard_yes_no(heard or "")
    if given is None:
        return {"understood": False, "heard": heard, "simulated": access.SIMULATED}
    right = given == case["applies"]
    for uid in case["decides"]:
        get_progress().review(who.organisation, who.person_id, uid, 3 if right else 1)
    if not right:
        _remember(who, found["body"]["body_id"], hard={"unit_id": case["decides"][0], "text": case["question"], "why": "answered"})
    return {"understood": True, "right": right, "expected": case["applies"], "heard": heard,
            "by": case["by"], "said": case["said"], "simulated": access.SIMULATED}


def _decided(found: dict) -> list[dict]:
    """The cases with a yes or no answer, in the order of the path's units they decide."""
    units, _ = ordered(found["units"], found["links"])
    place = {u["unit_id"]: i for i, u in enumerate(units)}
    cases = [c for c in found["cases"] if a_learner_can_answer(c)]
    return sorted(cases, key=lambda c: min((place.get(u, len(place)) for u in c["decides"]), default=len(place)))


@router.get("/exam/{body_id}")
def exam(body_id: str, person_id: str, organisation: str | None = None) -> dict:
    """
    Every case the guardian decided that this person may see, without the answers.

    The hard ones by construction: the boundary, the source the guardian overruled, the case
    almost but not quite inside the rule. Answered all at once, then marked, so no answer
    is seen before the last question.
    """
    who = _who(person_id, organisation)
    found = _body(body_id, who)
    return {"body": found["body"], "simulated": access.SIMULATED,
            "cases": [{"case_id": c["case_id"], "question": for_learner(c["question"], c["by"]), "kind": c["kind"],
                       "rests_on": _unlearned_before(found, list(c["decides"]), who)}
                      for c in _decided(found)]}


class ExamBody(BaseModel):
    person_id: str
    organisation: str | None = None
    answers: dict[str, bool | None]     # case id -> yes, no, or not answered


@router.post("/exam/{body_id}")
def mark_exam(body_id: str, body: ExamBody) -> dict:
    """
    Marked by code against the guardian's decisions, explained in their words. A part with a
    wrong answer comes back for review soon (FSRS "again"); one answered right is "good".
    """
    who = _who(body.person_id, body.organisation)
    found = _body(body_id, who)
    feedback, outcome = [], {}
    for case in _decided(found):
        given = body.answers.get(case["case_id"])
        right = given is not None and given == case["applies"]
        for uid in case["decides"]:
            outcome[uid] = outcome.get(uid, True) and right
        feedback.append({"case_id": case["case_id"], "question": for_learner(case["question"], case["by"]),
                         "right": right,
                         "answered": given, "expected": case["applies"], "by": case["by"],
                         "said": case["said"], "decides": case["decides"]})
    visible = {u["unit_id"] for u in found["units"]}
    for uid, right in outcome.items():
        if uid in visible:
            get_progress().review(who.organisation, who.person_id, uid, 3 if right else 1)
    return {"correct": sum(f["right"] for f in feedback), "total": len(feedback), "feedback": feedback,
            "simulated": access.SIMULATED}


class ReviewBody(BaseModel):
    person_id: str
    organisation: str | None = None
    unit_id: str
    rating: int


@router.post("/review")
def review(body: ReviewBody) -> dict:
    """How well this person recalled the unit: 1 again, 2 hard, 3 good, 4 easy (FSRS)."""
    who = _who(body.person_id, body.organisation)
    found, whole = _unit(body.unit_id, who)
    if body.rating <= 2:
        _remember(who, whole["body"]["body_id"], hard={"unit_id": body.unit_id, "text": found["text"], "why": "rated"})
    try:
        return {**get_progress().review(who.organisation, who.person_id, body.unit_id, body.rating), "simulated": access.SIMULATED}
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


class AskBody(BaseModel):
    person_id: str
    organisation: str | None = None
    body_id: str
    question: str
    lang: str = "en"
    unit_id: str | None = None       # the part in view: the tutor answers from it first


class HearBody(BaseModel):
    person_id: str
    organisation: str | None = None
    audio: str                       # base64 wav, when the live words did not come


@router.post("/hear")
def hear(body: HearBody) -> dict:
    """
    A question said aloud, to its words, when the live words did not come. Measured in a live
    run: every piece of speech went to the live relay as "undefined", and a learner who asked
    aloud was told to type instead, the recording thrown away. Metered as hearing (apu/meter.py).
    """
    _who(body.person_id, body.organisation)
    try:
        return {"said": voice.transcribe(base64.b64decode(body.audio))}
    except voice.VoiceUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


def _write_back_mmu(who: access.Person, question: str, reply_text: str, body_id: str | None = None) -> None:
    """Update the learner's MMU after the HTTP reply is sent, on the knowledge it was asked on: written in the
    background, it is not left to whichever knowledge is in view by then."""
    principal = meter.Principal(who.organisation, who.person_id, who.role)
    with meter.acting_as(principal):
        get_learner_mmu().write_back(who.organisation, who.person_id, question, reply_text, knowledge_id=body_id)


@router.post("/ask")
def ask(body: AskBody, background_tasks: BackgroundTasks = None) -> dict:
    """A question to the guardian's knowledge: guarded on the way in, faithful on the way out."""
    who = _who(body.person_id, body.organisation)
    found = _body(body.body_id, who)
    question = body.question.strip()[:1000]
    if not question:
        raise HTTPException(status_code=422, detail="Nothing was asked.")
    try:
        verdict = guard.check(question, body_id=body.body_id, body_name=found["body"]["name"],
                              covers=[u["text"] for u in found["units"]], language=body.lang,
                              session=who.person_id)
    except guard.GuardUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    if verdict.turn is None:
        # Off the topic, or distress: answered before any quota, so distress is never stopped.
        return {"kind": verdict.outcome.value, "text": verdict.reply, "citations": [],
                "simulated": access.SIMULATED}
    budget = meter.meter().grant("questions", 1)          # refused plainly, as a 429 (server.py)
    meter.meter().record(budget)
    version, cache = found["body"].get("version", 0), get_answers()
    kept = cache.get(who.organisation, body.body_id, version, who.allowed, question, body.lang)
    if kept:
        return {**kept, "cached": True, "warning": budget.warning, "simulated": access.SIMULATED}
    mmu = get_learner_mmu()
    _, mmu_context, _ = mmu.tutor_turn(who.organisation, who.person_id, body.body_id, question)
    memory_context = mmu_context.get("text", "").strip()
    result = answering.answer(verdict.turn, question=question, body_id=body.body_id, allowed=who.allowed,
                              store=get_reader(who.organisation), questions=for_learners(who.organisation),
                              guardian=found["body"]["guardian"], language=body.lang, step=meter.meter().level(),
                              focus=body.unit_id, memory_context=memory_context)
    # Only a worded answer, checked against the guardian's words and worded without a person's
    # MMU memory, is kept in the shared cache. Measured: answers given in the guardian's words
    # while the model was refused were cached, and kept being served after the model came back,
    # one of them quoting the wrong passage; and an answer worded with Sabine's MMU memory was
    # served from the cache to Ezekias.
    if result["kind"] == "worded":
        cache.put(who.organisation, body.body_id, version, who.allowed, question, body.lang, result,
                  memory_context=memory_context)
    path_info = _on_the_path(found, result, who, body)
    if background_tasks is not None:
        background_tasks.add_task(_write_back_mmu, who, question, result.get("text", ""), body.body_id)
    else:
        _write_back_mmu(who, question, result.get("text", ""), body.body_id)
    return {**result, **path_info, "warning": budget.warning, "simulated": access.SIMULATED}


def _on_the_path(found: dict, result: dict, who: access.Person, body: AskBody) -> dict:
    """What the tutor brings of the path into the conversation: the parts the answer rests on
    that are not learned yet (reminded, never enforced), the reviews due, a case to try."""
    cited = [c["unit_id"] for c in result.get("citations", [])]
    states = get_progress().states(who.organisation, who.person_id, [u["unit_id"] for u in found["units"]])
    due = sum(1 for s in states.values() if s["state"] == "due")
    focus = body.unit_id or (cited[0] if cited else None)
    case = next((c for c in found["cases"] if focus in c["decides"] and a_learner_can_answer(c)), None)
    _remember(who, body.body_id, asked={"question": body.question.strip()[:300], "unit_id": focus,
                                        "kind": result.get("kind")})
    return {"rests_on_unlearned": _unlearned_before(found, cited, who) if cited else [], "due": due,
            "try_case": {"case_id": case["case_id"], "question": for_learner(case["question"], case["by"])} if case else None}


class TicketsBody(BaseModel):
    tickets: list[str]


@router.post("/tickets")
def tickets(body: TicketsBody) -> dict:
    """
    Where a learner's own questions stand. No person is named: the ticket, kept on their
    device, is the only thing that ties a question to whoever asked it.
    """
    return {"tickets": follow_tickets(body.tickets)}


# ── the notebook, the session, and the modes ────────────────────────────────

@router.get("/session/{body_id}")
def session(body_id: str, person_id: str, organisation: str | None = None) -> dict:
    """Where this learner was on this knowledge, what they asked, what they found hard."""
    who = _who(person_id, organisation)
    _body(body_id, who)
    return {**get_learner_memory().load(who.organisation, who.person_id, body_id), "simulated": access.SIMULATED}


class KeepBody(BaseModel):
    person_id: str
    organisation: str | None = None
    body_id: str
    kind: str                       # whole, key_points or excerpt
    text: str = ""                  # the answer whole, or the excerpt chosen
    question: str = ""
    unit_ids: list[str] = []        # the parts the answer cites


@router.post("/notebook")
def keep(body: KeepBody) -> dict:
    """
    Keep an answer whole, its key points, or an excerpt. Key points are the guardian's own
    parts the answer cites, read from the library at this person's levels: never a summary a
    model wrote, and never a part this person may not see.
    """
    who = _who(body.person_id, body.organisation)
    found = _body(body.body_id, who)
    visible = {u["unit_id"]: u for u in found["units"]}
    cited = [visible[uid] for uid in body.unit_ids if uid in visible]
    if body.kind == "key_points":
        if not cited:
            raise HTTPException(status_code=422, detail="Key points come from the parts an answer cites.")
        text = "\n".join(f"- {u['text']}" for u in cited)
    elif body.kind in ("whole", "excerpt"):
        text = body.text.strip()[:4000]
        if not text:
            raise HTTPException(status_code=422, detail="Nothing to keep.")
    else:
        raise HTTPException(status_code=422, detail="Kept whole, as key points, or as an excerpt.")
    entry = get_learner_memory().keep(who.organisation, who.person_id, {
        "body_id": body.body_id, "kind": body.kind, "text": text, "question": body.question.strip()[:300],
        "cites": [{"unit_id": u["unit_id"], "quote": u["quote"]} for u in cited]})
    return {"entry": entry, "simulated": access.SIMULATED}


@router.get("/notebook")
def notebook(person_id: str, body_id: str | None = None, organisation: str | None = None) -> dict:
    who = _who(person_id, organisation)
    return {"entries": get_learner_memory().entries(who.organisation, who.person_id, body_id), "simulated": access.SIMULATED}


@router.delete("/notebook/{entry_id}")
def forget_entry(entry_id: str, person_id: str, organisation: str | None = None) -> dict:
    who = _who(person_id, organisation)
    return {"forgotten": get_learner_memory().forget(who.organisation, who.person_id, entry_id)}


@router.get("/memory")
def remembered(person_id: str, organisation: str | None = None, body_id: str | None = None) -> dict:
    """What Urithi remembers about this learner, as they can read it: each block's words, which knowledge it is
    about, what they said that it came from, and whether it reaches answers on this knowledge."""
    who = _who(person_id, organisation)
    return {"blocks": get_learner_mmu().blocks(who.organisation, who.person_id, knowledge_id=body_id),
            "simulated": access.SIMULATED}


@router.delete("/memory/{block_id}")
def forget_remembered(block_id: str, person_id: str, organisation: str | None = None) -> dict:
    """The learner removes one thing remembered about them; it no longer reaches any answer."""
    who = _who(person_id, organisation)
    return {"forgotten": get_learner_mmu().forget_block(who.organisation, who.person_id, block_id)}


@router.get("/notebook/sheet/{body_id}")
def revision_sheet(body_id: str, person_id: str, organisation: str | None = None, grade: int = 2,
                   lang: str = "en") -> dict:
    """The notebook of one knowledge as a revision sheet: on screen, and on braille pages."""
    from apu.modality.braille.sheet import braille_sheet
    from apu.modality.braille.translator import BrailleGrade

    who = _who(person_id, organisation)
    found = _body(body_id, who)
    entries = get_learner_memory().entries(who.organisation, who.person_id, body_id)
    lines = [found["body"]["name"], ""]
    for entry in entries:
        if entry.get("question"):
            lines.append(entry["question"])
        lines.extend([entry["text"], ""])
    text = "\n".join(lines).strip()
    try:
        sheet = braille_sheet(text, grade=BrailleGrade(grade if grade in (1, 2) else 2),
                              language="fr" if lang == "fr" else "en")
        pages = [list(page) for page in sheet.pages_unicode]
    except Exception:
        pages = []            # no braille on this machine: the sheet on screen still serves
    return {"text": text, "entries": len(entries), "braille_pages": pages, "simulated": access.SIMULATED}


class SayBody(BaseModel):
    person_id: str
    organisation: str | None = None
    text: str


@router.post("/say")
def say(body: SayBody) -> dict:
    """An answer read aloud, for a learner without a screen: a sentence or three, never a free
    speech service (metered in characters, refused past 600)."""
    who = _who(body.person_id, body.organisation)
    text = body.text.strip()
    if not text or len(text) > 600:
        raise HTTPException(status_code=422, detail="Up to 600 characters are read aloud at once.")
    del who                                                    # identified: the meter counts this person
    try:
        spoken = voice.synthesize(text, compressed=True)
    except voice.VoiceUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return {"audio": base64.b64encode(spoken.data).decode("ascii"), "mime": spoken.mime_type,
            "words": list(spoken.words), "text": text}


class BrailleTextBody(BaseModel):
    person_id: str
    organisation: str | None = None
    text: str
    grade: int = 2
    lang: str = "en"


@router.post("/braille")
def braille_text(body: BrailleTextBody) -> dict:
    """An answer on braille pages, for a learner who reads with their fingers (liblouis, local, free)."""
    from apu.modality.braille.sheet import braille_sheet
    from apu.modality.braille.translator import BrailleGrade

    _who(body.person_id, body.organisation)
    text = body.text.strip()
    if not text or len(text) > 2000:
        raise HTTPException(status_code=422, detail="Up to 2,000 characters at once.")
    try:
        sheet = braille_sheet(text, grade=BrailleGrade(body.grade if body.grade in (1, 2) else 2),
                              language="fr" if body.lang == "fr" else "en")
    except Exception as error:
        raise HTTPException(status_code=503, detail=f"Braille is not available here: {error}") from error
    return {"pages": [list(page) for page in sheet.pages_unicode], "brf": sheet.brf}
