# Architecture: organisations, quotas, cost, and Neo4j

Part of [architecture.md](architecture.md).

## Organisations, quotas and cost

**The organisation is the top level.** It owns its guardians, learners, knowledge, and policy.
A person may belong to several organisations, with a role in each. Every record carries its
organisation and every query filters on it (in Neo4j's vector index, storage prefixes, the
question box, and signed packages). Tests and deliberate defects enforce every boundary.

**Quotas per person and a ceiling on model cost.** Counted by one meter in `apu/`: questions,
characters read aloud, seconds transcribed, illustrations, source checks, bytes deposited, and
model cost against ceilings per request, person/day, organisation/month, and platform. Nearing
a ceiling, the service steps down (cached answer, cheaper model, the guardian's own words,
deferred work, then refusal). Distress replies and offline packages are never stopped by a
quota. **Cost follows the knowledge, not the number of people**: renderings and answers are
cached once per version of a part.

## Everywhere

**A teleprompter** shows streamed transcription when the person turns the microphone on, and
lights each word in time with Urithi's voice. **The showcase at /** links to both sides.

## [B] in Neo4j

```
(:Body {name, guardian, version, language})<-[:BELONGS_TO]-(:Unit)
(:Unit {kind, text, quote, at, said_at, language, access, version, status, embedding})
(:Unit)-[:PREREQUISITE_OF | LIMITS | MEETS]->(:Unit)
(:Case {question, said, by, applies, access})-[:DECIDES]->(:Unit)
(:Source {url, domain, says, jurisdiction})-[:SUPPORTS | DISAGREES]->(:Unit)
```

- **Access is a filter inside the vector index** (Cypher 25 `SEARCH ... WHERE`), so a part a
  learner may not see is never returned and never reaches a model. A case is never more open
  than the parts it decides, nor than the closed parts whose words it names.
- **One embedding model everywhere**, local ONNX, multilingual: online search and an offline
  package share one vector space.
- **The order holds across hidden parts**: a learner who may not see a step still gets the
  ones after it in the right order, without its name.
- **Deposited files are not in the graph**: object storage holds them, the graph a pointer.
- **Credentials** in `.env` only. A free Aura instance pauses after three days without
  activity; packages double as a backup.
