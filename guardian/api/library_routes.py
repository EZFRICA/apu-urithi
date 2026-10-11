"""The library's HTTP surface, for a guardian.

Identities are simulated (library.access): every reply that depends on one says so. A map is
published in its own organisation, by a guardian of that organisation, and nowhere else.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from apu import meter
from apu.logger import get_logger
from guardian.memory.store import get_maps
from guardian.publish import body_id_for, publication_from
from library import access
from library.model import KnowledgeError
from library.store import get_store

logger = get_logger("knowledge")
router = APIRouter(prefix="/api/guardian")


EVERY_LEVEL = ("public", "community", "restricted")


def _who(person_id: str | None, organisation: str | None = None) -> access.Person:
    try:
        who = access.person(person_id, organisation)
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    meter.act_as(meter.Principal(who.organisation, who.person_id, who.role))
    return who


def _guardian_of(work_map, person_id: str | None) -> access.Person:
    """The map's own guardian, acting in the map's own organisation."""
    try:
        return access.require_guardian(person_id, work_map.expert, organisation=work_map.organisation)
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error


@router.get("/people")
def list_people() -> dict:
    """Who one can be, in simulation: every membership, a person once per organisation."""
    return {"simulated": access.SIMULATED, "people": [access.as_listed(p) for p in access.memberships()]}


@router.get("/knowledge")
def knowledge(person_id: str, organisation: str | None = None) -> dict:
    """
    What this guardian has taught, one entry per body of knowledge: the latest map for it, and
    the version in the library. Teaching more continues that map, never a fresh one: a new
    version replaces the old whole, so starting again from nothing would publish less.
    """
    who = _who(person_id, organisation)
    if who.role != "guardian":
        raise HTTPException(status_code=403, detail=f"{who.name} is not a guardian in {who.organisation}.")
    store = get_store()
    latest: dict[str, dict] = {}
    for entry in get_maps().list_maps(who.organisation):
        if entry["expert"] != who.name:
            continue
        work_map = get_maps().load(entry["map_id"])
        body_id = body_id_for(work_map)
        if body_id in latest and latest[body_id]["created_at"] >= entry["created_at"]:
            continue
        latest[body_id] = {"map_id": work_map.map_id, "task": work_map.task, "body_id": body_id,
                           "created_at": entry["created_at"], "steps": len(work_map.steps),
                           "rules": len(work_map.guardrails), "confirmed": bool(work_map.confirmed_at),
                           "language": work_map.language,
                           "published": store.version_of(who.organisation, body_id)}
    return {"maps": sorted(latest.values(), key=lambda m: m["created_at"], reverse=True),
            "simulated": access.SIMULATED}


def _asked_levels(work_map, asked: dict[str, str]) -> dict[str, str]:
    """
    What the guardian chose now, over what each part already has in the library.

    Measured: a body taught again showed every part as public in the preview, including two
    the guardian had kept to the community, and one click on Publish would have opened them.
    A level is changed by the guardian, never by teaching the body again.
    """
    published = get_store().body_units(work_map.organisation, body_id_for(work_map), EVERY_LEVEL)
    # From the library; or, once withdrawn, from what the map remembers of its last publish.
    known = ({u["unit_id"]: u["access"] for u in published["units"]} if published else dict(work_map.access))
    if not known:
        return dict(asked)
    # Only parts still in the map: a part taught away since is not a typo to refuse.
    present = {u.unit_id for u in publication_from(work_map, version=0).units}
    kept = {unit_id: level for unit_id, level in known.items() if unit_id in present}
    return {**kept, **asked}


class PublishBody(BaseModel):
    map_id: str
    person_id: str
    default_access: str = "public"
    access: dict[str, str] = {}


@router.post("/preview")
def preview(body: PublishBody) -> dict:
    """
    What a publish would write, without writing it: each unit with the access level it would
    really get, including any raised because it repeats a more restricted unit's words.
    """
    work_map = get_maps().load(body.map_id)
    if work_map is None:
        raise HTTPException(status_code=404, detail="No such map.")
    _guardian_of(work_map, body.person_id)
    levels = _asked_levels(work_map, body.access)
    try:
        publication = publication_from(work_map, version=0, access=levels,
                                       default_access=body.default_access)
    except KnowledgeError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    asked = {**{u.unit_id: body.default_access for u in publication.units}, **levels}
    return {"body_id": publication.body.body_id, "simulated": access.SIMULATED,
            "units": [{"unit_id": u.unit_id, "kind": u.kind, "text": u.text, "quote": u.quote,
                       "access": u.access, "asked": asked[u.unit_id],
                       "raised": u.access != asked[u.unit_id]} for u in publication.units],
            "cases": len(publication.cases), "sources": len(publication.sources)}


@router.post("/publish")
def publish(body: PublishBody) -> dict:
    """A confirmed Work Map into the library, by its own guardian, as a new version."""
    work_map = get_maps().load(body.map_id)
    if work_map is None:
        raise HTTPException(status_code=404, detail="No such map.")
    _guardian_of(work_map, body.person_id)
    store = get_store()
    try:
        publication = publication_from(work_map, version=store.version_of(work_map.organisation, body_id_for(work_map)) + 1,
                                       access=_asked_levels(work_map, body.access),
                                       default_access=body.default_access)
    except KnowledgeError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    summary = store.publish(publication)
    work_map.access = {u.unit_id: u.access for u in publication.units}
    get_maps().save(work_map)
    logger.info("Published %s v%d: %d units", summary["body_id"], summary["version"], summary["units"])
    return {**summary, "simulated": access.SIMULATED}


@router.get("/bodies")
def bodies(person_id: str, organisation: str | None = None) -> dict:
    who = _who(person_id, organisation)
    return {"bodies": get_store().bodies_for(who.organisation, who.allowed), "as": who.name,
            "organisation": who.organisation, "simulated": access.SIMULATED}


@router.delete("/body/{body_id}")
def withdraw(body_id: str, person_id: str, organisation: str | None = None) -> dict:
    """The guardian takes their knowledge back: the body and everything hanging from it."""
    try:
        who = access.require_guardian(person_id, organisation=organisation)
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    store = get_store()
    known = {b["body_id"]: b for b in store.bodies_for(who.organisation, EVERY_LEVEL)}
    if body_id not in known:
        raise HTTPException(status_code=404, detail="No such body of knowledge.")
    if known[body_id]["guardian"] != who.name:
        raise HTTPException(status_code=403, detail=f"This knowledge is {known[body_id]['guardian']}'s, not {who.name}'s.")
    return {"withdrawn": store.withdraw(who.organisation, body_id), "simulated": access.SIMULATED}


@router.delete("/map/{map_id}")
def delete_knowledge(map_id: str, person_id: str, organisation: str | None = None) -> dict:
    """
    The guardian deletes a knowledge they teach, at their word, after a second press on the
    page: withdrawn from the library if it was published, then the map, its working memory,
    its class in progress and its documents (the archived copies too) are gone. Nothing of it
    is kept, and it cannot be undone.
    """
    from guardian.engine import vision
    from guardian.memory.store import get_sessions
    from guardian.memory.working import get_working
    from guardian.sources.store import get_archive, get_sources

    try:
        who = access.require_guardian(person_id, organisation=organisation)
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    work_map = get_maps().load(map_id)
    if work_map is None or work_map.organisation != who.organisation:
        raise HTTPException(status_code=404, detail="No such knowledge.")
    if work_map.expert != who.name:
        raise HTTPException(status_code=403, detail=f"This knowledge is {work_map.expert}'s, not {who.name}'s.")
    body_id = body_id_for(work_map)
    withdrawn = get_store().withdraw(work_map.organisation, body_id)
    # Every map of this knowledge: the page shows the latest, and an older one left behind
    # would come back in its place as if nothing had been deleted.
    maps = [entry["map_id"] for entry in get_maps().list_maps(work_map.organisation)
            if entry["expert"] == who.name and body_id_for(get_maps().load(entry["map_id"])) == body_id]
    sources = get_sources()
    documents = 0
    for each in maps:
        for record in sources.list(work_map.organisation, each):
            if record.get("archived") and record["archived"] != "local":
                try:
                    get_archive().remove(record["archived"])
                except Exception as error:
                    # The map still goes; the copy left is said in the log, to be removed by hand.
                    logger.warning("An archived document could not be removed: %s", error)
            sources.remove(work_map.organisation, each, record["source_id"])
            documents += 1
        get_working().forget(work_map.organisation, each)
        get_sessions().drop(each)
        vision.forget(each)
        get_maps().delete(each)
    logger.info("Deleted a knowledge: %d maps, %d documents, withdrawn: %s", len(maps), documents, withdrawn)
    return {"deleted": len(maps), "withdrawn": withdrawn, "documents": documents, "simulated": access.SIMULATED}
