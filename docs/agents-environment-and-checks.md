# Working on Urithi: environment, layout, and checks

Part of [AGENTS.md](../AGENTS.md).

## The environment

- macOS, Python 3.13 managed by `uv` (`pyproject.toml`, `uv.lock`), Node 24 for the page tests.
- The project is **not a git repository**. Keep a list of every file you change.
- One FastAPI server, `server.py`, run by `scripts/serve.sh` (restarts whatever holds 8790):
  - `/` the showcase, `/teach/` the guardian, `/learn/` the learner, `/presentation/` the stage.
- Services, by the names of their settings (values in `.env`, never shown):
  - `GEMINI_API_KEY`: judgment, wording, the guard, vision, illustrations; fallback for speech.
  - `ELEVENLABS_API_KEY`: speech out with word timings, speech in, live words in a class.
  - `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`: the library (Aura). Unset, it runs in
    memory, which is what the tests use.
  - `GUARDIAN_SOURCES_BUCKET` or `GCS_BUCKET_NAME`: where cited documents are archived.
  - `BRIGHTDATA_API_TOKEN`, `TAVILY_API_KEY`: public sources a rule is checked against.
  - Faster models for what a person waits on: `URITHI_CLASS_VISION_MODEL`,
    `URITHI_QUESTION_MODEL`, `URITHI_ANSWER_MODEL` (the main model when unset). The owner
    prefers speed; keep the code's safeguards (checks, fallbacks) rather than slower models.
- The local embedding model lives in `models/` and is never downloaded at runtime.
- Runtime data (SQLite, documents, renderings, logs) lives under `*/data/` and `logs/`;
  never commit it, never print personal content from it.

## The layout

```
server.py            mounts both sides; the meter's counters; warm up at start
apu/                 shared, stores nothing: config, logger, meter, inference (models),
                     modality (voice, live relay, picture), embeddings, ui/shared (css, js)
guardian/            engine (work map, questions, vision, absorb, tutor, probe), memory
                     (maps, sessions, working memory), sources, publish, api routes,
                     ui/teach (the guardian's page, classroom.js, capture.js)
library/             the library: model, access (registries/people.json), store (memory and
                     Neo4j), reader (read only, for the learner's side)
learner/             tutor (guard, answer), memory (progress, files, answers, notebook),
                     packages, renderings, api routes, ui/learn
exchange/            the question box between the sides, and the meter's counters
registries/          people, organisations, memberships; policy.json (quotas)
scripts/             serve.sh, mutate.py (the deliberate defects), demo and import tools
tests/               shared/, guardian/, learner/, presentation/ (node suites run by pytest),
                     screens/ (practice pages to share in a class)
docs/                architecture, plan, decisions/, the measured documents
.claude/             skills (rules per area) and agents (reviewers); read the skill of the
                     area you touch before you touch it
```

## How to check your work

```bash
uv run pytest -q tests                                   # everything; must stay green
uv run ruff check .                                      # must stay clean
uv run python scripts/mutate.py --only "<label words>"   # one deliberate defect
uv run python scripts/mutate.py                          # all of them, about 30 minutes
URITHI_LIVE_NEO4J=1 uv run pytest -q tests -k neo4j      # the store contract on real Neo4j
bash scripts/serve.sh                                    # restart the server on 8790
```

- Today: 495 tests pass, 7 are skipped (live tests behind flags), ruff is clean, and
  `scripts/mutate.py` holds 232 deliberate defects.
- **While `mutate.py` runs, it rewrites source files one at a time and the server serves
  them**: do not edit files, and do not test in the browser, until it has finished. It holds
  `.mutating` as a lock; a suite started meanwhile refuses to run.
- A mutant reported SKIPPED means its text no longer occurs exactly once: retarget it to the
  new line. A mutant MISSED means a guarantee nobody holds: write the test. Never delete or
  loosen a mutant to make a run pass.
- Page code is tested two ways: node suites that run the real modules against a stub browser
  (`tests/presentation/*.test.mjs`), and string checks of the page sources
  (`tests/shared/test_pages.py`). Prefer the node suites when behaviour can be run.
