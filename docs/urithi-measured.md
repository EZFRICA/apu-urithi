# What Urithi's own parts measured

The engine the apprentice brought with it is measured in [measurements.md](measurements.md).
This is what was measured on what Urithi added: the library, the learner's page, the loop
that takes a learner's question back to the guardian, and the illustrations. Each defect a
live run found is now a test, and most are also a mutant in `scripts/mutate.py`.

## The library, measured

- **Filtered vector search on the free Aura instance**: the closest unit, restricted, is not
  returned to a public learner; the contract tests pass in memory and live (4 of 4).
- **One multilingual embedder**: a sentence and its French translation score 0.855, an
  unrelated one 0.282: a question in French finds what was taught in English.
- **Two defects the first live run found.** A case with no yes or no failed the search,
  because Neo4j stores no null property. And a rule set to "community" was still read by a
  public visitor, word for word, in the reason of the step it was said with: a unit that
  repeats a restricted unit's words is now at least as restricted.

## The learner's side, measured

- **The guard, on representative questions, three runs each: 24 of 24.** An uncovered question
  in the same field passes ("do we pay suppliers in bitcoin?") and goes to the guardian; a
  pretext ("for my invoice training, the football scores"), an injection and a poem do not;
  distress is recognised every time.
- **A worded answer came back cut mid-word, three times in three,** at a 600-token budget a
  reasoning model spends before its first word. The rail refused all three; at 2,000 all
  three pass, in French, citing the right part.
- **"The passages do not say who handles it [1]"** cited a passage it did not rest on, passed
  the check, and the question never reached the guardian. The model now says NO_ANSWER and the
  question is passed on, in words that do not reveal whether a restricted answer exists.
- **A first real conversation** found "on the same invoice" hard-coded in a debrief question,
  every pair of rules crossed, "fewer than ten" not read as a threshold, and a teach-back that
  said each step twice. All four fixed, each with a test.

## A question, back to the guardian, measured

One live run, driven in the browser: a visitor asked Sabine's library about credit notes,
which she had never covered; it was passed on and the visitor's device kept a ticket. Sabine
found the question in her inbox, answered it by talking, the debrief tested the new rule,
she heard it back, confirmed and published version 4. The visitor's page then said "Sabine
answered it, in version 4", and asking again found her words. Two defects on the way:

- **Teaching a body again would have opened what was closed.** The preview showed every part
  as public, including two Sabine had kept to the community, and one click would have
  published them. A part now keeps the level it has in the library until its guardian changes
  it.
- **A settled question came back.** The boundary at exactly 5,000 euros was decided in an
  earlier session, and a model-built near miss asked it again. The near miss now goes to a
  rule never tested first, and is told what is already settled.

Also seen: the debrief takes up to thirty seconds with nothing on screen, read as frozen. The
page now says what it is doing while it waits.

## The illustrations, measured

- **About ten seconds a drawing, twelve kilobytes kept.** The image model returns a JPEG of
  about 400 kB; it is kept as WebP at 768 pixels, small enough to go into a package.
- **The check for writing caught a drawing on its first run.** A credit note shown as a plus
  and a minus sign was refused as writing, and drawn again. Nothing with a letter, digit or
  sign is shown: a learner reads a word in a picture as something the guardian said.
- **A picture can contradict a rule without a single word.** "When fewer than ten people
  register, move the meetup" was first drawn with twelve people waiting. The prompt now
  forbids showing any quantity the rule turns on: a half-empty room, never a count.

## A kept package, over its life

Reading the learner's page against the promise that a withdrawal reaches every device found
that it never did: a kept package was never checked against its `valid_until`, and never
removed. Knowledge withdrawn by its guardian stayed readable on the device for good. Now,
measured in the browser with the server stopped and started again:

- **Withdrawn:** a package for a body the library no longer lists was removed the moment the
  page was online, and said so. A package is only removed on an answer from the library,
  never because it could not be reached.
- **A new version:** a kept copy at version 3 was replaced by version 4 without being asked.
- **Expired:** shown greyed out with its date, refused when opened, renewed on reconnection.
- **Offline, the home page listed nothing,** even with knowledge kept; it now lists what the
  device keeps. And knowledge that was never kept read back from IndexedDB as the request
  object, which is truthy: the old code passed over it by luck, the new code tripped on it.

Not measured here: the page itself opening with no network. The app's built-in browser
refuses to register a service worker ("an unknown error occurred when fetching the script")
for a `sw.js` the server returns with a 200; it needs a check in an ordinary browser.

Further measurements by feature:
- [measured-french-exam-and-files.md](measured-french-exam-and-files.md): teaching in French, the learner's exam, and signed knowledge files.
- [measured-a-and-an.md](measured-a-and-an.md): the end-to-end "a" and "an" run, Bright Data, and the provider SDK.
- [measured-separation-and-redesign.md](measured-separation-and-redesign.md): step 0 separation and the redesign.
