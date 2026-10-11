"""What the learner's side may do with the library: read it, in one organisation, with a person's levels.

The learner's side never holds the store itself, whose publish and withdraw are guardian
actions (docs/architecture.md). Measured in the step 0 review: the learner's routes imported
the whole store, so a write was one call away and only a test reading two method names stood
in the way. This hands on the three reads and nothing else, bound to the organisation of the
person reading, and tests/shared/test_boundaries.py refuses any other way into the library
from learner/.
"""

import copy
import threading
from collections import OrderedDict

from library.model import check_organisation
from library.store import get_store

# A body as a person may see it, kept while it does not change. Measured on Neo4j: reading a
# body took 2.2 s (six round trips), on every question and every part opened; its stamp, one
# round trip. The key holds the stamp (version and when it was published), the levels, the
# organisation and the store, so a body republished, withdrawn or read with other levels is
# read again, never served from here.
_KEPT: OrderedDict = OrderedDict()
_KEPT_LOCK = threading.Lock()
KEPT_BODIES = 64


class Reader:
    """The library, read only, in one organisation. Every read takes the levels the person may see."""

    __slots__ = ("_organisation", "_store")

    def __init__(self, store, organisation: str):
        self._store = store
        self._organisation = check_organisation(organisation)

    def bodies_for(self, allowed) -> list[dict]:
        return self._store.bodies_for(self._organisation, allowed)

    def search(self, query: str, allowed, k: int = 5, body_id: str | None = None) -> list[dict]:
        return self._store.search(self._organisation, query, allowed, k=k, body_id=body_id)

    def body_units(self, body_id: str, allowed) -> dict | None:
        stamp_of = getattr(self._store, "stamp_of", None)
        if stamp_of is None:
            return self._store.body_units(self._organisation, body_id, allowed)
        stamp = stamp_of(self._organisation, body_id)
        if stamp is None:
            return None                     # withdrawn, or never published: nothing kept is served
        key = (id(self._store), self._organisation, body_id, frozenset(allowed), stamp)
        with _KEPT_LOCK:
            if key in _KEPT:
                _KEPT.move_to_end(key)
                return copy.deepcopy(_KEPT[key])
        found = self._store.body_units(self._organisation, body_id, allowed)
        if found is not None:
            with _KEPT_LOCK:
                _KEPT[key] = copy.deepcopy(found)
                while len(_KEPT) > KEPT_BODIES:
                    _KEPT.popitem(last=False)
        return found


def get_reader(organisation: str) -> Reader:
    """The library as configured (library.store.get_store), behind the reads alone, in one organisation."""
    return Reader(get_store(), organisation)
