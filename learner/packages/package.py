"""A knowledge package: one body, as one learner may see it, to learn from offline.

A projection of [B], read only, built for one person's access levels: a unit they may not see
is never put in it, so it never leaves the server for their device. It carries:

  - the units in learning order, their links, sources and quiz cases WITH their answers,
    because grading offline happens on the device (a learner who reads the file can see them:
    a package is for learning, not for an exam that counts);
  - renderings made when it is built: braille always, audio when asked, so a device that
    cannot synthesise speech still listens, and the illustrations already drawn (a package
    never draws one: it carries what a learner has seen, at a few kilobytes each);
  - a manifest: a hash of the content, the embedding model's identity, and a date after
    which the device should fetch it again, which is also when a withdrawal reaches it;
  - the library's signature over the manifest and the content, exactly as sent (format 2):
    a package handed from one device to another, as a file, is checked offline against the
    library's public key, so a changed word, answer, level or date is refused.
"""

import hashlib
import json
from datetime import UTC, datetime, timedelta

from apu import config
from apu.language import a_learner_can_answer, for_learner
from apu.logger import get_logger
from learner import renderings
from learner.packages import signing
from learner.tutor.path import ordered

logger = get_logger(__name__)

FORMAT = 2
VALID_DAYS = 30


def build(found: dict, *, person_id: str, organisation: str, allowed, language: str = "en",
          with_audio: bool = False) -> dict:
    units, cycle = ordered(found["units"], found["links"])
    guardian = found["body"]["guardian"]
    content = {
        "body": found["body"],
        "units": [{**u, "braille": _braille(u, guardian, language), "picture": renderings.picture_kept(u, organisation=organisation)}
                  for u in units],
        "links": found["links"],
        "sources": found["sources"],
        "evidence": found.get("evidence", []),     # the cited excerpts, never the documents
        "cases": [{**c, "question": for_learner(c["question"], c["by"])}
                  for c in found["cases"] if a_learner_can_answer(c)],
        "cycle_broken": cycle,
    }
    if with_audio:
        for unit in content["units"]:
            try:
                spoken = renderings.audio(unit, guardian, language, organisation=organisation)
                unit["audio"], unit["audio_mime"] = spoken["audio"], spoken["mime"]
                unit["audio_words"] = spoken.get("words", [])
            except Exception as error:
                logger.info("No audio for %s in the package: %s", unit["unit_id"], error)
                unit["audio"] = None
    content_json = json.dumps(content, sort_keys=True, ensure_ascii=False)
    now = datetime.now(UTC)
    key = signing.public_key()
    manifest = {
        "format": FORMAT, "body_id": found["body"]["body_id"], "version": found["body"]["version"],
        "for": person_id, "organisation": organisation, "access": list(allowed), "language": language,
        "built_at": now.isoformat(), "valid_until": (now + timedelta(days=VALID_DAYS)).isoformat(),
        "sha256": hashlib.sha256(content_json.encode()).hexdigest(),
        "embedding": {"model": config.EMBEDDING_MODEL, "dim": config.EMBEDDING_DIM},
        "key_id": key["key_id"],
    }
    manifest_json = json.dumps(manifest, sort_keys=True, ensure_ascii=False)
    # Signed as the exact strings sent, so a device checks the bytes it holds, with no
    # re-serialising (a float or a key order written differently would break the signature).
    return {"format": FORMAT, "manifest_json": manifest_json, "content_json": content_json,
            "key_id": key["key_id"], "signature": signing.sign(signed_bytes(manifest_json, content_json))}


class PackageError(ValueError):
    """A package that is not what the library gave out."""


def signed_bytes(manifest_json: str, content_json: str) -> bytes:
    return f"{manifest_json}\n{content_json}".encode("utf-8")


def open_package(package: dict, public_key: str) -> tuple[dict, dict]:
    """The device's check, as code: signature, then the content's hash. Returns (manifest, content)."""
    try:
        manifest_json, content_json = package["manifest_json"], package["content_json"]
        signature = package["signature"]
    except (KeyError, TypeError) as error:
        raise PackageError("This is not a knowledge package.") from error
    if not signing.verify(signed_bytes(manifest_json, content_json), signature, public_key):
        raise PackageError("This package was changed after the library signed it.")
    manifest = json.loads(manifest_json)
    if hashlib.sha256(content_json.encode()).hexdigest() != manifest["sha256"]:
        raise PackageError("This package's content is not the content its manifest names.")
    return manifest, json.loads(content_json)


def verify(package: dict, public_key: str | None = None) -> bool:
    try:
        open_package(package, public_key or signing.public_key()["public_key"])
        return True
    except PackageError:
        return False


def _braille(unit: dict, guardian: str, language: str):
    try:
        return renderings.braille(unit, guardian, 2, language)["pages_unicode"]
    except Exception as error:
        logger.info("No braille for %s: %s", unit["unit_id"], error)
        return None
