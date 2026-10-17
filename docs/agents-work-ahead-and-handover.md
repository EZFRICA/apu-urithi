# Working on Urithi: work ahead, open points, and handover

Part of [AGENTS.md](../AGENTS.md).

## What to read before the next work

- `docs/plan.md`: the steps are done (0 to 8, then the expert pupil P1 to P3); what is left is
  its list **Later, each a project of its own**. Ask the owner which comes next.
- `docs/decisions/0013` to `0018`: the switches belong to the person; anyone teaches; the
  APU memory; Urithi notes anything and only the guardian saves knowledge, by their own words;
  words beside meaning in search, a memory per knowledge, readable by its person; the stage
  learns what was published, as /learn/ does.
- `docs/architecture.md` for the design; `docs/measured-class.md`,
  `docs/measured-saving-and-forgetting.md`, `docs/measured-maps-pupil-and-learner.md` and
  `docs/measured-search.md` for
  what was measured last and why each rule exists. Many comments in the code begin with
  "Measured:" or "Found in the review of": they say which real failure a line prevents. Keep
  them true.

## Known open points

- A covered question can still reach the guardian as "nothing yet" when the model finds no
  answer twice in a row; measured after the fix, 0 in 18. The server logs which way each
  question went, never its words.
- The pupil's answers come from the model: measured 24 in 24 right, one of them calling a
  waiting proposal "saved".
- Any other implementation of the map store must keep its version: a save from an older copy is
  refused (`MapChanged`), never written over (`.claude/skills/store-interfaces`).
- With the smallest question model, a question sometimes names an option the screen never
  showed; it is told not to.
- The test process has once ended with a native `recursive_mutex lock failed` at exit; a
  second run passed. Note it if you see it again.
- `test_a_debrief_question_is_put_to_the_learner_about_what_the_guardian_said` failed once in
  three runs (the same case asked three times); unexplained so far.
- Whether a filmed class is itself published, or only the knowledge taken from it, is open
  (video sources, docs/decisions/0009).
- The teach-back reads a rule as "When {when}, you {then}": a rule taken from a sentence with no
  condition reads badly ("When an invoice is coded, you before coding an invoice..."). Two general
  ways are open, the owner's choice: a neutral template, or the guardian's own words.
- A fixed memory block (the current session) holds one knowledge at a time; keeping it per
  knowledge waits until it is measured as needed (docs/decisions/0017).
- Words count in search within one knowledge only; a search across all of an organisation's is
  by meaning alone, not measured yet (`scripts/measure_search.py`).
- Closed questions of deleted test knowledges stay in `exchange/data/questions.sqlite3`; no route
  removes one, and deleting rows by hand needs the owner's word.

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
