# Working on Urithi: environment, layout, and checks

Part of [AGENTS.md](../AGENTS.md).

## The environment

- macOS, Python 3.13 managed by `uv` (`pyproject.toml`, `uv.lock`), Node 24 for the page tests.
- The project is a git repository. Nothing is committed, pushed or branched without the
  owner's word (the house rules); keep the list of every file you change for the report.
- One FastAPI server, `server.py`, run by `scripts/serve.sh` (restarts whatever holds 8790):
  - `/` the showcase, `/teach/` the guardian, `/learn/` the learner, `/presentation/` the stage.
- Services, by the names of their settings (values in `.env`, never shown):
  - `GEMINI_API_KEY`: judgment, wording, the guard, vision, illustrations; fallback for speech.
  - `ELEVENLABS_API_KEY`: speech out with word timings, speech in, live words in a class.
  - `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`: the library (Aura). Unset, it runs in
    memory, which is what the tests use.
  - `GUARDIAN_SOURCES_BUCKET` or `GCS_BUCKET_NAME`: where cited documents are archived.
  - `BRIGHTDATA_API_TOKEN`, `TAVILY_API_KEY`: public sources a rule is checked against.
  - `ARIZE_API_KEY`, `ARIZE_SPACE_ID`: traces of the model calls, texts hidden (`apu/observability.py`);
    `URITHI_TRACING_REGION=eu` for a space in Europe; off in the tests; `scripts/check_tracing.py`
    checks the key with one small call.
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
                     Neo4j), reader (read only, for the learner's side), keywords (BM25, RRF)
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
uv run python scripts/measure_search.py                  # the search on 38 labelled questions
URITHI_LIVE_NEO4J=1 uv run pytest -q tests -k neo4j      # the store contract on real Neo4j
bash scripts/serve.sh                                    # restart the server on 8790
uv run python scripts/demo_map.py --quick                # a published knowledge for the stage (--guardian ezekias)
```

- On 2026-10-17: 607 tests pass, 10 are skipped (live tests behind flags), ruff is clean, and
  `scripts/mutate.py` holds 374 deliberate defects, all caught.
- **`mutate.py` works on copies of the repository in a temporary directory**, taken when it
  starts; the tree and the server are not touched. A change made while it runs is seen only in
  part (the mutant's own file is read again, the rest is the copy): after editing, run it again.
- A mutant reported SKIPPED means its text no longer occurs exactly once: retarget it to the
  new line. A mutant MISSED means a guarantee nobody holds: write the test. Never delete or
  loosen a mutant to make a run pass.
- Page code is tested two ways: node suites that run the real modules against a stub browser
  (`tests/presentation/*.test.mjs`), and string checks of the page sources
  (`tests/shared/test_pages.py`). Prefer the node suites when behaviour can be run.
