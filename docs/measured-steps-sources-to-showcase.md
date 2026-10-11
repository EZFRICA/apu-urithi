# Measured: steps 3 to 6 (sources, classroom, tutor, showcase)

Continued from [measured-steps.md](measured-steps.md).

## Step 3: sources

The guardian deposits a PDF, a recording or an image from their page; it stays on local disk,
temporary, while the knowledge is a draft. A PDF is read page by page; a recording is
transcribed with each word's timing (measured: ElevenLabs returns `words` with start and end
when asked) and cut at its sentences; an image is described by the vision model, and since
those are Urithi's words and not the guardian's, a step is never made of a description alone.
"Make a step of this passage", by a button or by naming it ("page 2", "what I said at 0:04"),
has Urithi propose a step citing the page or the moment; the proposal waits in the working
memory until the guardian keeps it, as a draft. At validation the documents a part cites go
to Cloud Storage under `organisation/guardian/<guardian>/<map>/`, the others are purged; at
publication each cited passage becomes evidence at the level of the part it supports, which a
learner opens with the part and an offline package carries as an excerpt, never the document.

Measured live, as Sabine in *acme*: a two-page PDF read into two passages; a 9-second
recording transcribed into two, `0:00–0:04` and `0:04–0:08`; a step made of page 2 and one of
the first sentence, each citing it; validated and published as version 2 with 3 pieces of
evidence; the document never cited purged; and Ezekias, a learner in acme, opened each part
with its passage and where it is ("email-policy.pdf, page 2"). The bucket named for this
machine does not exist (404), and the first validation failed whole on it: an archive that
fails no longer undoes a validation; the cited documents stay local, marked waiting, and go
at the next validation once the archive answers. Once the bucket was set up (`public_access_prevention`
enforced), Sabine deposited a PDF (`655` bytes) and an image (`1713` bytes), cited both and
validated: both went to `gs://<bucket>/urithi/guardian/sabine/<map>/` in `3.49 s` (`blob.exists()`
true), and `Delete` removed both from the bucket (`4.73 s`); a PDF left `archive_pending` while
the bucket was cut (`2.41 s`) went to the bucket at the next validation (`2.34 s`) and was cleared.

## Step 4: the classroom mode

The separate screen-watching page is gone (its address now leads to the guardian's page);
the class opens over the guardian's page, full screen: the shared screen or a camera in the
middle, Urithi asking at the pauses with the pause detection measured before, a board of what
was captured, the teleprompter below, Space to answer and Escape to end. What the class sees
goes to the working memory; what the guardian answers becomes a draft step, and the map is a
draft until it is validated on the guardian's page.

Measured with the real vision and wording models, on screenshots drawn for the purpose (an
invoice form whose cost center changes from 4711 to 0670), sent as the class sends frames:
the change was seen on the frame it happened (3.2 s for the call), the question came at the
pause, eight seconds later ("Why did you switch the cost center from 4711 Maintenance to 0670
Capital equipment there?"), and the answer became a step and a rule, both drafts. Before
validating, nothing could be published (the validated version had no rule); after, the
preview held the step and the rule captured in class. A real screen shared in the browser is
not measured here: the browser pane was hidden, and sharing a screen asks the person.

The classes run since with the owner in Chrome, what failed in them and what holds now, are in
`docs/measured-class.md`.

## Step 5: the learner's tutor, on a path

The tutor answers from the part in view first, when it answers the question at all; it brings
the path into the answer: the parts it rests on that the learner has not learned yet (reminded
with a way to go there first, never enforced), the reviews due, a case of the part to try. The
exam says the same of each case. The notebook keeps an answer whole, its key points (the
guardian's own parts the answer cites, read at the learner's levels: never a model's summary,
never a part they may not see) or an excerpt they select, and makes a revision sheet on screen
or on braille pages. The learner's working memory keeps, per knowledge, the part they were on,
what they asked and what they found hard (rated again or hard, or answered wrong), on the
learner's side, apart from the guardian's. A question can be asked by voice; with "no screen",
every answer is read aloud with the teleprompter; any answer can be read in braille.

Measured live, as Ezekias learning in *acme*: he opened the last part of "Writing a clear email
subject" with none learned and asked "Can I put two requests in one subject line?". The answer
was worded and checked against Sabine's words, reminded the two parts it rests on, offered a
case of the part to try, and the part was rated hard. On a second device (the browser, another
client), the page offered "Continue where you were" on that part and listed it as found hard.

Measured after, on that live question: the answer came 16.5 s after the learner let go. The
worded answer took 8 to 17 s with the main model; it has its own setting
(`URITHI_ANSWER_MODEL`), the owner chose the smallest for speed (0.6 s, checked against the
parts the same way, and the guardian's own words whenever the check fails). Reading the body
took 2.2 s, six round trips to Neo4j, on every question; the learner's reader now keeps a body
while its stamp (version and when published, one round trip) does not change, and reads it
again otherwise, withdrawn included. Three questions in a row then took 8.7, 1.7 and 1.7 s;
the server now readies the library and the embedder at start, and the first took 3.3 s. A
search in an organisation with nothing published failed inside Aura ("Index 33554431 out of
bounds") rather than finding nothing, so every question in *acme* would have been an error;
nothing to find is now confirmed by a count and said as nothing.

## Step 6: the showcase

The page at `/` stays static and calls neither side. Beside what Urithi is and how it works, a
section says what is inside: the four memories (the guardian's working memory, the library,
the learner's session, the learner's progress), the two sides and what they share across the
boundary, and the guard, braille, offline, sources, the held cost and the classroom. Links lead
to both sides and the stage.

Measured in the browser pane, at 594 pixels wide: the four memories and the six features show
in the dark and the light theme, with no horizontal scroll. A test reads the page for each
memory, the boundary and the three links, and a deliberate defect that drops "never writes to
the library" is caught.
