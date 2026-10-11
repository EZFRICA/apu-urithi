---
name: metering-and-cost
description: Quotas per person and the ceiling on model cost in Urithi: the meter that grants a budget before any costly call, the price table, the four ceilings and the step-down. Use when adding or changing any call to a model, speech, search or picture service, or when reviewing cost.
---

# Metering and cost

## The rule

**No costly call runs without a budget granted to it**, the way an answer cannot be composed
without a validated turn. The meter lives in `apu/` and every side uses it.

```python
grant = meter.grant(org, person, role, capability, estimate)   # refuses plainly, or grants
result = call(...)
meter.record(grant, actual)                                     # what it really cost
```

## What is counted

Questions to the tutor, characters read aloud, seconds transcribed, illustrations, source
checks, bytes deposited, model tokens by role.

## What the providers return

- **No provider returns a price.** The price table is ours, in configuration.
- **Gemini returns tokens** (`usage_metadata`: prompt, candidates, thoughts, total), read by
  `apu/inference/llm.py`, which hands every call's `Usage` to its listeners. **Output is
  `total - prompt`**: thinking is billed as output, and counting only the answer
  underestimates it many times over (decision 0012).
- **ElevenLabs returns a `character-cost` header**, in billed characters, not money.
- Before metering any other provider or capability, call it once for real and read what its
  response carries; write the finding in `docs/urithi-measured.md`.

## Policy is data

Per organisation, per role, per period (day, month), a warning level and a stop level; set by
the platform, narrowed by each organisation within its plan. Prices per model live in
configuration.

## Ceilings and the step-down

Ceilings per request, per person and day, per organisation and month, and for the platform.
Nearing one, in this order:

1. an answer already given for the same version of the knowledge (cache);
2. a cheaper model for the role, if measured for it (`model-role-benchmark`);
3. the guardian's own words: the faithful rail's extractive answer, which costs nothing;
4. heavy work deferred (illustrations, packages with audio);
5. a refusal that says why.

## Never

- A reply to distress is never stopped by a quota or a ceiling.
- Work served from an offline package is never counted.
- A refusal never reveals another person's or organisation's usage.

## Design for cost

Cost must follow the number of knowledge parts, not of people: render once per version of a
part and share it; cache answers per knowledge version and access level.
