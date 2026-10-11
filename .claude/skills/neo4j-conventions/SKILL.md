---
name: neo4j-conventions
description: How Urithi uses Neo4j for the library [B]: the graph model, filtered vector search, transactions, nulls, organisations and live contract tests. Use when writing or reviewing any Cypher, changing the library's model, or debugging a search.
---

# Neo4j in Urithi

## The model

```
(:Body {organisation, body_id, name, guardian, version, language})<-[:BELONGS_TO]-(:Unit)
(:Unit {organisation, unit_id, kind, text, quote, at, said_at, language, access, status, embedding})
(:Unit)-[:PREREQUISITE_OF | LIMITS | MEETS]->(:Unit)
(:Case {question, said, by, applies, access})-[:DECIDES]->(:Unit)
(:Source {url, domain, says, jurisdiction})-[:SUPPORTS | DISAGREES]->(:Unit)
```

## Rules

- **Access and organisation filter inside the vector search**, never after it (Cypher 25):
  `SEARCH u IN (VECTOR INDEX unit_embedding FOR $q WHERE u.organisation = $org AND u.status = $published AND u.access IN $allowed LIMIT $k)`.
  Every filtered property is declared on the index (`WITH [u.organisation, u.access, ...]`).
- **Parameters always**, never a value formatted into Cypher.
- **Managed transactions** (`execute_read`, `execute_write`), so a dropped connection is
  retried. A new version replaces the old one in one write transaction.
- **Neo4j stores no null.** Read optional properties with `.get`; a test covers a case with
  no yes or no.
- **One embedding model everywhere** (local ONNX, 384 dimensions); the index dimension
  follows it.
- **Links a learner sees** are computed from every link of the body, bridged across hidden
  parts, and name only visible parts.
- **Credentials** from `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`; never printed.

## Tests

The memory store and Neo4j pass the same contract tests. Run them live with
`URITHI_LIVE_NEO4J=1 uv run pytest tests -k neo4j`; each test creates bodies under a
random prefix and withdraws them at the end.
