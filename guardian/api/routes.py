"""The apprentice's HTTP surface.

HTTP rather than a websocket, deliberately. The apprentice looks at one frame every couple
of seconds and speaks a few times in a session; a request per observation is simpler to
reason about, simpler to retry, and leaves the websocket to the thing that actually needs
one, which is live audio.

Nothing here decides anything on the expert's behalf. Every route returns what the
apprentice noticed or wants to ask; the page shows it and a person answers.

Every route is a guardian's, and a map is its own guardian's alone: `person_id` names who is
asking (simulated, from the registry), and a map in the path or the body must be theirs.
Measured in the step 0 review: none of these routes asked who was there, so a learner could
read any guardian's draft, answer its cases, and confirm it, which is what opens publishing.
"""

import base64
import dataclasses
import functools
import re
import threading
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel

from apu import meter
from apu.logger import get_logger
from apu.modality import voice
from guardian.engine import (
    absorb,
    braille,
    commands,
    probe,
    provenance,
    questions,
    vision,
    wording,
)
from guardian.engine.tutor import mastery, review
from guardian.engine.workmap import Guardrail, MapChanged, Ruling, Step
from guardian.memory.store import get_maps, get_sessions, map_lock
from guardian.memory.working import get_working
from library import access

logger = get_logger("apprentice")


async def _a_guardian(request: Request, person_id: str | None = None,
                      organisation: str | None = None) -> access.Person:
    """A guardian of the organisation acted in, and when a map is named, that map's guardian
    in that map's organisation. Refused otherwise, plainly."""
    try:
        who = access.require_guardian(person_id, organisation=organisation)
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    map_id = request.path_params.get("map_id")
    if map_id is None and request.method == "POST":
        try:
            found = await request.json()
            map_id = found.get("map_id") if isinstance(found, dict) else None
        except ValueError:
            map_id = None
    if map_id:
        work_map = get_maps().load(map_id)
        if work_map is not None and (work_map.expert != who.name or work_map.organisation != who.organisation):
            raise HTTPException(status_code=403, detail=f"This map is {work_map.expert}'s, not {who.name}'s.")
    request.state.guardian = who
    meter.act_as(meter.Principal(who.organisation, who.person_id, who.role))
    return who


router = APIRouter(prefix="/api/guardian", dependencies=[Depends(_a_guardian)])


def writes_map(route):
    """A route that loads a map and saves it does both under the map's lock, so two requests never write
    one over the other; a map saved meanwhile by another process is refused, said plainly, never
    overwritten. Found in the review of 2026-10-14: the map was written back whole, the last one winning."""
    @functools.wraps(route)
    def held(*args, **kwargs):
        body = kwargs.get("body", args[0] if args else None)
        with map_lock(str(getattr(body, "map_id", "") or "")):
            try:
                return route(*args, **kwargs)
            except MapChanged as error:
                raise HTTPException(status_code=409, detail="This knowledge changed meanwhile, and nothing was "
                                                            "written over it: say it again.") from error
    return held


def _session(map_id: str) -> dict:
    """The session in progress for a map, from the session store (guardian/memory/store.py)."""
    return get_sessions().get(map_id, lambda: {
        "detector": questions.PauseDetector(),
        "fields": [],
        "field_at": {},
        "last_question_at": -999.0,
        "pending": None,
        "observations": [],
        "captured_steps": [],
        "recent_words": [],
        # Frames arrive every two seconds and a vision call takes longer than that, so two
        # observations run at once. Both used to see "nothing pending" and both asked:
        # measured, the same question twice, two seconds apart. Deciding is one at a time.
        "lock": threading.Lock(),
    })


def _voiced(text: str) -> dict:
    """The words as audio, with when each word is said, for the teleprompter; no audio and no
    words when speech fails. A silent apprentice is still a usable one."""
    try:
        audio = voice.synthesize(text)
        data = voice.wav_from_pcm(audio.data) if audio.mime_type.startswith("audio/l16") else audio.data
        return {"audio": base64.b64encode(data).decode("ascii"), "words": list(audio.words)}
    except Exception as error:
        logger.warning("The apprentice could not speak: %s", error)
        return {"audio": None, "words": []}


def _spoken(text: str) -> str | None:
    """The words as audio alone, or None."""
    return _voiced(text)["audio"]


def _record_class_moment(background_tasks: BackgroundTasks | None, organisation: str,
                         guardian_id: str, map_id: str, **moment) -> None:
    """Update the guardian's MMU after the HTTP reply is sent."""
    principal = meter.Principal(organisation, guardian_id.lower(), "guardian")

    def _run() -> None:
        from guardian.memory.mmu import get_guardian_mmu

        with meter.acting_as(principal):
            get_guardian_mmu().record_class_moment(organisation, guardian_id, map_id, **moment)

    if background_tasks is not None:
        background_tasks.add_task(_run)
    else:
        _run()


def _known_guardrails(work_map, memory=None) -> list[Guardrail]:
    """Rules already saved in work_map plus rules noted in working memory."""
    if memory is None:
        memory = get_working().load(work_map.organisation, work_map.map_id)
    known = list(work_map.guardrails)
    seen_ids = {g.guardrail_id for g in known}
    for block in memory.of_kind("retained", "rule-"):
        c = block.get("content") or {}
        gid = str(c.get("guardrail_id") or block["ref"].removeprefix("rule-"))
        if gid and gid not in seen_ids and c.get("when") and c.get("then"):
            seen_ids.add(gid)
            known.append(
                Guardrail(
                    guardrail_id=gid,
                    when=str(c["when"]),
                    then=str(c["then"]),
                    quote=str(c.get("quote") or c["then"]),
                    asked_at=float(c.get("asked_at", 0.0)),
                    severity=str(c.get("severity") or "check"),
                    said_at=str(c.get("said_at") or ""),
                    cites=tuple(c.get("cites") or ()),
                )
            )
    return known


def _notes_and_proposals(memory) -> tuple[list[dict], list[dict], list[dict]]:
    """Return (notes, noted_rules, proposals) from working memory."""
    notes = [b["content"] for b in memory.of_kind("recent", "note-") if isinstance(b.get("content"), dict)]
    noted_rules = [b["content"] for b in memory.of_kind("retained", "rule-") if isinstance(b.get("content"), dict)]
    proposals = [b["content"] for b in memory.of_kind("open", "proposal-") if isinstance(b.get("content"), dict)]
    return notes, noted_rules, proposals


def _refresh_proposals(work_map, memory, *, use_model: bool = True) -> list[dict]:
    """Decision 0016: re-read the guardian's notes and replace open note/rule proposals with
    at most what forms knowledge (one step with its reason, and/or one rule)."""
    notes, noted_rules, existing = _notes_and_proposals(memory)
    edited_by_id = {
        str(p.get("proposal_id") or ""): dict(p)
        for p in existing
        if isinstance(p, dict) and p.get("edited")
    }
    # A rule the guardian stated stays proposed until they save, ignore or forget it; only the
    # step proposal is judged again. Measured live: each new rule said replaced the one before,
    # and a rule said after a passed question was never offered at all.
    ignored = {str(v) for b in memory.of_kind("retained", "ignored-")
               for v in ((b.get("content") or {}).get("proposal_id"), (b.get("content") or {}).get("guardrail_id")) if v}
    # A proposal the guardian changed is theirs now: it stays until saved, ignored or forgotten.
    # Found in the review of 2026-10-14: an edited step was dropped here and its wording lost
    # whenever the judge chose another note.
    kept_rules = set()
    judged = absorb.judge_proposals(work_map, notes, noted_rules, use_model=use_model)
    out: list[dict] = []
    with memory.derived():
        for p in existing:
            if not isinstance(p, dict):
                continue
            if p.get("origin") == "rule":
                kept_rules.add(str(p.get("guardrail_id") or p.get("proposal_id") or ""))
            elif p.get("origin") in ("tell", "answer", "note") and not p.get("edited"):
                pid_old = str(p.get("proposal_id") or "")
                if pid_old:
                    memory.drop(f"proposal-{pid_old}")
        for prop in judged:
            pid_new = str(prop.get("proposal_id") or "")
            if pid_new in ignored or str(prop.get("guardrail_id") or "") in ignored:
                continue
            if prop.get("kind") == "rule" and str(prop.get("guardrail_id") or pid_new) in kept_rules:
                continue
            if pid_new in edited_by_id:
                out.append(edited_by_id[pid_new])
                continue
            memory.put("open", f"proposal-{pid_new}", prop)
            out.append(prop)
    return out


def _map_with_notes(
    work_map,
    memory,
    current_step: Step | None = None,
    current_rails: list[Guardrail] | tuple[Guardrail, ...] = (),
):
    """View of work_map including what the guardian has already said in notes and noted rules."""
    steps = list(work_map.steps)
    seen_reasons = {s.reason.strip() for s in steps if s.reason.strip()}
    notes, _, _ = _notes_and_proposals(memory)
    for n in reversed(notes):
        text = str(n.get("text") or n.get("reason") or "").strip()
        if not text or text in seen_reasons:
            continue
        rules_n = n.get("rules") or ()
        if n.get("kind") == "answer" or absorb.is_teaching_note(text, has_rules=bool(rules_n)):
            seen_reasons.add(text)
            steps.append(
                Step(
                    step_id=f"s-note-{len(steps) + 1}",
                    number=len(steps) + 1,
                    title=str(n.get("title") or absorb.title_for(text, "", limit=140)),
                    screen_moment=float(n.get("at", 0.0)),
                    observed=str(n.get("observed") or n.get("title") or ""),
                    decision=str(n.get("title") or ""),
                    reason=text,
                )
            )
    if current_step is not None and current_step.reason.strip() not in seen_reasons:
        if (
            current_step.observed != current_step.title
            or absorb.is_teaching_note(current_step.reason, has_rules=bool(current_rails))
        ):
            steps.append(dataclasses.replace(current_step, number=len(steps) + 1))
    known_rails = _known_guardrails(work_map, memory)
    rail_ids = {r.guardrail_id for r in known_rails}
    for r in current_rails:
        if r.guardrail_id not in rail_ids:
            known_rails.append(r)
            rail_ids.add(r.guardrail_id)
    return dataclasses.replace(work_map, steps=steps, guardrails=known_rails)


def _store_step_proposal(
    work_map,
    memory,
    step: Step,
    rails: list[Guardrail],
    origin: str = "teach",
    proposal_id: str | None = None,
) -> tuple[dict | None, dict]:
    """Decision 0016: record what Urithi heard/saw as a note and a pending proposal in working
    memory, never in work_map. Only the guardian's explicit save writes to work_map."""
    pid = proposal_id or uuid.uuid4().hex[:10]
    rules_dicts = [
        {
            "guardrail_id": r.guardrail_id,
            "when": r.when,
            "then": r.then,
            "severity": r.severity,
            "quote": r.quote,
            "at": r.asked_at,
            "said_at": r.said_at,
            "step_said_at": step.said_at,
            "cites": list(step.cites or r.cites or ()),
        }
        for r in rails
    ]
    cites_list = list(step.cites or ())
    proposal = {
        "proposal_id": pid,
        "kind": "step",
        "origin": origin,
        "number": step.number,
        "title": step.title,
        "reason": step.reason,
        "observed": step.observed,
        "decision": step.decision,
        "at": step.screen_moment,
        "said_at": step.said_at,
        "rules": rules_dicts,
        "guardrails": rules_dicts,
        "cites": cites_list,
    }
    note = {
        "note_id": pid,
        "kind": origin,
        "text": step.reason,
        "title": step.title,
        "observed": step.observed,
        "decision": step.decision,
        "at": step.screen_moment,
        "said_at": step.said_at,
        "rules": rules_dicts,
        "cites": cites_list,
    }
    memory.put("recent", f"note-{pid}", note)
    memory.put("recent", "said", {"text": step.reason, "step": step.number, "said_at": step.said_at})
    for r_dict in rules_dicts:
        memory.put("retained", f"rule-{r_dict['guardrail_id']}", r_dict)
    if origin not in ("tell", "answer"):
        memory.put("open", f"proposal-{pid}", proposal)
        return proposal, note
    has_rules = bool(rules_dicts)
    if not absorb.is_teaching_note(step.reason, has_rules=has_rules) and not has_rules:
        return None, note
    refreshed = _refresh_proposals(work_map, memory, use_model=True)
    if has_rules:
        # Every rule the guardian states here is proposed, whatever the judge picked: a rule said is
        # knowledge offered, until it is saved, ignored or forgotten.
        ignored = {str(v) for b in memory.of_kind("retained", "ignored-")
                   for v in ((b.get("content") or {}).get("proposal_id"), (b.get("content") or {}).get("guardrail_id")) if v}
        open_rule_ids = {str((b.get("content") or {}).get("guardrail_id") or "")
                         for b in memory.of_kind("open", "proposal-")}
        saved_ids = {g.guardrail_id for g in work_map.guardrails}
        chosen = None
        for r_dict in rules_dicts:
            gid = str(r_dict["guardrail_id"])
            if gid in ignored or gid in saved_ids:
                continue
            if gid not in open_rule_ids:
                made = absorb._build_rule_proposal(r_dict, rules_dicts, work_map.language)
                memory.put("open", f"proposal-{made['proposal_id']}", made)
                open_rule_ids.add(gid)
            chosen = chosen or next((b.get("content") for b in memory.of_kind("open", "proposal-")
                                     if str((b.get("content") or {}).get("guardrail_id") or "") == gid), None)
    else:
        chosen = next((p for p in refreshed if p.get("kind") == "step"), None)
    return chosen, note


class StartBody(BaseModel):
    task: str
    expert: str | None = None  # who is teaching is who is asking; a name sent is not trusted
    language: str = "en"       # what the guardian teaches in: "en" or "fr"


@router.post("/start")
def start(body: StartBody, request: Request) -> dict:
    who = request.state.guardian
    work_map = get_maps().new(body.task, who.name, wording.language_of(body.language), organisation=who.organisation)
    get_maps().save(work_map)
    _session(work_map.map_id)
    return {"map_id": work_map.map_id, "task": work_map.task, "expert": work_map.expert,
            "language": work_map.language}


def _said_now(rails: list) -> tuple[str, list]:
    """When it was said, stamped on the step and the rules it holds (see workmap.Guardrail)."""
    now = datetime.now(UTC).isoformat()
    return now, [dataclasses.replace(r, said_at=now) for r in rails]


class ObserveBody(BaseModel):
    map_id: str
    at: float
    frame: str | None = None     # base64 jpeg, without the data: prefix
    typing: bool = False
    talking: bool = False
    scrolling: bool = False
    silent: bool | None = None   # P2: keep questions for the debrief instead of asking aloud
    source: str = "screen"       # P3: "screen" or "camera" (gestures, objects, whiteboard, face blurring)
    camera_warned: bool = False  # P3: guardian warned when browser cannot blur faces before upload
    blurred_on_page: bool = False


@router.post("/observe")
def observe(body: ObserveBody, background_tasks: BackgroundTasks = None) -> dict:
    """
    One moment of the session: what the screen shows, and what the expert is doing.

    Returns a question only when there is a real pause and a real gap to close. Most calls
    return nothing, which is the point: an apprentice that speaks every two seconds is an
    interruption with a microphone.
    """
    work_map = get_maps().load(body.map_id)
    if work_map is None:
        return {"error": "No such session."}
    session = _session(body.map_id)
    # A class ended and another begun on the same map: its clock starts again at 0. Measured in
    # a live run: the question left unanswered and the time of the last question, both from the
    # class before, kept the new class from asking anything. A clock gone back is a new class.
    if body.at < session.get("last_at", -1.0):
        session.update(detector=questions.PauseDetector(), fields=[], field_at={}, last_question_at=-999.0,
                       pending=None, observations=[], captured_steps=[], last_judged=None,
                       asked=[], asked_questions=[])
        vision.forget(body.map_id)
    session["last_at"] = body.at
    session["source"] = body.source

    if body.source == "camera":
        if body.camera_warned or body.blurred_on_page:
            session["camera_warned"] = True
        if not session.get("camera_warned"):
            return {"watching": True, "change": None, "warning": "camera_unwarned", "unwarned_camera": True}

    session["detector"].update(questions.Activity(
        at=body.at, typing=body.typing, talking=body.talking, scrolling=body.scrolling))

    if not body.frame:
        change = None
    elif body.source == "camera":
        change = vision.what_changed(body.frame, body.map_id, body.at, source="camera")
    else:
        change = vision.what_changed(body.frame, body.map_id, body.at)
    if change:
        session["observations"].append(change)
        if change.field:
            # One edit, however many frames it spans: a field counts again only after a
            # pause in changing it, so typing a name is not "changed it twice".
            last = session["field_at"].get(change.field)
            if last is None or body.at - last > questions.SAME_EDIT_SECONDS:
                session["fields"].append(change.field)
            session["field_at"][change.field] = body.at

    if change:
        logger.info("Saw at %.1fs: %s", body.at, change.changed)
        # What the class captured goes to the working memory, to be validated (step 4).
        memory = get_working().load(work_map.organisation, work_map.map_id)
        memory.put("recent", "saw", {"changed": change.changed, "field": change.field, "at": body.at})
        get_working().save(work_map.organisation, work_map.map_id, memory)
    if body.silent is not None:
        session["silent"] = bool(body.silent)
    with session["lock"]:
        question = _question_if_due(work_map, session, body.at, change, background_tasks=background_tasks)
    if question is None:
        return {"watching": True, "change": change.changed if change else None}
    kind, latest, text, importance, why, deferred = question
    if deferred:
        return {"watching": True, "deferred": text, "kind": kind.value, "importance": importance,
                "why": why, "change": change.changed if change else None}
    logger.info("Asking a %s question at %.1fs: %s", kind.value, body.at, text)
    return {"question": text, "kind": kind.value, "importance": importance, "why": why, "about": latest.changed,
            "change": change.changed if change else None,
            **_voiced(text), "paused_for": session["detector"].paused_for(body.at)}


def _question_if_due(work_map, session: dict, at: float, change,
                     background_tasks: BackgroundTasks | None = None):
    """The question to ask now, or None. Called under the session's lock: checking that
    nothing is pending and marking a question pending are one step, or two frames ask twice."""
    if session["pending"] or not session["detector"].is_pause(at):
        return None
    if at - session["last_question_at"] < questions.MIN_SECONDS_BETWEEN_QUESTIONS:
        return None
    latest = change or (session["observations"][-1] if session["observations"] else None)
    if latest is None or at - latest.at > questions.STALE_SECONDS:
        return None
    if session.get("last_judged") is latest:
        return None
    session["last_judged"] = latest
    memory = get_working().load(work_map.organisation, work_map.map_id)
    notes_check, rules_check, _ = _notes_and_proposals(memory)
    if notes_check or rules_check:
        _refresh_proposals(work_map, memory, use_model=True)
        get_working().save(work_map.organisation, work_map.map_id, memory)
    recent_words = list(session.get("recent_words", []))
    said_block = memory.find("said")
    if said_block and isinstance(said_block.get("content"), dict):
        said_text = str(said_block["content"].get("text", "")).strip()
        if said_text and said_text not in recent_words:
            recent_words.append(said_text)
    effective_map = _map_with_notes(work_map, memory)
    t_judge = time.perf_counter()
    judgment = questions.judge_learner_gap(
        effective_map,
        latest,
        session["fields"],
        tuple(session.setdefault("asked", [])),
        recent_words=tuple(recent_words[-4:]),
        asked_questions=tuple(session.setdefault("asked_questions", [])),
    )
    judge_ms = (time.perf_counter() - t_judge) * 1000.0
    kind, importance, why, text = judgment.kind, judgment.importance, judgment.why, judgment.question
    logger.info(
        "Judged at %.1fs in %.0fms: kind=%s importance=%d",
        at,
        judge_ms,
        kind.value if kind else "none",
        importance,
    )
    if kind is None or not questions.should_ask(
        kind, importance, memory, organisation=work_map.organisation, guardian_id=work_map.expert
    ):
        return None
    _record_class_moment(
        background_tasks,
        work_map.organisation,
        work_map.expert,
        work_map.map_id,
        saw=latest.changed,
        question="" if session.get("silent") else text,
        why=why,
        deferred=text if session.get("silent") else "",
    )
    session["asked"].append(kind)
    session.setdefault("asked_questions", []).append(text)
    session["last_question_at"] = at
    if session.get("silent"):
        next_idx = len(session["asked"])
        while memory.find(f"deferred-{next_idx}") is not None:
            next_idx += 1
        memory.put(
            "open",
            f"deferred-{next_idx}",
            {
                "kind": kind.value,
                "question": text,
                "why": why,
                "about": latest.changed,
                "importance": importance,
                "at": at,
            },
        )
        get_working().save(work_map.organisation, work_map.map_id, memory)
        return kind, latest, text, importance, why, True
    memory.put("open", "question", {"text": text, "kind": kind.value, "importance": importance, "why": why})
    get_working().save(work_map.organisation, work_map.map_id, memory)
    session["last_question_text"] = text
    session["pending"] = {
        "kind": kind.value,
        "observation": latest,
        "asked_at": at,
        "importance": importance,
        "why": why,
        "question": text,
        "source": session.get("source", "screen"),
    }
    return kind, latest, text, importance, why, False


def _answer_pupil(
    work_map,
    session: dict,
    said: str,
    background_tasks: BackgroundTasks | None = None,
) -> dict:
    """Answer a question the guardian put to Urithi, without ever turning it into a step."""
    from guardian.sources.store import get_sources

    memory = get_working().load(work_map.organisation, work_map.map_id)
    if commands.is_save_preview_question(said):
        _refresh_proposals(work_map, memory, use_model=True)
        get_working().save(work_map.organisation, work_map.map_id, memory)
    observations = list(session.get("observations") or [])
    if not observations:
        saw_block = memory.find("saw")
        if saw_block and isinstance(saw_block.get("content"), dict) and saw_block["content"].get("changed"):
            observations.append(
                questions.Observation(
                    at=float(saw_block["content"].get("at", 0.0)),
                    changed=str(saw_block["content"]["changed"]),
                    field=str(saw_block["content"].get("field", "")),
                )
            )
    kept_screens: list[str] = []
    for rec in get_sources().list(work_map.organisation, work_map.map_id):
        for p in rec.get("passages") or ():
            text_p = str(p.get("text") or "").strip()
            if text_p:
                kept_screens.append(text_p)
    for step_item in work_map.steps:
        for cite in step_item.cites or ():
            text_c = str(cite.get("text") or "").strip()
            if text_c and text_c not in kept_screens:
                kept_screens.append(text_c)
    last_q = (
        str((session.get("pending") or {}).get("question") or "").strip()
        or str(session.get("last_question_text") or "").strip()
        or str(((memory.find("question") or {}).get("content") or {}).get("text") or "").strip()
    )
    notes, noted_rules, proposals = _notes_and_proposals(memory)
    previous_qa = tuple(session.get("pupil_qa") or ())
    reply_text = commands.answer_pupil_question(
        work_map,
        said,
        observations=observations,
        kept_screens=kept_screens,
        last_question=last_q,
        notes=notes,
        noted_rules=noted_rules,
        proposals=proposals,
        previous_qa=previous_qa,
    )
    session.setdefault("pupil_qa", []).append((said, reply_text))
    _record_class_moment(
        background_tasks,
        work_map.organisation,
        work_map.expert,
        work_map.map_id,
        said=said,
    )
    return {
        "intent": "ask_pupil",
        "heard": said,
        "answer": reply_text,
        "noted": reply_text,
        "step": None,
        "guardrails": [],
        "proposal": proposals[0] if proposals else None,
        "proposals": proposals,
        "question": None,
        "kind": None,
        **_voiced(reply_text),
        "teachable": work_map.is_teachable,
        "why_not": work_map.why_not_teachable(),
    }


class PassBody(BaseModel):
    map_id: str


@router.post("/pass")
def pass_question(body: PassBody) -> dict:
    """P2: The guardian passes the question; Urithi clears it and raises its learned threshold."""
    work_map = get_maps().load(body.map_id)
    if work_map is None:
        return {"error": "No such session."}
    session = _session(body.map_id)
    pending = session.get("pending")
    if pending is None:
        return {"passed": False, "error": "Nothing was asked."}
    kind = str(pending.get("kind") or "")
    importance = int(pending.get("importance", questions.DEFAULT_THRESHOLD))
    session["pending"] = None
    memory = get_working().load(work_map.organisation, work_map.map_id)
    memory.drop("question")
    new_threshold = questions.record_pass(
        memory, kind, importance, organisation=work_map.organisation, guardian_id=work_map.expert
    )
    get_working().save(work_map.organisation, work_map.map_id, memory)
    return {"passed": True, "kind": kind, "importance": importance, "threshold": new_threshold}


class SilentBody(BaseModel):
    map_id: str
    silent: bool


@router.post("/silent")
def set_silent(body: SilentBody) -> dict:
    """P2: Turn silent classroom mode on or off (questions are kept for the debrief)."""
    work_map = get_maps().load(body.map_id)
    if work_map is None:
        return {"error": "No such session."}
    session = _session(body.map_id)
    session["silent"] = bool(body.silent)
    memory = get_working().load(work_map.organisation, work_map.map_id)
    memory.put("recent", "silent", {"silent": bool(body.silent)})
    get_working().save(work_map.organisation, work_map.map_id, memory)
    return {"silent": bool(body.silent)}


class AnswerBody(BaseModel):
    map_id: str
    said: str | None = None       # already transcribed, when the page did it
    audio: str | None = None      # base64 wav, when it did not


@router.post("/answer")
def answer(body: AnswerBody, background_tasks: BackgroundTasks = None) -> dict:
    """Decision 0016: the guardian's answer is noted and proposed in working memory, never saved
    into work_map until the guardian asks to save it."""
    work_map = get_maps().load(body.map_id)
    session = _session(body.map_id)
    pending = session.get("pending")
    if work_map is None or pending is None:
        return {"error": "Nothing was asked."}

    said = (body.said or "").strip()
    if not said and body.audio:
        try:
            said = voice.transcribe(base64.b64decode(body.audio))
        except meter.Refused:
            raise
        except Exception as error:
            logger.warning("Could not hear the answer: %s", error)
            return {"error": "I could not hear that. Say it again?"}
    if not said:
        return {"error": "Nothing was said."}

    if commands.has_ask_pupil_cue(said) and commands.classify_command(said, language=work_map.language).intent == "ask_pupil":
        return _answer_pupil(work_map, session, said, background_tasks=background_tasks)
    if commands.has_save_cue(said):
        cmd = commands.classify_command(said, language=work_map.language)
        if cmd.intent == "save":
            return _save_from_voice(work_map, cmd.what)

    memory = get_working().load(work_map.organisation, work_map.map_id)
    observation = pending["observation"]
    # Urithi keeps watching while its question waits: the answer is about what the guardian did
    # since, not only the screen when it asked. Measured live: an answer about the date and the
    # channel chosen after the question was titled "Opened: November meetup".
    seen_since = [o for o in session.get("observations", []) if o.at > observation.at]
    if seen_since and pending.get("source", "screen") == "screen":
        observation = seen_since[-1]
    observed_text = observation.changed
    rails = absorb.find_guardrails(said, at=pending["asked_at"], language=work_map.language,
                                   known=_known_guardrails(work_map, memory))
    unconfirmed: list[str] = []
    unconfirmed_script: list[str] = []
    if pending.get("source") == "camera":
        observed_text, unconfirmed_script = absorb.strip_unconfirmed_camera_script(
            observation.changed, said, work_map.language
        )
        rails, unconfirmed = absorb.confirm_camera_rails(
            rails, said, pending.get("camera_text") or observation.changed, work_map.language
        )
        for word in reversed(unconfirmed_script):
            if word not in unconfirmed:
                unconfirmed.insert(0, word)
    said_at, rails = _said_now(rails)
    # A screen the guardian asked Urithi to remember (source_routes.remember): the step and its
    # rules cite it, and the step is named by what they said of it, the screen having no change.
    kept = tuple(pending.get("cites") or ())
    if kept:
        rails = [dataclasses.replace(r, cites=kept) for r in rails]

    step_observed = observed_text or absorb.title_for(said, "", limit=140)
    step = Step(
        step_id=f"s{len(work_map.steps) + 1}",
        number=len(work_map.steps) + 1,
        # What happened, from the screen. It used to be built from her answer, so the
        # title repeated the reason word for word and the step said everything twice.
        # The guardian's words name the step; what the screen showed stays in observed. Measured
        # live: "Event set to Done, Schedule the announcement clicked" titled a step in the tree.
        title=absorb.title_for(said, "", limit=140),
        screen_moment=observation.at,
        observed=step_observed,
        decision=step_observed,
        # Verbatim. The reason is the expert's, and a model that tidies it changes who
        # the new hire is being taught by.
        reason=said,
        guardrail_ids=tuple(r.guardrail_id for r in rails),
        said_at=said_at,
        cites=kept,
    )
    session.setdefault("recent_words", []).append(said)
    next_q = None
    next_kind = None
    if unconfirmed_script or (unconfirmed and not absorb.numbers_in(said)):
        confirm_q = _confirm_camera_value(work_map.language, unconfirmed[0])
        session["pending"] = {
            "kind": "limit",
            "observation": dataclasses.replace(observation, changed=step_observed),
            "asked_at": observation.at,
            "importance": 5,
            "question": confirm_q,
            "source": "camera",
            "cites": kept,
        }
        session["last_question_text"] = confirm_q
    else:
        seen_last = session["observations"][-1] if session.get("observations") else observation
        seen = dataclasses.replace(seen_last, at=observation.at, changed=step_observed)
        heard = questions.Observation(
            at=observation.at, changed=said, scene=seen.scene, screen_fields=seen.screen_fields
        )
        effective_map = _map_with_notes(work_map, memory, current_step=step, current_rails=rails)
        judgment = questions.judge_learner_gap(
            effective_map,
            seen,
            session.get("fields", []),
            tuple(session.setdefault("asked", [])),
            recent_words=tuple(session["recent_words"][-4:]),
            asked_questions=tuple(session.setdefault("asked_questions", [])),
            said=True,
            word_obs=heard,
        )
        if judgment.kind is not None and questions.should_ask(
            judgment.kind,
            judgment.importance,
            memory,
            organisation=work_map.organisation,
            guardian_id=work_map.expert,
        ):
            next_kind = judgment.kind
            next_q = judgment.question
            session["asked"].append(next_kind)
            session.setdefault("asked_questions", []).append(next_q)
            session["last_question_text"] = next_q
            session["pending"] = {
                "kind": next_kind.value,
                "observation": seen,
                "asked_at": observation.at,
                "importance": judgment.importance,
                "why": judgment.why,
                "question": next_q,
                "source": pending.get("source", "screen"),
            }
        else:
            session["pending"] = None
    memory.drop("question")
    proposal, note = _store_step_proposal(work_map, memory, step, rails, origin="answer")
    if next_q and next_kind:
        memory.put("open", "question", {"text": next_q, "kind": next_kind.value})
    get_working().save(work_map.organisation, work_map.map_id, memory)
    _record_class_moment(
        background_tasks,
        work_map.organisation,
        work_map.expert,
        work_map.map_id,
        said=said,
        question=pending.get("question", ""),
    )

    out = {
            "step": None,
            "guardrails": [],
            "proposal": proposal,
            "note": note,
            "question": next_q,
            "kind": next_kind.value if next_kind else None,
            "teachable": work_map.is_teachable,
            "why_not": work_map.why_not_teachable(),
            # Said back, short: in a class the guardian is looking at their own work, not at
            # this page, and hears that the answer was kept.
            "noted": _noted(work_map.language, proposal),
            **_voiced(_noted(work_map.language, proposal))}
    if unconfirmed and session["pending"] is not None:
        out["confirm_value"] = unconfirmed[0]
        out["question"] = session["pending"]["question"]
    return out


def _confirm_camera_value(language: str, value: str) -> str:
    return (
        f"J'ai lu {value} à la caméra : peux-tu confirmer la valeur exacte avant d'en faire une règle ?"
        if language == "fr"
        else f"I read {value} on the camera: can you confirm the exact value before I make it a rule?"
    )


def _noted(language: str, proposal: dict | None = None) -> str:
    """What Urithi says back after taking something from the guardian, and never more than is true:
    nothing is a step until the guardian saves it (docs/decisions/0016). Measured live: "Noted, as
    step 2" was said of proposals nobody had saved."""
    title = str((proposal or {}).get("title") or "").strip().rstrip(".")
    if not title:
        return "Noté. Continue." if language == "fr" else "Noted. Carry on."
    return (f"Proposé : {title}. Dis « garde ça » pour le garder." if language == "fr"
            else f'Proposed: {title}. Say "save this" to keep it.')


class TellBody(BaseModel):
    map_id: str
    said: str | None = None       # typed, or transcribed by the page
    audio: str | None = None      # a recording, transcribed here


class HearBody(BaseModel):
    map_id: str
    audio: str                    # base64 wav, when the live words did not come


@router.post("/hear")
def hear(body: HearBody) -> dict:
    """
    A recording to its words, and nothing else: in a class, what was said decides where it
    goes (an answer, or "remember this"). Measured in a live run: with no live words, the
    recording went straight to be an answer, and "keep the information on the venue" became one.
    """
    try:
        return {"said": voice.transcribe(base64.b64decode(body.audio))}
    except meter.Refused:
        raise
    except Exception as error:
        logger.warning("Could not hear the guardian: %s", error)
        return {"error": "I could not hear that. Say it again?"}


@router.post("/tell")
def tell(body: TellBody, background_tasks: BackgroundTasks = None) -> dict:
    """
    Teaching by conversation, with no screen to watch. Decision 0016: what the guardian says is
    recorded as a note and a pending proposal in working memory; nothing enters work_map until
    the guardian saves it.
    """
    work_map = get_maps().load(body.map_id)
    if work_map is None:
        return {"error": "No such session."}
    session = _session(body.map_id)
    said = (body.said or "").strip()
    if not said and body.audio:
        try:
            said = voice.transcribe(base64.b64decode(body.audio))
        except meter.Refused:
            raise
        except Exception as error:
            logger.warning("Could not hear the guardian: %s", error)
            return {"error": "I could not hear that. Say it again?"}
    if not said:
        return {"error": "Nothing was said."}

    if commands.has_ask_pupil_cue(said) and commands.classify_command(said, language=work_map.language).intent == "ask_pupil":
        return _answer_pupil(work_map, session, said, background_tasks=background_tasks)
    if commands.has_save_cue(said):
        cmd = commands.classify_command(said, language=work_map.language)
        if cmd.intent == "save":
            return _save_from_voice(work_map, cmd.what)

    memory = get_working().load(work_map.organisation, work_map.map_id)
    at = round(time.time() - session.setdefault("started", time.time()), 1)
    rails = absorb.find_guardrails(said, at=at, language=work_map.language, known=_known_guardrails(work_map, memory))
    said_at, rails = _said_now(rails)
    title = absorb.title_for(said, "", limit=140)
    step = Step(step_id=f"s{len(work_map.steps) + 1}", number=len(work_map.steps) + 1, title=title,
                screen_moment=at, observed=title, decision=title, reason=said,
                guardrail_ids=tuple(r.guardrail_id for r in rails), said_at=said_at)

    session.setdefault("recent_words", []).append(said)
    seen_last = session["observations"][-1] if session.get("observations") else None
    seen = questions.Observation(
        at=at,
        changed=title,
        scene=seen_last.scene if seen_last else "",
        screen_fields=seen_last.screen_fields if seen_last else (),
    )
    # Worded from the whole of what was said, not its title: the question names their words.
    heard = questions.Observation(
        at=at,
        changed=said,
        scene=seen.scene,
        screen_fields=seen.screen_fields,
    )
    effective_map = _map_with_notes(work_map, memory, current_step=step, current_rails=rails)
    judgment = questions.judge_learner_gap(
        effective_map,
        seen,
        session.get("fields", []),
        tuple(session.setdefault("asked", [])),
        recent_words=tuple(session["recent_words"][-4:]),
        asked_questions=tuple(session.setdefault("asked_questions", [])),
        said=True,
        word_obs=heard,
    )
    kind = (
        judgment.kind
        if (
            judgment.kind is not None
            and questions.should_ask(
                judgment.kind,
                judgment.importance,
                memory,
                organisation=work_map.organisation,
                guardian_id=work_map.expert,
            )
        )
        else None
    )
    question = judgment.question if kind else None
    if (session.get("pending") or {}).get("from") == "tell":
        session["pending"] = None   # what is said here answers the follow-up /tell asked before
    if question:
        session["asked"].append(kind)
        session.setdefault("asked_questions", []).append(question)
        session["last_question_text"] = question
        if "last_at" in session:
            # In a class, a follow-up is the one question waiting, on the class clock: nothing else is
            # asked over it, and it can be answered or passed like any other. Found in the review of
            # 2026-10-14: it was left unmarked, and the screen asked a second question at once.
            class_at = float(session["last_at"])
            session["last_question_at"] = class_at
            session["pending"] = {
                "kind": kind.value,
                "observation": dataclasses.replace(seen, at=class_at),
                "asked_at": class_at,
                "importance": judgment.importance,
                "why": judgment.why,
                "question": question,
                "source": session.get("source", "screen"),
                "from": "tell",
            }
    # The working memory (guardian/memory/working.py): the question just answered is closed,
    # what was said and the rules noted are kept, and the next question waits on the guardian.
    memory.drop("question")
    proposal, note = _store_step_proposal(work_map, memory, step, rails, origin="tell")
    if question:
        memory.put("open", "question", {"text": question, "kind": kind.value})
    get_working().save(work_map.organisation, work_map.map_id, memory)
    _record_class_moment(
        background_tasks,
        work_map.organisation,
        work_map.expert,
        work_map.map_id,
        said=said,
        question=question or "",
    )
    # A rule or step proposed from these words is said as proposed, like in class (measured live:
    # a rule was proposed and the guardian only heard "Noted. Carry on.").
    noted_msg = _noted(work_map.language, proposal)
    spoken_reply = question or noted_msg
    return {"step": None,
            "guardrails": [],
            "proposal": proposal,
            "note": note,
            "noted": spoken_reply,
            "answer": None if question else noted_msg,
            "question": question, "kind": kind.value if kind else None,
            **_voiced(spoken_reply),
            "teachable": work_map.is_teachable, "why_not": work_map.why_not_teachable()}


class SaveBody(BaseModel):
    map_id: str
    proposal_id: str | None = None
    what: str = ""
    title: str | None = None
    reason: str | None = None


_KIND_SELECTOR_RE = re.compile(
    r"^(?:the|this|that|a|an|la|le|l'|cette|ce|un|une)?\s*"
    r"(?:steps?|rules?|cases?|proposals?|notes?|[ée]tapes?|r[èe]gles?|cas|propositions?|"
    r"first|second|third|last|latest|#?\d)\b",
    re.IGNORECASE,
)


def _item_haystack(item: dict) -> str:
    parts = [
        str(item.get("title") or ""),
        str(item.get("reason") or ""),
        str(item.get("text") or ""),
        str(item.get("when") or ""),
        str(item.get("then") or ""),
        str(item.get("quote") or ""),
    ]
    for r in item.get("rules") or item.get("guardrails") or ():
        if isinstance(r, dict):
            parts.extend([str(r.get("when") or ""), str(r.get("then") or ""), str(r.get("quote") or "")])
    return " ".join(p for p in parts if p).lower()


def _match_proposal_or_note(what: str, items: list[dict]) -> dict | None:
    if not items:
        return None
    ordinal_map = {
        "1": 0, "#1": 0, "first": 0, "1st": 0, "one": 0, "premier": 0, "première": 0, "premiere": 0, "un": 0, "une": 0,
        "2": 1, "#2": 1, "second": 1, "2nd": 1, "two": 1, "deuxième": 1, "deuxieme": 1, "seconde": 1, "deux": 1,
        "3": 2, "#3": 2, "third": 2, "3rd": 2, "three": 2, "troisième": 2, "troisieme": 2, "trois": 2,
    }
    selector_filler = {
        "the", "a", "an", "this", "that", "proposal", "proposals", "one",
        "step", "steps", "rule", "rules", "case", "cases", "note", "notes",
        "la", "le", "l", "cette", "ce", "proposition", "propositions",
        "étape", "etape", "étapes", "etapes", "règle", "regle", "règles", "regles",
        "cas", "numéro", "numero", "number",
    }
    q = (what or "").strip().lower()
    if not q or commands._GENERIC_SAVE_WHAT_RE.match(q):
        return items[0] if len(items) == 1 else None
    if re.search(r"\b(?:last|latest|derni[èe]re|dernier)\b", q):
        return items[0]

    wants_rule = bool(re.search(r"\b(?:rules?|r[èe]gles?)\b", q))
    wants_step = bool(re.search(r"\b(?:steps?|[ée]tapes?)\b", q))
    wants_case = bool(re.search(r"\b(?:cases?|cas)\b", q))
    pool = list(items)
    if wants_rule and not wants_step:
        rule_pool = [it for it in pool if it.get("kind") == "rule" or (it.get("kind") != "step" and it.get("rules"))]
        if not rule_pool:
            rule_pool = [it for it in pool if it.get("rules")]
        if not rule_pool:
            return None
        pool = rule_pool
    elif wants_step and not wants_rule:
        step_pool = [it for it in pool if it.get("kind") == "step" or (not it.get("kind") and not it.get("rules"))]
        if not step_pool:
            return None
        pool = step_pool
    elif wants_case:
        case_pool = [it for it in pool if it.get("kind") == "case"]
        if not case_pool:
            return None
        pool = case_pool

    rem_words = [w for w in re.findall(r"#?[\wÀ-ÿ]+", q) if w not in selector_filler]
    if len(rem_words) == 1 and rem_words[0] in ordinal_map:
        idx = ordinal_map[rem_words[0]]
        if 0 <= idx < len(pool):
            return pool[idx]
        num_str = rem_words[0].lstrip("#")
        for it in pool:
            if str(it.get("number", "")) == num_str:
                return it
        return None
    if not rem_words:
        return pool[0] if len(pool) == 1 else None

    tokens = [w for w in rem_words if len(w) >= 3 or w.isdigit()]
    for item in pool:
        hay = _item_haystack(item)
        if q in hay or (tokens and all(t in hay for t in tokens)):
            return item
    best_item = None
    best_hits = 0
    for item in pool:
        hay = _item_haystack(item)
        hits = sum(1 for t in tokens if t in hay)
        if hits > best_hits:
            best_hits = hits
            best_item = item
    return best_item if best_hits > 0 else None


def _ask_which_proposal(language: str, proposals: list[dict]) -> str:
    parts: list[str] = []
    for idx, p in enumerate(proposals, 1):
        kind = p.get("kind") or "step"
        if kind == "rule":
            when = p.get("when") or (p.get("rules") or [{}])[0].get("when", "")
            then = p.get("then") or (p.get("rules") or [{}])[0].get("then", "")
            label = (
                f"la règle (quand {when}, {then})"
                if language == "fr"
                else f"the rule (when {when}, {then})"
            )
        elif kind == "case":
            label = f"le cas « {p.get('title', '')} »" if language == "fr" else f'the case "{p.get("title", "")}"'
        else:
            title = p.get("title") or p.get("reason") or ""
            label = f"l'étape « {title} »" if language == "fr" else f'the step "{title}"'
        parts.append(f"({idx}) {label}")
    joined = ", ".join(parts)
    if language == "fr":
        return f"Il y a {len(proposals)} propositions en attente : {joined}. Laquelle dois-je sauvegarder ?"
    return f"There are {len(proposals)} proposals waiting: {joined}. Which one should I save?"


@router.post("/save")
@writes_map
def save_proposal(body: SaveBody) -> dict:
    """Decision 0016: only the guardian saves knowledge into work_map, one item at a time."""
    work_map = get_maps().load(body.map_id)
    if work_map is None:
        raise HTTPException(status_code=404, detail="No such map.")
    memory = get_working().load(work_map.organisation, work_map.map_id)
    proposal: dict | None = None
    if body.proposal_id:
        block = memory.find(f"proposal-{body.proposal_id}")
        if block is None:
            raise HTTPException(status_code=404, detail="No such proposal.")
        proposal = dict(block["content"])
    else:
        open_proposals = [b["content"] for b in memory.of_kind("open", "proposal-") if isinstance(b.get("content"), dict)]
        # A note set aside (ignored or forgotten) is not saved by "save this" either. Found in the second
        # review of 2026-10-14: with nothing waiting, "save this" saved the note just ignored.
        aside = {str((b.get("content") or {}).get("proposal_id") or "") for b in memory.of_kind("retained", "ignored-")}
        recent_notes = [b["content"] for b in memory.of_kind("recent", "note-") if isinstance(b.get("content"), dict)
                        and str(b["content"].get("note_id") or b["ref"].removeprefix("note-")) not in aside]
        what_clean = (body.what or "").strip()
        if what_clean and not commands._GENERIC_SAVE_WHAT_RE.match(what_clean):
            matched_p = _match_proposal_or_note(what_clean, open_proposals)
            if matched_p is not None:
                proposal = dict(matched_p)
            else:
                matched_n = _match_proposal_or_note(what_clean, recent_notes)
                if matched_n is not None:
                    n_rules = list(matched_n.get("rules") or ())
                    proposal = {
                        "proposal_id": matched_n.get("note_id", ""),
                        "kind": "rule" if n_rules else "step",
                        "origin": matched_n.get("kind", "note"),
                        "title": matched_n.get("title") or absorb.title_for(matched_n.get("text", ""), "", limit=140),
                        "reason": matched_n.get("text", ""),
                        "observed": matched_n.get("observed") or matched_n.get("title", ""),
                        "decision": matched_n.get("title", ""),
                        "at": float(matched_n.get("at", 0.0)),
                        "said_at": matched_n.get("said_at", ""),
                        "rules": n_rules,
                        "cites": list(matched_n.get("cites") or ()),
                    }
                elif len(open_proposals) > 1:
                    msg = _ask_which_proposal(work_map.language, open_proposals)
                    return {
                        "intent": "save",
                        "saved_kind": None,
                        "ambiguous": True,
                        "proposals": open_proposals,
                        "step": None,
                        "guardrails": [],
                        "rules": 0,
                        "teachable": work_map.is_teachable,
                        "why_not": work_map.why_not_teachable(),
                        "question": msg,
                        "answer": msg,
                        "noted": msg,
                        **_voiced(msg),
                    }
                elif _KIND_SELECTOR_RE.match(what_clean):
                    raise HTTPException(status_code=404, detail="No such proposal.")
                else:
                    rails_direct = absorb.find_guardrails(
                        what_clean, at=0.0, language=work_map.language, known=work_map.guardrails
                    )
                    said_at_d, rails_direct = _said_now(rails_direct)
                    proposal = {
                        "proposal_id": "",
                        "kind": "rule" if rails_direct else "step",
                        "origin": "direct",
                        "title": absorb.title_for(what_clean, "", limit=140),
                        "reason": what_clean,
                        "observed": absorb.title_for(what_clean, "", limit=140),
                        "decision": absorb.title_for(what_clean, "", limit=140),
                        "at": 0.0,
                        "said_at": said_at_d,
                        "rules": [
                            {
                                "guardrail_id": r.guardrail_id,
                                "when": r.when,
                                "then": r.then,
                                "severity": r.severity,
                                "quote": r.quote,
                                "at": r.asked_at,
                                "said_at": r.said_at,
                                "cites": [],
                            }
                            for r in rails_direct
                        ],
                        "cites": [],
                    }
        elif len(open_proposals) > 1:
            msg = _ask_which_proposal(work_map.language, open_proposals)
            return {
                "intent": "save",
                "saved_kind": None,
                "ambiguous": True,
                "proposals": open_proposals,
                "step": None,
                "guardrails": [],
                "rules": 0,
                "teachable": work_map.is_teachable,
                "why_not": work_map.why_not_teachable(),
                "question": msg,
                "answer": msg,
                "noted": msg,
                **_voiced(msg),
            }
        elif len(open_proposals) == 1:
            proposal = dict(open_proposals[0])
        elif memory.of_kind("recent", "note-"):
            # "Save this" with nothing waiting is the latest note, and only it: set aside, nothing is saved,
            # never an older note in its place (found in the second review of 2026-10-14).
            latest = memory.of_kind("recent", "note-")[0]
            n0 = latest.get("content") or {}
            if str(n0.get("note_id") or latest["ref"].removeprefix("note-")) in aside:
                raise HTTPException(status_code=404, detail="Nothing pending to save.")
            n0_rules = list(n0.get("rules") or ())
            proposal = {
                "proposal_id": n0.get("note_id", ""),
                "kind": "rule" if n0_rules else "step",
                "origin": n0.get("kind", "note"),
                "title": n0.get("title") or absorb.title_for(n0.get("text", ""), "", limit=140),
                "reason": n0.get("text", ""),
                "observed": n0.get("observed") or n0.get("title", ""),
                "decision": n0.get("title", ""),
                "at": float(n0.get("at", 0.0)),
                "said_at": n0.get("said_at", ""),
                "rules": n0_rules,
                "cites": list(n0.get("cites") or ()),
            }
        else:
            raise HTTPException(status_code=404, detail="Nothing pending to save.")

    if proposal.get("kind") == "rule" and body.reason is not None and body.reason.strip():
        proposal = _reworded(work_map, proposal, body.reason.strip())
    elif body.reason is not None and body.reason.strip():
        proposal["reason"] = body.reason.strip()
        if body.title is None:
            proposal["title"] = absorb.title_for(proposal["reason"], "", limit=140)
    if body.title is not None and body.title.strip() and proposal.get("kind") != "rule":
        proposal["title"] = body.title.strip()

    if proposal.get("kind") == "case":
        r_data = proposal["ruling"]
        ruling = Ruling(
            ruling_id=r_data["ruling_id"],
            guardrail_id=r_data["guardrail_id"],
            kind=r_data["kind"],
            case=r_data.get("case") or {},
            question=r_data["question"],
            said=proposal.get("reason") or r_data["said"],
            applies=r_data.get("applies"),
            by=r_data.get("by") or work_map.expert,
            at=r_data.get("at") or datetime.now(UTC).isoformat(),
        )
        # A case answered again replaces the earlier answer: two answers to one case would teach
        # a learner both, and mark them wrong for one of them.
        replaced = proposal.get("replaced")
        work_map.rulings = [r for r in work_map.rulings if r.ruling_id != replaced]
        work_map.rulings.append(ruling)
        get_maps().save(work_map)
        if proposal.get("proposal_id"):
            memory.drop(f"proposal-{proposal['proposal_id']}")
            get_working().save(work_map.organisation, work_map.map_id, memory)
        tb = _record_teach_back(work_map, probe.teach_back(work_map))
        msg = "Cas enregistré." if work_map.language == "fr" else "Saved case."
        return {
            "intent": "save",
            "saved_kind": "case",
            "ruling": {"ruling_id": ruling.ruling_id, "kind": ruling.kind, "said": ruling.said, "applies": ruling.applies},
            "teach_back": tb,
            "step": None,
            "guardrails": [],
            "rules": 0,
            "teachable": work_map.is_teachable,
            "why_not": work_map.why_not_teachable(),
            "noted": msg,
            **_voiced(msg),
        }

    now = datetime.now(UTC).isoformat()
    cites = tuple(proposal.get("cites") or ())
    raw_rules = list(proposal.get("rules") or proposal.get("guardrails") or [])
    existing_ids = {g.guardrail_id for g in work_map.guardrails}
    rails = [
        Guardrail(
            guardrail_id=r["guardrail_id"],
            when=r["when"],
            then=r["then"],
            quote=r.get("quote", proposal["reason"]),
            asked_at=float(r.get("at", 0.0)),
            severity=r.get("severity") or "check",   # "stop" or "check": "warning" was refused
            said_at=r["step_said_at"] if "step_said_at" in r else (r.get("said_at") or now),
            cites=tuple(r.get("cites") or cites),
        )
        for r in raw_rules
        if r["guardrail_id"] not in existing_ids
    ]
    work_map.guardrails.extend(rails)
    is_rule_only = proposal.get("kind") == "rule"
    saved_step: Step | None = None
    if not is_rule_only:
        number = len(work_map.steps) + 1
        said_at = str(proposal.get("said_at") or "")
        # A step holds the rules said with it, and only those. Found in the review of 2026-10-14:
        # a step saved with none was given every rule of the knowledge, so the library linked each
        # rule to it and forgetting that step deleted every rule and its cases.
        step_gids = [r["guardrail_id"] for r in raw_rules]
        step = Step(
            step_id=f"s{number}",
            number=number,
            title=proposal["title"],
            screen_moment=float(proposal.get("at", 0.0)),
            observed=proposal.get("observed") or proposal["title"],
            decision=proposal.get("decision") or proposal["title"],
            reason=proposal["reason"],
            guardrail_ids=tuple(step_gids),
            said_at=said_at,
            cites=cites,
        )
        work_map.steps.append(step)
        saved_step = step
    elif work_map.steps and raw_rules:
        last_step = work_map.steps[-1]
        merged_gids = list(last_step.guardrail_ids)
        for r in raw_rules:
            gid = r["guardrail_id"]
            if gid not in merged_gids:
                merged_gids.append(gid)
        work_map.steps[-1] = dataclasses.replace(last_step, guardrail_ids=tuple(merged_gids))
    work_map.confirmed_at = None          # captured in class: a draft, until validated
    get_maps().save(work_map)

    session = _session(work_map.map_id)
    if saved_step is not None:
        session.setdefault("captured_steps", []).append(saved_step.step_id)
        if proposal.get("proposal_id"):
            # Which note it was saved from, so forgetting it sets that note aside whatever its wording.
            memory.put("retained", f"saved-{saved_step.step_id}", {"note_id": proposal["proposal_id"]})
    if proposal.get("proposal_id"):
        memory.drop(f"proposal-{proposal['proposal_id']}")
    for rail in rails:
        memory.put("retained", f"rule-{rail.guardrail_id}", {"when": rail.when, "then": rail.then})
    _clear_teach_back(work_map, memory)
    get_working().save(work_map.organisation, work_map.map_id, memory)
    saved_kind = "rule" if is_rule_only else "step"
    if saved_kind == "rule" and rails:
        msg = (
            f"Règle enregistrée : quand {rails[0].when}, {rails[0].then}."
            if work_map.language == "fr"
            else f"Saved as rule: when {rails[0].when}, {rails[0].then}."
        )
    elif saved_step is not None:
        msg = (
            f"Enregistré en étape {saved_step.number} : {saved_step.title}."
            if work_map.language == "fr"
            else f"Saved as step {saved_step.number}: {saved_step.title}."
        )
    else:
        msg = "Enregistré." if work_map.language == "fr" else "Saved."
    return {
        "intent": "save",
        "saved_kind": saved_kind,
        "step": (
            {
                "step_id": saved_step.step_id,
                "number": saved_step.number,
                "title": saved_step.title,
                "reason": saved_step.reason,
                "at": saved_step.screen_moment,
                "cites": list(cites),
            }
            if saved_step is not None
            else None
        ),
        "guardrails": [
            {"when": r.when, "then": r.then, "severity": r.severity, "quote": r.quote, "at": r.asked_at}
            for r in rails
        ],
        "rules": len(rails),
        "teachable": work_map.is_teachable,
        "why_not": work_map.why_not_teachable(),
        "noted": msg,
        **_voiced(msg),
    }


def _save_from_voice(work_map, what: str = "") -> dict:
    try:
        return save_proposal(SaveBody(map_id=work_map.map_id, what=what))
    except HTTPException as error:
        if error.status_code == 409:
            msg = ("La connaissance a changé entre-temps, rien n'a été écrasé : redis-le."
                   if work_map.language == "fr" else "The knowledge changed meanwhile, nothing was written over: say it again.")
        else:
            msg = (
                "Aucune proposition en attente à enregistrer."
                if work_map.language == "fr"
                else "Nothing pending to save yet."
            )
        return {
            "intent": "save",
            "step": None,
            "guardrails": [],
            "noted": msg,
            **_voiced(msg),
            "teachable": work_map.is_teachable,
            "why_not": work_map.why_not_teachable(),
        }


class ProposalActionBody(BaseModel):
    map_id: str
    proposal_id: str


@router.post("/proposal/ignore")
def ignore_proposal(body: ProposalActionBody) -> dict:
    """Decision 0016: ignore a pending proposal without saving it."""
    work_map = get_maps().load(body.map_id)
    if work_map is None:
        raise HTTPException(status_code=404, detail="No such map.")
    memory = get_working().load(work_map.organisation, work_map.map_id)
    block = memory.find(f"proposal-{body.proposal_id}")
    content = (block or {}).get("content") or {}
    dropped = memory.drop(f"proposal-{body.proposal_id}")
    # Ignored stays ignored: the next look at the notes does not offer it again, nor its rules.
    _set_aside(work_map, memory, body.proposal_id, content, with_rules=content.get("kind") == "rule")
    get_working().save(work_map.organisation, work_map.map_id, memory)
    return {"ignored": dropped, "proposal_id": body.proposal_id}


def _set_aside(work_map, memory, item_id: str, item: dict, *, with_rules: bool = True) -> None:
    """A proposal or a note the guardian ignored or forgot stays aside and is not offered again;
    forgotten, the rules said with it go too (a saved rule stays). Found in the review of 2026-10-14:
    "forget that" dropped a rule's proposal, and the next look at the notes proposed the rule again."""
    saved = {g.guardrail_id for g in work_map.guardrails}
    gids = {str(r.get("guardrail_id") or "") for r in (item.get("rules") or item.get("guardrails") or ())
            if isinstance(r, dict)} if with_rules else set()
    if item.get("guardrail_id"):
        gids.add(str(item["guardrail_id"]))
    gids = {g for g in gids if g and g not in saved}
    memory.put("retained", f"ignored-{item_id}", {"proposal_id": item_id, "guardrail_id": next(iter(gids), "")})
    for gid in gids:
        memory.drop(f"rule-{gid}")
        memory.drop(f"proposal-rule-{gid[:10]}")
        memory.put("retained", f"ignored-rule-{gid}", {"proposal_id": "", "guardrail_id": gid})


def _reworded(work_map, proposal: dict, text: str) -> dict:
    """A rule proposal said again in the guardian's corrected words: its when and then are read from
    them, its id kept. Found in the review of 2026-10-14: a rule changed before saving was saved in
    its first wording, since only the title and the reason were changed. Unreadable as a rule, the
    corrected words are kept as its quote and the clauses stay as they were."""
    if proposal.get("kind") != "rule":
        return proposal
    found = absorb.find_guardrails(text, at=float(proposal.get("at", 0.0)), language=work_map.language)
    rules = [dict(r) for r in (proposal.get("rules") or proposal.get("guardrails") or ()) if isinstance(r, dict)]
    first = rules[0] if rules else {"guardrail_id": proposal.get("guardrail_id") or uuid.uuid4().hex[:10]}
    first["quote"] = text
    if found:
        first.update(when=found[0].when, then=found[0].then, severity=found[0].severity)
    # More than one rule in the corrected words: each is kept, the first under the proposal's id.
    more = [{**{k: v for k, v in first.items() if k not in ("guardrail_id", "when", "then", "severity")},
             "guardrail_id": g.guardrail_id, "when": g.when, "then": g.then, "severity": g.severity}
            for g in found[1:]] if found else rules[1:]
    out = {**proposal, "rules": [first, *more], "guardrails": [first, *more], "quote": text, "reason": text,
           "when": first.get("when", proposal.get("when", "")), "then": first.get("then", proposal.get("then", ""))}
    out["title"] = wording.say(work_map.language, "rule_text", when=out["when"], then=out["then"])
    return out


class ProposalChangeBody(BaseModel):
    map_id: str
    proposal_id: str
    title: str | None = None
    reason: str | None = None


@router.post("/proposal/change")
def change_proposal(body: ProposalChangeBody) -> dict:
    """Decision 0016: adjust a pending proposal's wording in working memory before saving."""
    work_map = get_maps().load(body.map_id)
    if work_map is None:
        raise HTTPException(status_code=404, detail="No such map.")
    memory = get_working().load(work_map.organisation, work_map.map_id)
    block = memory.find(f"proposal-{body.proposal_id}")
    if block is None:
        raise HTTPException(status_code=404, detail="No such proposal.")
    proposal = dict(block["content"])
    if proposal.get("kind") == "rule" and body.reason is not None and body.reason.strip():
        proposal = _reworded(work_map, proposal, body.reason.strip())
    elif body.reason is not None and body.reason.strip():
        proposal["reason"] = body.reason.strip()
        if body.title is None:
            proposal["title"] = absorb.title_for(proposal["reason"], "", limit=140)
    if body.title is not None and body.title.strip() and proposal.get("kind") != "rule":
        proposal["title"] = body.title.strip()
    proposal["edited"] = True
    memory.put("open", f"proposal-{body.proposal_id}", proposal)
    get_working().save(work_map.organisation, work_map.map_id, memory)
    return {"proposal": proposal}


class ProvenanceBody(BaseModel):
    map_id: str
    country: str = ""          # where the rules apply, when they are a country's; none for grammar


@router.post("/provenance")
@writes_map
def check_provenance(body: ProvenanceBody) -> dict:
    """
    Look every learned rule up against the world.

    Run after the task, not during it: each rule costs a search and a few page reads, and
    the expert is not waiting on it. Nothing is rewritten. A rule a source contradicts is
    flagged for a person, because a search result does not overrule 24 years.
    """
    work_map = get_maps().load(body.map_id)
    if work_map is None:
        return {"error": "No such map."}
    # One search and a few page reads per rule: a budget for all of them, before the first.
    budget = meter.meter().grant("source_checks", len(work_map.guardrails))
    meter.meter().record(budget)

    checked = []
    for rail in work_map.guardrails:
        found = provenance.check(rail, context=work_map.task, country=body.country)
        rail_dict = found.as_dict()
        # Guardrail is frozen, so the rule is replaced rather than mutated: a rule whose
        # text could change after the expert said it is not the rule they said.
        index = work_map.guardrails.index(rail)
        work_map.guardrails[index] = type(rail)(
            **{**{f: getattr(rail, f) for f in rail.__dataclass_fields__},
               "provenance": rail_dict})
        # The whole rule, not only its provenance: this list replaces the one on screen,
        # and a rail redrawn without its severity or its quote loses the two things that
        # made it worth showing.
        checked.append({"guardrail_id": rail.guardrail_id, "when": rail.when,
                        "then": rail.then, "severity": rail.severity,
                        "quote": rail.quote, "at": rail.asked_at, **rail_dict})
    get_maps().save(work_map)

    return {"checked": checked,
            "conflicts": [c["guardrail_id"] for c in checked
                          if c["verdict"] == "conflicted"],
            "backend": next((cit["backend"] for c in checked
                             for cit in c["citations"]), "none")}


@router.get("/map/{map_id}")
def get_map(map_id: str) -> dict:
    work_map = get_maps().load(map_id)
    if work_map is None:
        return {"error": "No such map."}
    memory = get_working().load(work_map.organisation, map_id)
    notes, _, proposals = _notes_and_proposals(memory)
    return {
        "map_id": work_map.map_id, "task": work_map.task, "expert": work_map.expert,
        "teachable": work_map.is_teachable, "why_not": work_map.why_not_teachable(),
        "confirmed": bool(work_map.confirmed_at), "language": work_map.language,
        # The three states (docs/decisions/0002): each part validated or a draft, beside the
        # version published in the library, which the page reads from the knowledge list.
        "validated": work_map.as_validated() is not None, "states": work_map.states(),
        "order": [s.step_id for s in work_map.ordered_steps()], "sections": work_map.sections,
        "contents_draft": bool(work_map.validated) and (work_map.validated.get("order", []), work_map.validated.get(
            "sections", [])) != (work_map.order, work_map.sections),
        "steps": [{"step_id": s.step_id, "section": work_map.section_of(s.step_id), "number": s.number, "title": s.title, "at": s.screen_moment,
                   "observed": s.observed, "reason": s.reason,
                   "guardrails": [{"when": g.when, "then": g.then, "severity": g.severity,
                                   "quote": g.quote, "at": g.asked_at}
                                  for g in work_map.rails_for(s)]}
                  for s in work_map.ordered_steps()],
        "guardrails": [{"id": g.guardrail_id, "when": g.when, "then": g.then,
                        "severity": g.severity, "quote": g.quote, "at": g.asked_at,
                        "provenance": g.provenance}
                       for g in work_map.guardrails],
        "conflicts": [g.guardrail_id for g in work_map.conflicts],
        "rulings": [{"ruling_id": r.ruling_id, "kind": r.kind, "guardrail_id": r.guardrail_id,
                     "question": r.question, "said": r.said, "applies": r.applies}
                    for r in work_map.rulings if r.kind != "correction"],
        "proposals": proposals,
        "notes": notes,
    }


@router.get("/map/{map_id}/braille")
def get_map_in_braille(map_id: str, grade: int = 2) -> dict:
    """
    The Work Map for someone who reads with their fingers.

    The same knowledge a sighted new hire gets from the timeline, laid out on braille paper
    by the embosser code in apu/modality/braille: forty cells to a line, a form feed
    between pages, and a BRF an embosser prints from directly.
    """
    from apu.modality.braille.translator import BrailleGrade

    work_map = get_maps().load(map_id)
    if work_map is None:
        return {"error": "No such map."}
    if grade not in (1, 2):
        return {"error": "Grade 1 or grade 2."}
    try:
        doc = braille.emboss(work_map, grade=BrailleGrade(grade))
    except braille.BrailleUnavailable as error:
        # Said plainly. A blank page handed to someone who cannot see that it is blank is
        # the one failure this route must never commit.
        return {"error": f"Braille is not available on this machine: {error}"}
    return {"print": doc.print_text, "cells": doc.unicode_braille, "brf": doc.brf,
            "pages": doc.pages, "grade": doc.grade,
            "pages_unicode": [list(page) for page in doc.pages_unicode]}


class ContentsBody(BaseModel):
    map_id: str
    order: list[str]
    sections: list[dict] = []


@router.post("/contents")
@writes_map
def set_contents(body: ContentsBody) -> dict:
    """
    The guardian orders the knowledge top to bottom and groups steps into sections, before
    validating (docs/plan.md, docs/plan-done.md, step 2); the learner's path follows this order. Every step once,
    none invented: a contents that drops a step would publish less than was taught. A changed
    contents is a draft until validated again.
    """
    work_map = get_maps().load(body.map_id)
    if work_map is None:
        return {"error": "No such map."}
    known = {s.step_id for s in work_map.steps}
    if sorted(body.order) != sorted(known) or len(set(body.order)) != len(body.order):
        raise HTTPException(status_code=422, detail="The contents must hold every step once, and no other.")
    sections, placed = [], set()
    for section in body.sections:
        title = str(section.get("title", "")).strip()[:120]
        steps = [str(x) for x in section.get("steps", [])]
        if not title or not set(steps) <= known or placed & set(steps):
            raise HTTPException(status_code=422, detail="A section has a title, and steps of this map, each in one section.")
        placed |= set(steps)
        sections.append({"title": title, "steps": steps})
    work_map.order, work_map.sections = list(body.order), sections
    work_map.confirmed_at = None
    get_maps().save(work_map)
    _clear_teach_back(work_map)
    return {"order": work_map.order, "sections": work_map.sections}


@router.get("/memory/{map_id}")
def working_memory(map_id: str) -> dict:
    """What Urithi is in the middle of on this knowledge, head to tail: what "Carry on teaching" reopens."""
    work_map = get_maps().load(map_id)
    if work_map is None:
        return {"error": "No such map."}
    memory = get_working().load(work_map.organisation, map_id)
    notes, _, proposals = _notes_and_proposals(memory)
    return {"blocks": [{"kind": b["kind"], "ref": b["ref"], "content": b["content"]} for b in memory.ordered()],
            "question": (memory.find("question") or {}).get("content"),
            "cases": len(memory.of_kind("open", "case-")),
            "proposals": proposals,
            "notes": notes}


@router.get("/maps")
def list_maps(request: Request) -> dict:
    """This guardian's maps, never another's."""
    who = request.state.guardian
    return {"maps": [m for m in get_maps().list_maps(who.organisation) if m["expert"] == who.name]}


class ReviewBody(BaseModel):
    map_id: str
    case: dict[str, Any]
    about_to: str


@router.post("/review")
def review_action(body: ReviewBody) -> dict:
    """
    Teach mode. Called before the new hire's save, never after it.

    A blocked save is a question with the expert's reasoning attached, not a refusal: the
    person still decides, which is the whole difference between a tutor and a lock.
    """
    work_map = get_maps().load(body.map_id)
    if work_map is None:
        return {"error": "No such map."}
    if not work_map.is_teachable:
        return {"error": work_map.why_not_teachable()}

    started = time.time()
    result = review(work_map, body.case, body.about_to)
    logger.info("Reviewed a case against %d rails in %.2fs: allowed=%s",
                len(work_map.guardrails), time.time() - started, result.allowed)

    return {
        "allowed": result.allowed,
        # The decisions that let this case through. A tutor that stopped this exact case
        # last week and is silent today has to say why, or the new hire learns that the
        # guardrail is random.
        "cleared": [{"by": r.by, "said": r.said, "rule": r.guardrail_id}
                    for r in result.cleared],
        "interventions": [
            {"says": i.says, "quote": i.quote, "replay_at": i.replay_at,
             "certain": i.certain, "severity": i.guardrail.severity,
             "guardrail_id": i.guardrail.guardrail_id, **_voiced(i.says),
             # The same words as braille, ready to emboss. Spoken, the warning is gone
             # in four seconds while the new hire is still holding the decision; on
             # paper it stays on the desk as long as they need it.
             "cells": braille.intervention_cells(i.says),
             "slip": braille.intervention_pages(i.says)}
            for i in result.interventions
        ],
        "mastery": mastery(work_map,
                           {i.guardrail.guardrail_id for i in result.interventions}),
    }



# ── Module 2: the debrief ────────────────────────────────────────────────────

class MapBody(BaseModel):
    map_id: str


def _probe_out(found: probe.Probe, remaining: int) -> dict:
    return {**found.as_dict(), "remaining": remaining, **_voiced(found.question)}


@router.post("/debrief")
def start_debrief(body: MapBody) -> dict:
    """
    The cases where the expert's rules are least clear, one at a time.

    Not "is anything unclear?", which an expert always answers no. The boundary, the
    collision and the public source that disagrees, each put as a concrete case.
    """
    work_map = get_maps().load(body.map_id)
    if work_map is None:
        return {"error": "No such map."}
    found = probe.probes_for(work_map)
    memory = get_working().load(work_map.organisation, work_map.map_id)
    deferred_blocks = memory.of_kind("open", "deferred-")
    deferred_questions = [b["content"] for b in deferred_blocks]
    for b in deferred_blocks:
        c = b["content"]
        gid = work_map.guardrails[0].guardrail_id if work_map.guardrails else "classroom"
        found.append(
            probe.Probe(
                probe_id=f"deferred-{uuid.uuid4().hex[:8]}",
                kind=c.get("kind", "reason"),
                guardrail_id=gid,
                question=c["question"],
                case={"situation": c.get("about", ""), "importance": c.get("importance", 3)},
                built_by="code",
                action=c.get("about", "follow the step"),
            )
        )
        memory.drop(b["ref"])
    _session(body.map_id)["probes"] = found
    for old in memory.of_kind("open", "case-"):
        memory.drop(old["ref"])
    for case in reversed(found):        # put at the front of the open ones: the first case first
        memory.put("open", f"case-{case.probe_id}", case.as_dict())
    get_working().save(work_map.organisation, work_map.map_id, memory)
    if not found:
        tb = _record_teach_back(work_map, probe.teach_back(work_map))
        return {"done": True, "teach_back": tb, "deferred_questions": deferred_questions}
    return {"probe": _probe_out(found[0], len(found) - 1), "total": len(found),
            "deferred_questions": deferred_questions}


class RuleBody(BaseModel):
    map_id: str
    probe_id: str
    said: str | None = None
    audio: str | None = None
    by: str | None = None


@router.post("/rule")
def rule(body: RuleBody) -> dict:
    """Decision 0016: one answer to a debrief case, recorded as a note and a pending proposal in
    working memory; saved to work_map.rulings only when the guardian saves it."""
    work_map = get_maps().load(body.map_id)
    session = _session(body.map_id)
    pending = session.get("probes") or []
    if not pending and work_map is not None:
        # The session was lost (a restart): the cases still to test come back from the working memory.
        memory = get_working().load(work_map.organisation, work_map.map_id)
        pending = session["probes"] = [probe.Probe(**b["content"]) for b in memory.of_kind("open", "case-")]
    current = next((p for p in pending if p.probe_id == body.probe_id), None)
    if work_map is None or current is None:
        return {"error": "Nothing was asked."}

    said = (body.said or "").strip()
    if not said and body.audio:
        try:
            said = voice.transcribe(base64.b64decode(body.audio))
        except meter.Refused:
            raise
        except Exception as error:
            logger.warning("Could not hear the ruling: %s", error)
            return {"error": "I could not hear that. Say it again?"}
    if not said:
        return {"error": "Nothing was said."}

    ruling = probe.rule_on(current, said, by=body.by or work_map.expert)
    replaced = session.get("replacing", {}).pop(current.probe_id, None)
    pending.remove(current)
    memory = get_working().load(work_map.organisation, work_map.map_id)
    memory.drop(f"case-{current.probe_id}")
    pid = uuid.uuid4().hex[:10]
    ruling_dict = {
        "ruling_id": ruling.ruling_id,
        "guardrail_id": ruling.guardrail_id,
        "kind": ruling.kind,
        "case": ruling.case,
        "question": ruling.question,
        "said": ruling.said,
        "applies": ruling.applies,
        "by": ruling.by,
        "at": ruling.at,
    }
    proposal = {
        "proposal_id": pid,
        "kind": "case",
        "origin": "debrief",
        "title": current.question,
        "reason": ruling.said,
        "ruling": ruling_dict,
        "replaced": replaced,
        "rules": [],
        "guardrails": [],
        "cites": [],
    }
    note = {
        "note_id": pid,
        "kind": "debrief",
        "text": said,
        "title": current.question,
        "case": current.question,
        "applies": ruling.applies,
        "at": 0.0,
        "said_at": ruling.at,
        "rules": [],
        "cites": [],
    }
    memory.put("recent", f"note-{pid}", note)
    memory.put("recent", "said", {"text": said, "case": current.question})
    memory.put("open", f"proposal-{pid}", proposal)
    get_working().save(work_map.organisation, work_map.map_id, memory)

    reply = {
        "ruling": {"kind": ruling.kind, "said": ruling.said, "applies": ruling.applies},
        "proposal": proposal,
        "note": note,
    }
    if pending:
        reply["probe"] = _probe_out(pending[0], len(pending) - 1)
    else:
        text = _record_teach_back(work_map, probe.teach_back(work_map))
        reply.update({"done": True, "teach_back": text, **_voiced(text)})
    return reply


class ReaskBody(BaseModel):
    map_id: str
    ruling_id: str


@router.post("/reask")
@writes_map
def reask(body: ReaskBody) -> dict:
    """
    A case the guardian already answered, put to them again, because the teach-back showed
    their answer was not what they meant. Measured: "an unique solution" answered yes in a
    hurry, and nothing but this would have kept it out of every learner's exam.

    The earlier answer stays until the new one is given, then is replaced by it.
    """
    work_map = get_maps().load(body.map_id)
    if work_map is None:
        return {"error": "No such map."}
    found = next((r for r in work_map.rulings if r.ruling_id == body.ruling_id and r.kind != "correction"), None)
    rail = work_map.guardrail(found.guardrail_id) if found else None
    if found is None or rail is None:
        return {"error": "No such answer."}
    again = probe.Probe(
        probe_id=str(uuid.uuid4()), kind=found.kind, guardrail_id=found.guardrail_id,
        question=found.question, case={k: v for k, v in found.case.items() if k not in ("first", "other")},
        built_by="model" if found.kind == "near_miss" else "code", action=rail.then,
        other_guardrail_id=found.case.get("other", ""))
    session = _session(body.map_id)
    session["probes"] = [again]
    session.setdefault("replacing", {})[again.probe_id] = found.ruling_id
    work_map.confirmed_at = None
    get_maps().save(work_map)
    _clear_teach_back(work_map)
    return {"probe": _probe_out(again, 0)}


class ForgetRuleBody(BaseModel):
    map_id: str
    guardrail_id: str


@router.post("/forget-rule")
@writes_map
def forget_rule(body: ForgetRuleBody) -> dict:
    """
    A rule the guardian did not give, or gave twice, taken out of their map, with the cases
    that tested it. Their sentences stay: only what was read out of them goes.
    """
    work_map = get_maps().load(body.map_id)
    if work_map is None or work_map.guardrail(body.guardrail_id) is None:
        return {"error": "No such rule."}
    gone = body.guardrail_id
    work_map.guardrails = [g for g in work_map.guardrails if g.guardrail_id != gone]
    work_map.rulings = [r for r in work_map.rulings
                        if r.guardrail_id != gone and r.case.get("other") != gone]
    work_map.steps = [dataclasses.replace(s, guardrail_ids=tuple(i for i in s.guardrail_ids if i != gone))
                      for s in work_map.steps]
    work_map.confirmed_at = None
    get_maps().save(work_map)
    # Set aside too, or the next look at the notes proposes it again. Measured live on 2026-10-15: a
    # rule removed came back as a proposal, and "save this" then asked which one instead of saving.
    memory = get_working().load(work_map.organisation, work_map.map_id)
    _set_aside(work_map, memory, f"rule-{gone[:10]}", {"guardrail_id": gone})
    _clear_teach_back(work_map, memory)
    get_working().save(work_map.organisation, work_map.map_id, memory)
    return {"removed": True, "teachable": work_map.is_teachable, "why_not": work_map.why_not_teachable()}


class ConfirmBody(BaseModel):
    map_id: str
    confirmed: bool
    correction: str = ""


def _map_digest(work_map) -> dict:
    return {
        "steps": [
            {
                "step_id": s.step_id,
                "number": s.number,
                "title": s.title,
                "reason": s.reason,
                "guardrail_ids": list(s.guardrail_ids),
                "cites": list(s.cites or ()),
            }
            for s in work_map.steps
        ],
        "guardrails": [
            {
                "guardrail_id": g.guardrail_id,
                "when": g.when,
                "then": g.then,
                "severity": g.severity,
                "quote": g.quote,
                "cites": list(g.cites or ()),
            }
            for g in work_map.guardrails
        ],
        "order": list(work_map.order),
        "sections": [dict(sec) for sec in work_map.sections],
    }


def _record_teach_back(work_map, text: str) -> str:
    digest = _map_digest(work_map)
    memory = get_working().load(work_map.organisation, work_map.map_id)
    memory.put("retained", "teach-back", {"digest": digest, "text": text})
    get_working().save(work_map.organisation, work_map.map_id, memory)
    _session(work_map.map_id)["teach_back_digest"] = digest
    return text


def _clear_teach_back(work_map, memory=None) -> None:
    own = memory is None
    if own:
        memory = get_working().load(work_map.organisation, work_map.map_id)
    memory.drop("teach-back")
    if own:
        get_working().save(work_map.organisation, work_map.map_id, memory)
    _session(work_map.map_id).pop("teach_back_digest", None)


def _has_current_teach_back(work_map) -> bool:
    digest = _map_digest(work_map)
    memory = get_working().load(work_map.organisation, work_map.map_id)
    block = memory.find("teach-back")
    if block and isinstance(block.get("content"), dict) and block["content"].get("digest") == digest:
        return True
    if _session(work_map.map_id).get("teach_back_digest") == digest:
        return True
    return False


def _archive_cited(work_map) -> None:
    """
    At validation (docs/decisions/0004): the documents a validated part cites go to the archive
    (Cloud Storage, under organisation/guardian/<guardian>/<map>/); a document no part cites is
    never uploaded, and is purged from the local disk.
    """
    import re

    from guardian.sources.store import get_archive, get_sources

    cited = {c["source_id"] for part in [*work_map.steps, *work_map.guardrails] for c in (part.cites or ())}
    store = get_sources()
    for record in store.list(work_map.organisation, work_map.map_id):
        if record["source_id"] not in cited:
            store.remove(work_map.organisation, work_map.map_id, record["source_id"])
            continue
        if record.get("archived"):
            continue
        guardian = re.sub(r"[^a-z0-9]+", "-", work_map.expert.lower()).strip("-") or "guardian"
        name = re.sub(r"[^A-Za-z0-9._-]+", "-", record["name"]).strip("-") or "document"
        path = f"{work_map.organisation}/guardian/{guardian}/{work_map.map_id}/{record['source_id']}-{name}"
        data = store.data(work_map.organisation, work_map.map_id, record["source_id"]) or b""
        try:
            record["archived"] = get_archive().put(path, data, record["mime"]) or "local"
            record.pop("archive_pending", None)
        except Exception as error:
            # Measured live: the bucket named for the machine did not exist, and validating
            # failed whole. The parts are validated all the same; the document stays here,
            # said to be waiting, and goes at the next validation once the archive answers.
            logger.warning("A cited document could not be archived, kept local: %s", error)
            record["archive_pending"] = str(error)[:200]
        store.update(work_map.organisation, work_map.map_id, record)


@router.post("/confirm")
@writes_map
def confirm(body: ConfirmBody):
    """
    The expert says yes, that is how it works, or says what is wrong.

    A correction is kept as what it is, the expert's words about their own map, and the map
    stays unconfirmed until they confirm it. Nothing rewrites a rule on their behalf.
    """
    from datetime import UTC, datetime
    from fastapi.responses import JSONResponse

    work_map = get_maps().load(body.map_id)
    if work_map is None:
        return {"error": "No such map."}
    if body.confirmed:
        if not _has_current_teach_back(work_map):
            msg = (
                "Le récapitulatif n'a pas été produit depuis le dernier changement de la carte : "
                "produis et écoute le récapitulatif avant de valider."
                if work_map.language == "fr"
                else "The teach-back has not been produced since the last change to this map; "
                "produce the teach-back before confirming."
            )
            return JSONResponse(
                status_code=409,
                content={"confirmed": False, "confirmed_at": None, "error": msg, "detail": msg},
            )
        work_map.confirmed_at = datetime.now(UTC).isoformat()
        work_map.validated = work_map.snapshot()     # what is published from now on, until validated again
        _archive_cited(work_map)
    else:
        work_map.confirmed_at = None
        work_map.rulings.append(Ruling(
            ruling_id=f"correction-{len(work_map.rulings) + 1}", guardrail_id="",
            kind="correction", case={}, question="Is that how it works?",
            said=body.correction.strip() or "No.", applies=None, by=work_map.expert,
            at=datetime.now(UTC).isoformat()))
        _clear_teach_back(work_map)
    get_maps().save(work_map)
    return {"confirmed": bool(work_map.confirmed_at), "confirmed_at": work_map.confirmed_at}


# ── Module 3: the exam, and precedent after the expert has gone ──────────────

@router.get("/exam/{map_id}")
def get_exam(map_id: str) -> dict:
    work_map = get_maps().load(map_id)
    if work_map is None:
        return {"error": "No such map."}
    items = probe.exam(work_map)
    return {"items": [{"ruling_id": i.ruling_id, "question": i.question,
                       "case": {k: v for k, v in i.case.items()
                                if k not in ("source", "public_threshold")}}
                      for i in items]}


class GradeBody(BaseModel):
    map_id: str
    answers: dict[str, bool]


@router.post("/exam/grade")
def grade_exam(body: GradeBody) -> dict:
    work_map = get_maps().load(body.map_id)
    if work_map is None:
        return {"error": "No such map."}
    result = probe.grade(work_map, body.answers)
    return {"correct": result.correct, "total": result.total, "feedback": result.feedback}


class SpokenAnswerBody(BaseModel):
    map_id: str
    ruling_id: str
    said: str | None = None       # already transcribed, when the page did it
    audio: str | None = None      # base64 WAV otherwise


@router.post("/exam/answer")
def answer_exam_aloud(body: SpokenAnswerBody) -> dict:
    """
    One exam case, answered out loud.

    For a new hire who cannot see radio buttons: the case is read to them, they say yes or
    no, and they hear whether that is what the expert decided, in the expert's words. A
    reply that is not clearly yes or no is not graded; it is asked again.
    """
    work_map = get_maps().load(body.map_id)
    if work_map is None:
        return {"error": "No such map."}
    ruling = next((r for r in work_map.rulings
                   if r.ruling_id == body.ruling_id and r.applies is not None), None)
    if ruling is None:
        return {"error": "No such case in this exam."}
    said = (body.said or "").strip()
    if not said and body.audio:
        try:
            said = voice.transcribe(base64.b64decode(body.audio))
        except voice.VoiceUnavailable as error:
            return {"error": str(error)}
    answer = probe.heard_yes_no(said)
    if answer is None:
        says = "I did not catch a yes or a no. Say yes, or no."
        return {"heard": said, "understood": False, "says": says, **_voiced(says)}
    right = answer == ruling.applies
    says = f"{'Right' if right else 'Not quite'}. {ruling.by} said: {ruling.said}"
    return {"heard": said, "understood": True, "answer": answer, "right": right,
            "expected": ruling.applies, "says": says, **_voiced(says)}


class SayBody(BaseModel):
    text: str


# Long enough for a case or a step, short enough that this is not a free speech service.
SAY_MAX_CHARS = 600


@router.post("/say")
def say(body: SayBody) -> dict:
    """A sentence the page already shows, read out: the case, the step, the question."""
    text = body.text.strip()
    if not text:
        return {"error": "Nothing to read."}
    if len(text) > SAY_MAX_CHARS:
        return {"error": f"Longer than {SAY_MAX_CHARS} characters; read it in parts."}
    return {**_voiced(text)}


@router.get("/map/{map_id}/teach-back")
def get_teach_back(map_id: str, spoken: bool = False) -> dict:
    """
    The map as the apprentice explains it back: the words the expert heard and confirmed,
    built from the map, never paraphrased. With spoken=true, read out as well.
    """
    work_map = get_maps().load(map_id)
    if work_map is None:
        return {"error": "No such map."}
    text = _record_teach_back(work_map, probe.teach_back(work_map))
    return {"text": text, "expert": work_map.expert, "task": work_map.task,
            "confirmed_at": work_map.confirmed_at,
            **(_voiced(text) if spoken else {"audio": None, "words": []})}


class PrecedentBody(BaseModel):
    map_id: str
    guardrail_id: str
    case: dict[str, Any]
    said: str
    applies: bool
    by: str


@router.post("/precedent")
@writes_map
def add_precedent(body: PrecedentBody) -> dict:
    """
    Someone with authority decided a case the tutor stopped.

    The controller clears an unknown supplier, or confirms it was right to stop. That
    decision is the same kind of thing as Sabine's, and is kept the same way: the map does
    not freeze the day its first expert retires, it keeps the judgments of the people after
    her, each one attributed to whoever made it.
    """
    from datetime import UTC, datetime

    work_map = get_maps().load(body.map_id)
    if work_map is None:
        return {"error": "No such map."}
    if work_map.guardrail(body.guardrail_id) is None:
        return {"error": "No such rule on this map."}
    if not body.said.strip() or not body.by.strip():
        return {"error": "A precedent needs what was decided and who decided it."}
    ruling = Ruling(ruling_id=f"precedent-{len(work_map.rulings) + 1}",
                    guardrail_id=body.guardrail_id, kind="escalation", case=body.case,
                    question="Decided after the tutor stopped this case.",
                    said=body.said.strip(), applies=body.applies, by=body.by.strip(),
                    at=datetime.now(UTC).isoformat())
    work_map.rulings.append(ruling)
    get_maps().save(work_map)
    return {"ruling_id": ruling.ruling_id, "rulings": len(work_map.rulings)}
