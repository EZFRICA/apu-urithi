---
name: release
description: How a version of Urithi is prepared, checked and handed to the owner for release. Use when the owner asks to prepare a release, a commit, a pull request or a deployment.
---

# Preparing a release

Nothing is committed, pushed or deployed until the owner says so. This prepares everything so
that saying so is enough.

## Checks

1. `uv run pytest -q` green; `uv run ruff check .` clean.
2. `uv run python scripts/mutate.py` catches every mutant.
3. Live contract tests: `URITHI_LIVE_NEO4J=1 uv run pytest tests -k neo4j`.
4. No Markdown file over 100 lines; no dash in prose; no confidential model name; no key.
5. A real-condition run of what changed (`real-condition-test`).
6. `git status` reviewed file by file: nothing from `data/`, `models/`, `.env` or a scratch
   file.

## The notes

What changed for a guardian, for a learner, for an operator; what was measured; what is known
not to work yet. In English, in the repository's style.

## Deployment

The deployment target is decided later (see `docs/plan.md`). When it is: the image builds
from the Dockerfile, secrets come from the secret manager, the signing key is provided rather
than generated, and the production stores pass their contract tests before traffic.
