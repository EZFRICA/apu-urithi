"""Block types of the MMU, and the types the memory must never contain.

English block types used across Urithi (docs/decisions/0015):
  - temporary:   what is in progress right now (current_class or current_session), inserted at HEAD
  - project:     open questions, drafts and cases under study, inserted right after HEAD
  - knowledge:   the knowledge being taught or in view (active_knowledge), inserted after HEAD
  - fundamental: the person themselves (preferences, learned threshold, profile), before TAIL

Escalation and distress events are about safety or behaviour, not knowledge, and letting them
into the DLL or into the L3 tables the BMJ search reads would feed them back into prompts.
Both the DLL and the L3 driver refuse these types, and the search drops any row carrying one.
"""

TEMPORARY_BLOCK_TYPE = "temporary"
PROJECT_BLOCK_TYPE = "project"
KNOWLEDGE_BLOCK_TYPE = "knowledge"
FUNDAMENTAL_BLOCK_TYPE = "fundamental"

# What belongs to the knowledge in view, against what is about the person whatever they learn. Measured on
# 2026-10-15: a learner's memory written on one knowledge (its question, its session) reached the answer on
# another, labelled with the new knowledge's name, and a covered question was found unanswered 10 times in 10.
SCENARIO_BLOCK_TYPES: frozenset[str] = frozenset({TEMPORARY_BLOCK_TYPE, PROJECT_BLOCK_TYPE, KNOWLEDGE_BLOCK_TYPE})

ESCALATION_EVENT_BLOCK_TYPE = "escalation_event"
DISTRESS_EVENT_BLOCK_TYPE = "distress_event"

EXCLUDED_BLOCK_TYPES: frozenset[str] = frozenset({
    ESCALATION_EVENT_BLOCK_TYPE,
    DISTRESS_EVENT_BLOCK_TYPE,
})
TUTORING_EXCLUDED_BLOCK_TYPES = EXCLUDED_BLOCK_TYPES


class ForbiddenBlockType(ValueError):
    """A block type that is kept out of the memory was offered to it."""


def refuse_excluded_block_type(block_type: str | None) -> None:
    if block_type in EXCLUDED_BLOCK_TYPES:
        raise ForbiddenBlockType(
            f"Block type {block_type!r} is kept out of the MMU memory; it must never enter "
            "the DLL or the L3 vector store."
        )


refuse_non_tutoring_block_type = refuse_excluded_block_type
