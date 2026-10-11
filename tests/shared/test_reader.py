"""
The library as the learner's side reads it, kept while it does not change.

Target: library/reader.py, library/store.py (stamp_of). Measured on Neo4j: reading a body took
2.2 s (six round trips), on every question and every part opened; its stamp takes one. What is
checked is that a kept body is never served once it has changed, been withdrawn, or is read
with other levels.
"""

import dataclasses

from library import store
from library.reader import Reader
from tests.support import BODY, ORG, community


class Counting(store.MemoryKnowledgeStore):
    def __init__(self):
        super().__init__()
        self.reads = 0

    def body_units(self, organisation, body_id, allowed):
        self.reads += 1
        return super().body_units(organisation, body_id, allowed)


def test_a_body_unchanged_is_read_once_and_served_as_a_copy():
    library = Counting()
    library.publish(community())
    reader = Reader(library, ORG)
    first = reader.body_units(BODY, ("public",))
    first["units"].clear()                       # what a caller does to its copy stays its own
    again = reader.body_units(BODY, ("public",))
    assert library.reads == 1 and len(again["units"]) == 3
    again["units"].clear()                       # and what is served from _KEPT is a copy too
    third = reader.body_units(BODY, ("public",))
    assert library.reads == 1 and len(third["units"]) == 3


def test_a_body_republished_withdrawn_or_read_with_other_levels_is_read_again():
    library = Counting()
    library.publish(community())
    reader = Reader(library, ORG)
    public = reader.body_units(BODY, ("public",))
    member = reader.body_units(BODY, ("public", "community"))
    assert len(public["units"]) == 3 and len(member["units"]) == 4, "the levels are part of what is kept"
    republished = community()
    republished = dataclasses.replace(republished, body=dataclasses.replace(republished.body, published_at="later"))
    library.publish(republished)                 # same version number, published again
    assert reader.body_units(BODY, ("public",)) is not None and library.reads == 3
    library.withdraw(ORG, BODY)
    assert reader.body_units(BODY, ("public",)) is None, "withdrawn: nothing kept is served"
    assert library.reads == 3, "and the body is not read for nothing: its stamp said it is gone"
