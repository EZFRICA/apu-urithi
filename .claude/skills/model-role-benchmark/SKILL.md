---
name: model-role-benchmark
description: How a model is measured in one role of Urithi before it becomes that role's default, online or local. Use when changing a model in configuration, adding a provider, trying a local model, or when a role's quality or cost is in question.
---

# Measuring a model in its role

A model is never the default for a role because it is good in general. It is the default
because it was measured in that exact role, against the others, here.

## The roles

| Role | What is measured |
|---|---|
| Wording the apprentice's questions | one spoken question, about the gap, not truncated |
| Rule extraction | rules stated and only those, no duplicates, `then` readable after "you" or "tu" |
| Reading a yes or a no | agreement with the guardian's intent on a fixed set of answers |
| The input guard | on topic, off topic, distress, injection: every case, several runs |
| The faithful answer | cites every sentence, quotes verbatim, says NO_ANSWER when it should |
| The source judge | relevant or not, agrees or not, against hand-labelled pages |
| Vision | what changed between two frames |
| Speech in and out | words right, latency, length of audio against text |
| Illustration | no writing, no count the rule turns on |

## How

1. A fixed set of inputs per role, with the expected outcome decided by a person, kept in
   the repository (no personal data).
2. Each candidate run on the whole set, at least three times; record outcome, latency and
   cost per call.
3. Compare with the current default. A candidate replaces it only if it is not worse on the
   guarantee the role exists for, whatever it gains elsewhere.
4. Change the role's setting in `apu/config.py` (or the side's config), never the code.
5. Write the table and the decision in the measured document of the area.

Local models (llama.cpp, Ollama, Whisper, Piper) go through the same set before they can be
chosen, even for offline use.
