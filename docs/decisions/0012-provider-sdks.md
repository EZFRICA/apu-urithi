# 0012: Models are called through their provider's own SDK

Decided: 2026-10-05, by the owner.

## Context
The two text roles called Gemini through its OpenAI-compatible endpoint. Measured on a real
call: neither path returns a price, and that endpoint hides the thinking tokens it bills,
reporting 2 completion tokens for a call whose total was 121. A meter reading it would count
a fraction of the cost.

## Decision
`apu/inference/llm.py` calls Gemini through `google-genai`, keeping the callers' chat shape
(messages, `temperature`, `max_tokens`, JSON mode). Every call hands its usage (prompt,
output with thinking, total) to listeners; the meter subscribes there. The OpenAI SDK is
removed.

## Consequences
Cost is counted from what is billed: measured, wording one question spent 623 thinking tokens
for a 17-token answer. Another provider is added with its own SDK behind the same two
functions.

## Alternatives set aside
- Keep the compatible endpoint and estimate thinking: a guess where the SDK gives the number.
