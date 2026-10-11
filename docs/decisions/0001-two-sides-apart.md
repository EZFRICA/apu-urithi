# 0001: The guardian's side and the learner's side are kept apart

Decided: 2026-10-05, by the owner.

## Context
The first build mixed them: one SQLite file held learners' reviews and the guardian's inbox, the guardian answered through the learner's routes, and learner code imported the guardian's engine.

## Decision
The code is split into five packages: `apu/` (shared core, storing nothing), `library/` ([B], Neo4j), `exchange/` (the anonymous question box), `guardian/` and `learner/`, each side built like `apu`. The two sides never import each other; only the guardian writes to the library; each writes only to its own storage.

## Consequences
Each boundary is a test and a deliberate defect. A side can later be deployed alone. Moving the existing code is step 0 of the plan.

## Alternatives set aside
- One package with folders by feature: the boundary would live in reviews only.
