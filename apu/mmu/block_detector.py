"""Heuristic detector proposing a new dynamic DLL block."""

from apu.logger import get_logger
from apu.mmu.block_proposal import BlockProposal

logger = get_logger(__name__)

MIN_TURNS_FOR_DETECTION = 4
TOPIC_REPETITION_THRESHOLD = 2


def detect_new_block_opportunity(history: list[dict], dll: dict) -> dict | None:
    """Analyze recent history to detect if a new dynamic memory block should be created."""
    if len(history) < MIN_TURNS_FOR_DETECTION:
        return None

    dynamic_count = dll.get("dynamic_block_count", 0)
    dynamic_max = dll.get("dynamic_block_max", 5)
    if dynamic_count >= dynamic_max:
        logger.debug("Dynamic block limit reached (%d/%d).", dynamic_count, dynamic_max)
        return None

    recent_user_messages = [
        m["content"] for m in history[-6:]
        if m.get("role") == "user" and isinstance(m.get("content"), str)
    ]
    if not recent_user_messages:
        return None

    learning_triggers = [
        "i don't understand", "explain", "what is", "how",
        "why", "i'm struggling", "difficult", "new chapter",
        "step", "rule", "example", "je ne comprends pas", "explique",
    ]

    trigger_count = sum(
        1 for msg in recent_user_messages
        for trigger in learning_triggers
        if trigger.lower() in msg.lower()
    )

    if trigger_count >= TOPIC_REPETITION_THRESHOLD:
        proposed_id = f"dynamic_block_{dynamic_count + 1}"
        logger.info("Block opportunity detected (triggers=%d): %s", trigger_count, proposed_id)
        topic = recent_user_messages[-1].strip()
        return BlockProposal(
            proposed_id=proposed_id,
            label="Topic currently being studied",
            type="temporary",
            initial_content=topic[:500],
            keywords=[],
            reason=f"Person showed {trigger_count} active signals.",
        )

    return None
