# 0008: How Urithi is deployed is decided later

Decided: 2026-10-05, by the owner.

## Context
The design must not assume one process, but choosing services now is early.

## Decision
Locally one server mounts both sides. Nothing in the code assumes one process. Two services, with the learner's read-only on the library, is the likely choice.

## Consequences
Each side remains its own application.

## Alternatives set aside
- None considered.
