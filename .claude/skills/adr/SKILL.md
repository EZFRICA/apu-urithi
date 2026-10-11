---
name: adr
description: How an architecture decision of Urithi is recorded, so the reason survives the conversation it was taken in. Use when the owner decides something about the design (a boundary, a state, a store, organisations, cost), or when a measurement forces a design change.
---

# Recording a decision

Decisions taken in conversation are lost with it. Each one gets a short record in
`docs/decisions/`, numbered: `0001-two-sides-apart.md`.

## The record

```markdown
# 0001: The guardian's side and the learner's side are kept apart

Decided: YYYY-MM-DD, by the owner.

## Context
What was true, and what forced a choice. Measurements if any.

## Decision
One paragraph, in the present tense.

## Consequences
What becomes easier, what becomes harder, what is now a test.

## Alternatives set aside
Each in one sentence, with why.
```

## Rules

- In English, in the repository's style, under 100 lines (most fit in thirty).
- A record is never edited to change the decision: a new one replaces it and says which.
- `docs/architecture.md` describes the current design; the records explain how it got there.
- Decisions already taken, to record first: the two sides and their packages; the three
  states; prerequisites reminded not enforced; storage local while drafting and uploaded at
  saving; resources behind interfaces; organisations; quotas and the cost ceiling;
  deployment deferred; video deferred.
