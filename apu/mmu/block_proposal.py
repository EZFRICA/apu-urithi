"""The shape of a block proposal: one definition, used by both detector and executor.

The detector once emitted `block_type` while the executor read `type`, and neither
`initial_content` nor `keywords` was produced. Nothing raised: a block with `type=None`
and `content=None` was created and reported as success. Having one declared shape stops
the two sides drifting again.
"""

from typing import TypedDict


class BlockProposal(TypedDict):
    """A proposed dynamic memory block, as passed from detector to executor."""

    proposed_id: str
    label: str
    type: str            # a DLL block type: temporary | project | knowledge | fundamental
    initial_content: str
    keywords: list[str]
    reason: str


REQUIRED_FIELDS = ("proposed_id", "label", "type", "initial_content")


def validate(proposal: dict | None) -> str | None:
    """Return None if the proposal can be executed, else why it cannot."""
    if not proposal:
        return "proposal is empty"
    if not isinstance(proposal, dict):
        return f"proposal must be a dict, got {type(proposal).__name__}"

    missing = [f for f in REQUIRED_FIELDS if not str(proposal.get(f) or "").strip()]
    if missing:
        return f"missing or empty required field(s): {', '.join(missing)}"
    return None
