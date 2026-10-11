# 0002: Knowledge moves through three states

Decided: 2026-10-05, by the owner.

## Context
The guardian must always validate before anything is kept, and choose later who may learn it.

## Decision
Draft (the working memory), saved (validated, the guardian's only), published (with access levels). Validating needs the teach-back confirmed. Anything taught after validation returns that part to draft.

## Consequences
Saving and publishing are separate actions in the guardian's page and API.

## Alternatives set aside
- Saving as publishing: the guardian could not keep validated work private.
