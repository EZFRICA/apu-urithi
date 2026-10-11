"""The learner's side: where progress, renderings and the packages' signing key are kept.

Its own directory, never written by the guardian's side (docs/architecture.md).
"""

import os

from apu import (
    config as _shared,  # noqa: F401  (loads .env before anything here is read)
)

_HERE = os.path.dirname(os.path.abspath(__file__))

DATA_DIR = os.environ.get("LEARNER_DATA_DIR", os.path.join(_HERE, "data"))
PROGRESS_PATH = os.environ.get("LEARNER_PROGRESS_PATH", os.path.join(DATA_DIR, "learners.sqlite3"))
MMU_DIR = os.environ.get("LEARNER_MMU_DIR", os.path.join(DATA_DIR, "mmu"))

# The signing key for knowledge packages, as a PEM (learner/packages/signing.py). Without it a
# key is made under DATA_DIR on first use; a server whose disk does not last must be given
# one, or the packages it signed cannot be checked after a restart.
SIGNING_KEY_ENV = "LEARNER_SIGNING_KEY"
