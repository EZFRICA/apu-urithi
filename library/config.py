"""The library's configuration: where Neo4j is, and the registry of who is who.

The credentials are Neo4j's own variable names, as an Aura instance hands them out; without
NEO4J_URI the library runs in memory, which is what the tests use.
"""

import os

from apu import (
    config as _shared,  # noqa: F401  (loads .env before anything here is read)
)

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

NEO4J_URI_ENV = "NEO4J_URI"
NEO4J_USERNAME_ENV = "NEO4J_USERNAME"
NEO4J_PASSWORD_ENV = "NEO4J_PASSWORD"
NEO4J_DATABASE_ENV = "NEO4J_DATABASE"

# Who is who, in simulation: the registry the access levels are decided from.
PEOPLE_PATH = os.environ.get("URITHI_PEOPLE_PATH", os.path.join(_REPO_ROOT, "registries", "people.json"))
