# Working on Urithi: work ahead, open points, and handover

Part of [AGENTS.md](../AGENTS.md).

## What to read before the next work

- `docs/plan.md`, section **Next: the guardian's expert pupil**, is the work ahead:
  - **P1, the guardian's commands**, understood by intent with the fast model rather than by
    keywords ("remember this", "this is an example", "a common mistake", "compare with
    before", "forget that"), and a part of the screen pointed at.
  - **P2, the expert pupil**: what a learner would miss, judged by importance; asked only
    when important, at a pause; passable; a silent mode that keeps questions for the
    debrief; the guardian's threshold learned from what they pass.
  - **P3, the camera's own rules**: gestures, objects, a whiteboard, pauses read from a
    camera that always moves, other people's faces blurred.
- `docs/decisions/0013` and `0014`: the switches belong to the person; anyone teaches; the
  learner's side stays a tutor that answers when asked and takes no initiative; no learners
  live in the class for now.
- `docs/architecture.md` for the design, `docs/measured-steps.md` and `docs/measured-class.md`
  for what was measured and why each rule exists. Many comments in the code begin with
  "Measured:": they say which real failure a line prevents. Keep them true.

## Known open points

- **Two fixes are designed and not applied** (the owner has not decided yet): a question
  waiting is dropped on the page when the guardian says "remember this" while the server
  still holds it, and the class stops asking; and "keep this" heard anywhere in a sentence is
  too wide ("we keep this channel public" counts as a request). Ask before applying either.
- With the smallest question model, a question sometimes names an option the screen never
  showed; it is told not to.
- The test process has once ended with a native `recursive_mutex lock failed` at exit; a
  second run passed. Note it if you see it again.
- `test_a_debrief_question_is_put_to_the_learner_about_what_the_guardian_said` failed once in
  three runs (the same case asked three times); unexplained so far.
- Whether a filmed class is itself published, or only the knowledge taken from it, is open
  (video sources, docs/decisions/0009).

## Handing your work over for review

When you stop, check that the journal has an entry for every action, then write a short report
(in French, for the owner) that says:

1. Every file you created, changed or deleted.
2. What you ran, with the numbers: tests passed, ruff, which mutants you added and whether
   each is caught.
3. **The live run of each change**: what you did on which page, with which real services and
   inputs, and what was measured; and any change not run live, named as such.
4. What you did not run or could not check, plainly.
5. Any data you created with real services, and whether it was removed.
6. That nothing is committed.
