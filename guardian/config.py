"""The guardian's side: where its work maps and working memories are kept.

Its own directory, never written by the learner's side (docs/architecture.md).
"""

import os

from apu import (
    config as _shared,  # noqa: F401  (loads .env before anything here is read)
)

_HERE = os.path.dirname(os.path.abspath(__file__))

DATA_DIR = os.environ.get("GUARDIAN_DATA_DIR", os.path.join(_HERE, "data"))
WORKMAP_PATH = os.environ.get("GUARDIAN_WORKMAP_PATH", os.path.join(DATA_DIR, "workmap.sqlite3"))
MMU_DIR = os.environ.get("GUARDIAN_MMU_DIR", os.path.join(DATA_DIR, "mmu"))

# An exported map that seeds an empty deployment, so the stage has something to present.
SEED_MAP_ENV = "GUARDIAN_SEED_MAP"

# Where a deposited document goes once a validated part cites it (docs/decisions/0004): a Cloud
# Storage bucket, under organisation/guardian/<guardian>/<map>/. Read from GCS_BUCKET_NAME when
# set for the whole machine. Empty: cited documents stay on local disk, said in the log.
SOURCES_BUCKET = os.environ.get("GUARDIAN_SOURCES_BUCKET") or os.environ.get("GCS_BUCKET_NAME", "")
# The largest document one deposit may carry.
SOURCES_MAX_BYTES = int(os.environ.get("GUARDIAN_SOURCES_MAX_BYTES", str(20 * 1024 * 1024)))
