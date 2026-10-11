"""A unit in the forms a learner needs: spoken, in braille, and illustrated.

A rendering belongs to a unit and its version (boundary 4 in docs/architecture.md): the cache
key is a hash of the unit's id, version, words and language, so a changed unit is rendered
again and an unchanged one is never paid for twice. The same files go into an offline package.
Each organisation's renderings live under its own prefix: nothing drawn for one is served to another.
"""

import base64
import hashlib
import json

from apu import config
from apu.modality import picture as pictures
from apu.modality import voice
from apu.modality.braille.sheet import braille_sheet
from apu.modality.braille.translator import BrailleGrade
from learner.memory.files import get_files

SAID = {"en": "{guardian} said", "fr": "{guardian} a dit"}


def spoken_text(unit: dict, guardian: str, language: str = "en") -> str:
    said = SAID.get(language, SAID["en"]).format(guardian=guardian)
    return f"{unit['text']} {said}: {unit['quote']}"


def _key(unit: dict, language: str) -> str:
    raw = f"{unit['unit_id']}|{unit.get('version', 1)}|{unit['text']}|{unit['quote']}|{language}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def audio(unit: dict, guardian: str, language: str = "en", *, organisation: str) -> dict:
    """The unit read out, as base64 MP3 (WAV when the provider gives no MP3), with when each
    word is said, kept beside it for the teleprompter. Raises voice.VoiceUnavailable."""
    key = _key(unit, language)
    files = get_files()
    for extension, mime in ((".mp3", "audio/mpeg"), (".wav", "audio/wav")):
        kept = files.read(organisation, key + extension)
        timed = files.read(organisation, key + ".words.json")
        # Audio made before word timings existed is made again, once, with them: measured, the
        # parts already listened to read back on the teleprompter as one block, not word by word.
        if kept is not None and timed is not None:
            return {"audio": base64.b64encode(kept).decode("ascii"), "mime": mime, "cached": True,
                    "text": spoken_text(unit, guardian, language), "words": json.loads(timed)}
    spoken = voice.synthesize(spoken_text(unit, guardian, language), compressed=True)
    extension = ".mp3" if spoken.mime_type == "audio/mpeg" else ".wav"
    files.write(organisation, key + extension, spoken.data)
    files.write(organisation, key + ".words.json", json.dumps(list(spoken.words)).encode())
    return {"audio": base64.b64encode(spoken.data).decode("ascii"), "mime": spoken.mime_type,
            "cached": False, "text": spoken_text(unit, guardian, language), "words": list(spoken.words)}


def braille(unit: dict, guardian: str, grade: int = 2, language: str = "en") -> dict:
    """The unit as embossed pages, the same layout as the .brf an embosser prints."""
    sheet = braille_sheet(spoken_text(unit, guardian, language), grade=BrailleGrade(grade),
                          language="fr" if language == "fr" else "en")
    return {"pages_unicode": [list(page) for page in sheet.pages_unicode], "brf": sheet.brf,
            "pages": sheet.pages, "grade": grade}


def _picture_name(unit: dict) -> str:
    # No language in the key: a picture holds no words, so one serves every language.
    raw = f"{unit['unit_id']}|{unit.get('version', 1)}|{unit['text']}|{unit['quote']}|{config.PICTURE_MODEL}"
    return f"{hashlib.sha256(raw.encode()).hexdigest()[:32]}.webp"


def picture_kept(unit: dict, *, organisation: str) -> dict | None:
    """The illustration already drawn for this version of the unit, or None. Never draws."""
    kept = get_files().read(organisation, _picture_name(unit))
    if kept is None:
        return None
    return {"image": base64.b64encode(kept).decode("ascii"), "mime": "image/webp"}


def picture(unit: dict, *, organisation: str) -> dict:
    """An illustration of the unit, drawn once per version. Raises pictures.PictureUnavailable."""
    kept = picture_kept(unit, organisation=organisation)
    if kept:
        return {**kept, "cached": True}
    drawn = pictures.illustrate(unit["text"], unit["quote"])
    get_files().write(organisation, _picture_name(unit), drawn.data)
    return {"image": base64.b64encode(drawn.data).decode("ascii"), "mime": drawn.mime_type, "cached": False}
