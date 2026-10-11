"""Words heard as they are said: the teleprompter's ear.

The page streams the microphone as 16 kHz, 16-bit PCM over a websocket while the person holds
Space; this relays it to ElevenLabs realtime transcription (`scribe_v2_realtime`, as measured
in the school tutor's live lab) and sends each partial transcript back at once, so the person
sees their words appear as they speak them and can tell at once when one was heard wrong. When
they let go, the page sends {"type": "end"}; the committed text comes back as the final words,
and the page sends those through the side's ordinary route: the guard, the meter and the
answer stay where they are, and nothing here decides anything.

Frames from the page:   binary PCM, or {"type": "end"}
Frames to the page:     {"type": "partial", "text"}, {"type": "final", "text"},
                        {"type": "unavailable" | "refused", "detail"}

No transcription service, or none answering: "unavailable", and the page sends the recording
the batch way, as before. Metered in seconds heard (apu/meter.py): a quota already spent is
refused before the first word; the seconds are recorded when an utterance ends. Who may open
it: a request with an Origin header must come from this server's own pages.
"""

import asyncio
import base64
import contextlib
import json
import os
import time

from starlette.websockets import WebSocket, WebSocketDisconnect

from apu import config, meter
from apu.logger import get_logger
from apu.modality import voice

logger = get_logger(__name__)

BYTES_PER_SECOND = 32000          # 16 kHz, 16-bit, one channel
COMMIT_WAIT = 1.5                 # seconds to wait for the committed text after "end"
OPEN_WAIT = 5.0                   # seconds the transcription service has to answer the opening


def same_origin(ws: WebSocket) -> bool:
    """A page of this server, or a client with no Origin (curl, the tests, a script on this machine)."""
    origin = ws.headers.get("origin")
    if not origin:
        return True
    host = ws.headers.get("host", "")
    return origin.split("://", 1)[-1].rstrip("/") == host


class _Utterance:
    """One press of Space: the audio heard, the transcription socket, what came back."""

    def __init__(self):
        self.audio = bytearray()
        self.connection = None
        self.committed = ""
        self.done = asyncio.Event()
        self.started = time.perf_counter()


async def _open(send, loop, said: _Utterance):
    from elevenlabs.client import ElevenLabs
    from elevenlabs.realtime import AudioFormat, CommitStrategy, RealtimeEvents

    client = ElevenLabs(api_key=os.environ.get(config.ELEVENLABS_API_KEY_ENV, ""))
    connection = await client.speech_to_text.realtime.connect({
        "model_id": "scribe_v2_realtime", "audio_format": AudioFormat.PCM_16000,
        "sample_rate": 16000, "commit_strategy": CommitStrategy.MANUAL,
    })

    def partial(data: dict):
        text = (data.get("text") or data.get("transcript") or "").strip()
        if text:
            asyncio.run_coroutine_threadsafe(send({"type": "partial", "text": text}), loop)

    def committed(data: dict):
        text = (data.get("text") or data.get("transcript") or "").strip()
        if text:
            said.committed = f"{said.committed} {text}".strip()
        loop.call_soon_threadsafe(said.done.set)

    def failed(data: dict):
        logger.info("Realtime transcription said: %s", str(data.get("error") or data.get("message") or data)[:200])

    connection.on(RealtimeEvents.PARTIAL_TRANSCRIPT, partial)
    connection.on(RealtimeEvents.COMMITTED_TRANSCRIPT, committed)
    connection.on(RealtimeEvents.ERROR, failed)
    return connection


async def relay(ws: WebSocket, principal: meter.Principal, *, opener=None) -> None:
    """Serve one page's microphone until it goes. `opener` opens the transcription socket;
    read when called, not when this module was loaded, so a test can stand in for the service."""
    opener = opener or _open
    if not same_origin(ws):
        await ws.close(code=4403)
        return
    await ws.accept()

    async def send(message: dict):
        with contextlib.suppress(Exception):    # the page may have gone between two words
            await ws.send_text(json.dumps(message))

    if config.VOICE_STT_PROVIDER != "elevenlabs" or not os.environ.get(config.ELEVENLABS_API_KEY_ENV):
        await send({"type": "unavailable", "detail": "No live transcription here; the recording is sent whole."})
        await ws.close()
        return
    try:
        meter.meter().grant("transcribed_seconds", 1, principal)
    except meter.Refused as refused:
        await send({"type": "refused", "detail": refused.reason, "refused": refused.capability})
        await ws.close()
        return

    loop = asyncio.get_running_loop()
    said = _Utterance()
    try:
        while True:
            message = await ws.receive()
            if message.get("type") == "websocket.disconnect":
                break
            if message.get("bytes") is not None:
                chunk = message["bytes"]
                if said.connection is None and not said.audio:
                    try:
                        # Bounded: measured in a test, a service that never answered the
                        # opening held the page's microphone forever.
                        said.connection = await asyncio.wait_for(opener(send, loop, said), OPEN_WAIT)
                    except Exception as error:
                        # A third party socket with no documented exceptions: the page falls
                        # back to sending the recording whole.
                        logger.warning("Live transcription could not start: %s", error)
                        await send({"type": "unavailable", "detail": "Live transcription is not answering."})
                said.audio.extend(chunk)
                if said.connection is not None:
                    with contextlib.suppress(Exception):     # one frame lost degrades, never ends, the turn
                        await said.connection.send({"audio_base_64": base64.b64encode(chunk).decode("ascii")})
            elif message.get("text"):
                try:
                    asked = json.loads(message["text"])
                except (json.JSONDecodeError, TypeError):
                    continue
                if asked.get("type") == "end":
                    await send({"type": "final", "text": await _finish(said, principal)})
                    said = _Utterance()
    except (WebSocketDisconnect, ConnectionResetError):
        pass
    finally:
        if said.connection is not None:
            with contextlib.suppress(Exception):
                await said.connection.close()


async def _finish(said: _Utterance, principal: meter.Principal) -> str:
    """The committed words of one utterance; the batch transcription when the live one gave none."""
    text = ""
    if said.connection is not None:
        with contextlib.suppress(Exception):
            await said.connection.commit()
            await asyncio.wait_for(said.done.wait(), COMMIT_WAIT)
        with contextlib.suppress(Exception):
            await said.connection.close()
        text = said.committed.strip()
        if text:
            seconds = max(1.0, len(said.audio) / BYTES_PER_SECOND)
            m = meter.meter()
            m.record(m.grant("transcribed_seconds", seconds, principal, never_refuse=True))
    if not text and len(said.audio) >= 3200:
        with contextlib.suppress(Exception):     # metered inside voice.transcribe
            with meter.acting_as(principal):
                text = await asyncio.to_thread(voice.transcribe, voice.wav_from_pcm(bytes(said.audio), 16000))
    return text
