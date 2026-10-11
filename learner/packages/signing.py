"""The library's signature on a knowledge package (Ed25519).

A package can leave the server as a file: copied to a USB key, sent to a phone, handed on in
a place with no network. Whoever receives it must be able to tell, offline, that it is what
the library gave out: that no word of the guardian's was changed, no answer to a quiz turned
round, no access level lowered, no expiry pushed back. A hash cannot say that, since anyone
who edits the file can recompute it. A signature can: only the library holds the private
key, and a device that has met the library once keeps its public key.

The key comes from LEARNER_SIGNING_KEY (a PEM, from a secret manager in production), or
from a file under the data directory, made on first use. A server that makes a new key at
every start would leave every package it gave out unverifiable, hence the variable.
"""

import base64
import hashlib
import os

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from learner import config

ALGORITHM = "Ed25519"
_key: Ed25519PrivateKey | None = None


def _path() -> str:
    return os.path.join(config.DATA_DIR, "keys", "library-signing.pem")


def _load() -> Ed25519PrivateKey:
    pem = os.environ.get(config.SIGNING_KEY_ENV)
    if pem:
        return serialization.load_pem_private_key(pem.encode(), password=None)
    path = _path()
    if os.path.exists(path):
        with open(path, "rb") as handle:
            return serialization.load_pem_private_key(handle.read(), password=None)
    key = Ed25519PrivateKey.generate()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                       serialization.NoEncryption()))
    return key


def private_key() -> Ed25519PrivateKey:
    global _key
    if _key is None:
        _key = _load()
    return _key


def set_key(key: Ed25519PrivateKey | None) -> None:
    """For tests, and for a deployment that hands the key over itself."""
    global _key
    _key = key


def _raw(public: Ed25519PublicKey) -> bytes:
    return public.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def public_key() -> dict:
    raw = _raw(private_key().public_key())
    return {"algorithm": ALGORITHM, "key_id": hashlib.sha256(raw).hexdigest()[:16],
            "public_key": base64.b64encode(raw).decode("ascii")}


def sign(data: bytes) -> str:
    return base64.b64encode(private_key().sign(data)).decode("ascii")


def verify(data: bytes, signature: str, public_key_b64: str) -> bool:
    try:
        Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key_b64)).verify(
            base64.b64decode(signature), data)
        return True
    except (InvalidSignature, ValueError):
        return False
