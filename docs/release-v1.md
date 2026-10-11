# Urithi v1: release notes

Prepared 2026-10-10. Nothing is committed, tagged or deployed until the owner says so.

## For a guardian

- Teach by conversation, typed or spoken, in English or French. Urithi notes anything it hears
  and sees, but only the guardian saves knowledge (docs/decisions/0016): Urithi proposes a step
  or a rule in the guardian's words, and "save this", a named proposal ("save the rule") or the
  Save button keeps exactly one; with several waiting and none named, it asks which.
- A question put to Urithi ("did you see my screen?", "what rule?") is answered in one short
  sentence from what it saw and noted, never invented, never twice the same.
- A classroom on a shared screen or on a camera, under three switches only the guardian holds:
  the microphone, hands free listening after a question, and vision. Nothing listens or
  captures on its own (docs/decisions/0013).
- Commands in class: remember this (with a region pointed at), this is an example, a common
  mistake, compare with before, forget that (the latest proposal or note), save.
- The expert pupil: at a pause after a change, it judges what a learner would miss from what
  was seen, read on screen and said, asks one question or none, learns from questions passed,
  keeps questions for the debrief in silent mode.
- On camera: a whiteboard read, other faces blurred, a value read in another script or a camera
  number kept until the guardian confirms it.
- Documents (PDF, audio, images) cited by page or timing; public sources checked; a debrief;
  validating once the teach-back has been heard since the last change, then publishing (with at
  least one rule saved) with an access level per part; cited documents archived in the
  organisation's bucket, removed with the knowledge.
- A memory that lasts (the APU memory: a cache, a list of typed blocks, a vector store, the
  most relevant block brought forward on each search), written after the reply.

## For a learner

- A path through the knowledge, listening with a teleprompter, braille, illustrations.
- A tutor on demand that answers only from the parts the learner may see, with citations; a
  question it cannot answer goes to the guardian without the learner's name.
- An exam, a signed package that works offline and is refused if changed, and progress resumed
  on a second device.
- A memory of the learner's own questions, used to word answers, never shared with another
  learner and never put in the shared answer cache.

## For an operator

- One server on port 8790 (`scripts/serve.sh`), the library in Neo4j, the rest on local disk
  and SQLite behind one interface each.
- Every model call is granted by the meter before it is made and costed per role from the
  `URITHI_PRICE_*` prices in `.env` (see `.env.example`). The meter's usage rows are never
  deleted.
- The deliberate defects run in parallel copies of the repository and check the clean suite in
  each copy first.

## Measured, live, on 2026-10-09 and 2026-10-10

| What | Result |
|---|---|
| Tests, offline | 542 passed, 7 skipped; ruff clean |
| Deliberate defects | 285 of 285 caught, in parallel copies |
| Live Neo4j contract | 8 passed |
| A guardian's conversation turn | 498 to 781 ms warm, 2.3 to 2.7 s cold |
| A question put to Urithi, in the page | median 2.6 s; 8 of 10 under 3 s |
| The owner's 12 class sentences, no save | 0 steps, 0 rules, 0 proposals; every one answered |
| A rule with a prohibition, 5 runs | kept whole 5 times out of 5 |
| First question in a screen class | 14.7 s; a question passed teaches the threshold |
| Whiteboard read on camera | 12.8 s, values right |
| A learner's answer | 1.6 to 2.7 s; from the cache 0.6 to 0.9 s |
| Speech out, speech in | 763 ms, 797 ms, read back word for word |
| Two cited documents archived on validation | 3.5 s; removed on Delete |
| A closed part asked by a visitor | nothing told, 0 citations |

The details are in the measured documents linked from [measurements.md](measurements.md) and
[urithi-measured.md](urithi-measured.md).

## Known not to work yet

- The question, answer and class vision models have no price of their own: they are costed at
  the main and vision prices, so the meter overstates their cost. Main and vision prices rise on
  2027-01-01 and must be updated in `.env` then.
- When speech fails over to the second provider, nobody is told; five such refusals were seen.
- The camera's change threshold ignores changes the size of a screen: a screen is taught by
  sharing it.
- The shared answer cache is filled only by learners whose memory is empty.
- The memory's lock holds within one server process; several processes need a shared lock.
- Identity is simulated; there is no real sign in.
- Deployment, video sources, learners joining a class live and a meeting add-on come later
  ([plan.md](plan.md)).
