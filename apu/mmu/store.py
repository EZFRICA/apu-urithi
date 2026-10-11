"""Per-organisation, per-person MMU store and metered memory write-back.

Used by both guardian/memory/ and learner/memory/ so each side owns its storage directory
under guardian/data/mmu or learner/data/mmu, behind a getter and a setter, and neither side
ever reads the other's memory (docs/decisions/0015).
"""

import asyncio
import contextlib
import threading
import time
from pathlib import Path
from typing import Protocol

from apu import embeddings, meter
from apu.inference import llm
from apu.inference.llm import call_extraction_model
from apu.logger import get_logger
from apu.mmu import cache_l1, dll as mmu_dll, lance_driver
from apu.mmu.block_detector import detect_new_block_opportunity
from apu.mmu.block_types import refuse_excluded_block_type
from apu.mmu.extraction import parse_extraction

logger = get_logger(__name__)


def _require_scope(organisation: str, person_id: str) -> tuple[str, str]:
    org = (organisation or "").strip().lower()
    pid = (person_id or "").strip().lower()
    if not org or not pid:
        raise ValueError("An MMU memory always belongs to one person in one organisation.")
    for part in (org, pid):
        if "/" in part or "\\" in part or ".." in part:
            raise ValueError(f"Invalid scope identifier: {part!r}")
    return org, pid


class MmuLocks(Protocol):
    """Per-(organisation, person_id) lock interface for MMU read-modify-write."""

    def lock(self, organisation: str, person_id: str) -> contextlib.AbstractContextManager[None]: ...


class MemoryMmuLocks:
    """In-memory per-(organisation, person_id) re-entrant locks for a single server."""

    def __init__(self) -> None:
        self._guard = threading.Lock()
        self._locks: dict[tuple[str, str], threading.RLock] = {}

    @contextlib.contextmanager
    def lock(self, organisation: str, person_id: str):
        org, pid = _require_scope(organisation, person_id)
        with self._guard:
            rlock = self._locks.get((org, pid))
            if rlock is None:
                rlock = threading.RLock()
                self._locks[(org, pid)] = rlock
        with rlock:
            yield


_mmu_locks: MmuLocks | None = None


def get_mmu_locks() -> MmuLocks:
    global _mmu_locks
    if _mmu_locks is None:
        _mmu_locks = MemoryMmuLocks()
    return _mmu_locks


def set_mmu_locks(locks: MmuLocks | None) -> None:
    global _mmu_locks
    _mmu_locks = locks


def _run_sync(coro):
    """Run an MMU coroutine from synchronous code, whether an event loop is running or not."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is None:
        return asyncio.run(coro)
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def _extractor_ready() -> bool:
    """True when the extraction model role is configured and the meter budget is ok."""
    try:
        if meter.meter().level() != "ok":
            return False
    except RuntimeError:
        pass
    return llm.is_configured("extraction")


class MmuStore(Protocol):
    def load_dll(self, organisation: str, person_id: str) -> dict: ...
    def save_dll(self, organisation: str, person_id: str, dll: dict) -> None: ...
    def update_block(self, organisation: str, person_id: str, block_id: str, content: str,
                     dll: dict | None = None) -> dict: ...
    def read_block(self, organisation: str, person_id: str, block_id: str,
                   dll: dict | None = None) -> tuple[str | None, str, float]: ...
    def read_context(self, organisation: str, person_id: str,
                     dll: dict | None = None) -> dict: ...
    def search(self, organisation: str, person_id: str, query: str | list[float],
               dll: dict | None = None) -> list[dict]: ...
    def write_back(self, organisation: str, person_id: str, user_text: str, reply_text: str,
                   dll: dict | None = None, *, history: list[dict] | None = None) -> dict: ...


class PersonMmuStore:
    """MMU store for one side (guardian or learner), isolated by (organisation, person_id)."""

    def __init__(
        self,
        base_dir: str,
        *,
        side: str,
        fixed_blocks: tuple[tuple[str, str, str, list[str]], ...],
    ):
        self.base_dir = base_dir
        self.side = side
        self.fixed_blocks = fixed_blocks

    def lock(self, organisation: str, person_id: str):
        return get_mmu_locks().lock(organisation, person_id)

    def _person_dir(self, organisation: str, person_id: str) -> Path:
        org, pid = _require_scope(organisation, person_id)
        return Path(self.base_dir) / org / pid

    def dll_path(self, organisation: str, person_id: str) -> str:
        return str(self._person_dir(organisation, person_id) / "metadata_links.json")

    def db_path(self, organisation: str, person_id: str) -> str:
        return str(self._person_dir(organisation, person_id) / "lancedb")

    def stamp_path(self, organisation: str, person_id: str) -> str:
        return str(self._person_dir(organisation, person_id) / "embedding_stamp.json")

    def l1_prefix(self, organisation: str, person_id: str) -> str:
        org, pid = _require_scope(organisation, person_id)
        return f"{self.side}:{org}:{pid}:"

    def load_dll(self, organisation: str, person_id: str) -> dict:
        org, pid = _require_scope(organisation, person_id)
        with self.lock(org, pid):
            return _run_sync(
                mmu_dll.load_dll(
                    path=self.dll_path(org, pid),
                    fixed_blocks=self.fixed_blocks,
                    organisation=org,
                    person_id=pid,
                )
            )

    def save_dll(self, organisation: str, person_id: str, dll: dict) -> None:
        org, pid = _require_scope(organisation, person_id)
        with self.lock(org, pid):
            mmu_dll.save_dll(dll, path=self.dll_path(org, pid))

    def switch_knowledge(self, organisation: str, person_id: str, knowledge_id: str,
                         title: str = "") -> dict:
        org, pid = _require_scope(organisation, person_id)
        with self.lock(org, pid):
            return _run_sync(
                mmu_dll.switch_knowledge(
                    org,
                    knowledge_id,
                    title=title,
                    path=self.dll_path(org, pid),
                    fixed_blocks=self.fixed_blocks,
                    person_id=pid,
                )
            )

    def update_block(
        self,
        organisation: str,
        person_id: str,
        block_id: str,
        content: str,
    ) -> dict:
        org, pid = _require_scope(organisation, person_id)
        with self.lock(org, pid):
            dll = self.load_dll(org, pid)
            return _run_sync(
                mmu_dll.update_node_content(
                    block_id,
                    content,
                    dll,
                    path=self.dll_path(org, pid),
                    db_path=self.db_path(org, pid),
                    stamp_path=self.stamp_path(org, pid),
                    l1_prefix=self.l1_prefix(org, pid),
                )
            )

    def create_dynamic_block(
        self,
        organisation: str,
        person_id: str,
        block_id: str,
        label: str,
        block_type: str,
        initial_content: str,
        keywords: list[str] | None = None,
        vector: list[float] | None = None,
    ) -> dict:
        org, pid = _require_scope(organisation, person_id)
        refuse_excluded_block_type(block_type)
        if vector is None:
            vector = embeddings.get_embedder().embed([initial_content])[0]
        with self.lock(org, pid):
            dll = self.load_dll(org, pid)
            return _run_sync(
                mmu_dll.create_dynamic_block(
                    block_id=block_id,
                    label=label,
                    block_type=block_type,
                    initial_content=initial_content,
                    keywords=list(keywords or []),
                    created_by=self.side,
                    dll=dll,
                    vector=vector,
                    path=self.dll_path(org, pid),
                    db_path=self.db_path(org, pid),
                    stamp_path=self.stamp_path(org, pid),
                    l1_prefix=self.l1_prefix(org, pid),
                )
            )

    def page_out_block(self, organisation: str, person_id: str, block_id: str) -> dict:
        org, pid = _require_scope(organisation, person_id)
        with self.lock(org, pid):
            dll = self.load_dll(org, pid)
            return _run_sync(
                mmu_dll.page_out_block(
                    block_id,
                    dll,
                    path=self.dll_path(org, pid),
                    l1_prefix=self.l1_prefix(org, pid),
                )
            )

    def read_block(
        self,
        organisation: str,
        person_id: str,
        block_id: str,
    ) -> tuple[str | None, str, float]:
        """Read a block through L1 -> L2 -> L3, returning (content, tier, elapsed_ms)."""
        org, pid = _require_scope(organisation, person_id)
        prefix = self.l1_prefix(org, pid)
        l1_key = f"{prefix}{block_id}"

        t0 = time.perf_counter()
        cached = cache_l1.get(l1_key)
        if cached is not None:
            elapsed = (time.perf_counter() - t0) * 1000.0
            return cached, "L1", elapsed

        with self.lock(org, pid):
            t1 = time.perf_counter()
            own_dll = self.load_dll(org, pid)
            node = own_dll.get("nodes", {}).get(block_id)
            if node and node.get("content"):
                content = node["content"]
                elapsed = (time.perf_counter() - t1) * 1000.0
                cache_l1.set(l1_key, content, block_type=node.get("type"))
                mmu_dll.record_access(block_id, own_dll)
                self.save_dll(org, pid, own_dll)
                return content, "L2", elapsed

            t2 = time.perf_counter()
            l3_content = _run_sync(
                lance_driver.get_l3_store().get_block_content(block_id, db_path=self.db_path(org, pid))
            )
            elapsed = (time.perf_counter() - t2) * 1000.0
            if l3_content:
                own_dll = self.load_dll(org, pid)
                node = own_dll.get("nodes", {}).get(block_id)
                b_type = (node or {}).get("type", "temporary")
                if block_id not in own_dll.get("nodes", {}):
                    own_dll = _run_sync(
                        mmu_dll.page_in_block(
                            block_id,
                            b_type,
                            l3_content,
                            own_dll,
                            path=self.dll_path(org, pid),
                            l1_prefix=prefix,
                        )
                    )
                else:
                    own_dll["nodes"][block_id]["content"] = l3_content
                    cache_l1.set(l1_key, l3_content, block_type=b_type)
                    mmu_dll.record_access(block_id, own_dll)
                    self.save_dll(org, pid, own_dll)
                return l3_content, "L3", elapsed

            return None, "MISS", elapsed

    def read_context(
        self,
        organisation: str,
        person_id: str,
    ) -> dict:
        """Compile active memory context across L1/L2/L3 in HEAD -> TAIL order."""
        org, pid = _require_scope(organisation, person_id)
        with self.lock(org, pid):
            own_dll = self.load_dll(org, pid)
            lines: list[str] = []
            blocks: dict[str, str] = {}
            tiers: dict[str, str] = {}
            timings_ms: dict[str, float] = {}

            for node_id in mmu_dll._head_to_tail_order(own_dll):
                node = own_dll["nodes"][node_id]
                content, tier, ms = self.read_block(org, pid, node_id)
                timings_ms[node_id] = round(ms, 3)
                tiers[node_id] = tier
                if content:
                    blocks[node_id] = content
                    lines.append(f"- {node.get('label', node_id)}: {content}")

            own_dll = self.load_dll(org, pid)
            return {
                "text": "\n".join(lines),
                "blocks": blocks,
                "tiers": tiers,
                "timings_ms": timings_ms,
                "head_id": own_dll.get("head_id"),
                "order": mmu_dll._head_to_tail_order(own_dll),
            }

    def search(
        self,
        organisation: str,
        person_id: str,
        query: str | list[float],
    ) -> list[dict]:
        """Search L3 with BMJ promotion and automatic page-in of paged-out blocks into L2."""
        org, pid = _require_scope(organisation, person_id)
        if isinstance(query, str):
            vector = embeddings.get_embedder().embed([query])[0]
        else:
            vector = list(query)
        with self.lock(org, pid):
            own_dll = self.load_dll(org, pid)
            return _run_sync(
                mmu_dll.search_memory(
                    vector,
                    class_level="local",
                    subject="local",
                    dll=own_dll,
                    path=self.dll_path(org, pid),
                    db_path=self.db_path(org, pid),
                    stamp_path=self.stamp_path(org, pid),
                    l1_prefix=self.l1_prefix(org, pid),
                )
            )

    def write_back(
        self,
        organisation: str,
        person_id: str,
        user_text: str,
        reply_text: str,
        *,
        history: list[dict] | None = None,
    ) -> dict:
        """Extract turn memory with the metered extraction model and write back to L1/L2/L3."""
        org, pid = _require_scope(organisation, person_id)
        fixed_ids = [item[0] for item in self.fixed_blocks]

        if self.side == "guardian":
            prompt = f"""You are the memory extraction system for Urithi's guardian side.
Extract concise plain-text notes from this teaching exchange to update the guardian's memory blocks.

GUARDIAN: "{user_text[:500]}"
URITHI: "{(reply_text or '')[:400]}"

Return ONLY a valid JSON object with these keys (empty string if nothing to update):
- current_class: What the guardian is teaching or showing right now, and the question waiting.
- active_knowledge: Key step, rule or example retained for the knowledge being taught.
- teaching_preferences: Any stated preference about how Urithi should ask or stay quiet.
- guardian_profile: Any background or domain detail the guardian shared about themselves.
"""
        else:
            prompt = f"""You are the memory extraction system for Urithi's learner side.
Extract concise plain-text notes from this tutoring exchange to update the learner's memory blocks.

LEARNER: "{user_text[:500]}"
TUTOR: "{(reply_text or '')[:400]}"

Return ONLY a valid JSON object with these keys (empty string if nothing to update):
- current_session: What the learner is asking about or studying right now. Always fill this.
- active_knowledge: Which part or rule of the knowledge is under study.
- learning_preferences: Learning style, difficulty, or what the learner found hard.
- learner_profile: Any personal goal, background or language preference shared by the learner.
"""

        problems: list[str] = []
        updates: dict[str, str] = {}
        if _extractor_ready():
            try:
                raw = call_extraction_model(
                    [{"role": "user", "content": prompt}],
                    temperature=0.0,
                    response_format={"type": "json_object"},
                    max_tokens=1000,
                )
                updates, parse_problems = parse_extraction(raw)
                problems.extend(parse_problems)
            except Exception as e:
                logger.warning("Memory extraction model call failed (%s); using fallback.", e)
                problems.append(f"the memory extractor could not be reached ({e})")

        if not updates:
            head_block = fixed_ids[0]
            fallback_text = f"Recent turn: {user_text.strip()[:240]}"
            if len(fallback_text) > 5:
                updates = {head_block: fallback_text}
            else:
                problems.append("nothing was extracted from this exchange")

        with self.lock(org, pid):
            own_dll = self.load_dll(org, pid)
            written: list[str] = []
            for block_id, new_info in updates.items():
                if block_id not in own_dll.get("nodes", {}):
                    continue
                try:
                    own_dll = _run_sync(
                        mmu_dll.update_node_content(
                            block_id,
                            new_info,
                            own_dll,
                            path=self.dll_path(org, pid),
                            db_path=self.db_path(org, pid),
                            stamp_path=self.stamp_path(org, pid),
                            l1_prefix=self.l1_prefix(org, pid),
                        )
                    )
                    written.append(block_id)
                except Exception as e:
                    logger.error("Failed to store memory block '%s': %s", block_id, e)
                    problems.append(f"{block_id}: could not be saved ({e})")

            proposal = None
            if history:
                proposal = detect_new_block_opportunity(history, own_dll)
                if proposal:
                    _run_sync(
                        mmu_dll.auto_execute_block_proposal(
                            proposal,
                            path=self.dll_path(org, pid),
                            db_path=self.db_path(org, pid),
                            stamp_path=self.stamp_path(org, pid),
                            l1_prefix=self.l1_prefix(org, pid),
                        )
                    )

        return {"updated": written, "problems": problems, "proposal": proposal}

    def forget_person(self, organisation: str, person_id: str) -> None:
        """Remove all MMU files and L1 entries for one person in one organisation."""
        import shutil

        org, pid = _require_scope(organisation, person_id)
        with self.lock(org, pid):
            prefix = self.l1_prefix(org, pid)
            for k in list(cache_l1._cache.keys()):
                if k.startswith(prefix):
                    cache_l1.invalidate(k)
            lance_driver.reset_db(self.db_path(org, pid))
            target = self._person_dir(org, pid)
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
