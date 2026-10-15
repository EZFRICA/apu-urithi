# Measured: the map written once, the pupil's answers, the learner's (2026-10-15)

Part of [urithi-measured.md](urithi-measured.md). Follows
[measured-saving-and-forgetting.md](measured-saving-and-forgetting.md). Tests in
`tests/guardian/test_saving_and_forgetting.py` and `tests/learner/test_learning.py`, each with its
deliberate defect in `scripts/mutate.py`.

## The map, written by one at a time

A map was written back whole, so the later of two writers undid the other. Now every route that
loads and saves a map holds that map's lock (`guardian/memory/store.py`, `map_lock`), and the store
keeps a version: a save from an older copy is refused (`MapChanged`), said as a 409, never written
over. An import replaces a map whole, deliberately. Tested: two saves at once both land; a save
made elsewhere meanwhile is said, and kept.

## Migration of this machine's maps

`scripts/migrate_step_rules.py` takes off the rules a step was given by mistake (before
2026-10-14, a step saved with no rule got every rule then known), in the map and in its validated
version, never deleting a rule. Which ones: a rule an earlier step already held, not said with this
step. Run on this machine: 1 map in 6 changed, Ezekias's "Leading a tech community: the organiser's
first week": step 2 lost the pizza rule (saved at 275 s of the shoot, when only that rule existed),
kept the two rules saved alone after it (277 s and 279 s); its 4 steps stayed validated; a second
run changed nothing. A first rule (unlink what was said before the step) would have taken one of
those two as well: the shoot's timeline showed it, and the rule was changed before applying.
The copy taken first is in `guardian/data/`. The knowledge was not published; nothing to republish.

## The teach-back says a step once

"Step 3: Common mistake: accepting..., because a common mistake is accepting..." read the same
words twice. A title whose words are nearly all in the reason is now said once, in the guardian's
words. Live: "Step 2: A common mistake is announcing in #general, where the post is lost within an
hour."

## The pupil's answers, from the facts

The answers were chosen by lists of words met live ("room", "role", "whole", "give me"), and a fluent
answer from the model was refused when it lacked listed words; the prompt itself carried those cases.
Live, with two rules saved, "I said rule, not room." was answered "I have not cited or noted any rule
yet". Now the model answers from the facts, by general rules (the facts decide; a misheard word is read
for its likely meaning; what the facts hold as none is said plainly); with no model, Urithi says what it
knows, the same for any question; knowing nothing, it says so plainly. Measured through the server, as
Sabine: 24 answers in 24 right (with two rules, the 12 name a saved rule, "What role are you talking
about?" included; with none, the 12 say no rule is noted and name the proposal). One in 24 called a
waiting proposal "saved". In class: 3 questions in 3 answered from the rules and the screen.

## The learner's answer, read again before the guardian is asked

A covered question was sometimes sent to the guardian as "nothing yet". Logged now (never the
question's words): the model had found no answer in passages scoring up to 0.903. Measured: after an
uncovered question, an answerable one was passed on 2 times in 6; at temperature 0, a covered one 1
in 6. Now worded at temperature 0, told that the learner's memory never decides, and read again once
before being passed on. After: 18 answerable questions in 18 answered (15 worded, 3 in the guardian's
words), the uncovered one passed on 6 times in 6.

## Live, all of it

- Suite: 586 passed, 7 skipped; ruff clean; deliberate defects 333 in 333 (330 in the full run, two
  retargeted lines and one timed out under the load of the live runs, each caught alone).

- Learner side, a knowledge published by Sabine with one part for members: 28 checks in 28 (path and
  parts by level, listen, braille, covered, French, off topic, distress stored nowhere, uncovered to
  the inbox and declined, no leak to the visitor, the member answered, signed package, withdraw).
- Class as Sabine, the screen changing every 3 s: 19 checks in 19, 323 frames, 0 server errors.
- The meter held: Ezekias reached his daily ceiling (0.9997 of 1.00) during the runs, and Urithi went
  on without a model, plainly; the rest ran as Sabine. Speech: the narration key answered 401, the
  second voice provider took over, every part was heard.

## Every component, live, the same morning

A run of every component as Sabine, with a visitor and a member: the four pages; teaching typed,
by voice (synthesised, then heard) and in French; a recording and an image deposited, each a step
citing it; public sources; a rule removed; the debrief, a case taken back; the teach-back,
validation, publication with a part for members; reading, listening, braille, illustration,
practice, the exam, seven kinds of question, the notebook, a review, offline sync, a signed package
(a changed one refused); the inbox answered by teaching and publishing again, then declined;
Ezekias's published knowledge read; withdrawal. The first run passed 52 checks in 57 and found:
- **A recording could not be deposited** when the first speech key was refused (401), though speech
  in a class fell back. Now heard by the second transcriber, cited as the whole recording, its
  moments not invented.
- **A rule removed came back as a proposal,** so "save this" asked which one and the step said just
  before was not saved. A rule removed is now set aside like one forgotten.
- **The showcase and the teach page asked for `/favicon.ico`** and logged a 404: they declare their
  icon now, as the other pages do.

Two other failures were the test's own reading of a reply. After the fixes: 58 checks in 58, 0
server errors; the class again, 19 in 19 (87 frames). Suite 589 passed, 7 skipped; deliberate
defects 337 in 337, in one full run.

## Every component again, after the merge commits (afternoon)

The same run found 56 in 58. Both failures were the learner's answer with the faster answer model:
- **A covered question went to the guardian.** The learner's memory named their previous question,
  on another knowledge; with it, the model found a covered question unanswered 10 times in 10, and
  reading again with the same memory changed nothing. The second reading is now without it: 0 in 10.
- **Asked in French, the English passage came back alone, quoted,** 2 to 4 times in 10. The answer
  is written in the learner's language (10 in 10 after), and one with no words of its own is given
  as the guardian's words, with their name.
Then 58 in 58 (two misreadings of the test script fixed: "quatorze", "fourteen"), the class 19 in 19
(93 frames). A test of two saves at once failed 2 runs in 24 under load: fixed, 0 in 32.
