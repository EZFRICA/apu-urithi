"""
What a class sees: two frames to one short line, from a model fast enough to keep up.

Target: guardian/engine/vision.py. The model is faked; what is checked is which model is
asked, and what the code makes of whatever it answers.
"""

import json
from types import SimpleNamespace

import pytest

from apu import config
from apu.modality import voice
from guardian.engine import vision


class Answers:
    def __init__(self, text):
        self.text = text
        self.models = SimpleNamespace(generate_content=self._generate)
        self.asked = []

    def _generate(self, model, contents, config=None):
        self.asked.append(model)
        return SimpleNamespace(text=self.text, usage_metadata=None, candidates=[])


@pytest.fixture
def answering():
    def install(answer):
        client = Answers(answer if isinstance(answer, str) else json.dumps(answer))
        voice.set_client(client)
        return client

    yield install
    voice.set_client(None)
    vision.forget("class")


def test_a_class_is_read_by_its_own_fast_model(answering):
    """Measured on the same real pair, three times each: 12.3 s a pair with the general vision
    model, 0.9 s with the class's, which saw the change and named it."""
    client = answering({"changed": "channel set to #members", "field": "Announce in", "decision": True})
    assert vision.what_changed("YQ==", "class", 1.0) is None, "the first frame has nothing to compare"
    seen = vision.what_changed("Yg==", "class", 3.0)
    assert seen.changed == "channel set to #members" and seen.field == "Announce in"
    assert client.asked == [config.CLASS_VISION_MODEL] and config.CLASS_VISION_MODEL != config.VISION_MODEL


def test_a_list_of_changes_is_read_and_anything_else_skips_the_frame(answering):
    """Measured: a smaller model answered with a list, and the class's call failed outright."""
    answering([{"changed": "date set to 15 Oct", "field": "Date", "decision": True}])
    vision.what_changed("YQ==", "class", 1.0)
    assert vision.what_changed("Yg==", "class", 3.0).changed == "date set to 15 Oct"
    for odd in ("[]", '"moved"', "not json"):
        answering(odd)
        assert vision.what_changed("Yw==", "class", 5.0) is None, odd


def test_the_part_a_guardian_names_is_copied_rather_than_the_screen_described(monkeypatch):
    """Measured in a real class: "keep venue, format, last meetup, today; not the date" was kept
    as a description of the whole screen. The guardian's words now name the part copied."""
    from apu.modality import picture

    sent = []

    class Seeing:
        models = SimpleNamespace(generate_content=lambda model, contents, config=None:
                                 sent.append(contents[1]) or SimpleNamespace(text="Venue: Dockside Library",
                                                                             usage_metadata=None, candidates=[]))

    monkeypatch.setattr(picture, "get_client", lambda: Seeing())
    picture.describe(b"jpg", "image/jpeg", focus="keep venue, format, last meetup, today")
    picture.describe(b"jpg", "image/jpeg")
    named, whole = sent
    assert "keep venue, format, last meetup, today" in named and "Copy exactly what that part shows" in named
    assert whole == picture.DESCRIBE_PROMPT


def test_the_class_vision_is_told_to_name_the_values_it_reads():
    """Measured in a live run: "Date and Announce in fields were filled", and the question then
    guessed the date. The class vision is told to quote each new value as written."""
    assert "name each control that changed and its new value exactly as written" in vision.SYSTEM
    assert "Never say only that fields were filled or changed" in vision.SYSTEM
