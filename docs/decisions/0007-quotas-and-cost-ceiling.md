# 0007: Quotas per person and a ceiling on model cost

Decided: 2026-10-05, by the owner.

## Context
Every paid call multiplied by millions of people is the cost that decides whether the service lives.

## Decision
One meter in `apu/` grants a budget before any costly call and records what it cost. Quotas per organisation, role and period; ceilings per request, person, organisation and platform, set by the platform and narrowed by each organisation. Nearing a ceiling the service steps down: cached answer, cheaper model, the guardian's own words, deferred work, then refusal. Distress and offline work are never stopped or counted.

## Consequences
Cost follows knowledge, not people: renderings and answers are shared per knowledge version.

## Alternatives set aside
- A hard stop at the ceiling: learners lose answers that cost nothing to give.
