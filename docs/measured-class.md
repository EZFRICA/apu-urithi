# The class in real conditions

What the owner's real classes in Chrome found, and a live run with every real service, after
Step 4 of `docs/plan.md` was first measured (`docs/measured-steps.md`). Each paragraph says what
failed, how it was measured, and what holds now; each fix has its test and its deliberate
defect in `scripts/mutate.py`.

The first real class failed. The owner shared the practice page of `tests/screens` in Chrome
and worked in it: about 35 frames were posted, nothing was seen, nothing was asked, and with
the class open over the guardian's page, behind the shared window, there was no way to answer
but to go back to that tab. Read again, the vision model saw the change on a pair of real
captures ("clicked Schedule the announcement") but took 8 to 14 s a pair. So the class now
reads its frames from the stream itself, on a clock run in a worker (a background tab slows
neither), and sends a frame only when some pixels changed: on a canvas standing in for the
shared screen, 2 frames went to be read in 8 s instead of 4. The question opens the microphone
by itself once said, and the answer ends after 1.8 s of quiet; nothing said in 12 s, and the
question waits. The class's notes keep what Urithi saw, asked, heard and kept, each with the
class clock, and the answer kept is said back aloud. The question, the microphone and the
notes can float above the guardian's work (Document Picture-in-Picture, in Chrome).

Measured in the browser pane with the real vision, wording and voice: the change was seen, the
question came at 0:25 and was said, the microphone opened, closed after 12 s of silence, and
an answer typed in the class became step 1, a draft, in the notes at 1:10. The floating window
could not open in the pane, which said so; it, and the class again in Chrome, wait for the
owner's real run.

The second real class, in Chrome, stopped at "Listening…" and said nothing back: the
ElevenLabs key was refused (401, "invalid_api_key") for live words and for transcription
alike. Speech already fell back to Gemini; hearing now does too (a sentence said and heard
back word for word, 2.2 s), the page says "Heard. Writing it down…" while a recording is
heard, and an answer that cannot be heard is said in the class instead of nothing.

The class then got a vision model of its own (`URITHI_CLASS_VISION_MODEL`). Five models read
the same real pair three times each: the general vision model took 12.3 s a pair (24.4 s at
worst); the one chosen took 0.9 s, saw the change every time and named the values ("Date
changed from Thu 22 Oct to Thu 15 Oct, and Announcement channel changed to #members"), and
saw nothing in a screen at rest. Another small model answered with a list and stopped the
call; a list is now read, and any other answer skips the frame. Illustrations and deposited
pictures keep the general vision model, where the time matters less than the reading.

In the third real class the guardian spoke more than they clicked, and the questions went
wrong: the introduction ("how an organiser can create the event") reached the wording model as
a change on screen and came back as "At what member count does that creation rule stop
applying?"; the answer ("the size does not matter, the structure does") came back as "At what
threshold does a community become too important?". What is said is now worded as said, with
no number nobody mentioned, an introduction is asked what is done first, and a gap answered
once is not asked again. Replayed on the owner's own words with the real model: "When an
organizer creates an event for the community, what do you do first, and why?", then "If an
event doesn't fit that structure, what do you do and who do you ask?". The wording took 6 to
16 s with the main model; it has its own setting (`URITHI_QUESTION_MODEL`), and a faster model
of the same provider asked the same questions in about 2 s, while the smallest invented a
number ("How many attendees make an event require approval?"). The owner chose the smallest
for speed (0.5 to 1.4 s a question): on a screen change it asks well; on an introduction, five
tries in five brought in a rule or a threshold nobody had said.

Then the owner asked to tell Urithi to remember something on the screen. In a class, a button
or a spoken "remember this" (or "retiens ça") keeps the shared screen as it is, as a source of
the draft, described by the class's fast model so it can be read without seeing it. Said with
words ("remember this: members only is for the second reminder"), those words are a draft step
citing the screen at that moment; said alone, Urithi asks what to remember, and the answer is
that step. It comes before a question that waits, and a screen no validated part cites is
purged like any document. Measured in the browser pane with the real models: alone, the
question was said 3.0 s after the click and the microphone opened; with words, step 2 citing
"the screen at 1:35" was kept and said back in 3.1 s.

The owner had no way to delete a knowledge. The guardian's page now has "Delete" beside each,
asked twice, as withdrawing is. It withdraws the knowledge from the library if it was
published, then removes every map of it (the page shows the latest, and an older one left
behind came back in its place), their working memory, any class in progress and their
documents, archived copies included. Only its own guardian can; another is refused, and
another organisation's is not found. Checked in the browser pane: four knowledges, each with
"Delete", the published one beside "Withdraw from the library".

In the next real class the owner asked twice to keep part of the screen, the way people say it
("so I want you to keep the information on the part from November meetup until the library has
three free evenings left"; "I just want to keep some information: venue, format, last meetup,
today; not the date"). Neither started with "remember", so neither was heard as a request:
both were taught as rules, and asked about. A request to keep is now heard anywhere in a
sentence, in English or French, while teaching that only mentions keeping ("we keep the venue
booked two weeks ahead") is still teaching; and the guardian's words name the part copied.
Replayed on a real capture of the practice page with the owner's two sentences: the first part
was copied exactly, from "November meetup" to "three free evenings left" (2.1 s); the second
kept venue, format, last meetup and today, and nothing else (0.7 s).


Further classroom measurements by feature:
- [measured-class-switches-and-camera.md](measured-class-switches-and-camera.md): live speech relay, person-held switches, and camera safety rails.
- [measured-class-mmu-and-pupil.md](measured-class-mmu-and-pupil.md): the APU memory hierarchy and the expert pupil.
- [measured-class-p1-p3-and-v1.md](measured-class-p1-p3-and-v1.md): pointing, frame comparison, camera thresholds, and the full v1 end-to-end run.
