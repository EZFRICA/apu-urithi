# 0005: Every store sits behind an interface

Decided: 2026-10-05, by the owner.

## Context
Ten million people need production resources; a laptop needs none. Which ones is a deployment choice.

## Decision
Maps, memories, progress, the question box, counters, renderings, sources and the state of a session in progress each have an interface, a local implementation (SQLite, local disk) and contract tests any production implementation must pass.

## Consequences
The session state now in a server-process dictionary moves behind an interface in step 0b.

## Alternatives set aside
- Choosing production databases now: decides a deployment before it is needed.
