"""Who is asking, in simulation, in which organisation, and what they may see there.

SIMULATED IDENTITY. Who someone is, is chosen by the caller, not proven: anyone who can reach
the server can be anyone in the registry. What IS enforced: once an identity is taken as
given, the organisations it belongs to, its role in each and its access level in each come
only from the registry (config.PEOPLE_PATH), never from anything the request declares.
Replacing this module with real authentication changes how the person id is obtained;
nothing downstream of it changes.

A person may belong to several organisations, with a different role in each (docs/decisions/
0006): a guardian in one, a learner in another. A request names the organisation it acts in;
the registry decides whether the person belongs to it. One that names none acts in the
person's first membership.

Every response that depends on an identity says it is simulated.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path

from library import config
from library.model import check_access, levels_up_to

SIMULATED = True
ROLES = ("guardian", "learner")
_ORGANISATION_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


class UnknownPerson(PermissionError):
    """Not in the registry. Treated as nobody, never as a default visitor."""


class NotAMember(PermissionError):
    """In the registry, but not in the organisation the request names."""


@dataclass(frozen=True)
class Person:
    """One membership: a person, in one organisation, with a role and an access level there."""

    person_id: str
    name: str
    role: str          # guardian or learner, in this organisation
    access: str        # the most restricted level they may see, in this organisation
    organisation: str

    @property
    def allowed(self) -> tuple[str, ...]:
        return levels_up_to(self.access)


def _registry() -> dict:
    """Read on every call: it is a small file, and a change to it applies at once."""
    return json.loads(Path(config.PEOPLE_PATH).read_text(encoding="utf-8"))


def organisations() -> dict[str, str]:
    """Organisation id to its name."""
    found = {}
    for entry in _registry().get("organisations", []):
        if not _ORGANISATION_ID.match(entry["organisation"]):
            raise ValueError(f"Unusable organisation id {entry['organisation']!r}.")
        found[entry["organisation"]] = entry["name"]
    return found


def memberships() -> list[Person]:
    """Every membership in the registry, in its order."""
    data = _registry()
    names = {p["person_id"]: p["name"] for p in data.get("people", [])}
    known = organisations()
    found = []
    for entry in data.get("memberships", []):
        check_access(entry["access"])
        if entry["role"] not in ROLES:
            raise ValueError(f"Unknown role {entry['role']!r} for {entry['person_id']}.")
        if entry["organisation"] not in known:
            raise ValueError(f"{entry['person_id']} belongs to an unknown organisation {entry['organisation']!r}.")
        if entry["person_id"] not in names:
            raise ValueError(f"A membership names {entry['person_id']!r}, who is not among the people.")
        found.append(Person(entry["person_id"], names[entry["person_id"]], entry["role"], entry["access"],
                            entry["organisation"]))
    return found


def people() -> dict[str, Person]:
    """Each person by their first membership: the organisation a request naming none acts in."""
    found: dict[str, Person] = {}
    for membership in memberships():
        found.setdefault(membership.person_id, membership)
    return found


def person(person_id: str | None, organisation: str | None = None) -> Person:
    """The person's membership in the organisation named, or in their first one."""
    pid = (person_id or "").strip()
    theirs = [m for m in memberships() if m.person_id == pid]
    if not theirs:
        raise UnknownPerson(f"{person_id!r} is not in the registry.")
    if not organisation:
        return theirs[0]
    for membership in theirs:
        if membership.organisation == organisation:
            return membership
    raise NotAMember(f"{theirs[0].name} does not belong to {organisation!r}.")


def require_guardian(person_id: str | None, guardian_name: str | None = None,
                     organisation: str | None = None) -> Person:
    """Only a guardian publishes or withdraws, only their own knowledge, only in their organisation."""
    who = person(person_id, organisation)
    if who.role != "guardian":
        raise PermissionError(f"{who.name} is not a guardian in {who.organisation}.")
    if guardian_name is not None and who.name != guardian_name:
        raise PermissionError(f"This knowledge is {guardian_name}'s, not {who.name}'s.")
    return who


def as_listed(p: Person) -> dict:
    """A membership as the pages list it."""
    return {"person_id": p.person_id, "name": p.name, "role": p.role, "access": p.access,
            "organisation": p.organisation, "organisation_name": organisations().get(p.organisation, p.organisation)}
