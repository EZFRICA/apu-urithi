---
name: load-test
description: How Urithi is load tested toward 10 million people: scenarios, the measures that matter, and acceptance levels. Use before a production resource is chosen, after a change to a hot path (search, answer, package, sync), or when asked whether it scales.
---

# Load testing

The question is never "does it hold" but "what does one more person cost, and where does it
stop". Measure, write the numbers, decide from them.

## Scenarios

1. **Learners reading**: open the contents, a part, its audio and braille (cached per version).
2. **Learners asking**: the guard, the search, the faithful answer, with the cache warm and
   cold.
3. **Packages**: build, refresh after a new version, sync of offline reviews.
4. **Guardians**: a teaching session, the debrief, a publication.
5. **A peak**: one popular knowledge, many learners at once, right after it is published.

## Measures

Latency (median and 99th percentile), errors, cost per person and per scenario (from the
meter), model calls per scenario, cache hit rate, database and Neo4j query times.

## Rules

- Models are faked with recorded latencies for load; real model calls are measured apart, in
  small numbers, for cost.
- Run against the production implementations of the stores, never against SQLite to draw
  production conclusions.
- Use a dedicated organisation and remove its data afterwards.
- The tool (k6 or Locust) is added through `uv` or kept outside the repository.

## Report

A table per scenario, the bottleneck found, the change it calls for, and whether that change
is a resource (a deployment choice) or a design change (an architecture decision, see `adr`).
