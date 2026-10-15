---
name: incident-runbook
description: What Urithi does, and what an operator does, when a dependency fails: a model, speech, search, Neo4j, object storage, the signing key or the meter. Use when something is down or degraded, or when designing how a new dependency fails.
---

# When something fails

The rule everywhere: **fail closed and say so**. An honest "unavailable" is better than a
guess, and the offline package keeps learners going.

| Fails | Urithi does | The operator |
|---|---|---|
| The guard's model | answers nothing (`GuardUnavailable`), says so | check the key and the provider status |
| The answer's model | shows the guardian's own words (extractive) | the same |
| The pupil's model (a class) | says in one sentence what it knows: what it saw, the rule noted or that none is, its question | the same |
| The command classifier | falls back to fixed patterns: "save this" still saves; the other commands only when said plainly | the same |
| Speech out | the second voice takes over (measured on 2026-10-15, the first key refused); else shows the text | check the speech key or provider |
| Speech in | asks to type instead | the same |
| Public search | says refused or failed, tries the next service; rules stay unchecked, never "house rule" | allow-list, zone names, quotas of the search service |
| Neo4j | learners continue from kept packages; publishing waits | instance paused or down; credentials |
| Object storage | saving waits; drafts stay local | bucket, credentials |
| The signing key | packages are not built; kept ones still verify | provide the key from the secret manager, never a new one |
| The meter | costly calls are refused, distress replies still go | the counter store |

## After an incident

What happened, from when to when, who was affected, what was seen, what is changed so it does
not happen again, written with numbers and kept beside the measured documents.
