"""The guardian's microphone, live: their words on the teleprompter as they say them.

A websocket, so not under the router of guardian/api/routes.py, whose dependency reads an HTTP
request; the same check is made here: a guardian of the organisation acted in, from the
registry. What is relayed and how is apu/modality/live.py's.
"""

from fastapi import APIRouter, WebSocket

from apu import meter
from apu.modality import live
from library import access

router = APIRouter(prefix="/api/guardian")


@router.websocket("/listen")
async def listen(ws: WebSocket, person_id: str = "", organisation: str | None = None) -> None:
    try:
        who = access.require_guardian(person_id, organisation=organisation)
    except PermissionError:
        await ws.close(code=4403)
        return
    await live.relay(ws, meter.Principal(who.organisation, who.person_id, who.role))
