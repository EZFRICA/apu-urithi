"""What a guardian deposits: documents kept while the knowledge is a draft, and archived once cited.

Behind interfaces (docs/decisions/0004 and 0005):

  sources   the deposits of one map, on local disk, temporary: the file and what was read
            from it (its passages). Never in the graph.
  archive   where a document goes when a validated part cites it: Cloud Storage, under
            organisation/guardian/<guardian>/<map>/; or nowhere, kept local, said in the log.
            A document deposited and never cited is never uploaded, and is purged at validation.

Every name lives under its organisation and map, and never climbs out of them.
"""

import json
import os
import re
import uuid
from typing import Protocol

from apu.logger import get_logger
from guardian import config

logger = get_logger(__name__)
_SAFE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


def _safe(part: str, what: str) -> str:
    if not part or not _SAFE.match(part) or ".." in part:
        raise ValueError(f"No usable {what}.")
    return part


class SourceStore(Protocol):
    def save(self, organisation: str, map_id: str, record: dict, data: bytes) -> dict: ...
    def list(self, organisation: str, map_id: str) -> list[dict]: ...
    def get(self, organisation: str, map_id: str, source_id: str) -> dict | None: ...
    def data(self, organisation: str, map_id: str, source_id: str) -> bytes | None: ...
    def update(self, organisation: str, map_id: str, record: dict) -> None: ...
    def remove(self, organisation: str, map_id: str, source_id: str) -> None: ...


class LocalSources:
    def __init__(self, root: str | None = None):
        self.root = root

    def _folder(self, organisation: str, map_id: str) -> str:
        root = self.root or os.path.join(config.DATA_DIR, "sources")
        folder = os.path.join(root, _safe(organisation, "organisation"), _safe(map_id, "map"))
        os.makedirs(folder, exist_ok=True)
        return folder

    def _index(self, folder: str) -> dict:
        path = os.path.join(folder, "index.json")
        if not os.path.exists(path):
            return {}
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)

    def _write_index(self, folder: str, index: dict) -> None:
        with open(os.path.join(folder, "index.json.part"), "w", encoding="utf-8") as handle:
            json.dump(index, handle, ensure_ascii=False)
        os.replace(os.path.join(folder, "index.json.part"), os.path.join(folder, "index.json"))

    def save(self, organisation: str, map_id: str, record: dict, data: bytes) -> dict:
        folder = self._folder(organisation, map_id)
        record = {**record, "source_id": record.get("source_id") or uuid.uuid4().hex[:12]}
        with open(os.path.join(folder, _safe(record["source_id"], "source") + ".bin"), "wb") as handle:
            handle.write(data)
        index = self._index(folder)
        index[record["source_id"]] = record
        self._write_index(folder, index)
        return record

    def list(self, organisation: str, map_id: str) -> list[dict]:
        return list(self._index(self._folder(organisation, map_id)).values())

    def get(self, organisation: str, map_id: str, source_id: str) -> dict | None:
        return self._index(self._folder(organisation, map_id)).get(source_id)

    def data(self, organisation: str, map_id: str, source_id: str) -> bytes | None:
        path = os.path.join(self._folder(organisation, map_id), _safe(source_id, "source") + ".bin")
        if not os.path.exists(path):
            return None
        with open(path, "rb") as handle:
            return handle.read()

    def update(self, organisation: str, map_id: str, record: dict) -> None:
        folder = self._folder(organisation, map_id)
        index = self._index(folder)
        index[record["source_id"]] = record
        self._write_index(folder, index)

    def remove(self, organisation: str, map_id: str, source_id: str) -> None:
        folder = self._folder(organisation, map_id)
        index = self._index(folder)
        index.pop(source_id, None)
        self._write_index(folder, index)
        path = os.path.join(folder, _safe(source_id, "source") + ".bin")
        if os.path.exists(path):
            os.remove(path)


class Archive(Protocol):
    def put(self, path: str, data: bytes, mime_type: str) -> str | None: ...
    def remove(self, where: str) -> None: ...


class CloudStorageArchive:
    """The bucket the owner set up: google-cloud-storage, with the machine's default credentials."""

    def __init__(self, bucket: str):
        self.bucket = bucket

    def put(self, path: str, data: bytes, mime_type: str) -> str:
        from google.cloud import storage

        blob = storage.Client().bucket(self.bucket).blob(path)
        blob.upload_from_string(data, content_type=mime_type)
        return f"gs://{self.bucket}/{path}"

    def remove(self, where: str) -> None:
        """What put() kept, gone; a copy already gone is not an error."""
        from google.api_core.exceptions import NotFound
        from google.cloud import storage

        prefix = f"gs://{self.bucket}/"
        if not where.startswith(prefix):
            return
        try:
            storage.Client().bucket(self.bucket).blob(where[len(prefix):]).delete()
        except NotFound:
            pass


class LocalOnly:
    """No bucket configured: the document stays where it is, and the log says so once."""

    def put(self, path: str, data: bytes, mime_type: str) -> None:
        logger.warning("No sources bucket is set: %s stays on local disk.", path)
        return None

    def remove(self, where: str) -> None:
        return None


_sources: SourceStore | None = None
_archive: Archive | None = None


def get_sources() -> SourceStore:
    global _sources
    if _sources is None:
        _sources = LocalSources()
    return _sources


def set_sources(store: SourceStore | None) -> None:
    global _sources
    _sources = store


def get_archive() -> Archive:
    global _archive
    if _archive is None:
        _archive = CloudStorageArchive(config.SOURCES_BUCKET) if config.SOURCES_BUCKET else LocalOnly()
    return _archive


def set_archive(archive: Archive | None) -> None:
    global _archive
    _archive = archive
