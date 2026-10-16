"""The learner's APU memory (MMU), per organisation and per learner (docs/decisions/0015).

Holds the four fixed learner blocks in L1/L2/L3 (`current_session`, `active_knowledge`,
`learning_preferences`, `learner_profile`) plus up to `MAX_DYNAMIC_BLOCKS` dynamic blocks with
LRU page-out to L3, Semantic Page Fault page-in back to L2, and BMJ promotion on search.

Owned by the learner's side under `learner/data/mmu`, behind `get_learner_mmu()` and
`set_learner_mmu()`; never read by the guardian's side, and never writing to the Neo4j library.
"""

from apu.mmu import dll as mmu_dll
from apu.mmu.dll import LEARNER_FIXED_BLOCKS
from apu.mmu.store import PersonMmuStore
from learner import config


class LearnerMmuStore(PersonMmuStore):
    def __init__(self, base_dir: str | None = None):
        super().__init__(
            base_dir or config.MMU_DIR,
            side="learner",
            fixed_blocks=LEARNER_FIXED_BLOCKS,
        )

    def record_session_event(
        self,
        organisation: str,
        person_id: str,
        body_id: str,
        *,
        on: str | None = None,
        asked: dict | None = None,
        hard: dict | None = None,
    ) -> None:
        """Sync a session event (part in view, question asked, or hard part) into the MMU."""
        if not organisation or not person_id:
            return
        with self.lock(organisation, person_id):
            self.switch_knowledge(organisation, person_id, body_id)
            if on:
                text = f"Currently viewing part {on} of knowledge {body_id}."
                try:
                    self.update_block(organisation, person_id, "current_session", text, knowledge_id=body_id,
                                      source={"by": "session", "said": text})
                except Exception:
                    dll = self.load_dll(organisation, person_id)
                    dll["nodes"]["current_session"]["content"] = text
                    mmu_dll.tag_node(dll["nodes"]["current_session"], dll, knowledge_id=body_id, source={"by": "session", "said": text})
                    self.save_dll(organisation, person_id, dll)
            if hard:
                text = f"Found hard on {body_id}: {hard.get('unit_id', '')} ({hard.get('text', '')[:160]})."
                try:
                    self.update_block(organisation, person_id, "learning_preferences", text, knowledge_id=body_id,
                                      source={"by": "session", "said": text})
                except Exception:
                    dll = self.load_dll(organisation, person_id)
                    dll["nodes"]["learning_preferences"]["content"] = text
                    mmu_dll.tag_node(dll["nodes"]["learning_preferences"], dll, knowledge_id=body_id, source={"by": "session", "said": text})
                    self.save_dll(organisation, person_id, dll)
            if asked:
                q_text = str(asked.get("question") or "").strip()
                if q_text:
                    text = f"Asked on {body_id} ({asked.get('unit_id') or 'general'}): {q_text[:200]}"
                    try:
                        self.update_block(organisation, person_id, "active_knowledge", text, knowledge_id=body_id,
                                          source={"by": "session", "said": text})
                    except Exception:
                        dll = self.load_dll(organisation, person_id)
                        dll["nodes"]["active_knowledge"]["content"] = text
                        mmu_dll.tag_node(dll["nodes"]["active_knowledge"], dll, knowledge_id=body_id, source={"by": "session", "said": text})
                        self.save_dll(organisation, person_id, dll)

    def tutor_turn(
        self,
        organisation: str,
        person_id: str,
        body_id: str,
        question: str,
    ) -> tuple[dict, dict, list[dict]]:
        """Run L1 -> L2 -> L3 retrieval with BMJ promotion before the tutor words an answer."""
        with self.lock(organisation, person_id):
            self.switch_knowledge(organisation, person_id, body_id)
            try:
                hits = self.search(organisation, person_id, question)
            except Exception:
                hits = []
            context = self.read_context(organisation, person_id, knowledge_id=body_id)   # this knowledge's, and the person's
            dll = self.load_dll(organisation, person_id)
            return dll, context, hits


_learner_mmu: LearnerMmuStore | None = None


def get_learner_mmu() -> LearnerMmuStore:
    global _learner_mmu
    if _learner_mmu is None:
        _learner_mmu = LearnerMmuStore()
    return _learner_mmu


def set_learner_mmu(store: LearnerMmuStore | None) -> None:
    global _learner_mmu
    _learner_mmu = store
