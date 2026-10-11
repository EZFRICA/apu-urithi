---
name: store-interfaces
description: How every store in Urithi sits behind an interface, so SQLite and the local disk run locally and managed services in production with no change to the code that uses them. Use when adding persistence, a cache, file storage or session state, or when preparing a production resource.
---

# Stores behind interfaces

The resources that carry 10 million people are a deployment choice. The design guarantees
only that they can be swapped. So nothing outside a store's own module knows whether it
talks to SQLite or a managed database, to the local disk or Cloud Storage.

## What is a store

Maps and working memories, validated knowledge, progress and the notebook, the question box,
quota counters and cost records, renderings (audio, braille, pictures), deposited sources,
and **the state of a session in progress** (never a module-level dictionary).

## The pattern

1. A protocol in the owning package (`guardian/memory/store.py`, `learner/memory/store.py`,
   `exchange/store.py`...) with only the operations callers need.
2. A local implementation (SQLite, local disk, in process) that is the default.
3. A getter and a setter (`get_store()`, `set_store()`), chosen from configuration, as
   `library` does today.
4. **Contract tests** run against every implementation; a production implementation is
   accepted when it passes them, live, behind an environment flag.

## Object storage

- Local disk while drafting: temporary.
- Saving uploads to Cloud Storage only what a validated part cites, under
  `organisation/<side>/<owner>/...`. Unused documents are never uploaded and are purged.
- The bucket name comes from configuration; credentials never appear in the repository.

## Checks

- No `sqlite3`, `open()` on data or cloud client outside a store module.
- No global mutable state holding user data in a route module.
- Every store method takes the organisation, or an object that carries it.
