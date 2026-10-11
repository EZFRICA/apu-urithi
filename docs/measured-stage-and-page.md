# Measured: the stage and the page driven end to end

Part of [measurements.md](measurements.md).

## The stage, measured

The deck's behaviour runs under node against a fake server (`tests/presentation`, 36
checks), and its wiring against the real one: a test reads every route `bridge.js` calls and
fails if the server does not publish it.

**Reading a spoken yes or no found its own defect on the first run.** "No, it does not" came
back as unclear, because "it does" was on the list of ways to say yes and matched inside the
no. Fifteen phrasings in three languages are now in the suite, hesitations included, and an
answer that holds both words, or neither, is asked again rather than graded.

**The braille on screen is the embosser's, character for character.** The embosser lays a
page out in Braille ASCII. The stage shows the same lines turned back into cells, and a test
turns them back into Braille ASCII and compares them with the `.brf`: identical, page breaks
included.

## The page, driven end to end

The apprentice's own page was run headless, start to finish, with one stand-in: the shared
screen is an invoicing form drawn on a canvas and typed into by a script. Vision, questions,
rules, sources, debrief, teach and exam were the real server. Three defects, none visible in
a unit test of one part, each now a test and a mutant:

- **The same question, twice, two seconds apart.** A vision call is slower than the gap
  between frames, so two observations ran at once and both found nothing pending. Deciding
  to ask is one step under a per-session lock.
- **Typing a name was a change of mind.** "Typed Brenn", then the full name, reached the
  ledger as two edits of one field, and the apprentice asked what made her change it "the
  second time". Changes to a field less than ten seconds apart are one edit.
- **Silent after the first answer.** Once a step had a reason and a stop rule existed, the
  ledger had nothing left to ask, so the next decision on screen, the cost center, went
  unasked. A decision no step explains is now a reason question.

## Urithi's own parts

The library, the learner's side, the question loop and the illustrations were measured
separately: [urithi-measured.md](urithi-measured.md).
