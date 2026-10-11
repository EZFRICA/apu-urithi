---
name: real-condition-test
description: The end-to-end test of Urithi in real conditions, as a guardian and as learners, with the real models, Neo4j, speech and search, driven in the browser. Use after a step of the plan, before calling a feature done, or when asked to test everything for real.
---

# A real-condition test

The reference run is the "a" or "an" knowledge taught by Ezekias (see
`docs/urithi-measured.md` and `docs/measured-a-and-an.md`). It found nineteen defects no unit test could. Repeat it, adapted
to what changed, and write down what it finds.

## Before

- `scripts/serve.sh` (port 8790). Check configuration by variable names only.
- Know what is published already; name any test data you create, and remove it afterwards
  unless the owner wants it kept. Never delete the meter's usage rows
  (`exchange/data/counters.sqlite3`), even after a live test: those calls were really paid
  for, and the meter is the only trace of the spend.

## As the guardian (`/teach/`)

1. Start a knowledge, in English and once in French. Teach by typing, and one sentence by
   voice (synthesise it, then send it as a recording, so transcription is real).
2. Read the map: invented rules, duplicates, titles cut inside a word.
3. Deposit a source (audio, PDF, image) and build a part from it, once step 3 exists.
4. Check against public sources: which service answered, refusals said as refusals, no
   conflict from a social network or a cut snippet.
5. The debrief: answer one case wrongly on purpose, then take it back from the teach-back.
   Remove a rule that was not given.
6. Validate, choose access levels (close one part), publish. Check what was raised.

## As learners (`/learn/`), a visitor and a member

7. The contents, the order, what each may see. Read, listen, braille, practise (once by
   voice), see, rate.
8. Ask: covered, in French, off topic, distress, uncovered (it reaches the inbox), about a
   closed part (no leak to the visitor, an answer for the member).
9. The exam: no case from a closed part for the visitor, no "which one" question.
10. Keep offline, stop the server by its port, learn offline, restart, sync. Save the file,
    import it, import it changed.

## Back to the guardian

11. The inbox: answer one question, decline one; publish; the learner's page says so.
12. Withdraw; the device drops its copy at its next connection. Republish: the levels hold.

## After

- Remove the test data created (maps, published knowledge, questions, sessions, cached
  answers, memories), but never delete the meter's usage rows
  (`exchange/data/counters.sqlite3`): those calls were really paid for, and the meter is the
  only trace of the spend.
- One paragraph per defect in `docs/urithi-measured.md`, with the numbers.
- Every fix through the `add-a-guarantee` skill.
- Report to the owner in French: what was found, fixed, measured, what remains, what data was
  left in place.
