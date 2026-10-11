"""
Illustrations: a memory aid drawn from a guardian's words, that must say nothing of its own.

Target: apu/modality/picture.py, learner/renderings.py, the picture route and packages.

Every model is faked. What is checked is what the code guarantees whatever a model does: a
drawing with writing in it is never shown, a check that cannot be had shows nothing, one
drawing serves a unit's version and is never drawn twice, and a package never draws.
"""

import io
import json
from types import SimpleNamespace

import pytest

from learner.memory.progress import set_progress
from PIL import Image

from apu import config
from learner import config as learner_config
from apu.modality import picture
from learner import renderings

UNIT = {"unit_id": "ezekias--community:rule-1", "version": 1, "text": "When fewer than ten people register, move it.",
        "quote": "Under ten registrations, I move the meetup.", "at": 3.0}


def png(size=(1200, 900)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, (200, 180, 120)).save(out, format="PNG")
    return out.getvalue()


class FakeModels:
    """Answers the drawing call with an image and the check with what it is told to say."""

    def __init__(self, looks=("NO",)):
        self.looks = list(looks)
        self.calls = []

    def generate_content(self, model, contents, config=None):
        self.calls.append(model)
        if model == picture.config.PICTURE_MODEL:
            part = SimpleNamespace(inline_data=SimpleNamespace(data=png(), mime_type="image/png"))
            return SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(parts=[part]))])
        return SimpleNamespace(text=self.looks.pop(0) if self.looks else "NO")


@pytest.fixture
def models():
    fake = FakeModels()
    picture.set_client(SimpleNamespace(models=fake))
    yield fake
    picture.set_client(None)


@pytest.fixture(autouse=True)
def renderings_here(monkeypatch, tmp_path):
    monkeypatch.setattr(learner_config, "DATA_DIR", str(tmp_path))


def test_a_drawing_with_no_writing_is_kept_small_and_in_webp(models):
    drawn = picture.illustrate(UNIT["text"], UNIT["quote"])
    assert drawn.mime_type == "image/webp"
    with Image.open(io.BytesIO(drawn.data)) as image:
        assert max(image.size) <= 768
    assert models.calls == [config.PICTURE_MODEL, config.VISION_MODEL], "every drawing is looked at"


def test_a_drawing_with_writing_is_drawn_again_then_refused(models):
    models.looks = ["YES", "NO"]
    picture.illustrate(UNIT["text"], UNIT["quote"])
    assert models.calls.count(config.PICTURE_MODEL) == 2
    models.looks, models.calls = ["YES", "YES"], []
    with pytest.raises(picture.PictureUnavailable, match="writing"):
        picture.illustrate(UNIT["text"], UNIT["quote"])


@pytest.mark.parametrize("said", ["", "Maybe", "I see a person"])
def test_a_check_with_no_clear_answer_shows_nothing(models, said):
    models.looks = [said]
    with pytest.raises(picture.PictureUnavailable):
        picture.illustrate(UNIT["text"], UNIT["quote"])


def test_a_check_that_fails_shows_nothing(models):
    """Fail closed: a drawing nobody could look at is not shown."""
    def broken(model, contents, config=None):
        if model == picture.config.VISION_MODEL:
            raise RuntimeError("down")
        return FakeModels().generate_content(model, contents, config)
    models.generate_content = broken
    with pytest.raises(picture.PictureUnavailable, match="could not be checked"):
        picture.illustrate(UNIT["text"], UNIT["quote"])


def test_the_prompt_asks_for_no_writing_no_counts_and_holds_the_words_as_data():
    prompt = picture.DRAW_PROMPT
    assert "no writing" in prompt.lower() and "no numbers" in prompt
    assert "countable quantity" in prompt, "a picture of twelve people would contradict 'fewer than ten'"
    assert "<knowhow>{text}</knowhow>" in prompt


def test_without_a_key_there_is_no_picture(monkeypatch):
    picture.set_client(None)
    monkeypatch.delenv(config.GEMINI_API_KEY_ENV, raising=False)
    with pytest.raises(picture.PictureUnavailable):
        picture.get_client()


def test_one_drawing_per_version_and_kept_never_draws(models):
    assert renderings.picture_kept(UNIT, organisation="urithi") is None, "looking never draws"
    assert models.calls == []
    first = renderings.picture(UNIT, organisation="urithi")
    again = renderings.picture(UNIT, organisation="urithi")
    assert not first["cached"] and again["cached"] and first["image"] == again["image"]
    assert models.calls.count(config.PICTURE_MODEL) == 1
    renderings.picture({**UNIT, "version": 2}, organisation="urithi")
    assert models.calls.count(config.PICTURE_MODEL) == 2, "a new version is drawn again"
    assert renderings.picture_kept(UNIT, organisation="urithi")["mime"] == "image/webp"


# ── the route and the package ────────────────────────────────────────────────

@pytest.fixture
def client(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from apu import embeddings as embedder
    from learner.memory.progress import Progress
    from library import store
    from server import app
    from tests.support import BODY, WordEmbedder, community

    embedder.set_embedder(WordEmbedder())
    lib = store.MemoryKnowledgeStore()
    lib.publish(community())
    store.set_store(lib)
    set_progress(Progress(str(tmp_path / "p.sqlite3")))
    yield TestClient(app), BODY
    store.set_store(None)
    embedder.set_embedder(None)


def test_a_hidden_unit_has_no_picture_and_nothing_is_drawn_for_it(client, models):
    http, body = client
    reply = http.get(f"/api/learner/unit/{body}:rule-report/picture", params={"person_id": "visitor"})
    assert reply.status_code == 404 and models.calls == []


def test_the_picture_is_drawn_once_shown_in_the_unit_and_carried_offline(client, models):
    http, body = client
    unit = f"{body}:rule-cancel"
    assert http.get(f"/api/learner/unit/{unit}", params={"person_id": "visitor"}).json()["picture"] is False
    pkg = http.get(f"/api/learner/package/{body}", params={"person_id": "visitor"}).json()
    assert all(u["picture"] is None for u in json.loads(pkg["content_json"])["units"]) and models.calls == [], \
        "a package never draws"
    drawn = http.get(f"/api/learner/unit/{unit}/picture", params={"person_id": "visitor"}).json()
    assert drawn["mime"] == "image/webp"
    assert http.get(f"/api/learner/unit/{unit}", params={"person_id": "visitor"}).json()["picture"] is True
    pkg = http.get(f"/api/learner/package/{body}", params={"person_id": "visitor"}).json()
    kept = {u["unit_id"]: u["picture"] for u in json.loads(pkg["content_json"])["units"]}
    assert kept[unit]["image"] == drawn["image"]


def test_no_picture_is_a_503_said_plainly(client, models):
    http, body = client
    models.looks = ["YES", "YES"]
    reply = http.get(f"/api/learner/unit/{body}:rule-cancel/picture", params={"person_id": "visitor"})
    assert reply.status_code == 503 and "writing" in reply.json()["detail"]


def test_the_path_carries_only_links_between_units_one_may_see(client):
    http, body = client
    links = http.get(f"/api/learner/path/{body}", params={"person_id": "visitor"}).json()["links"]
    assert links and not any("rule-report" in (link["source_id"] + link["target_id"]) for link in links)


def test_audio_kept_without_its_word_timings_is_made_again_once(monkeypatch):
    """Measured: parts listened to before word timings existed read back on the teleprompter
    as one block. Made again once, with the timings; then served from the cache."""
    from apu.modality import voice
    from learner.memory.files import get_files

    made = []

    def synthesize(text, compressed=False):
        made.append(text)
        return voice.SpokenAudio(b"ID3audio", "audio/mpeg", ({"word": "A", "start": 0.0, "end": 0.2},))

    monkeypatch.setattr(voice, "synthesize", synthesize)
    key = renderings._key(UNIT, "en")
    get_files().write("urithi", key + ".mp3", b"ID3old")                 # kept, from before timings
    first = renderings.audio(UNIT, "Ezekias", organisation="urithi")
    second = renderings.audio(UNIT, "Ezekias", organisation="urithi")
    assert first["words"] == [{"word": "A", "start": 0.0, "end": 0.2}] and not first["cached"]
    assert second["cached"] and second["words"] == first["words"] and len(made) == 1
