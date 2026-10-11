# Measured, step by step (from step 0b)

What each step of [plan.md](plan.md) was measured doing, with the real services, the real
pages and the real library. What came before is in [urithi-measured.md](urithi-measured.md)
and [measurements.md](measurements.md). A number here was run; a number not yet run is never
written.

## Step 0b: the foundations of scale

**Organisations.** The registry now holds organisations, people and memberships: Ezekias guards
in *urithi* and learns in *acme*; Sabine guards in both. Every record carries its organisation
and every query filters on it; in Neo4j the organisation is a filter of the vector index, and
the schema moved itself on first contact: the records published before organisations existed
were given the one there was, the single-property constraints became `(organisation, id)`,
and the vector index was rebuilt with the organisation first. Measured live: Sabine published
the a/an knowledge in *acme* (version 1, 16 parts) beside Ezekias's version 3 in *urithi*; a
member of urithi listed and searched only urithi's, Ezekias as a learner in acme only acme's,
and the acme body was not found (404) for the urithi member. The library's contract for two
organisations with the same body id passes on memory and on live Neo4j.

**Stores behind interfaces.** Maps, the state of a session in progress (once a dictionary in a
route module), progress, renderings and the answer cache each have an interface, a local
implementation, and a getter and setter; the contract tests run every implementation. A test
refuses a database or a file opened outside a store module, and state held in a route module.

**The meter.** Every model, speech, transcription and illustration call is granted a budget
before and recorded after, from what the provider billed (thinking included). Quotas per
organisation, role and period, with a warning and a stop; four cost ceilings; an organisation
narrows the platform's limits and never widens them. Measured live, with a tight policy and
illustrative prices: the first answer was worded by the model; once the platform's ceiling
was met, the next answers came in the guardian's own words at no cost, said as such; the
question asked again by the same member came from the cache; a fifth question met the
quota, refused in plain words (429); and distress was still answered, past every limit.

The run found three defects, each now a test and a deliberate defect: an answer stepped down
because the model was refused did not say it had stepped down; with no model, the guardian's
words quoted the passage ranked first rather than the one holding the question's own word
("useful"), and a lead-in ("One more thing") could win the same way; and answers given in the
guardian's words while the model was refused were cached and kept being served after it came
back. Only a worded answer, checked against the guardian's words, is now kept.

## Step 1: the words, and the teleprompter

**What Urithi says, word by word.** ElevenLabs is asked for the time of every character
(measured: `with-timestamps` returns `characters` with start and end times beside the audio);
they are joined into words, kept beside each rendering, and the teleprompter lights each word
when the audio's own clock reaches it. Audio rendered before timings existed is made again
once, with them: measured, the parts already listened to read back as one block. Measured in
the browser on a part of 42 words read in 13.5 s: every word lit, in order. The pane was hidden
while it ran, and a hidden page's animation frames are slowed to about one a second, so the
lag measured there (median 0.52 s) is the browser's, not the teleprompter's; with the page in
view a word is lit on the first frame after its time, which is not yet measured here.

**What the person says, as they say it.** The microphone streams 16 kHz PCM to each side's
`/listen` socket, relayed to ElevenLabs realtime transcription; partial words come back at once,
the committed words when Space is let go, and those go through the side's ordinary route. Without
a live service the recording is sent whole, as before. Measured live: a 10-second sentence
streamed at real-time pace into the running server came back in 10 partials; 26 words in 27 were
seen, each a median 0.84 s after it was said (90% within 1.51 s), and the final words 0.43 s
after the audio ended. A test found that a service that never answered the opening held the
microphone forever; the opening is now bounded to five seconds.

**One keyboard map.** The keys every page shares (Space talks, Esc goes back) and each page's
own are listed by `?`, in the page's language, never while typing.

## Step 2: the guardian's two memories and three states

**The working memory**, one per knowledge, is a doubly linked list of blocks kept by a store:
what was just said at the head, what is open (the question Urithi is waiting on, the cases
still to test) after it, what is retained (the rules noted) before the tail; touched again, a
block moves to the front of its kind; past two hundred, the oldest recent ones go first.

**Three states, part by part.** Validating keeps the version the guardian heard back and
confirmed; anything taught or changed after it is a draft, part by part, and publishing always
publishes the validated version, so a draft never reaches the library. A map confirmed before
versions were kept is its own. **The contents**: the guardian moves steps up and down and names
their sections from the keyboard; the learner's path and contents tree follow that order, the
step numbers staying each part's identity so a learner's progress and the access levels hold.
Withdrawing is on the guardian's page, two presses.

Measured live, as Sabine in *acme*: a knowledge was taught over three sessions with the server
restarted between them. After the first restart the question Urithi had left open was still
there and was answered; the knowledge was then debriefed, validated and published (version 1,
4 parts). Then a new rule was taught, a debrief started and the server restarted before the
case was answered: the case came back from the working memory and the answer was taken. On the
page: the new step marked draft, the states read "Draft · Validated · Published v1, changed
since v1", and "Carry on teaching" opened on the question left open.

Steps 3 to 6 (sources, classroom mode, the learner's tutor, and the showcase) are in [measured-steps-sources-to-showcase.md](measured-steps-sources-to-showcase.md).
