# Measured: step 0 separation and the redesign

Part of [urithi-measured.md](urithi-measured.md).

## The separation, step 0, run for real

The code now lives in five packages (`apu`, `library`, `exchange`, `guardian`, `learner`),
each side under its own address and in its own data directory; the boundary is read from the
code by `tests/shared/test_boundaries.py`, every rule with a deliberate defect. The data moved
with it: 22 maps, 8 review cards, 3 questions, 38 renderings and the signing key, counted
before and after. Then the a/an knowledge was taught again in the browser through the new
routes: a ninth rule, a near miss on "European vacation", the teach-back, version 3 published;
a learner asking "a or an before useful?" got an answer citing the rule taught minutes before.

That run found four defects, now fixed:

- **A near miss cut in half.** The model spent 1,919 of 2,000 tokens thinking and the case
  came back cut after 300 characters, three times in three for the abbreviation rule; once
  the response even said it had stopped normally. A cut answer now fails as a failure, never
  passes for an answer, and a near miss is asked with little thinking: 19 cases in 19 across
  the nine rules, five in five on the one that failed.
- **A lead-in taken for a step.** "One more thing. When a word starts with a u..." became a
  step called "One more thing"; a short sentence before a much longer one is now skipped.
- **The name read back in lower case**: "choosing a or an in english". Only its first letter
  is lowered now.
- **"Open a lesson file"**, and ten more strings in two languages. What is handed on is
  knowledge; a test reads every file of the product for the word. Switching language also
  left "Taught by Ezekias" in English on a French page; what the server sent is rebuilt.

### The review of step 0, closed

Three crossings the architecture review found, each now a test and a deliberate defect. The
learner's side held the whole library store and the whole question box: it now holds a reader
of three reads and a box it can only ask and follow a ticket in, and a test lists, file by
file, the only modules of the library and the box it may import. The guardian's routes asked
nobody who was there: on the running server, a visitor, no one, and Sabine are now refused
Ezekias's draft (403), Ezekias reads it, and each guardian lists only their own maps (19 and
2). Who teaches is who asks; a name sent to start a map is no longer trusted.

## The redesign, first pass

One look for every page (`apu/ui/shared/urithi.css`): warm paper or warm ink, as the system
says or as the person chooses, gold for the guardian, teal for the learner, the guardian's own
words always in a serif. The guardian's page had drawn its look from the learner's stylesheet;
both now draw from the shared one, and a test refuses the crossing. `/` is a static showcase;
watch me work moved to `/watch/`. On both sides the knowledge is a tree (`apu/ui/shared/tree.js`):
steps, the rules under each, the cases decided under each rule, opened and closed from the
keyboard; on the learner's side every part says where the learner stands, in a mark and a
word, and a prerequisite not yet learned is reminded with a way to go there first, never
enforced. Measured in the browser: the a/an tree opened, moved and chose by keys alone; no
horizontal scroll at 390 px; the teleprompter stayed on for the 13.5 seconds the part was read
aloud, then went. What it does not do yet: it shows a sentence once it is transcribed, not word
by word as it is said; streamed transcription is step 1 of the plan.
