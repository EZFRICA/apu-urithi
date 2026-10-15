# Urithi: what the guardian and the learner do

Part of [README.md](../README.md).

## What the guardian does

**Talks, and saves what counts.** Urithi notes everything and proposes, in the guardian's own
words, a step or a rule ("if fewer than ten people have registered three days before, I move the
meetup" becomes a rule a machine can check); nothing is knowledge until the guardian says "save
this" (decision 0016). It asks for the gap it needs closed next: where does that stop, who do
you ask when it does not cover the case; asked back, it answers from what it saw and noted.

**In English or in French.** The guardian says which when they start, and the apprentice
asks, tests and reads back in that language; a French rule stays in French ("quand moins de
dix personnes sont inscrites, tu déplaces le meetup"), and "moins de dix" is a threshold
decided by arithmetic like "fewer than ten". Each sentence keeps the date it was said.

**Is tested.** The debrief computes the cases where the rules are least clear and puts each
one as a concrete case, built by code: *exactly ten registrations, do you move it?* Two rules
at once where one says to stop: *which first?* A public source that disagrees (Bright Data,
then Tavily when it refuses; a country only for knowledge that has one; a social network is
never a source): *the law says 800, you said 5,000*. Each answer is kept verbatim as
precedent, and outranks the rule on the cases it settled.

**Hears it back, and takes back what was misheard.** The teach-back is built from the map,
never paraphrased, and says each case with its answer, so a hurried "yes" shows. Any case can
be answered again, replacing the earlier answer; a rule the guardian did not give, or gave
twice, can be taken out with the cases that tested it.

**Decides who may learn it.** Each part gets an access level: public, community, restricted. A part that
repeats the words of a more restricted part is raised to that level, so a sentence is never
open in one place and closed in another, and a test case that names a closed part's words is
closed with it. Teaching the same body again continues its map, and a part keeps its level
until the guardian changes it, even after a withdrawal; anything taught after the teach-back
is heard back again before it can be published.

**Shows the work in a class.** On a shared screen or a camera, the guardian holds the three
switches (microphone off until turned on, listening after a question, vision). At a pause
after a change, the expert pupil judges what a learner would miss (`importance` 1 to 5, with
its `why` kept in the notes and memory) and asks only above the guardian's threshold; a passed
question raises that threshold in the guardian's fundamental memory across knowledges, and
silent mode defers questions to the debrief. Spoken or typed commands (`save`, `remember`,
`example`, `mistake`, `compare`, `forget`) work with a pointed screen region; on a camera,
handheld sway is filtered, other people's faces are blurred while the guardian's stays clear,
and numbers or foreign scripts read from a board wait for the guardian's confirmation.

**Answers what learners asked.** A question the library had no answer to arrives in the
guardian's inbox, without the name of who asked. The guardian answers it the way they teach
anything, or says it is not something they teach; publishing closes it against the new
version, and the learner's page says so.

## What the learner does

- **Follows a path** ordered by prerequisites: nothing before what it rests on.
- **Takes each part in the form they need**: read, with the guardian's words and when they were
  said; listen (ElevenLabs, cached per version); braille (liblouis, the embosser's own pages);
  practise on the cases the guardian decided, graded by code and explained in their words;
  see, where the part sits among the others, drawn by code from the guardian's own links, and
  an illustration drawn by a model as a memory aid (below).
- **Reviews when it is due**: FSRS schedules each part for each person (`py-fsrs`).
- **Tests themselves.** Every case the guardian decided and this person may see, answered yes
  or no, and marked only at the end, by code, in the guardian's words. A part with a wrong
  answer comes back for review soon. It works offline too, marked on the device.
- **Asks.** A guard reads the question first; an answer is composed only from what the learner
  may see and only shown if every sentence cites the guardian. A question with no answer is
  passed to the guardian; the learner's device keeps a ticket, the only thing that ties the
  question to them, and the page says when the guardian has answered, and in which version.
- **Learns offline.** "Keep for offline" stores a package: the parts this person may see, with
  braille and audio rendered when it was built, a content hash and the embedding model's
  identity. Reading, listening, braille and practice work with no network; reviews made
  offline are sent when it returns; asking waits, and the page says so. A package expires
  after thirty days, is replaced by a new version, and leaves the device once its body is
  withdrawn.
- **Hands knowledge on, as a file.** The library signs every package (Ed25519). Saved as a
  file and opened on another device with no network, it is checked against the library's
  public key: a changed word, quiz answer, access level or date is refused, and a file made
  for a higher access level than its reader's is not opened.

## How knowledge is kept

Four memories, kept apart (the boundaries are tests):

| | | where |
|---|---|---|
| **[A] evidence** | what was said and shown, verbatim | `guardian/data/` and Cloud Storage when cited |
| **[B] knowledge** | the library: units, links, decided cases, sources | **Neo4j**, a graph with a vector index |
| **[C] guardian memory** | working memory per knowledge, and the guardian's APU MMU (L1 cache, L2 DLL, L3 LanceDB, BMJ, page-in, learned threshold) | `guardian/data/` |
| **[D] learner memory** | the learner's APU MMU (session, knowledge in view, preferences), FSRS reviews, notebook; the question box in `exchange/` | `learner/data/` and `exchange/data/` |

**Access is decided before retrieval, never after generation.** The access filter runs inside
Neo4j's vector index (`SEARCH ... WHERE u.access IN $allowed`), so a part a learner may not
see is never returned, however close to the question, and never reaches a model. One local
embedding model (multilingual ONNX, 384 dimensions) is used online and offline, so a question
in French finds what was taught in English. Nothing a learner does ever becomes knowledge.
