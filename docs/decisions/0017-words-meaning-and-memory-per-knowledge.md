# 0017: Words beside meaning, a memory per knowledge, readable by its person

Decided: 2026-10-16, by the owner, after reading TencentDB Agent Memory: take its three general
ideas, measure everything. Refines 0015 (the APU memory).

## Context
The library ranked parts by meaning alone, and a measured defect ("a or an before useful?", the
silent H ranked first) had been met by a tie-break on shared words. A learner's memory was one
list for every knowledge: opening another changed a label, not the contents, and a memory written
on one knowledge reached the answer on another (2 lines in 2), once making a covered question go
unanswered 10 times in 10. Nothing in the memory said where a block came from, and the learner
could not see it.

## Decision
- **Search** ranks the parts of one knowledge by meaning and, when the question is asked in the
  knowledge's language, by its words (BM25), fused by reciprocal rank (k = 60). The score an
  answer is held to stays the meaning's. Across languages, and across all of an organisation's
  knowledge, the meaning ranks alone. The same code ranks the words in both stores.
- **Memory** blocks about what is in progress or under study (temporary, project, knowledge)
  carry the knowledge they were written on; the context for an answer is that knowledge's blocks
  and the person's own. A block whose knowledge is unknown is not assumed to be this one's.
- **Every block keeps its source** (what it was written from, and when); the learner reads what
  is remembered about them and removes any of it, from every tier.

## Consequences
- Measured, before and after: first right part 30 then 32 in 38; French unchanged; median search
  on Aura unchanged once words are read in the same query (docs/measured-search.md).
- A fixed block holds one knowledge at a time: memory kept per knowledge in those slots is the
  next step, not taken until it is measured as needed.
- Tests: a closed part never comes back by its words; another language leaves the order as the
  meaning's; one knowledge's memory never reaches another's answer; a removed block is gone from
  L3.

## Alternatives set aside
- Neo4j's full-text index: measured, it scored the text and the quote apart and lost the gain.
- Keywords in every language at half weight: still lost French questions (9 in 12 against 10).
- A shared team memory: it would cross the two sides and the organisations kept apart.
