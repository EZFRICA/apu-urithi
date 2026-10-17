# Urithi

*"In Africa, when an old man dies, a library burns."* Amadou Hampâté Bâ, UNESCO, 1960.

Urithi (Swahili: inheritance) rethinks how knowledge is handed on. Until now, the person who
knows records videos, writes documents, makes audio, and every learner follows the same path
through them. Here the **guardian** teaches the way that comes naturally, by talking, by
showing their screen, and Urithi structures it during the exchange: it asks *why* at the
right moment, writes the rules down in the guardian's own words, tests them like code, and
publishes nothing until the guardian has heard it back and said it is right. The **learner**
then learns the way they need: reading, listening, braille, practising, asking, online or not.

Ezekias Bokove had the idea for Urithi during a hackathon. The engine that listens to the
guardian and tests their rules is in `guardian/engine/`.

```bash
brew install liblouis                    # or: apt install liblouis-dev (braille)
uv sync
cp .env.example .env                     # GEMINI_API_KEY, ELEVENLABS_API_KEY, NEO4J_*, BRIGHTDATA_API_TOKEN
uv run python -m server              # or scripts/serve.sh, which restarts it by its port
```

| | |
|---|---|
| `http://localhost:8790/` | **the showcase**: what Urithi is, static, the way into both sides |
| `http://localhost:8790/teach/` | **teach**: a conversation, the knowledge growing beside it as a tree, documents to cite, the classroom mode on a shared screen or a camera (Urithi asks at the pauses and listens hands free, "remember this" keeps part of the screen, the question and the notes can float above the work), the debrief, then validate and publish with an access level per part; a knowledge can be deleted, asked twice |
| `http://localhost:8790/learn/` | **learn**: the contents as a tree beside the part in view and the questions, each part read, heard, in braille or practised, reviews when due; what Urithi remembers about the learner, readable and removable |
| `http://localhost:8790/presentation/` | **the stage**: /learn/ on the desk of a learner who cannot see the screen: what was published, at their level, part by part (heard in the guardian's words, braille), practice, the exam, questions asked aloud; any learner (`?learner=visitor`) |

The design is [docs/architecture.md](docs/architecture.md), and the order it is built in
[docs/plan.md](docs/plan.md). What was
measured, and the defects measuring found: the engine in [docs/measurements.md](docs/measurements.md),
Urithi's own parts in [docs/urithi-measured.md](docs/urithi-measured.md).

---

For what each side does and how knowledge is kept see [docs/readme-sides.md](docs/readme-sides.md); for safety and honest limits see [docs/readme-safety-and-limits.md](docs/readme-safety-and-limits.md).

## Configuration

| Variable | |
|---|---|
| `GEMINI_API_KEY` | judgment, wording, the guard, vision, illustrations (`gemini-3.1-flash-image`) |
| `ELEVENLABS_API_KEY` | speech: `eleven_v4_turbo` out, `scribe_v2` in |
| `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD` | the library; without them it runs in memory |
| `BRIGHTDATA_API_TOKEN` | public sources (Tavily is the fallback) |
| `LEARNER_SIGNING_KEY` | the key packages are signed with (PEM); made once under `learner/data/` if unset |
| `URITHI_PORT` | 8790 by default |
| `URITHI_CLASS_VISION_MODEL`, `URITHI_QUESTION_MODEL`, `URITHI_ANSWER_MODEL` | faster models for what a person waits on: a class's frames, the question asked, a learner's answer (the main model when unset) |
| `GUARDIAN_SOURCES_BUCKET` | where documents a validated part cites are archived (else `GCS_BUCKET_NAME`) |

The embedding model lives in `models/` (about 240 MB) and is never downloaded at runtime. The
`Dockerfile` runs on Cloud Run with keys from Secret Manager.

## Proved, not claimed

```bash
uv run pytest -q                         # offline, no key needed
URITHI_LIVE_NEO4J=1 uv run pytest tests/shared/test_library.py -k neo4j   # the same contract, live
uv run python scripts/measure_search.py  # the search on 38 labelled questions, by meaning and by words
uv run python scripts/mutate.py          # 374 deliberate defects in parallel copies, each must be caught
```

## What is in the box

```
server.py               one server: both sides, each under its own address
apu/                    the shared core, stores nothing: models, speech, braille, embeddings, mmu/
library/                [B]: the published knowledge in Neo4j, searched with access levels
exchange/               the question box and meter counters, the one place both sides share
guardian/               the guardian's side, /api/guardian: the engine (questions, commands,
                        vision, debrief, precedent, provenance), work maps, mmu, publishing, inbox
guardian/ui/teach/      the guardian's page and classroom mode
learner/                the learner's side, /api/learner: path, guard, faithful answers, mmu,
                        FSRS reviews, exam, signed packages
learner/ui/learn/       the learner's page, installable, works offline
apu/ui/shared/          the look both sides share (light and dark), the tree, the teleprompter
apu/ui/showcase/        the static page at /
apu/ui/presentation/    the stage
registries/people.json  simulated identities
tests/                  guardian/, learner/, shared/, presentation/: each side proved apart
```

## License

Apache License 2.0: see [LICENSE](LICENSE) and [NOTICE](NOTICE).
