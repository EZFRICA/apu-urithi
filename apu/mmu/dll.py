"""Semantic MMU: doubly linked list of memory blocks, LRU paging, page-in and BMJ routing.

Invariants:
  - insertion positions by type: temporary at HEAD, project and knowledge right after HEAD,
    fundamental just before TAIL (never at TAIL).
  - fixed blocks (`is_fixed: True`) are never paged out or deleted.
  - dynamic block cap (`config.MAX_DYNAMIC_BLOCKS`): creating or paging in a block at the cap
    pages out the least recently accessed non-fixed block (`last_accessed`, falling back to
    `last_modified`). A paged-out block leaves the DLL while its row remains in L3 (LanceDB).
  - page-in ("Semantic Page Fault Check"): when `search_memory` finds a relevant block in L3
    (`user_memory`) that is not currently in `dll["nodes"]`, it pages the block back into the
    active DLL, evicting the LRU dynamic block if at the cap.
  - BMJ promotion in `search_memory`: only the FIRST relevant result that is a DLL node moves
    to HEAD, on the caller's DLL handle in place.
"""

import asyncio
import fcntl
import json
import os
import uuid
from datetime import datetime
from pathlib import Path

from apu import config, embeddings
from apu.logger import get_logger
from apu.mmu import cache_l1, lance_driver
from apu.mmu.block_proposal import validate as validate_proposal
from apu.mmu.block_types import refuse_excluded_block_type

logger = get_logger(__name__)

_dll_locks: dict[str, asyncio.Lock] = {}

METADATA_LINKS_PATH: str = ""

CERTAINTY_THRESHOLDS = config.CERTAINTY_THRESHOLDS
MIN_RELEVANCE_CERTAINTY = config.MIN_RELEVANCE_CERTAINTY

LEARNER_FIXED_BLOCKS = (
    ("current_session", "Current Session", "temporary",
     ["session", "current", "question", "explain", "today", "now", "help"]),
    ("active_knowledge", "Active Knowledge", "knowledge",
     ["knowledge", "part", "step", "rule", "case", "practice", "exam", "topic"]),
    ("learning_preferences", "Learning Preferences", "fundamental",
     ["learning", "style", "difficulty", "hard", "strength", "weakness", "preference"]),
    ("learner_profile", "Learner Profile", "fundamental",
     ["name", "level", "role", "organisation", "language", "goal", "background"]),
)

GUARDIAN_FIXED_BLOCKS = (
    ("current_class", "Current Class", "temporary",
     ["class", "screen", "camera", "question", "waiting", "today", "now"]),
    ("active_knowledge", "Active Knowledge", "project",
     ["knowledge", "step", "rule", "source", "debrief", "kept", "draft"]),
    ("teaching_preferences", "Teaching Preferences", "fundamental",
     ["threshold", "passed", "pupil", "silence", "style", "preference"]),
    ("guardian_profile", "Guardian Profile", "fundamental",
     ["name", "expert", "role", "organisation", "language", "domain"]),
)


def _l1_key_for(dll: dict | None, block_id: str, l1_prefix: str = "") -> str:
    """Always scope an L1 cache key so two organisations or people never share an entry."""
    if l1_prefix:
        return f"{l1_prefix}{block_id}"
    if isinstance(dll, dict):
        org = (dll.get("organisation") or "").strip()
        pid = (dll.get("person_id") or "").strip()
        if org or pid:
            return f"{org}:{pid}:{block_id}"
    return block_id


def get_dll_lock(agent_id: str) -> asyncio.Lock:
    """Get or create an asyncio.Lock for a specific agent."""
    if agent_id not in _dll_locks:
        _dll_locks[agent_id] = asyncio.Lock()
    return _dll_locks[agent_id]


def _resolve_dll_path(path: str | None = None) -> str:
    resolved = path or METADATA_LINKS_PATH
    if not resolved:
        raise ValueError("No DLL path configured: supply path from the owning side's store.")
    return resolved


def _build_fixed_nodes(spec: tuple[tuple[str, str, str, list[str]], ...]) -> dict[str, dict]:
    now = datetime.now().isoformat()
    nodes: dict[str, dict] = {}
    ids = [item[0] for item in spec]
    for idx, (block_id, label, block_type, keywords) in enumerate(spec):
        nodes[block_id] = {
            "id": block_id,
            "label": label,
            "type": block_type,
            "is_fixed": True,
            "created_by": "system",
            "keywords": list(keywords),
            "active": True,
            "access_count": 0,
            "last_accessed": now,
            "last_modified": now,
            "prev": ids[idx - 1] if idx > 0 else None,
            "next": ids[idx + 1] if idx < len(ids) - 1 else None,
        }
    return nodes


async def init_dll(
    *,
    path: str | None = None,
    fixed_blocks: tuple[tuple[str, str, str, list[str]], ...] = LEARNER_FIXED_BLOCKS,
    organisation: str = "",
    person_id: str = "",
) -> dict:
    """Initialize the Living DLL with 4 fixed core blocks."""
    nodes = _build_fixed_nodes(fixed_blocks)
    ids = list(nodes.keys())
    now = datetime.now().isoformat()
    dll = {
        "agent_id": f"agent-{uuid.uuid4()}",
        "organisation": organisation,
        "person_id": person_id,
        "head_id": ids[0],
        "tail_id": ids[-1],
        "dynamic_block_count": 0,
        "dynamic_block_max": config.MAX_DYNAMIC_BLOCKS,
        "created_at": now,
        "last_modified": now,
        "knowledge_selection": {
            "organisation": organisation or "local",
            "knowledge_id": "general",
        },
        "nodes": nodes,
    }
    save_dll(dll, path=path)
    return dll


async def force_reinit_dll(*, path: str | None = None,
                           fixed_blocks: tuple = LEARNER_FIXED_BLOCKS,
                           organisation: str = "", person_id: str = "") -> dict:
    """Forcefully reset the DLL to its original 4-block state."""
    return await init_dll(path=path, fixed_blocks=fixed_blocks,
                          organisation=organisation, person_id=person_id)


async def switch_knowledge(
    organisation: str,
    knowledge_id: str,
    *,
    title: str = "",
    path: str | None = None,
    fixed_blocks: tuple = LEARNER_FIXED_BLOCKS,
    person_id: str = "",
) -> dict:
    """Update the active knowledge context in the DLL without reinitializing memory."""
    dll = await load_dll(path=path, fixed_blocks=fixed_blocks,
                         organisation=organisation, person_id=person_id)
    dll["knowledge_selection"] = {"organisation": organisation, "knowledge_id": knowledge_id}
    if "active_knowledge" in dll["nodes"]:
        label = f"{organisation.upper()}: {title or knowledge_id}"
        dll["nodes"]["active_knowledge"]["label"] = label
        dll["nodes"]["active_knowledge"]["last_modified"] = datetime.now().isoformat()
    save_dll(dll, path=path)
    return dll


async def load_dll(
    agent_id: str | None = None,
    *,
    path: str | None = None,
    fixed_blocks: tuple = LEARNER_FIXED_BLOCKS,
    organisation: str = "",
    person_id: str = "",
) -> dict:
    """Load the DLL state from disk, initializing a fresh DLL if no file exists."""
    del agent_id
    target = Path(_resolve_dll_path(path))
    if not target.exists():
        return await init_dll(path=str(target), fixed_blocks=fixed_blocks,
                              organisation=organisation, person_id=person_id)

    dll = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(dll.get("knowledge_selection"), dict):
        dll["knowledge_selection"] = {
            "organisation": organisation or "local",
            "knowledge_id": "general",
        }
        save_dll(dll, path=str(target))
    return dll


def save_dll(dll: dict, *, path: str | None = None) -> None:
    """Persist the DLL state to disk with an exclusive lock file and atomic per-PID replace."""
    dll["last_modified"] = datetime.now().isoformat()
    target = _resolve_dll_path(path)
    os.makedirs(os.path.dirname(target) or ".", exist_ok=True)

    tmp_path = f"{target}.{os.getpid()}.{threading.get_ident()}.tmp"
    lock_fd = os.open(target + ".lock", os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        tmp_fd = os.open(tmp_path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
        try:
            payload = json.dumps(dll, ensure_ascii=False, indent=2).encode("utf-8")
            os.write(tmp_fd, payload)
            os.fsync(tmp_fd)
        finally:
            os.close(tmp_fd)
        os.replace(tmp_path, target)
    finally:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        finally:
            os.close(lock_fd)


import threading  # noqa: E402


async def search_memory(
    query_vector: list[float],
    class_level: str = "local",
    subject: str = "local",
    dll: dict | None = None,
    *,
    path: str | None = None,
    db_path: str | None = None,
    stamp_path: str | None = None,
    l1_prefix: str = "",
) -> list[dict]:
    """Bidirectional Metadata Jump (BMJ) with Semantic Page Fault Check (page-in from L3)."""
    results = await lance_driver.get_l3_store().search_block_index(
        query_vector,
        limit=12,
        class_level=class_level,
        subject=subject,
        db_path=db_path,
        stamp_path=stamp_path,
    )

    if not results:
        return []

    if dll is None:
        dll = await load_dll(path=path)

    top_blocks: list[dict] = []
    promoted = False

    for res in results:
        b_id = res["block_id"]
        b_type = res["block_type"]
        certainty = res["certainty"]

        threshold = CERTAINTY_THRESHOLDS.get(b_type, MIN_RELEVANCE_CERTAINTY)
        if certainty >= threshold:
            # SEMANTIC PAGE FAULT CHECK: if a relevant user_memory block in L3 was paged out of
            # the active DLL, page it back into L2 before applying BMJ promotion.
            if b_id not in dll["nodes"] and res.get("source_table") == "user_memory":
                logger.info("Semantic MMU: PAGE FAULT for '%s'. Re-paging into active DLL.", b_id)
                dll = await page_in_block(
                    b_id,
                    b_type,
                    res.get("content", ""),
                    dll,
                    path=path,
                    l1_prefix=l1_prefix,
                )

            top_blocks.append(res)
            if not promoted and b_id in dll["nodes"]:
                dll = move_to_front(b_id, dll)
                record_access(b_id, dll)
                save_dll(dll, path=path)
                promoted = True

    return top_blocks


def move_to_front(block_id: str, dll: dict) -> dict:
    """Move the selected node to HEAD position (O(1) access on next query)."""
    if dll.get("head_id") == block_id or block_id not in dll["nodes"]:
        return dll

    nodes = dll["nodes"]
    target = nodes[block_id]
    prev_id, next_id = target["prev"], target["next"]

    if prev_id:
        nodes[prev_id]["next"] = next_id
    if next_id:
        nodes[next_id]["prev"] = prev_id
    if dll["tail_id"] == block_id:
        dll["tail_id"] = prev_id

    old_head = dll["head_id"]
    nodes[old_head]["prev"] = block_id
    target["prev"] = None
    target["next"] = old_head
    dll["head_id"] = block_id

    return dll


def record_access(block_id: str, dll: dict) -> None:
    """Mark a DLL node as just accessed so LRU eviction has real access timestamps."""
    node = dll.get("nodes", {}).get(block_id)
    if node is None:
        return
    node["access_count"] = node.get("access_count", 0) + 1
    node["last_accessed"] = datetime.now().isoformat()


def _head_to_tail_order(dll: dict) -> list[str]:
    order, current = [], dll.get("head_id")
    visited: set[str] = set()
    while current and current not in visited:
        visited.add(current)
        order.append(current)
        current = dll["nodes"][current]["next"]
    return order


def _tail_to_head_order(dll: dict) -> list[str]:
    order, current = [], dll.get("tail_id")
    visited: set[str] = set()
    while current and current not in visited:
        visited.add(current)
        order.append(current)
        current = dll["nodes"][current]["prev"]
    return order


def get_all_nodes(dll: dict) -> list[dict]:
    """Return all nodes in HEAD -> TAIL order."""
    return [dll["nodes"][nid] for nid in _head_to_tail_order(dll)]


def insert_node_by_type(block_type: str, new_node: dict, dll: dict) -> dict:
    """Insert a node into the DLL according to its block type."""
    refuse_excluded_block_type(block_type)
    nodes = dll["nodes"]
    b_id = new_node["id"]
    nodes[b_id] = new_node

    if block_type == "temporary":
        old_head = dll["head_id"]
        new_node["prev"] = None
        new_node["next"] = old_head
        if old_head:
            nodes[old_head]["prev"] = b_id
        dll["head_id"] = b_id
        if dll["tail_id"] is None:
            dll["tail_id"] = b_id

    elif block_type == "fundamental":
        tail_id = dll["tail_id"]
        if tail_id and nodes[tail_id]["prev"]:
            before_tail_id = nodes[tail_id]["prev"]
            new_node["prev"] = before_tail_id
            new_node["next"] = tail_id
            nodes[before_tail_id]["next"] = b_id
            nodes[tail_id]["prev"] = b_id
        else:
            old_head = dll["head_id"]
            new_node["prev"] = None
            new_node["next"] = old_head
            if old_head:
                nodes[old_head]["prev"] = b_id
            dll["head_id"] = b_id

    else:
        # project / knowledge: right after HEAD
        head_id = dll["head_id"]
        after_head_id = nodes[head_id]["next"] if head_id else None
        new_node["prev"] = head_id
        new_node["next"] = after_head_id
        if head_id:
            nodes[head_id]["next"] = b_id
        if after_head_id:
            nodes[after_head_id]["prev"] = b_id
        else:
            dll["tail_id"] = b_id

    return dll


async def page_out_block(
    block_id: str,
    dll: dict,
    *,
    path: str | None = None,
    l1_prefix: str = "",
) -> dict:
    """Page out a dynamic block from the active DLL while leaving its row in L3."""
    if block_id not in dll["nodes"]:
        return dll
    node = dll["nodes"][block_id]
    if node.get("is_fixed", False):
        return dll

    prev_id, next_id = node["prev"], node["next"]
    if prev_id:
        dll["nodes"][prev_id]["next"] = next_id
    if next_id:
        dll["nodes"][next_id]["prev"] = prev_id
    if dll["head_id"] == block_id:
        dll["head_id"] = next_id
    if dll["tail_id"] == block_id:
        dll["tail_id"] = prev_id

    del dll["nodes"][block_id]
    dll["dynamic_block_count"] = max(0, dll.get("dynamic_block_count", 1) - 1)

    cache_l1.invalidate(_l1_key_for(dll, block_id, l1_prefix))
    save_dll(dll, path=path)
    return dll


async def _evict_lru_if_needed(
    dll: dict,
    *,
    path: str | None = None,
    l1_prefix: str = "",
) -> dict:
    dynamic_count = dll.get("dynamic_block_count", 0)
    dynamic_max = dll.get("dynamic_block_max", config.MAX_DYNAMIC_BLOCKS)
    if dynamic_count >= dynamic_max:
        dynamic_nodes = [
            (nid, n) for nid, n in dll["nodes"].items()
            if not n.get("is_fixed", False)
        ]
        if dynamic_nodes:
            lru_id, _ = min(
                dynamic_nodes,
                key=lambda x: x[1].get("last_accessed") or x[1].get("last_modified") or "1970-01-01T00:00:00",
            )
            dll = await page_out_block(lru_id, dll, path=path, l1_prefix=l1_prefix)
    return dll


async def page_in_block(
    block_id: str,
    block_type: str,
    content: str,
    dll: dict,
    *,
    label: str | None = None,
    keywords: list[str] | None = None,
    path: str | None = None,
    l1_prefix: str = "",
) -> dict:
    """Bring a paged-out block from L3 back into the active L2 DLL (Semantic Page Fault)."""
    refuse_excluded_block_type(block_type)
    if block_id in dll["nodes"]:
        record_access(block_id, dll)
        if content:
            dll["nodes"][block_id]["content"] = content
            cache_l1.set(_l1_key_for(dll, block_id, l1_prefix), content, block_type=block_type)
        save_dll(dll, path=path)
        return dll

    dll = await _evict_lru_if_needed(dll, path=path, l1_prefix=l1_prefix)

    now = datetime.now().isoformat()
    new_node = {
        "id": block_id,
        "label": label or block_id.replace("_", " ").title(),
        "type": block_type,
        "content": content,
        "is_fixed": False,
        "created_by": "mmu_page_in",
        "keywords": list(keywords or []),
        "active": True,
        "access_count": 1,
        "last_accessed": now,
        "last_modified": now,
        "prev": None,
        "next": None,
    }
    dll = insert_node_by_type(block_type, new_node, dll)
    dll["dynamic_block_count"] = dll.get("dynamic_block_count", 0) + 1
    if content:
        cache_l1.set(_l1_key_for(dll, block_id, l1_prefix), content, block_type=block_type)
    save_dll(dll, path=path)
    return dll


async def create_dynamic_block(
    block_id: str,
    label: str,
    block_type: str,
    initial_content: str,
    keywords: list[str],
    created_by: str,
    dll: dict,
    vector: list[float] | None = None,
    *,
    path: str | None = None,
    db_path: str | None = None,
    stamp_path: str | None = None,
    l1_prefix: str = "",
) -> dict:
    """Create a new dynamic block in L3 and link it into the L2 DLL."""
    refuse_excluded_block_type(block_type)
    if block_id in dll["nodes"]:
        raise ValueError(f"Block '{block_id}' already exists in the DLL.")

    if not vector or not any(float(x) != 0.0 for x in vector):
        raise ValueError(f"Cannot index block '{block_id}': no vector supplied (or all zeros).")

    dll = await _evict_lru_if_needed(dll, path=path, l1_prefix=l1_prefix)

    await lance_driver.get_l3_store().upsert_local_block(
        block_id=block_id,
        content=initial_content,
        block_type=block_type,
        class_level="local",
        subject="local",
        vector=vector,
        db_path=db_path,
        stamp_path=stamp_path,
    )

    now = datetime.now().isoformat()
    new_node = {
        "id": block_id,
        "label": label,
        "type": block_type,
        "content": initial_content,
        "is_fixed": False,
        "created_by": created_by,
        "keywords": keywords,
        "active": True,
        "access_count": 0,
        "last_accessed": now,
        "last_modified": now,
        "prev": None,
        "next": None,
    }
    dll = insert_node_by_type(block_type, new_node, dll)
    dll["dynamic_block_count"] = dll.get("dynamic_block_count", 0) + 1
    cache_l1.set(_l1_key_for(dll, block_id, l1_prefix), initial_content, block_type=block_type)
    save_dll(dll, path=path)
    return dll


async def update_node_content(
    block_id: str,
    new_content: str,
    dll: dict,
    *,
    path: str | None = None,
    db_path: str | None = None,
    stamp_path: str | None = None,
    l1_prefix: str = "",
) -> dict:
    """Update a block's content across L1, L2 (DLL) and L3 (LanceDB)."""
    if block_id not in dll["nodes"]:
        raise ValueError(f"Block '{block_id}' not found in the DLL.")

    block_type = dll["nodes"][block_id].get("type", "temporary")
    refuse_excluded_block_type(block_type)
    l1_key = _l1_key_for(dll, block_id, l1_prefix)

    # 1. Invalidate L1
    cache_l1.invalidate(l1_key)

    # 2. Embed and upsert in L3
    vector = await asyncio.to_thread(lambda: embeddings.get_embedder().embed([new_content])[0])
    await lance_driver.get_l3_store().upsert_local_block(
        block_id=block_id,
        content=new_content,
        block_type=block_type,
        class_level="local",
        subject="local",
        vector=vector,
        db_path=db_path,
        stamp_path=stamp_path,
    )

    # 3. Populate L1
    cache_l1.set(l1_key, new_content, block_type=block_type)

    # 4. Update DLL node and persist
    dll["nodes"][block_id]["content"] = new_content
    dll["nodes"][block_id]["last_modified"] = datetime.now().isoformat()
    record_access(block_id, dll)
    save_dll(dll, path=path)
    return dll


async def auto_execute_block_proposal(
    proposal: dict,
    *,
    path: str | None = None,
    db_path: str | None = None,
    stamp_path: str | None = None,
    l1_prefix: str = "",
) -> bool:
    """Validate, embed and execute a dynamic block proposal."""
    problem = validate_proposal(proposal)
    if problem:
        logger.warning("Refusing malformed block proposal (%s): %r", problem, proposal)
        return False

    dll = await load_dll(path=path)
    proposed_id = proposal["proposed_id"]
    content = proposal["initial_content"].strip()

    try:
        vector = await asyncio.to_thread(lambda: embeddings.get_embedder().embed([content])[0])
    except Exception as e:
        logger.error("Cannot embed block proposal '%s': %s", proposed_id, e)
        return False

    try:
        await create_dynamic_block(
            block_id=proposed_id,
            label=proposal["label"],
            block_type=proposal["type"],
            initial_content=content,
            keywords=proposal.get("keywords", []),
            created_by="agent_proposal",
            dll=dll,
            vector=vector,
            path=path,
            db_path=db_path,
            stamp_path=stamp_path,
            l1_prefix=l1_prefix,
        )
        return True
    except Exception as e:
        logger.error("Cannot create block proposal '%s': %s", proposed_id, e)
        return False


async def delete_block_stitching(
    block_id: str,
    dll: dict,
    *,
    path: str | None = None,
    db_path: str | None = None,
    l1_prefix: str = "",
) -> dict:
    """Permanently delete a dynamic block from L3, L2 and L1."""
    if block_id not in dll["nodes"]:
        return dll
    node = dll["nodes"][block_id]
    if node.get("is_fixed", False):
        return dll

    await lance_driver.get_l3_store().delete_local_block(block_id, db_path=db_path)

    prev_id, next_id = node["prev"], node["next"]
    if prev_id:
        dll["nodes"][prev_id]["next"] = next_id
    if next_id:
        dll["nodes"][next_id]["prev"] = prev_id
    if dll["head_id"] == block_id:
        dll["head_id"] = next_id
    if dll["tail_id"] == block_id:
        dll["tail_id"] = prev_id

    del dll["nodes"][block_id]
    dll["dynamic_block_count"] = max(0, dll.get("dynamic_block_count", 1) - 1)
    cache_l1.invalidate(_l1_key_for(dll, block_id, l1_prefix))
    save_dll(dll, path=path)
    return dll
