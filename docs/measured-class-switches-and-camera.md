# Measured in class: live speech relay, switches, and camera rails

Part of [measured-class.md](measured-class.md).

A live run, end to end, with every real service: real captures of the practice page as the
shared screen, real speech as the microphone. It found five faults no unit test had: every
piece of speech went to the live relay as the string "undefined" (`chunk.buffer` of a plain
buffer), so no word ever appeared while the guardian spoke; once words came, the same words
sent again through the silence kept the answer from ever ending; a recording without live
words went straight to be an answer, before "keep this" could be heard in it; a class begun
again on the same map never asked, its clock behind the last question of the class before; and
a question was said over the guardian speaking. All five are fixed, each with its test. The
last run: the screen changed at 6.0 s, was seen at 8.9 s and asked about at once; the answer,
said from 12.0 s to 18.3 s, appeared word by word from 14.2 s, ended at 21.3 s and was step 5,
said back at 22.9 s; "I want you to keep the information on the venue, the format, and the last
meetup" was heard as a request at 35.5 s and kept exactly those three lines from the screen; a
screen change while the guardian spoke waited, and was asked after what they said was kept.

After that run, the class vision was told to quote each new value as written: on the run's
own pair it had said "Date and Announce in fields were filled", and now says, three times in
three, 'Date set to "Thu 22 Oct, 18:30", Announce in set to "#announcements"' (the example in
its instruction is from another domain, so it is not copied). A step kept from the screen is
named by what to keep ("The venue, the format, and the last meetup"), not by the request; its
words stay the guardian's, whole. And the learner's side had the same live relay: a question
said aloud had never been heard as it was spoken, and was thrown away for "type instead".
Asked aloud in a live run, "Do I write a or an before the word hour?" appeared word by word,
and was answered from Ezekias's parts, checked against them.

Then the owner decided where the class goes (docs/decisions/0013): Urithi listens only when it
awaits an answer, and only while the guardian has turned the microphone on; the guardian alone
turns on and off the microphone, listening after a question, and the vision. The class had
opened the microphone by itself, to tell pauses from speech, and after each question; now the
microphone is off until the guardian turns it on, "answer aloud" and listening after a question
wait for it, holding Space does not open it, and the switches are kept for the next class.
Checked on the page: microphone off, the two that need it unavailable, the vision on.

Two defects found in review were then fixed and run live in Chrome with real 1280 px captures
(JPEG at 0.7) and 16 kHz mono speech. First, saying "remember this" with words while a question
waited had cleared the question on the page while the server still held it, so the class never
asked again; now a screen kept with words keeps the waiting question on screen ("Kept. Urithi's
question still waits for you."), while a screen kept without words replaces it with "What should
I remember about this screen?". Measured live: after the screen change was seen at 0:23 and
asked about at 0:28 ("Why announcements rather than general for the announce in?"), "Remember
this, the venue holds 60 seats and the format is two talks" was heard in 8.5 s, kept as step 1
in 3.4 s (11.9 s in all) and left the question waiting on screen; "Remember this" alone (8.4 s)
replaced it with "What should I remember about this screen?", which the next spoken answer
(9.7 s) closed as step 2. Second, "keep this" anywhere in a sentence had matched ordinary
teaching ("We keep this channel public for newcomers."); a request now has to address Urithi
("you", "tu", "vous"), state a wish ("want to keep"), say "please", or start the sentence.
Measured live: "We keep this channel public for newcomers." (9.0 s) was taken as the answer to
the waiting question (step 3, 0 screen keeps), while "Keep this part, the venue and the format."
(9.2 s) was heard as a request and kept that part of the screen as step 4.

Five serious defects found while reviewing P1, P2 and P3 were then fixed and run live on
`/teach/` with a 1280x720 camera stream (JPEG at 0.7). First, "forget that" had popped the last
step of the whole map, even one taught in conversation or validated; the session now records
which step IDs this class captured, refuses to undo anything else ("Nothing from this class to
forget."), and names the step it undid ("Forgot step 2: Example: venting the relief line on
Rig B."). Second, a "compare" step had appended Urithi's comparison to the guardian's `reason`;
`reason` now stays the guardian's words verbatim, while Urithi's comparison goes into `observed`
and the cited passage. Third, when the browser provides `FaceDetector`, `capture.js` blurs
smaller faces on the canvas before any camera frame leaves the page; when it does not (as in
standard Chrome without experimental flags), the page warns the guardian when camera mode opens,
the server refuses unwarned camera `observe` calls, and an empty `other_faces` list from the
page never skips server-side face detection and blurring on kept stills. Fourth, a numeric value
read by the camera ("2.4 bar max" had been read as "24 bar max" in a live run) never enters a
rule unless the guardian states that number in their own words: answering "That is the relief
limit on the board." withheld the rule and asked "I read 0.0 on the camera: can you confirm the
exact value before I make it a rule?", and answering with "2.4 bar max" recorded the rule `when
pressure exceeds 2.4 bar, open the vent bypass immediately`. Fifth, `record_pass` had capped a
kind's learned threshold at 5, so passing a `reason` question of importance 5 still allowed the
next one; the cap is now 6, and after passing "Why relief limit rather than vent bypass first?"
(`reason: 6`), the next pause at 28.0 s asked nothing.

