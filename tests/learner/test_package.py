"""
A knowledge package: one body, as one learner may see it, signed by the library.

Target: learner/packages/package.py, learner/packages/signing.py, the package and key routes

A package can travel as a file, from one device to another, with no network on the way. It
must carry nothing its learner may not see, and a device must refuse it if anything in it
changed after the library signed it: a word, a quiz answer, an access level, an expiry.
"""

import base64
import json
import os

import pytest

from learner.memory.progress import set_progress
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from apu import embeddings as embedder
from learner.packages import package, signing
from library import store
from tests.support import BODY, WordEmbedder, community


@pytest.fixture
def client(monkeypatch, tmp_path):
    from learner.memory.progress import Progress
    from server import app

    embedder.set_embedder(WordEmbedder())
    lib = store.MemoryKnowledgeStore()
    lib.publish(community())
    store.set_store(lib)
    set_progress(Progress(str(tmp_path / "p.sqlite3")))
    yield TestClient(app)
    store.set_store(None)
    embedder.set_embedder(None)


def fetched(client, person="visitor") -> dict:
    return client.get(f"/api/learner/package/{BODY}", params={"person_id": person}).json()


def test_a_package_holds_only_what_its_learner_may_see(client):
    pkg = fetched(client)
    manifest, content = package.open_package(pkg, client.get("/api/learner/key").json()["public_key"])
    assert manifest["for"] == "visitor" and manifest["access"] == ["public"]
    assert not any("rule-report" in u["unit_id"] for u in content["units"])
    assert not any("rule-report" in json.dumps(c) for c in content["cases"])
    assert "rule-report" not in pkg["content_json"], "a hidden unit never leaves the server"
    member = json.loads(fetched(client, "member")["content_json"])
    assert any("rule-report" in u["unit_id"] for u in member["units"])


def test_the_library_signs_it_and_says_which_key(client):
    pkg = fetched(client)
    key = client.get("/api/learner/key").json()
    assert key["algorithm"] == "Ed25519" and pkg["key_id"] == key["key_id"] == json.loads(pkg["manifest_json"])["key_id"]
    assert package.verify(pkg, key["public_key"])


@pytest.mark.parametrize("change", [
    ("content_json", "Ten is enough. We hold it.", "Ten is not enough."),      # the guardian's words
    ("content_json", '"applies": false', '"applies": true'),                    # a quiz answer
    ("manifest_json", '"access": ["public"]', '"access": ["public", "community"]'),  # the level
    ("manifest_json", '"valid_until": "2', '"valid_until": "3'),                # the expiry
])
def test_a_package_changed_after_signing_is_refused(client, change):
    pkg = fetched(client)
    public = client.get("/api/learner/key").json()["public_key"]
    field, before, after = change
    assert before in pkg[field], f"the test's own premise: {before!r} is in the {field}"
    changed = {**pkg, field: pkg[field].replace(before, after, 1)}
    with pytest.raises(package.PackageError, match="changed after the library signed it"):
        package.open_package(changed, public)


def test_a_package_signed_by_another_key_is_refused(client):
    pkg = fetched(client)
    stranger = Ed25519PrivateKey.generate()
    forged = {**pkg, "signature": base64.b64encode(
        stranger.sign(package.signed_bytes(pkg["manifest_json"], pkg["content_json"]))).decode()}
    assert not package.verify(forged)
    with pytest.raises(package.PackageError):
        package.open_package({"nothing": "here"}, signing.public_key()["public_key"])


def test_the_key_is_kept_across_restarts(tmp_path, monkeypatch):
    """A new key at every start would leave every package given out unverifiable."""
    from learner import config

    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.delenv(config.SIGNING_KEY_ENV, raising=False)
    signing.set_key(None)
    first = signing.public_key()
    signing.set_key(None)
    assert signing.public_key() == first
    assert oct(os.stat(tmp_path / "keys" / "library-signing.pem").st_mode & 0o777) == "0o600"


def test_a_key_from_the_environment_is_used(monkeypatch):
    from cryptography.hazmat.primitives import serialization

    from learner import config

    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption()).decode()
    monkeypatch.setenv(config.SIGNING_KEY_ENV, pem)
    signing.set_key(None)
    data = b"the guardian's words"
    assert signing.verify(data, signing.sign(data), signing.public_key()["public_key"])
    assert key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw) == \
        base64.b64decode(signing.public_key()["public_key"])
