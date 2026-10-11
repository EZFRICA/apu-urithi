"""The learner's side's files: renderings (audio, illustrations), kept per organisation.

Behind an interface (.claude/skills/store-interfaces): the local disk here, object storage in
production, the same contract for both (tests/shared/test_stores.py). Every name lives under
its organisation's prefix, and a name never climbs out of it.
"""

import os
from typing import Protocol

from learner import config


class FileStore(Protocol):
    def read(self, organisation: str, name: str) -> bytes | None: ...
    def write(self, organisation: str, name: str, data: bytes) -> None: ...


def _safe(part: str, what: str) -> str:
    if not part or "/" in part or "\\" in part or part.startswith("."):
        raise ValueError(f"No usable {what}: a file is kept under its organisation, by a plain name.")
    return part


class LocalFiles:
    def __init__(self, root: str | None = None):
        self.root = root

    def _path(self, organisation: str, name: str) -> str:
        root = self.root or os.path.join(config.DATA_DIR, "renderings")
        folder = os.path.join(root, _safe(organisation, "organisation"))
        os.makedirs(folder, exist_ok=True)
        return os.path.join(folder, _safe(name, "name"))

    def read(self, organisation: str, name: str) -> bytes | None:
        path = self._path(organisation, name)
        if not os.path.exists(path):
            return None
        with open(path, "rb") as handle:
            return handle.read()

    def write(self, organisation: str, name: str, data: bytes) -> None:
        path = self._path(organisation, name)
        with open(path + ".part", "wb") as handle:
            handle.write(data)
        os.replace(path + ".part", path)   # whole or not at all: a reader never meets half a file


_files: FileStore | None = None


def get_files() -> FileStore:
    global _files
    if _files is None:
        _files = LocalFiles()
    return _files


def set_files(store: FileStore | None) -> None:
    global _files
    _files = store
