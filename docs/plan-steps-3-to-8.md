# Urithi: completed steps (3 to 8)

Continued from [plan-done.md](plan-done.md); part of [plan.md](plan.md).

## Step 3: sources (done)

- Deposit audio, PDF and images from the guardian's page; stored in Cloud Storage under the
  guardian's prefix; never in the graph.
- Audio transcribed with timings, PDF cut by page, images described; all kept as evidence [A].
- "Make a step of this passage", by voice or text: Urithi proposes, citing page or timing; the
  working memory keeps what matters; nothing is knowledge before validation.
- A part's sources, at its access level, become evidence a learner can open.
- **Measured**: a real PDF and a real recording turned into validated parts, every quote
  traced back to its page or timing.

## Step 4: the classroom mode (done)

- A full-screen mode of the guardian's page: screen or camera, teleprompter, a board of what
  is captured, Urithi's questions at the pauses (the measured pause detection of today).
- What is captured goes to the working memory, to be validated.
- The separate screen-watching page goes; the stage stays, beside the showcase.
- **Measured**: a real session on a shared screen, questions at the pauses, nothing published
  without validation.

## Step 5: the learner's tutor, on a path (done)

- **The contents in view**, top to bottom, each part's state; the part in view in the middle;
  the tutor beside it; the teleprompter below.
- **The tutor**, from the school tutor: text, voice or braille, "a screen is available", the
  conversation anchored to the part in view, faithful answers only.
- **Prerequisites reminded** when a part is opened, when an answer rests on an unlearned part,
  and at the exam.
- **The notebook**: keep an answer whole, as key points or as an excerpt; a revision sheet on
  screen or in braille.
- **The learner's working memory**: the session, what they asked, what they found hard.
- **Progress** on the device, with a server copy kept apart; changing devices restores it.
- Everything offline still works from the signed package.
- **Measured**: a learner who never saw the first part asks about the last, and is reminded;
  the same learner continues on a second device.

## Step 6: the showcase (done)

- `/` becomes a static page: the features and the components, the four memories, the
  boundary between the two sides, offline, braille, the guard; links to both sides and the
  stage.

## Step 7: the APU memory on both sides (docs/decisions/0015, done)

- **The MMU in `apu/mmu/`**, shared and storing nothing: typed blocks; L1, a cache with a
  lifetime per type; L2, the DLL (insertion by type, a cap, the least recently used paged out
  to L3); L3, a vector store behind an interface, LanceDB first; BMJ, one block promoted to the
  head on each search; page-in of a block found in L3; a memory write-back after each turn.
- **The guardian's side:** the class (what is on screen, the question waiting), the knowledge
  being taught (what was said, seen, kept, the questions kept for the debrief), the guardian
  (the threshold learned from what they pass, their preferences), kept across knowledges.
- **The learner's side:** the session, the knowledge in view, the learner (preferences, what
  they found hard); the tutor's answers read memory through the MMU.
- Per organisation and per person; neither side reads the other's memory; the library stays
  in Neo4j and is never written by the learner's side.
- **Measured:** a block paged out to L3 (`cap=3`, `4` dynamic blocks) and paged back in
  (`similarity=0.8199`); a block promoted by BMJ; a guardian's threshold (`4`) kept from one
  knowledge to the next; read latencies `L1 0.0029 ms`, `L2 0.0329 ms`, `L3 44.3490 ms`
  ([measured-class.md](measured-class.md)).

## Step 8: the guardian's expert pupil (docs/decisions/0013, 0014, done)

Anyone who has knowledge to share teaches. The guardian holds the switches: microphone,
listening after a question, vision. The learner's side stays a tutor that answers when asked.

- **P1, the guardian's commands (done):** understood by intent with the fast model rather than
  by keywords ("remember this", "this is an example", "a common mistake", "compare with before",
  "forget that"), pre-filtered by command cue in `< 0.1 ms` for ordinary speech; a part of the
  screen pointed at (`#class-video`, `#class-point`).
- **P2, the expert pupil (done):** what is missing for a learner judged by importance (`1..5`)
  in a single structured JSON call at a pause (`kind`, `importance`, `why`, `question`), checked
  against seen and said words; asked only when `importance >= threshold`; passable; silent mode
  keeping questions across classes (`deferred-{n}`) for the debrief; the guardian's threshold
  learned from what they pass and kept in the guardian's MMU across knowledges.
- **P3, the camera's own rules (done):** gestures, objects, a whiteboard, camera pixel-change
  threshold (`350` pixels above `32`, reducing sensor-noise vision calls by `96.4%`), pauses
  read from a camera that always moves, faces of others blurred on every kept or compared frame,
  and unconfirmed camera numbers or foreign-script tokens withheld until confirmed.
- **Measured** for each, in a real class on screen and camera: what was asked, what was passed,
  and how long each step took ([measured-class.md](measured-class.md)).
