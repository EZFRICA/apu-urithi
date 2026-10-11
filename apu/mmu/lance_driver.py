"""L3 storage: local LanceDB vector store behind the MMU interface.

Checks both vector dimension (from the Arrow schema) and embedder model name (from a per-table
stamp sidecar) before searching a table, normalizes vectors on both write and query so
`1 - _distance / 2` equals cosine similarity, escapes SQL literals in filter predicates, and
deletes superseded rows on upsert so table size stays proportional to distinct blocks.
"""

import json
import os
import threading
from datetime import datetime
from pathlib import Path

import lancedb

from apu import config, embeddings
from apu.mmu.block_types import EXCLUDED_BLOCK_TYPES, refuse_excluded_block_type

_dbs: dict[str, object] = {}
_db_lock = threading.Lock()

# Default paths used only when a test or standalone caller does not pass an explicit store path.
# Overridden per test by fixtures, and per side by guardian/memory and learner/memory.
LANCE_DB_PATH: str = ""
EMBEDDING_STAMP_PATH: str = ""

normalize_vector = embeddings.normalize


class EmbeddingMismatch(RuntimeError):
    """The stored vectors were not produced by the configured embedder."""


def _resolve_db_path(db_path: str | None = None) -> str:
    resolved = db_path or LANCE_DB_PATH
    if not resolved:
        raise ValueError("No LanceDB path configured: supply db_path from the owning side's store.")
    return resolved


def _resolve_stamp_path(stamp_path: str | None = None, db_path: str | None = None) -> str:
    if stamp_path:
        return stamp_path
    if EMBEDDING_STAMP_PATH and not db_path:
        return EMBEDDING_STAMP_PATH
    base = _resolve_db_path(db_path)
    return os.path.join(os.path.dirname(base.rstrip("/\\")), "embedding_stamp.json")


def get_db(db_path: str | None = None):
    """Initialize or retrieve the connection to LanceDB for the given path (thread-safe)."""
    target = _resolve_db_path(db_path)
    with _db_lock:
        if target not in _dbs or _dbs[target] is None:
            os.makedirs(target, exist_ok=True)
            _dbs[target] = lancedb.connect(target)
        return _dbs[target]


def reset_db(db_path: str | None = None) -> None:
    """Clear cached LanceDB connection(s)."""
    with _db_lock:
        if db_path is None:
            _dbs.clear()
        else:
            _dbs.pop(db_path, None)


def list_table_names(db=None, *, db_path: str | None = None) -> list[str]:
    """Return the table names in the DB as a plain list of strings."""
    db = get_db(db_path) if db is None else db
    raw = db.list_tables()

    if isinstance(raw, (list, tuple)):
        names = list(raw)
    else:
        tables = getattr(raw, "tables", None)
        if tables is None:
            raise TypeError(
                f"lancedb list_tables() returned {type(raw).__name__} with no "
                "'.tables' attribute. apu.mmu.lance_driver.list_table_names needs updating."
            )
        names = list(tables)

    bad = [n for n in names if not isinstance(n, str)]
    if bad:
        raise TypeError(
            f"lancedb list_tables() yielded non-string table names: {bad!r}. "
            "apu.mmu.lance_driver.list_table_names needs updating."
        )
    return names


def _sql_literal(value: str) -> str:
    """Quote a value for use in a LanceDB filter predicate by doubling single quotes."""
    return "'" + str(value).replace("'", "''") + "'"


def _read_stamp_doc(stamp_path: str | None = None, db_path: str | None = None) -> dict:
    """Read the per-table embedding stamp sidecar. Empty dict if absent or corrupt."""
    path = Path(_resolve_stamp_path(stamp_path, db_path))
    if not path.exists():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(doc, dict):
        return {}
    if "model" in doc:
        return {name: doc for name in ("knowledge_registry", "edu_registry", "user_memory")}
    return doc


def read_stamp(table_name: str, *, stamp_path: str | None = None, db_path: str | None = None) -> dict | None:
    """Which embedder wrote this table, or None if never recorded."""
    return _read_stamp_doc(stamp_path, db_path).get(table_name)


def write_stamp(table_name: str, *, stamp_path: str | None = None, db_path: str | None = None) -> None:
    """Record the configured embedder as the owner of one table."""
    path = Path(_resolve_stamp_path(stamp_path, db_path))
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = _read_stamp_doc(stamp_path, db_path)
    doc[table_name] = {
        "model": config.EMBEDDING_MODEL,
        "dim": config.EMBEDDING_DIM,
        "updated_at": datetime.now().isoformat(),
    }
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")


def _table_vector_dim(table) -> int | None:
    """Vector width from the Arrow schema, without reading any rows."""
    try:
        field = table.schema.field("vector")
    except KeyError:
        return None
    return getattr(field.type, "list_size", None) or None


def verify_embedding_space(
    table,
    table_name: str,
    *,
    stamp_path: str | None = None,
    db_path: str | None = None,
) -> None:
    """Refuse to search a table whose vectors are not in the configured embedding space."""
    expected_model = config.EMBEDDING_MODEL
    expected_dim = config.EMBEDDING_DIM

    table_dim = _table_vector_dim(table)
    if table_dim is not None and table_dim != expected_dim:
        raise EmbeddingMismatch(
            f"Table '{table_name}' holds {table_dim}-dim vectors, but the configured "
            f"embedder ({expected_model}) produces {expected_dim}-dim vectors."
        )

    stamp = read_stamp(table_name, stamp_path=stamp_path, db_path=db_path)
    if stamp is None:
        return

    stamped_model = stamp.get("model")
    stamped_dim = stamp.get("dim")
    if stamped_model != expected_model or stamped_dim != expected_dim:
        raise EmbeddingMismatch(
            f"Table '{table_name}' was embedded with '{stamped_model}' (dim={stamped_dim}), "
            f"but the configured embedder is '{expected_model}' (dim={expected_dim})."
        )


async def search_block_index(
    query_vector: list[float],
    limit: int = 12,
    class_level: str | None = None,
    subject: str | None = None,
    *,
    db_path: str | None = None,
    stamp_path: str | None = None,
) -> list[dict]:
    """Perform a local vector search in LanceDB across registry and user_memory tables."""
    db = get_db(db_path)
    results: list[dict] = []
    existing_tables = list_table_names(db)
    query_vector = normalize_vector(query_vector)

    for reg_table in ("knowledge_registry", "edu_registry"):
        if reg_table in existing_tables:
            table = db.open_table(reg_table)
            verify_embedding_space(table, reg_table, stamp_path=stamp_path, db_path=db_path)
            query = table.search(query_vector, vector_column_name="vector")
            filters = []
            if class_level:
                filters.append(f"class_level = {_sql_literal(class_level.lower())}")
            if subject:
                filters.append(f"subject = {_sql_literal(subject.lower())}")
            if filters:
                query = query.where(" AND ".join(filters))
            df = query.limit(limit).to_pandas()
            for _, row in df.iterrows():
                if row["block_type"] in EXCLUDED_BLOCK_TYPES:
                    continue
                results.append({
                    "block_id": row["id"],
                    "chapter_id": row["id"],
                    "block_type": row["block_type"],
                    "certainty": 1 - (row["_distance"] / 2),
                    "content": row["content"],
                    "source_table": reg_table,
                })

    if "user_memory" in existing_tables:
        table = db.open_table("user_memory")
        verify_embedding_space(table, "user_memory", stamp_path=stamp_path, db_path=db_path)
        df = table.search(query_vector, vector_column_name="vector").limit(limit).to_pandas()
        for _, row in df.iterrows():
            if row["block_type"] in EXCLUDED_BLOCK_TYPES:
                continue
            results.append({
                "block_id": row["id"],
                "chapter_id": row["id"],
                "block_type": row["block_type"],
                "certainty": 1 - (row["_distance"] / 2),
                "content": row["content"],
                "source_table": "user_memory",
            })

    results.sort(key=lambda x: x["certainty"], reverse=True)
    return results[:limit]


async def get_block_content(block_id: str, *, db_path: str | None = None) -> str | None:
    """Retrieve the text content of a specific block from LanceDB."""
    db = get_db(db_path)
    existing_tables = list_table_names(db)
    predicate = f"id = {_sql_literal(block_id)}"

    for table_name in ("user_memory", "knowledge_registry", "edu_registry"):
        if table_name in existing_tables:
            table = db.open_table(table_name)
            res = table.search().where(predicate).limit(1).to_pandas()
            if not res.empty:
                return res.iloc[0]["content"]

    return None


async def upsert_local_block(
    block_id: str,
    content: str,
    block_type: str,
    class_level: str,
    subject: str,
    vector: list[float],
    *,
    db_path: str | None = None,
    stamp_path: str | None = None,
) -> None:
    """Save or update a memory block in the local user_memory table."""
    refuse_excluded_block_type(block_type)
    db = get_db(db_path)
    table_name = "user_memory"

    data = [{
        "id": block_id,
        "content": content,
        "block_type": block_type,
        "class_level": class_level.lower(),
        "subject": subject.lower(),
        "vector": normalize_vector(vector),
        "updated_at": datetime.now().isoformat(),
    }]

    if table_name not in list_table_names(db):
        db.create_table(table_name, data=data)
    else:
        table = db.open_table(table_name)
        table.delete(f"id = {_sql_literal(block_id)}")
        table.add(data)

    write_stamp(table_name, stamp_path=stamp_path, db_path=db_path)


async def delete_local_block(block_id: str, *, db_path: str | None = None) -> None:
    """Delete a block from the local user_memory table if present."""
    db = get_db(db_path)
    if "user_memory" in list_table_names(db):
        table = db.open_table("user_memory")
        table.delete(f"id = {_sql_literal(block_id)}")


from typing import Protocol  # noqa: E402


class VectorStore(Protocol):
    """The L3 vector store interface (docs/decisions/0015)."""

    async def search_block_index(
        self,
        query_vector: list[float],
        limit: int = 12,
        class_level: str | None = None,
        subject: str | None = None,
        *,
        db_path: str | None = None,
        stamp_path: str | None = None,
    ) -> list[dict]: ...

    async def get_block_content(self, block_id: str, *, db_path: str | None = None) -> str | None: ...

    async def upsert_local_block(
        self,
        block_id: str,
        content: str,
        block_type: str,
        class_level: str,
        subject: str,
        vector: list[float],
        *,
        db_path: str | None = None,
        stamp_path: str | None = None,
    ) -> None: ...

    async def delete_local_block(self, block_id: str, *, db_path: str | None = None) -> None: ...


class LanceVectorStore:
    """Local LanceDB implementation of the L3 VectorStore interface."""

    async def search_block_index(
        self,
        query_vector: list[float],
        limit: int = 12,
        class_level: str | None = None,
        subject: str | None = None,
        *,
        db_path: str | None = None,
        stamp_path: str | None = None,
    ) -> list[dict]:
        return await search_block_index(
            query_vector,
            limit=limit,
            class_level=class_level,
            subject=subject,
            db_path=db_path,
            stamp_path=stamp_path,
        )

    async def get_block_content(self, block_id: str, *, db_path: str | None = None) -> str | None:
        return await get_block_content(block_id, db_path=db_path)

    async def upsert_local_block(
        self,
        block_id: str,
        content: str,
        block_type: str,
        class_level: str,
        subject: str,
        vector: list[float],
        *,
        db_path: str | None = None,
        stamp_path: str | None = None,
    ) -> None:
        await upsert_local_block(
            block_id=block_id,
            content=content,
            block_type=block_type,
            class_level=class_level,
            subject=subject,
            vector=vector,
            db_path=db_path,
            stamp_path=stamp_path,
        )

    async def delete_local_block(self, block_id: str, *, db_path: str | None = None) -> None:
        await delete_local_block(block_id, db_path=db_path)


_l3_store: VectorStore | None = None


def get_l3_store() -> VectorStore:
    global _l3_store
    if _l3_store is None:
        _l3_store = LanceVectorStore()
    return _l3_store


def set_l3_store(store: VectorStore | None) -> None:
    global _l3_store
    _l3_store = store
