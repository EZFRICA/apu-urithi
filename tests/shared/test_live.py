"""
The teleprompter's ear: words heard as they are said, relayed live.

Target: apu/modality/live.py, the /listen websockets of both sides.

The transcription service is faked: what is checked is what the relay decides whatever it
hears: partials go back at once, the committed words come back as the final text, the seconds
are counted, a spent quota is refused before the first word, a page from elsewhere is refused,
and without a live service the page is told to send the recording whole.
"""

import asyncio
import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from apu import config, meter
from apu.modality import live


def fake_opener(heard=("a useful", "a useful tip"), committed="a useful tip", opened=None):
    async def opener(send, loop, said):
        class Socket:
            frames = 0

            async def send(self, frame):
                Socket.frames += 1
                if Socket.frames <= len(heard):
                    await send_partial(heard[Socket.frames - 1])

            async def commit(self):
                said.committed = committed
                said.done.set()

            async def close(self):
                pass

        async def send_partial(text):
            await send({"type": "partial", "text": text})

        if opened is not None:
            opened.append(1)
        return Socket()
    return opener


@pytest.fixture
def listening(monkeypatch):
    from server import app

    monkeypatch.setattr(config, "VOICE_STT_PROVIDER", "elevenlabs")
    monkeypatch.setenv(config.ELEVENLABS_API_KEY_ENV, "test-key-not-real")
    monkeypatch.setattr(live, "_open", fake_opener())
    return TestClient(app)


def _say(ws, frames=3):
    for _ in range(frames):
        ws.send_bytes(b"\0\0" * 1600)        # a tenth of a second each
    ws.send_text(json.dumps({"type": "end"}))


def test_partials_come_back_as_they_are_heard_and_the_final_words_at_the_end(listening):
    with listening.websocket_connect("/api/learner/listen?person_id=member") as ws:
        _say(ws)
        seen = [json.loads(ws.receive_text()) for _ in range(3)]
    assert seen == [{"type": "partial", "text": "a useful"}, {"type": "partial", "text": "a useful tip"},
                    {"type": "final", "text": "a useful tip"}]
    spent = meter.meter().counters.total("transcribed_seconds", since=datetime.now(UTC) - timedelta(hours=1),
                                         person_id="member")
    assert spent == 1.0, "counted, at least a second per utterance"


def test_a_spent_quota_is_refused_before_the_first_word(listening, tmp_path, monkeypatch):
    opened = []
    monkeypatch.setattr(live, "_open", fake_opener(opened=opened))
    path = tmp_path / "policy.json"
    path.write_text(json.dumps({"quotas": {"learner": {"transcribed_seconds": {"period": "day", "stop": 5}}}}))
    monkeypatch.setattr(config, "POLICY_PATH", str(path))
    meter.meter().counters.add("urithi", "member", "learner", "transcribed_seconds", 5, datetime.now(UTC))
    with listening.websocket_connect("/api/learner/listen?person_id=member") as ws:
        ws.send_bytes(b"\0\0" * 1600)     # answered as a partial if the refusal was skipped
        refused = json.loads(ws.receive_text())
    assert refused["type"] == "refused" and refused["refused"] == "transcribed_seconds"
    assert not opened, "refused before opening the live transcription service"


def test_without_a_live_service_the_page_is_told_to_send_the_recording(listening, monkeypatch):
    monkeypatch.setattr(config, "VOICE_STT_PROVIDER", "gemini")
    with listening.websocket_connect("/api/learner/listen?person_id=member") as ws:
        assert json.loads(ws.receive_text())["type"] == "unavailable"


def test_a_page_from_elsewhere_is_refused(listening):
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect) as closed:
        with listening.websocket_connect("/api/learner/listen?person_id=member",
                                         headers={"origin": "https://elsewhere.example"}) as ws:
            ws.send_text(json.dumps({"type": "end"}))     # answered at once if it was let in
            ws.receive_text()
    assert closed.value.code == 4403


def test_the_guardians_ear_is_a_guardians(listening):
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect) as closed:
        with listening.websocket_connect("/api/guardian/listen?person_id=visitor") as ws:
            ws.send_text(json.dumps({"type": "end"}))
            ws.receive_text()
    assert closed.value.code == 4403
    with listening.websocket_connect("/api/guardian/listen?person_id=ezekias") as ws:
        _say(ws, frames=1)
        assert json.loads(ws.receive_text())["type"] == "partial"


def test_nothing_committed_falls_back_to_the_recording_whole(listening, monkeypatch):
    from apu.modality import voice

    monkeypatch.setattr(live, "_open", fake_opener(heard=(), committed=""))
    monkeypatch.setattr(voice, "transcribe", lambda audio, *a: "heard the batch way")
    with listening.websocket_connect("/api/learner/listen?person_id=member") as ws:
        _say(ws)
        assert json.loads(ws.receive_text()) == {"type": "final", "text": "heard the batch way"}


def test_the_relay_holds_no_state_between_two_utterances(listening):
    with listening.websocket_connect("/api/learner/listen?person_id=member") as ws:
        _say(ws)
        [ws.receive_text() for _ in range(3)]
        _say(ws)
        again = [json.loads(ws.receive_text()) for _ in range(3)]
    assert again[-1] == {"type": "final", "text": "a useful tip"}, "a second press is heard on its own"


def test_same_origin_reads_the_host():
    class Fake:
        def __init__(self, headers):
            self.headers = headers

    assert live.same_origin(Fake({"host": "localhost:8790", "origin": "http://localhost:8790"}))
    assert live.same_origin(Fake({"host": "localhost:8790"}))
    assert not live.same_origin(Fake({"host": "localhost:8790", "origin": "http://evil.test"}))
    assert asyncio.iscoroutinefunction(live.relay)


def test_a_service_that_never_opens_does_not_hold_the_microphone(listening, monkeypatch):
    """Measured: with a service that never answered the opening, the relay waited forever."""
    fallback = fake_opener()

    async def never(send, loop, said):
        await asyncio.sleep(1.0)
        return await fallback(send, loop, said)

    monkeypatch.setattr(live, "OPEN_WAIT", 0.2)
    monkeypatch.setattr(live, "_open", never)
    with listening.websocket_connect("/api/learner/listen?person_id=member") as ws:
        ws.send_bytes(b"\0\0" * 1600)
        assert json.loads(ws.receive_text())["type"] == "unavailable"
