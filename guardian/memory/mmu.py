"""The guardian's APU memory (MMU), per organisation and per guardian (docs/decisions/0015).

Holds the four fixed guardian blocks in L1/L2/L3 (`current_class`, `active_knowledge`,
`teaching_preferences`, `guardian_profile`) plus up to `MAX_DYNAMIC_BLOCKS` dynamic blocks with
LRU page-out to L3, Semantic Page Fault page-in back to L2, and BMJ promotion on search.

Because `teaching_preferences` is a fixed `fundamental` block owned by `(organisation, guardian)`,
the threshold learned when a guardian passes questions in one knowledge is kept when they start
teaching the next knowledge, and is never evicted when dynamic blocks are paged out.
"""

from apu.mmu.dll import GUARDIAN_FIXED_BLOCKS
from apu.mmu.store import PersonMmuStore
from guardian import config

DEFAULT_THRESHOLD = 3


class GuardianMmuStore(PersonMmuStore):
    def __init__(self, base_dir: str | None = None):
        super().__init__(
            base_dir or config.MMU_DIR,
            side="guardian",
            fixed_blocks=GUARDIAN_FIXED_BLOCKS,
        )

    def load_threshold(self, organisation: str, guardian_id: str) -> tuple[int, dict[str, int], int]:
        """Return (level, by_kind, passed) from the guardian's fixed teaching_preferences block."""
        if not organisation or not guardian_id:
            return DEFAULT_THRESHOLD, {}, 0
        with self.lock(organisation, guardian_id):
            dll = self.load_dll(organisation, guardian_id)
            node = dll.get("nodes", {}).get("teaching_preferences", {})
            meta = node.get("pupil_threshold")
            if not isinstance(meta, dict):
                return DEFAULT_THRESHOLD, {}, 0
            level = int(meta.get("threshold", DEFAULT_THRESHOLD))
            by_kind = {str(k): int(v) for k, v in (meta.get("by_kind") or {}).items()}
            passed = int(meta.get("passed", 0))
            return level, by_kind, passed

    def save_threshold(
        self,
        organisation: str,
        guardian_id: str,
        *,
        threshold: int,
        by_kind: dict[str, int],
        passed: int,
        last_passed: str = "",
    ) -> None:
        """Persist the guardian's learned pupil threshold in their fixed teaching_preferences block."""
        if not organisation or not guardian_id:
            return
        summary = (
            f"Pupil importance threshold: {threshold} "
            f"(passed={passed}, by_kind={by_kind}, last_passed={last_passed or 'none'})."
        )
        with self.lock(organisation, guardian_id):
            try:
                self.update_block(organisation, guardian_id, "teaching_preferences", summary)
            except Exception:
                pass
            dll = self.load_dll(organisation, guardian_id)
            node = dll["nodes"]["teaching_preferences"]
            node["content"] = summary
            node["pupil_threshold"] = {
                "threshold": int(threshold),
                "by_kind": {str(k): int(v) for k, v in by_kind.items()},
                "passed": int(passed),
                "last_passed": last_passed,
            }
            self.save_dll(organisation, guardian_id, dll)

    def record_class_moment(
        self,
        organisation: str,
        guardian_id: str,
        knowledge_id: str,
        *,
        saw: str = "",
        question: str = "",
        why: str = "",
        said: str = "",
        kept: str = "",
        deferred: str = "",
    ) -> None:
        """Update the guardian's MMU during a class or teaching turn."""
        if not organisation or not guardian_id:
            return
        with self.lock(organisation, guardian_id):
            self.switch_knowledge(organisation, guardian_id, knowledge_id)
            if saw or question or why:
                text = f"On screen: {saw or 'unchanged'}. Waiting question: {question or 'none'}."
                if why:
                    text += f" Why: {why[:160]}"
                try:
                    self.update_block(organisation, guardian_id, "current_class", text)
                except Exception:
                    dll = self.load_dll(organisation, guardian_id)
                    dll["nodes"]["current_class"]["content"] = text
                    self.save_dll(organisation, guardian_id, dll)
            parts = []
            if saw:
                parts.append(f"saw: {saw[:120]}")
            if why:
                parts.append(f"why: {why[:140]}")
            if said:
                parts.append(f"said: {said[:160]}")
            if kept:
                parts.append(f"kept: {kept[:120]}")
            if deferred:
                parts.append(f"deferred: {deferred[:160]}")
            if parts:
                dll = self.load_dll(organisation, guardian_id)
                existing = (dll["nodes"]["active_knowledge"].get("content") or "").strip()
                line = "; ".join(parts)
                updated = f"{existing} | {line}"[-700:] if existing else f"Knowledge {knowledge_id}: {line}"
                try:
                    self.update_block(organisation, guardian_id, "active_knowledge", updated)
                except Exception:
                    dll = self.load_dll(organisation, guardian_id)
                    dll["nodes"]["active_knowledge"]["content"] = updated
                    self.save_dll(organisation, guardian_id, dll)
        if said:
            try:
                self.search(organisation, guardian_id, said)
            except Exception:
                pass
            self.write_back(organisation, guardian_id, said, question)


_guardian_mmu: GuardianMmuStore | None = None


def get_guardian_mmu() -> GuardianMmuStore:
    global _guardian_mmu
    if _guardian_mmu is None:
        _guardian_mmu = GuardianMmuStore()
    return _guardian_mmu


def set_guardian_mmu(store: GuardianMmuStore | None) -> None:
    global _guardian_mmu
    _guardian_mmu = store
