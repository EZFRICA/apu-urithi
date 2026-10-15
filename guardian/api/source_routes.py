"""The guardian's sources: deposit a document, read it into passages, make a step of one.

Step 3 of docs/plan.md (docs/plan-steps-3-to-8.md). A deposit stays local while the knowledge is a draft; it is read into
passages (guardian/sources/passages.py); "make a step of this passage", by a button, by voice
or by text ("page 3", "what I said at 1:10"), has Urithi propose a step citing the exact page
or moment, kept in the working memory; nothing is knowledge until the guardian accepts it, and
nothing is published until the knowledge is validated. Guardian routes, under the same check
as guardian/api/routes.py: a guardian of the map's organisation, its own guardian.
"""

import base64
import dataclasses
import re
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from apu import config as shared_config
from apu import meter
from apu.modality import picture
from guardian import config
from guardian.api import routes
from guardian.api.routes import _a_guardian
from guardian.engine import absorb, commands, questions, vision
from guardian.engine.workmap import Step
from guardian.memory.store import get_maps
from guardian.memory.working import get_working
from guardian.sources import passages
from guardian.sources.store import get_sources

router = APIRouter(prefix="/api/guardian", dependencies=[Depends(_a_guardian)])


def _map(map_id: str):
    work_map = get_maps().load(map_id)
    if work_map is None:
        raise HTTPException(status_code=404, detail="No such map.")
    return work_map


class DepositBody(BaseModel):
    map_id: str
    name: str
    mime: str
    data: str            # base64


@router.post("/sources")
def deposit(body: DepositBody) -> dict:
    """A document, kept for this draft, and what can be read from it."""
    work_map = _map(body.map_id)
    try:
        raw = base64.b64decode(body.data, validate=True)
    except ValueError as error:
        raise HTTPException(status_code=422, detail="The document did not arrive whole.") from error
    if not raw or len(raw) > config.SOURCES_MAX_BYTES:
        raise HTTPException(status_code=413, detail=f"A document up to {config.SOURCES_MAX_BYTES // (1024 * 1024)} MB.")
    try:
        passages.kind_of(body.mime)
    except passages.Unreadable as error:
        raise HTTPException(status_code=415, detail=str(error)) from error
    budget = meter.meter().grant("deposited_bytes", len(raw))   # refused plainly at the limit
    try:
        read = passages.read(raw, body.mime)
    except passages.Unreadable as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    meter.meter().record(budget)
    record = get_sources().save(work_map.organisation, work_map.map_id, {
        "name": body.name.strip()[:120] or "document", "mime": body.mime, "kind": passages.kind_of(body.mime),
        "bytes": len(raw), "deposited_at": datetime.now(UTC).isoformat(), "passages": read}, raw)
    return {"source": record}


@router.get("/sources/{map_id}")
def list_sources(map_id: str) -> dict:
    work_map = _map(map_id)
    return {"sources": get_sources().list(work_map.organisation, map_id)}


class ProposeBody(BaseModel):
    map_id: str
    source_id: str
    passage: int | None = None   # its number; or name it in `said`
    said: str = ""               # "make a step of page 3", or the guardian's own words for an image


@router.post("/sources/propose")
def propose(body: ProposeBody) -> dict:
    """Urithi proposes a step from one passage, citing it; kept in the working memory until accepted."""
    work_map = _map(body.map_id)
    source = get_sources().get(work_map.organisation, work_map.map_id, body.source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="No such document in this draft.")
    chosen = (next((p for p in source["passages"] if p["n"] == body.passage), None) if body.passage
              else passages.find(body.said, source["passages"]))
    if chosen is None:
        raise HTTPException(status_code=422, detail="Name a page, a moment, or a passage of this document.")
    words = chosen["text"]
    if chosen.get("described"):
        # An image's description is Urithi's; the step needs the guardian's own words about it.
        words = body.said.strip()
        if not words:
            raise HTTPException(status_code=422, detail="Say what this image shows you, in your words.")
    memory = get_working().load(work_map.organisation, work_map.map_id)
    rails = absorb.find_guardrails(words, at=0.0, language=work_map.language, known=routes._known_guardrails(work_map, memory))
    said_at, rails = routes._said_now(rails)
    cite = {"source_id": source["source_id"], "name": source["name"], "where": chosen["where"],
            "text": chosen["text"][:600]}
    rails = [dataclasses.replace(r, cites=(cite,)) for r in rails]
    title = absorb.title_for(words, "", limit=140)
    number = len(work_map.steps) + 1
    step = Step(step_id=f"s{number}", number=number, title=title, screen_moment=0.0,
                observed=title, decision=title, reason=words,
                guardrail_ids=tuple(r.guardrail_id for r in rails), said_at=said_at, cites=(cite,))
    proposal, _ = routes._store_step_proposal(work_map, memory, step, rails, origin="source")
    get_working().save(work_map.organisation, work_map.map_id, memory)
    return {"proposal": proposal}


class AcceptBody(BaseModel):
    map_id: str
    proposal_id: str


@router.post("/sources/accept")
def accept(body: AcceptBody) -> dict:
    """The guardian says yes: the proposal becomes a step, citing its passage, a draft until validated."""
    saved = routes.save_proposal(routes.SaveBody(map_id=body.map_id, proposal_id=body.proposal_id))
    return {"step": saved["step"], "rules": saved["rules"], "guardrails": saved["guardrails"]}


class RememberBody(BaseModel):
    map_id: str
    frame: str            # the shared screen now, base64 JPEG
    said: str = ""        # what to remember about it, in the guardian's words; none, and Urithi asks
    at: float = 0.0       # the class clock
    region: dict | None = None   # pointed part of the screen {x, y, w, h} in 0..1
    source: str = "screen"
    other_faces: list | None = None


def _clock(seconds: float) -> str:
    return f"{int(seconds) // 60}:{int(seconds) % 60:02d}"


# "I want you to keep the information on the venue, the format..." is a request; what it names
# is "the venue, the format...". Measured in a live run: the step was titled with the request.
_REQUEST = re.compile(
    r"^(?:\W*(?:ok(?:ay)?|so|um+|uh+|well|alors|bon|euh)\b)*\W*"
    r"(?:(?:i\s+(?:just\s+)?(?:want|would like|need)\s+(?:you\s+)?to|i'd like you to|please|can you|could you|"
    r"je\s+veux\s+que\s+tu|j'aimerais\s+que\s+tu|peux-tu|s'il te pla[iî]t)\s+)?"
    r"(?:remember|keep(?:\s+in\s+mind)?|save|note|retiens|retiennes|gardes?|notes?|sauvegardes?)\s+"
    r"(?:(?:the|this|that|these|some|les|la|le|ces|cette|ça|ceci)\s+)?"
    r"(?:(?:info(?:rmation)?s?|screen|écran)\s+)?(?:(?:on|about|of|from|sur|de|du|des)\s+)?",
    re.IGNORECASE)


def _named(said: str) -> str:
    """What a request to keep names, as a title; the request itself when it names nothing."""
    rest = _REQUEST.sub("", said, count=1).strip(" ,.;:")
    return (rest[:1].upper() + rest[1:]) if len(rest) > 3 else said


def _asked_to_remember(language: str) -> str:
    return "Qu'est-ce que je dois retenir de cet écran ?" if language == "fr" else "What should I remember about this screen?"


@router.post("/remember")
def remember(body: RememberBody, background_tasks: BackgroundTasks = None) -> dict:
    """
    "Remember this", in a class: the shared screen as it is now, kept as a source of this draft
    and described (Urithi's words, so it can be read by someone who cannot see it). With the
    guardian's words it is a draft step at once, citing the screen; without, Urithi asks what to
    remember about it, and the answer becomes that step (routes.answer). Nothing is published
    until the knowledge is validated, and a screen no validated part cites is never archived.
    """
    work_map = _map(body.map_id)
    said = body.said.strip()
    if said and commands.has_ask_pupil_cue(said) and commands.classify_command(said, language=work_map.language).intent == "ask_pupil":
        return routes._answer_pupil(work_map, routes._session(work_map.map_id), said, background_tasks=background_tasks)
    if said and commands.has_save_cue(said):
        cmd_s = commands.classify_command(said, language=work_map.language)
        if cmd_s.intent == "save":
            return routes._save_from_voice(work_map, cmd_s.what)
    try:
        raw = base64.b64decode(body.frame, validate=True)
    except ValueError as error:
        raise HTTPException(status_code=422, detail="The screen did not arrive whole.") from error
    if not raw or len(raw) > config.SOURCES_MAX_BYTES:
        raise HTTPException(status_code=413, detail="The screen could not be kept.")
    faces = _camera_faces(work_map.map_id, raw, body.source, body.other_faces)
    if faces:
        raw = vision.blur_other_faces(raw, faces)
    if body.region:
        raw = commands.crop_region(raw, body.region)
    budget = meter.meter().grant("deposited_bytes", len(raw))
    try:
        # Measured in a real class: the guardian named the part to keep ("venue, format, last
        # meetup, today; not the date"), and a description of the whole screen kept none of it.
        described = picture.describe(raw, "image/jpeg", model=shared_config.CLASS_VISION_MODEL,
                                     focus=body.said.strip())
    except picture.PictureUnavailable:
        described = ""        # kept all the same: what counts is what the guardian says of it
    meter.meter().record(budget)
    if body.source == "camera" and said:
        described, _ = absorb.strip_unconfirmed_camera_script(described, said, work_map.language)
    where = f"the screen at {_clock(body.at)}"
    record = get_sources().save(work_map.organisation, work_map.map_id, {
        "name": f"screen-{_clock(body.at).replace(':', 'm')}.jpg", "mime": "image/jpeg", "kind": "image",
        "bytes": len(raw), "deposited_at": datetime.now(UTC).isoformat(),
        "passages": [{"n": 1, "where": where, "text": described[:passages.MAX_PASSAGE], "described": True}]}, raw)
    cite = {"source_id": record["source_id"], "name": record["name"], "where": where, "text": described[:600]}
    memory = get_working().load(work_map.organisation, work_map.map_id)
    memory.put("recent", "kept-screen", {"source_id": record["source_id"], "where": where})

    if not said:
        question = _asked_to_remember(work_map.language)
        routes._session(work_map.map_id)["last_question_text"] = question
        routes._session(work_map.map_id)["pending"] = {
            "kind": "remember", "observation": questions.Observation(at=body.at, changed=where),
            "source": body.source, "camera_text": described,
            "asked_at": body.at, "cites": (cite,)}
        memory.put("open", "question", {"text": question, "kind": "remember"})
        get_working().save(work_map.organisation, work_map.map_id, memory)
        routes._record_class_moment(
            background_tasks, work_map.organisation, work_map.expert, work_map.map_id,
            kept=where, question=question,
        )
        return {"source": record, "described": described, "question": question, **routes._voiced(question)}

    rails = absorb.find_guardrails(said, at=body.at, language=work_map.language, known=routes._known_guardrails(work_map, memory))
    if body.source == "camera":
        rails, _ = absorb.confirm_camera_rails(rails, said, described, work_map.language)
    said_at, rails = routes._said_now(rails)
    rails = [dataclasses.replace(r, cites=(cite,)) for r in rails]
    number = len(work_map.steps) + 1
    title = absorb.title_for(_named(said), "", limit=140)
    step = Step(step_id=f"s{number}", number=number, title=title, screen_moment=body.at, observed=title,
                decision=title, reason=said, guardrail_ids=tuple(r.guardrail_id for r in rails),
                said_at=said_at, cites=(cite,))
    routes._session(work_map.map_id).setdefault("recent_words", []).append(said)
    proposal, note = routes._store_step_proposal(work_map, memory, step, rails, origin="remember")
    get_working().save(work_map.organisation, work_map.map_id, memory)
    routes._record_class_moment(
        background_tasks, work_map.organisation, work_map.expert, work_map.map_id,
        kept=where, said=said,
    )
    noted = routes._noted(work_map.language, proposal)
    return {"source": record, "described": described,
            "step": None,
            "guardrails": [],
            "proposal": proposal,
            "note": note,
            "noted": noted, **routes._voiced(noted)}


class CommandBody(BaseModel):
    map_id: str
    said: str
    frame: str | None = None
    at: float = 0.0
    region: dict | None = None
    source: str = "screen"
    other_faces: list | None = None


def _camera_faces(map_id: str, raw: bytes, source: str, other_faces: list | None) -> list:
    """Faces to blur: an empty list sent by the page never skips blurring on a camera frame."""
    faces = list(other_faces or [])
    if source == "camera":
        faces.extend(vision.last_other_faces(map_id) or vision.detect_other_faces(raw, map_id))
    return faces


def _keep_screen_cite(
    work_map, frame_b64: str | None, at: float, focus: str, region: dict | None,
    source: str = "screen", other_faces: list | None = None, described_override: str = "",
):
    """Save and describe the current screen (or pointed region) when a command refers to it."""
    if not frame_b64:
        return (), ""
    try:
        raw = base64.b64decode(frame_b64, validate=True)
    except ValueError:
        return (), ""
    if not raw or len(raw) > config.SOURCES_MAX_BYTES:
        return (), ""
    faces = _camera_faces(work_map.map_id, raw, source, other_faces)
    if faces:
        raw = vision.blur_other_faces(raw, faces)
    if region:
        raw = commands.crop_region(raw, region)
    budget = meter.meter().grant("deposited_bytes", len(raw))
    if described_override.strip():
        described = described_override.strip()
    else:
        try:
            described = picture.describe(
                raw, "image/jpeg", focus=focus.strip(), model=shared_config.CLASS_VISION_MODEL
            )
        except picture.PictureUnavailable:
            described = ""
    meter.meter().record(budget)
    where = f"the screen at {_clock(at)}"
    record = get_sources().save(
        work_map.organisation,
        work_map.map_id,
        {
            "name": f"screen-{_clock(at).replace(':', 'm')}.jpg",
            "mime": "image/jpeg",
            "kind": "image",
            "bytes": len(raw),
            "deposited_at": datetime.now(UTC).isoformat(),
            "passages": [{"n": 1, "where": where, "text": described[: passages.MAX_PASSAGE], "described": True}],
        },
        raw,
    )
    cite = {"source_id": record["source_id"], "name": record["name"], "where": where, "text": described[:600]}
    return (cite,), described


@router.post("/command")
@routes.writes_map
def run_command(body: CommandBody, background_tasks: BackgroundTasks = None) -> dict:
    """
    P1: Understand the guardian's classroom command by intent with QUESTION_MODEL
    ("remember", "example", "mistake", "compare", "forget", or "none") and carry it out.
    """
    work_map = _map(body.map_id)
    said = (body.said or "").strip()
    cmd = commands.classify_command(said, language=work_map.language)
    if cmd.intent == "none":
        return {"intent": "none"}
    if cmd.intent == "ask_pupil":
        session = routes._session(work_map.map_id)
        if body.frame and not session.get("observations"):
            try:
                raw = base64.b64decode(body.frame, validate=True)
                if raw and len(raw) <= config.SOURCES_MAX_BYTES:
                    if body.region:
                        raw = commands.crop_region(raw, body.region)
                    described = picture.describe(
                        raw, "image/jpeg", focus=said, model=shared_config.CLASS_VISION_MODEL
                    ).strip()
                    if described:
                        session.setdefault("observations", []).append(
                            questions.Observation(at=body.at, changed=described[:300], scene=described)
                        )
            except Exception:
                pass
        return routes._answer_pupil(
            work_map, session, said, background_tasks=background_tasks
        )

    if cmd.intent == "save":
        # Saving is the guardian's explicit word (docs/decisions/0016), read as /tell and /answer read
        # it, never a model's guess. Found in the review of 2026-10-14: every line said in class comes
        # here first, and a model answering "save" wrote knowledge nobody asked to keep.
        if not commands.has_save_cue(said):
            return {"intent": "none"}
        return routes._save_from_voice(work_map, cmd.what)

    if cmd.intent == "remember":
        if not body.frame:
            return {"intent": "none"}
        res = remember(
            RememberBody(
                map_id=body.map_id,
                frame=body.frame,
                said=cmd.what or said,
                at=body.at,
                region=body.region,
                source=body.source,
                other_faces=body.other_faces,
            ),
            background_tasks=background_tasks,
        )
        return {"intent": "remember", **res}

    memory = get_working().load(work_map.organisation, work_map.map_id)
    session = routes._session(work_map.map_id)
    captured = session.setdefault("captured_steps", [])

    if cmd.intent == "forget":
        # "Forget that" acts on the latest thing Urithi took from the guardian, a proposal or a
        # note; a saved item only when the guardian says it is the saved one. Measured live:
        # "forget that last step" was read as the saved kind (a proposal is a step too), and the
        # scratch proposal it meant stayed, to be saved later.
        explicit_saved = bool(re.search(r"\b(?:saved|sauvegard\w*|enregistr\w*)\b", said, re.IGNORECASE))
        if not explicit_saved:
            open_props = memory.of_kind("open", "proposal-")
            if open_props:
                p_block = open_props[0]
                p_content = p_block.get("content") or {}
                pid = p_content.get("proposal_id") or p_block["ref"].removeprefix("proposal-")
                memory.drop(p_block["ref"])
                memory.drop(f"note-{pid}")
                routes._set_aside(work_map, memory, pid, p_content)
                get_working().save(work_map.organisation, work_map.map_id, memory)
                title_p = str(p_content.get("title") or "")
                msg = (
                    f"Proposition ignorée : {title_p}."
                    if work_map.language == "fr"
                    else f"Forgot proposal: {title_p}."
                )
                return {
                    "intent": "forget",
                    "forgotten": title_p,
                    "dropped_proposal": pid,
                    "steps": len(work_map.steps),
                    "noted": msg,
                    **routes._voiced(msg),
                }
            if not captured:
                recent_notes = memory.of_kind("recent", "note-")
                if recent_notes:
                    n_block = recent_notes[0]
                    n_content = n_block.get("content") or {}
                    nid = n_content.get("note_id") or n_block["ref"].removeprefix("note-")
                    memory.drop(n_block["ref"])
                    routes._set_aside(work_map, memory, nid, n_content)
                    get_working().save(work_map.organisation, work_map.map_id, memory)
                    title_n = str(n_content.get("title") or n_content.get("text") or "")
                    msg = (
                        f"Note oubliée : {title_n}."
                        if work_map.language == "fr"
                        else f"Forgot note: {title_n}."
                    )
                    return {
                        "intent": "forget",
                        "forgotten": title_n,
                        "dropped_note": nid,
                        "steps": len(work_map.steps),
                        "noted": msg,
                        **routes._voiced(msg),
                    }
        if (
            not captured
            or not work_map.steps
            or work_map.confirmed_at is not None
            or work_map.steps[-1].step_id != captured[-1]
        ):
            msg = (
                "Rien de cette séance à oublier."
                if work_map.language == "fr"
                else "Nothing from this class to forget."
            )
            return {"intent": "forget", "forgotten": "", "steps": len(work_map.steps), "noted": msg, **routes._voiced(msg)}
        captured.pop()
        removed = work_map.steps.pop()
        # Only the rules said with this step (the same moment) and held by no other step. A rule saved
        # on its own is attached to the step before it, and stays when that step is forgotten (found in
        # the second review of 2026-10-14); unsure, a rule stays rather than go.
        still_held = {gid for s in work_map.steps for gid in s.guardrail_ids}
        said_with = {g.guardrail_id for g in work_map.guardrails
                     if g.guardrail_id in (removed.guardrail_ids or ()) and removed.said_at and g.said_at == removed.said_at}
        gone_rails = said_with - still_held
        if gone_rails:
            work_map.guardrails = [g for g in work_map.guardrails if g.guardrail_id not in gone_rails]
            work_map.rulings = [r for r in work_map.rulings if r.guardrail_id not in gone_rails]
            for gid in gone_rails:
                memory.drop(f"rule-{gid}")
        work_map.order = [sid for sid in work_map.order if sid != removed.step_id]
        work_map.sections = [
            {**sec, "steps": [sid for sid in sec.get("steps", []) if sid != removed.step_id]}
            for sec in work_map.sections
        ]
        work_map.sections = [sec for sec in work_map.sections if sec["steps"]]
        work_map.confirmed_at = None
        get_maps().save(work_map)
        memory.drop(f"example-{removed.number}")
        memory.drop(f"mistake-{removed.number}")
        memory.drop(f"compare-{removed.number}")
        # The note it was saved from goes aside too. Measured live on 2026-10-14: the step forgotten
        # came straight back as a proposal, its note judged again once the step was gone.
        saved_from = str(((memory.find(f"saved-{removed.step_id}") or {}).get("content") or {}).get("note_id") or "")
        memory.drop(f"saved-{removed.step_id}")
        for n_block in memory.of_kind("recent", "note-"):
            n_content = n_block.get("content") or {}
            n_id = str(n_content.get("note_id") or n_block["ref"].removeprefix("note-"))
            if n_id == saved_from or str(n_content.get("text") or "").strip() == removed.reason.strip():
                nid = n_content.get("note_id") or n_block["ref"].removeprefix("note-")
                memory.drop(n_block["ref"])
                memory.drop(f"proposal-{nid}")
                routes._set_aside(work_map, memory, nid, n_content)
        routes._clear_teach_back(work_map, memory)
        get_working().save(work_map.organisation, work_map.map_id, memory)
        msg = (
            f"Étape {removed.number} oubliée : {removed.title}."
            if work_map.language == "fr"
            else f"Forgot step {removed.number}: {removed.title}."
        )
        return {
            "intent": "forget",
            "forgotten": removed.title,
            "removed_number": removed.number,
            "steps": len(work_map.steps),
            "noted": msg,
            **routes._voiced(msg),
        }

    if cmd.intent == "compare":
        before_raw = vision.frame_before_change(work_map.map_id, body.frame or "")
        if before_raw is None:
            sources = get_sources().list(work_map.organisation, work_map.map_id)
            if sources:
                before_raw = get_sources().data(
                    work_map.organisation, work_map.map_id, sources[-1]["source_id"]
                )
        now_raw = b""
        if body.frame:
            try:
                now_raw = base64.b64decode(body.frame, validate=True)
                faces = _camera_faces(work_map.map_id, now_raw, body.source, body.other_faces)
                if faces:
                    now_raw = vision.blur_other_faces(now_raw, faces)
                if body.region:
                    now_raw = commands.crop_region(now_raw, body.region)
            except ValueError:
                now_raw = b""
        diff = commands.compare_frames(before_raw, now_raw, focus=cmd.what) if now_raw else ""
        cites, _ = _keep_screen_cite(
            work_map, body.frame, body.at, diff or cmd.what or said, body.region,
            source=body.source, other_faces=body.other_faces, described_override=diff,
        )
        prefix = "Comparaison" if work_map.language == "fr" else "Comparison"
        title = f"{prefix}: {absorb.title_for(diff or cmd.what or said, '', limit=110)}"
        reason = said
        said_at, _ = routes._said_now([])
        number = len(work_map.steps) + 1
        step = Step(
            step_id=f"s{number}",
            number=number,
            title=title,
            screen_moment=body.at,
            observed=diff or title,
            decision="comparison",
            reason=reason,
            guardrail_ids=(),
            said_at=said_at,
            cites=cites,
        )
        session.setdefault("recent_words", []).append(reason)
        proposal, note = routes._store_step_proposal(work_map, memory, step, [], origin="compare")
        memory.put("retained", f"compare-{number}", {"text": reason, "diff": diff, "step": number})
        get_working().save(work_map.organisation, work_map.map_id, memory)
        noted = routes._noted(work_map.language, proposal)
        return {
            "intent": "compare",
            "comparison": diff,
            "step": None,
            "guardrails": [],
            "proposal": proposal,
            "note": note,
            "noted": noted,
            **routes._voiced(noted),
        }

    # "example" or "mistake"
    cites, described = _keep_screen_cite(
        work_map, body.frame, body.at, cmd.what or said, body.region,
        source=body.source, other_faces=body.other_faces,
    )
    rails = absorb.find_guardrails(said, at=body.at, language=work_map.language, known=routes._known_guardrails(work_map, memory))
    if body.source == "camera":
        rails, _ = absorb.confirm_camera_rails(rails, said, described, work_map.language)
    said_at, rails = routes._said_now(rails)
    if cites:
        rails = [dataclasses.replace(r, cites=cites) for r in rails]
    number = len(work_map.steps) + 1
    if cmd.intent == "example":
        prefix = "Exemple" if work_map.language == "fr" else "Example"
    else:
        prefix = "Erreur fréquente" if work_map.language == "fr" else "Common mistake"
    core = absorb.title_for(cmd.what or said, "", limit=110)
    title = f"{prefix}: {core}"
    step = Step(
        step_id=f"s{number}",
        number=number,
        title=title,
        screen_moment=body.at,
        observed=title,
        decision=cmd.intent,
        reason=said,
        guardrail_ids=tuple(r.guardrail_id for r in rails),
        said_at=said_at,
        cites=cites,
    )
    session.setdefault("recent_words", []).append(said)
    proposal, note = routes._store_step_proposal(work_map, memory, step, rails, origin=cmd.intent)
    memory.put("retained", f"{cmd.intent}-{number}", {"text": said, "what": cmd.what, "step": number})
    get_working().save(work_map.organisation, work_map.map_id, memory)
    noted = routes._noted(work_map.language, proposal)
    return {
        "intent": cmd.intent,
        "described": described,
        "step": None,
        "guardrails": [],
        "proposal": proposal,
        "note": note,
        "noted": noted,
        **routes._voiced(noted),
    }

