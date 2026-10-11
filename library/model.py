"""The records of the library: bodies of knowledge, units, the links between them, the cases a
guardian decided, and the public sources a unit was checked against.

Every record that holds knowledge carries the guardian's own words (`quote`) and when they
said them (`at`), because a learner is taught by a person, not by a paraphrase.
"""

from dataclasses import asdict, dataclass, field

# Who may see a unit. Ordered from the most open: a learner allowed "restricted" is allowed
# the two before it as well, which is how the simulated registry grants them.
ACCESS_LEVELS: tuple[str, ...] = ("public", "community", "restricted")

UNIT_KINDS: tuple[str, ...] = ("step", "limit", "caution")

# The links a unit can have to another. Kept to a closed list: a relationship type comes from
# this code, never from a model's output or a request, so it is safe to place in a query.
LINK_TYPES: tuple[str, ...] = ("PREREQUISITE_OF", "LIMITS", "MEETS")


class KnowledgeError(ValueError):
    """A record that cannot be stored as given."""


def check_organisation(organisation: str | None) -> str:
    """Every read and every write names its organisation; none is never "all of them"."""
    if not organisation or not str(organisation).strip():
        raise KnowledgeError("No organisation: the library is never read or written across organisations.")
    return str(organisation)


def check_access(level: str) -> str:
    if level not in ACCESS_LEVELS:
        raise KnowledgeError(f"Unknown access level {level!r}; one of {', '.join(ACCESS_LEVELS)}.")
    return level


def levels_up_to(level: str) -> tuple[str, ...]:
    """Everything a person allowed `level` may see: that level and the more open ones."""
    check_access(level)
    return ACCESS_LEVELS[: ACCESS_LEVELS.index(level) + 1]


@dataclass(frozen=True)
class Body:
    """One body of knowledge, from one guardian: "Code a supplier invoice", by Sabine."""

    body_id: str
    name: str
    guardian: str
    version: int
    published_at: str
    language: str = "en"
    organisation: str = ""    # who owns it (docs/decisions/0006); the store refuses none


@dataclass(frozen=True)
class Unit:
    unit_id: str
    body_id: str
    kind: str                 # step, limit or caution
    text: str                 # what it says, in one sentence
    quote: str                # the guardian's words it rests on, verbatim
    at: float                 # seconds into the session the words were said
    access: str = "public"
    status: str = "published"
    language: str = "en"
    version: int = 1
    said_at: str | None = None  # when the words were said, as a date and time, if known
    section: str = ""          # the section of the contents it sits in, as the guardian grouped it

    def __post_init__(self):
        if self.kind not in UNIT_KINDS:
            raise KnowledgeError(f"Unknown unit kind {self.kind!r}.")
        check_access(self.access)
        if not self.quote.strip():
            raise KnowledgeError("A unit without the guardian's words is not the guardian's knowledge.")

    def embedding_text(self) -> str:
        """What is embedded: what it says, and the words it says it from."""
        return f"{self.text}\n{self.quote}"

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Link:
    source_id: str
    target_id: str
    type: str

    def __post_init__(self):
        if self.type not in LINK_TYPES:
            raise KnowledgeError(f"Unknown link type {self.type!r}.")


@dataclass(frozen=True)
class Case:
    """A concrete case the guardian decided: the debrief's precedent, and the exam's questions."""

    case_id: str
    body_id: str
    kind: str                 # boundary, source, collision, near_miss, escalation
    question: str
    said: str                 # the decision, in the words of whoever made it
    by: str
    applies: bool | None
    decides: tuple[str, ...]  # the unit ids it is a decision about
    access: str = "public"


@dataclass(frozen=True)
class SourceRef:
    """A public source a unit was checked against, and whether it agrees."""

    source_id: str
    body_id: str
    url: str
    domain: str
    says: str
    relation: str             # SUPPORTS or DISAGREES
    unit_id: str
    jurisdiction: str = ""


@dataclass(frozen=True)
class Evidence:
    """A passage of a document the guardian deposited, cited by a unit: at that unit's level."""

    evidence_id: str
    body_id: str
    unit_id: str
    name: str                 # the document, as the guardian named it
    where: str                # "page 3", "1:04–1:22", "the image"
    excerpt: str              # the passage, as the document holds it
    access: str = "public"


@dataclass
class Publication:
    """Everything one publish writes, as one unit of work."""

    body: Body
    units: list[Unit] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)
    cases: list[Case] = field(default_factory=list)
    sources: list[SourceRef] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
