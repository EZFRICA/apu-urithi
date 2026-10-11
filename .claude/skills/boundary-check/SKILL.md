---
name: boundary-check
description: The rules that keep the guardian's side and the learner's side of Urithi apart, and the organisations apart from each other. Use before adding a module, an import, a route, a store or a file path, and when reviewing any change that touches more than one package.
---

# The boundaries

## Two rules that are never bent

**1. Nothing on the learner's side reads without the person's filter.** Every method, route or
query that serves a learner, the tutor included, takes the person's allowed access levels and
organisation, and filters on them inside the query. "Every unit of a body for the tutor" means
every unit *this person may see*: the tutor's model is part of the learner's side, and a unit
it reads can come out in its answer. There is no unfiltered "all units" read for the learner's
side. If something genuinely needs every unit, it is a guardian action, on the guardian's side.

**2. A guardian action lives on the guardian's side, whatever the code does today.** Reading
the question box, answering a question, declining one, publishing, withdrawing: under
`/api/guardian/` (`guardian/api/`), with the question box itself in `exchange/`. The guardian's
side reaches the question box only through `exchange`, **never by importing the learner's code**
(`learner/`): moving a route to the guardian's side while it still imports the learner's store
only moves the crossing. `tests/shared/test_boundaries.py` reads this from the code.

## The rest

From `docs/architecture.md`. Each rule is a test in `tests/` and a deliberate defect in
`scripts/mutate.py`.

## Packages

```
apu/        shared core, stores nothing
library/    [B] the library (Neo4j)
exchange/   the anonymous question box
guardian/   the guardian's side, built like apu
learner/    the learner's side, built like apu
```

1. `guardian` and `learner` never import each other.
2. Both may import `apu`, `library` and `exchange`. `apu` imports none of them.
3. Only `guardian` writes to `library`. `learner` only reads, through a read interface.
4. `exchange` holds a question and its status, never who asked: the learner's ticket stays on
   their device.
5. Each side writes only to its own data directory and its own prefix in object storage, and
   reads only its own settings (`GUARDIAN_*`, `LEARNER_*`) beside the shared ones.
6. Nothing a learner does becomes knowledge. A learner's question reaches a guardian only
   through `exchange`.

## Organisations

7. Every record carries its organisation; every query filters on it, including the vector
   index filter in Neo4j.
8. Storage paths start with the organisation.
9. Nothing is read across organisations, except through an explicit grant (later).

## Access

10. Access is decided before retrieval, never after generation.
11. A case is never more open than the parts it decides, nor than closed parts whose
    distinctive words it names.
12. The order of a path holds across hidden parts without naming them.

## How to check a change

- New import between packages: is it allowed by rules 1 to 3? If not, the code is on the
  wrong side, or belongs in `apu`.
- New store or file: which side owns it, which organisation prefix, which interface?
- New route: under `/api/guardian/` or `/api/learner/`; does it check the role and the
  organisation from the registry, never from the request?
- New query: does it filter on organisation and access before anything reaches a model?
- Run `uv run pytest tests -q -k "boundary or architecture"` and the mutants of these rules.
