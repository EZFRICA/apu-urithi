# Urithi: architecture

*"In Africa, when an old man dies, a library burns."* Amadou Hampâté Bâ, UNESCO, 1960.

Urithi (Swahili: inheritance) rethinks how knowledge is handed on. The **guardian** hands on
what they know in whatever form comes naturally, talking, showing, sharing a document, and
Urithi structures it with them. The **learner** follows a path through it, the way they need:
talking with a tutor, listening, reading, braille, testing themselves. We speak of
*knowledge*, never of a course: what is handed on is a person's judgment, not a syllabus.

This note is the design. [plan.md](plan.md) is the order it is built in,
[decisions/](decisions/) why each choice was made, and the last section here what already
runs and where it moves to.

## Principles

1. **The guardian's words are the knowledge.** Everything a learner receives traces back to
   what the guardian said or validated, verbatim and attributed. What does not is marked as
   such: an illustration, a translation, a public source.
2. **No guarantee depends on the quality of a model.** Comparisons, test cases, the reading
   of a yes or a no, grading, prerequisites and access are decided by code. A model words and
   interprets; with a weaker one, wording suffers and decisions stay right.
3. **Online and offline are both first-class.** Every capability sits behind an interface
   with an online and a local implementation, chosen per deployment.
4. **A global system that anyone adapts.** Domain, languages, models and storage are
   configuration, not code.
5. **Access is decided before retrieval, never after generation.**
6. **The guardian's side and the learner's side are kept apart**, in code, in storage and in
   their interfaces, and meet only where this note says (below).
7. **The keyboard is a first-class way in.** Every action has a key, Space talks, `?` lists
   the keys of the page.

## The packages

```
apu/         the shared core, which stores nothing: models (inference), mmu (L1 cache, L2 DLL,
             L3 vector interface, BMJ, page-in, write-back), embeddings, speech, braille,
             pictures, plain text, logging, meter, base configuration
library/     [B] the library, in Neo4j: the guardian publishes to it, the learner reads it
exchange/    what both sides share besides [B]: the question box, and the meter's counts
guardian/    built like apu, for the guardian
  config.py    its settings (GUARDIAN_*)
  memory/      the guardian's APU MMU, working memory per knowledge, and validated maps
  sources/     what the guardian deposits: audio, PDF, images (video later); transcripts
  engine/      questions, commands, vision, rule extraction, debrief, teach-back, public sources
  api/         /api/guardian/...
  ui/          the guardian's page and the classroom mode
learner/     built like apu, for the learner
  config.py    its settings (LEARNER_*)
  memory/      the learner's APU MMU, the session with the tutor, and progress (FSRS, notebook, exams)
  tutor/       the conversation, the guard, faithful answers, the contents and prerequisites
  packages/    signed packages, offline learning, synchronisation
  api/         /api/learner/...
  ui/          the learner's page, installable, offline
server.py    one local server mounting both; a static showcase at /
```

**The boundary, each rule a test.** `guardian` and `learner` never import each other; both
may import `apu`, `library` and `exchange`. Only `guardian` writes to `library`. Each writes
only to its own data directory and its own prefix in object storage, and reads only its own
settings. Each rule has a deliberate defect in `scripts/mutate.py`.

Each side is its own FastAPI application. Locally `server.py` mounts both; how they are
deployed is decided later, and nothing in the code assumes one process.

**Every store sits behind an interface**, so the resources are a deployment choice, not a
design one: SQLite and the local disk on a laptop, a managed database, a shared cache and
Cloud Storage in production, with no change to the code that uses them. That includes the
state of a session in progress, behind `SessionStore` (`guardian/memory/store.py`): held in the
server process locally, and moved to a shared store by a deployment with no change to the routes.

## What runs where (v1, done)

| Package | Holds | Data |
|---|---|---|
| `apu/` | inference, `mmu/` (L1, L2 DLL, L3 LanceDB interface, BMJ, page-in), modality, embeddings, language, meter, logging, config | none |
| `library/` | store, model, access registry, read-only `reader.py`, `keywords.py` (words beside meaning) | Neo4j |
| `exchange/` | the question box and the meter's counters | `exchange/data/` |
| `guardian/` | engine (map, questions, commands, vision, absorb, tutor, probe), memory (maps, sessions, working, MMU), sources, publish, `/teach/` | `guardian/data/` |
| `learner/` | tutor (guard, answer), memory (progress, files, answers, notebook, MMU), packages, renderings, `/learn/` | `learner/data/` |
| `server.py` | mounts both sides; the only module that imports both | none |

`tests/shared/test_boundaries.py` reads the imports, the routes and the data paths from the
code, and each rule has a deliberate defect in `scripts/mutate.py`.
Measured as it was built: [measurements.md](measurements.md), [urithi-measured.md](urithi-measured.md),
[measured-steps.md](measured-steps.md) and [measured-class.md](measured-class.md).

## The parts in detail

- [architecture-memory.md](architecture-memory.md): the memories and the APU memory hierarchy.
- [architecture-sides.md](architecture-sides.md): the guardian's side and the learner's side.
- [architecture-organisations-and-neo4j.md](architecture-organisations-and-neo4j.md): organisations, quotas, cost, and Neo4j.
- [architecture-safety-and-pages.md](architecture-safety-and-pages.md): capabilities behind interfaces and safety.
