"""The Work Map: what an expert does, why they do it, and where they stop and ask.

A recording says what happened. An automation tool copies the clicks. Neither can teach,
because neither holds the reason. This is the third thing: every step carries the screen
moment it happened at, the decision taken, the reason **in the expert's own words**, and
the guardrails around it.

The guardrails are the point. They are not prose for a human to read later: each one is a
condition a machine can check, so when a new hire works a case the tutor can catch a breach
before it is saved rather than explain it afterwards. An expert says "unknown supplier:
stop and ask the controller" once, out loud, and that sentence becomes a rail.
"""

import json
import os
import sqlite3
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

from apu import config as shared_config
from guardian import config

WORKMAP_PATH = config.WORKMAP_PATH
LEGACY_ORGANISATION = shared_config.LEGACY_ORGANISATION


class WorkMapError(RuntimeError):
    """The map cannot hold what it was given."""


class MapChanged(WorkMapError):
    """The map was written by someone else since it was loaded: saved now, it would undo their change.
    Found in the review of 2026-10-14: a map was written back whole, the last writer winning."""


@dataclass(frozen=True)
class Guardrail:
    """
    A limit the expert stated, in a form the tutor can check.

    `when` is the condition in the expert's words. `then` is what they said to do about it,
    which is nearly always to stop and ask a named person. `quote` is the sentence it came
    from, kept verbatim: a rail a new hire cannot trace back to a person who said it is a
    rule they will work around.
    """

    guardrail_id: str
    when: str
    then: str
    quote: str
    asked_at: float          # seconds into the session, so the screen moment can be replayed
    severity: str = "stop"   # "stop" (never proceed) or "check" (proceed with care)
    # Where this rule comes from, once it has been looked up: corroborated by a public
    # source, in conflict with one, a house rule, or not yet checked. A dict rather than a
    # type, so a map written before provenance existed still loads.
    provenance: dict | None = None
    # When it was said, as a date and time. A session's seconds start again at zero in the
    # next session, so on a map taught over several, "at 0:12" says nothing about when.
    said_at: str | None = None
    # The deposited passages it rests on: [{"source_id", "name", "where", "text"}] (step 3).
    cites: tuple = ()

    def __post_init__(self):
        if self.severity not in ("stop", "check"):
            raise WorkMapError(f"A guardrail is 'stop' or 'check', not {self.severity!r}.")
        if not self.when.strip() or not self.then.strip():
            raise WorkMapError("A guardrail needs both a condition and what to do about it.")


@dataclass(frozen=True)
class Step:
    """One thing the expert did, and why."""

    step_id: str
    number: int
    title: str                       # "Code the invoice to a cost center"
    screen_moment: float             # seconds into the session
    observed: str                    # what the vision model saw change
    decision: str                    # what the expert chose
    reason: str                      # the expert's own words, verbatim
    guardrail_ids: tuple[str, ...] = ()
    confirmed: bool = False          # the expert heard the teach-back and said yes
    said_at: str | None = None       # when it was said, as a date and time (see Guardrail)
    cites: tuple = ()                # the deposited passages it rests on (see Guardrail)


@dataclass(frozen=True)
class Ruling:
    """
    A person's decision on one specific case. Precedent, in the legal sense.

    A rule says what to do in general and is silent at its edges. A ruling is what
    somebody with the authority to decide said about one concrete case at one of those
    edges, in their own words. The tutor cites it when a new case matches, the way a judge
    cites a prior judgment, and the map keeps learning after the expert has gone: when the
    controller settles a case the tutor stopped, that becomes a ruling too.
    """

    ruling_id: str
    guardrail_id: str                # the rule this case tested
    kind: str                        # "boundary", "collision", "source", "near_miss", "escalation"
    case: dict                       # the concrete case that was put to them
    question: str                    # what they were asked, verbatim
    said: str                        # what they answered, verbatim
    applies: bool | None             # whether the rule applies to this case; None if they
                                     # answered something that is not a yes or a no
    by: str                          # who decided: the expert, or the person after them
    at: str                          # when


@dataclass
class WorkMap:
    map_id: str
    task: str
    expert: str
    created_at: str
    steps: list[Step] = field(default_factory=list)
    guardrails: list[Guardrail] = field(default_factory=list)
    confirmed_at: str | None = None
    rulings: list[Ruling] = field(default_factory=list)
    # The language the guardian teaches in: the apprentice asks, tests and reads back in it.
    language: str = "en"
    # Who may learn each part, as last published: a body withdrawn and published again keeps
    # what its guardian kept closed, rather than opening it by default.
    access: dict = field(default_factory=dict)
    # Whose knowledge it is (docs/decisions/0006): published there, and only there.
    organisation: str = ""
    # The validated version (docs/decisions/0002): what the guardian heard back and confirmed,
    # kept whole. What is taught after it is a draft until validated again; publishing always
    # publishes this, never a part the guardian has not heard back.
    validated: dict | None = None
    # The contents, as the guardian orders them: steps top to bottom, and sections grouping
    # them. Empty: the order they were taught in. The learner's path follows this order.
    order: list = field(default_factory=list)
    sections: list = field(default_factory=list)
    # How many times the map was saved: a save from an older copy is refused, never written over a newer one.
    version: int = 0

    def ordered_steps(self) -> list["Step"]:
        position = {step_id: i for i, step_id in enumerate(self.order)}
        return sorted(self.steps, key=lambda s: (position.get(s.step_id, len(position) + s.number), s.number))

    def section_of(self, step_id: str) -> str:
        return next((sec["title"] for sec in self.sections if step_id in sec.get("steps", [])), "")

    def snapshot(self) -> dict:
        """What validating keeps: every part, and the contents."""
        return {"steps": [asdict(s) for s in self.steps], "guardrails": [asdict(g) for g in self.guardrails],
                "rulings": [asdict(r) for r in self.rulings], "order": list(self.order),
                "sections": [dict(sec) for sec in self.sections]}

    def as_validated(self) -> "WorkMap | None":
        """The validated version, as a map; a map confirmed before versions were kept is its own."""
        if self.validated is None:
            return self if self.confirmed_at else None
        kept = self.validated
        return WorkMap(map_id=self.map_id, task=self.task, expert=self.expert, created_at=self.created_at,
                       steps=[Step(**{**st, "guardrail_ids": tuple(st["guardrail_ids"])}) for st in kept["steps"]],
                       guardrails=[Guardrail(**g) for g in kept["guardrails"]],
                       rulings=[Ruling(**r) for r in kept["rulings"]], confirmed_at=self.confirmed_at or "validated",
                       language=self.language, access=self.access, organisation=self.organisation,
                       order=list(kept.get("order", [])), sections=list(kept.get("sections", [])))

    def states(self) -> dict[str, str]:
        """Each part, "validated" or "draft": a part is validated when the validated version holds it as it is."""
        kept = self.as_validated()
        held = {}
        if kept is not None:
            held.update({f"step:{s.step_id}": (s.title, s.reason, tuple(s.guardrail_ids)) for s in kept.steps})
            held.update({f"rule:{g.guardrail_id}": (g.when, g.then, g.severity, g.quote) for g in kept.guardrails})
        now = {f"step:{s.step_id}": (s.title, s.reason, tuple(s.guardrail_ids)) for s in self.steps}
        now.update({f"rule:{g.guardrail_id}": (g.when, g.then, g.severity, g.quote) for g in self.guardrails})
        return {key: "validated" if held.get(key) == value else "draft" for key, value in now.items()}

    def rulings_for(self, guardrail_id: str) -> list[Ruling]:
        return [r for r in self.rulings if r.guardrail_id == guardrail_id]

    def guardrail(self, guardrail_id: str) -> Guardrail | None:
        return next((g for g in self.guardrails if g.guardrail_id == guardrail_id), None)

    def rails_for(self, step: Step) -> list[Guardrail]:
        return [g for g in (self.guardrail(i) for i in step.guardrail_ids) if g]

    @property
    def conflicts(self) -> list[Guardrail]:
        """Rules a public source contradicts. The reason this is worth running at all."""
        return [g for g in self.guardrails
                if (g.provenance or {}).get("verdict") == "conflicted"]

    @property
    def is_teachable(self) -> bool:
        """
        Whether a new person could do the task from this.

        The test of a teaching source, made into a property: a map with steps but no reasons is a
        recording, and a map with no guardrails has not learned when to stop. Both are
        refused as a teaching source rather than quietly used as one.
        """
        return (
            bool(self.steps)
            and all(step.reason.strip() for step in self.steps)
            and bool(self.guardrails)
        )

    def why_not_teachable(self) -> str:
        if not self.steps:
            return "Nothing was captured yet."
        missing = [s.number for s in self.steps if not s.reason.strip()]
        if missing:
            return f"No reason was given for step {', '.join(str(n) for n in missing)}."
        if not self.guardrails:
            return "No limit was stated, so the tutor has nothing to stop a new hire on."
        return ""


def _connect(path: str = WORKMAP_PATH) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS workmaps (
            map_id TEXT PRIMARY KEY,
            task TEXT NOT NULL,
            expert TEXT NOT NULL,
            created_at TEXT NOT NULL,
            confirmed_at TEXT,
            steps TEXT NOT NULL,
            guardrails TEXT NOT NULL
        )
    """)
    # Added after the first maps were written. A column added in place, rather than a new
    # table, so a map from before rulings existed still loads, with none.
    columns = {row[1] for row in connection.execute("PRAGMA table_info(workmaps)")}
    if "rulings" not in columns:
        connection.execute("ALTER TABLE workmaps ADD COLUMN rulings TEXT NOT NULL DEFAULT '[]'")
    if "language" not in columns:
        connection.execute("ALTER TABLE workmaps ADD COLUMN language TEXT NOT NULL DEFAULT 'en'")
    if "access" not in columns:
        connection.execute("ALTER TABLE workmaps ADD COLUMN access TEXT NOT NULL DEFAULT '{}'")
    for name in ("validated", "contents"):
        if name not in columns:
            connection.execute(f"ALTER TABLE workmaps ADD COLUMN {name} TEXT")
    if "version" not in columns:
        connection.execute("ALTER TABLE workmaps ADD COLUMN version INTEGER NOT NULL DEFAULT 0")
    if "organisation" not in columns:
        # Maps written before organisations existed belong to the one there was.
        connection.execute("ALTER TABLE workmaps ADD COLUMN organisation TEXT NOT NULL DEFAULT ''")
        connection.execute("UPDATE workmaps SET organisation = ? WHERE organisation = ''", (LEGACY_ORGANISATION,))
    connection.commit()
    return connection


def _owned(organisation: str) -> str:
    """A map is always some organisation's; one with none is refused, never filed under a default."""
    if not organisation:
        raise WorkMapError("A map belongs to an organisation; none was given.")
    return organisation


class WorkMapStore:
    def __init__(self, path: str = WORKMAP_PATH):
        self.path = path

    def new(self, task: str, expert: str, language: str = "en", *, organisation: str) -> WorkMap:
        return WorkMap(map_id=str(uuid.uuid4()), task=task, expert=expert,
                       created_at=datetime.now(UTC).isoformat(), language=language,
                       organisation=_owned(organisation))

    def save(self, work_map: WorkMap) -> None:
        """Written when nobody saved it since it was loaded; refused otherwise (MapChanged)."""
        with _connect(self.path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT version FROM workmaps WHERE map_id = ?", (work_map.map_id,)).fetchone()
            if row is not None and int(row[0]) != work_map.version:
                raise MapChanged(f"The map {work_map.map_id} was saved meanwhile (version {row[0]}, "
                                 f"this copy {work_map.version}).")
            version = (int(row[0]) if row is not None else work_map.version) + 1
            connection.execute(
                "INSERT OR REPLACE INTO workmaps (map_id, task, expert, created_at, "
                "confirmed_at, steps, guardrails, rulings, language, access, organisation, validated, contents, "
                "version) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (work_map.map_id, work_map.task, work_map.expert, work_map.created_at,
                 work_map.confirmed_at,
                 json.dumps([asdict(s) for s in work_map.steps]),
                 json.dumps([asdict(g) for g in work_map.guardrails]),
                 json.dumps([asdict(r) for r in work_map.rulings]), work_map.language,
                 json.dumps(work_map.access), _owned(work_map.organisation),
                 json.dumps(work_map.validated) if work_map.validated is not None else None,
                 json.dumps({"order": work_map.order, "sections": work_map.sections}), version),
            )
        work_map.version = version

    def load(self, map_id: str) -> WorkMap | None:
        with _connect(self.path) as connection:
            row = connection.execute(
                "SELECT map_id, task, expert, created_at, confirmed_at, steps, guardrails, "
                "rulings, language, access, organisation, validated, contents, version FROM workmaps WHERE map_id = ?",
                (map_id,)).fetchone()
        if row is None:
            return None
        return WorkMap(
            map_id=row[0], task=row[1], expert=row[2], created_at=row[3], confirmed_at=row[4],
            # JSON has no tuples, so the ids come back as a list and go back to a tuple:
            # a Step is frozen, and a mutable field on a frozen record is a lie.
            steps=[Step(**{**s, "guardrail_ids": tuple(s["guardrail_ids"])})
                   for s in json.loads(row[5])],
            guardrails=[Guardrail(**g) for g in json.loads(row[6])],
            rulings=[Ruling(**r) for r in json.loads(row[7] or "[]")],
            language=row[8] or "en",
            access=json.loads(row[9] or "{}"),
            organisation=row[10] or LEGACY_ORGANISATION,
            validated=json.loads(row[11]) if row[11] else None,
            order=json.loads(row[12] or "{}").get("order", []),
            sections=json.loads(row[12] or "{}").get("sections", []),
            version=int(row[13] or 0),
        )

    def delete(self, map_id: str) -> bool:
        """The map gone, at its guardian's word: nothing of it is kept here."""
        with _connect(self.path) as connection:
            return connection.execute("DELETE FROM workmaps WHERE map_id = ?", (map_id,)).rowcount > 0

    def list_maps(self, organisation: str | None = None) -> list[dict]:
        """Every map, or those of one organisation."""
        with _connect(self.path) as connection:
            rows = connection.execute(
                "SELECT map_id, task, expert, created_at, confirmed_at, organisation FROM workmaps "
                "ORDER BY created_at DESC").fetchall()
        return [{"map_id": r[0], "task": r[1], "expert": r[2], "created_at": r[3], "confirmed_at": r[4],
                 "organisation": r[5]} for r in rows if organisation is None or r[5] == organisation]

    # ── a map as a file ──────────────────────────────────────────────────────

    def export(self, map_id: str) -> dict | None:
        """One map as plain JSON: what a deployment ships so its stage is not empty."""
        work_map = self.load(map_id)
        if work_map is None:
            return None
        return {"map_id": work_map.map_id, "task": work_map.task, "expert": work_map.expert,
                "created_at": work_map.created_at, "confirmed_at": work_map.confirmed_at,
                "steps": [asdict(s) for s in work_map.steps],
                "guardrails": [asdict(g) for g in work_map.guardrails],
                "rulings": [asdict(r) for r in work_map.rulings], "language": work_map.language,
                "organisation": work_map.organisation, "validated": work_map.validated,
                "order": work_map.order, "sections": work_map.sections}

    def import_map(self, data: dict) -> WorkMap:
        """The reverse of export, through the same constructors load uses, so a file that
        does not hold a valid map fails here rather than on the stage."""
        work_map = WorkMap(
            map_id=data["map_id"], task=data["task"], expert=data["expert"],
            created_at=data["created_at"], confirmed_at=data.get("confirmed_at"),
            steps=[Step(**{**s, "guardrail_ids": tuple(s["guardrail_ids"])})
                   for s in data["steps"]],
            guardrails=[Guardrail(**g) for g in data["guardrails"]],
            rulings=[Ruling(**r) for r in data.get("rulings", [])],
            language=data.get("language", "en"),
            organisation=data.get("organisation") or LEGACY_ORGANISATION,
            validated=data.get("validated"), order=data.get("order", []), sections=data.get("sections", []))
        current = self.load(work_map.map_id)        # an import replaces the map whole, deliberately
        work_map.version = current.version if current is not None else 0
        self.save(work_map)
        return work_map
