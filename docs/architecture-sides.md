# Architecture: the guardian's side and the learner's side

Part of [architecture.md](architecture.md).

## The guardian's side

**Sources.** The guardian deposits audio, PDF and images (video comes later). They become
evidence [A]: audio is transcribed with timings, a PDF is cut by page, an image is described.
While drafting they stay on local storage; **saving uploads to Cloud Storage only the documents
a validated part cites**, under `organisation/guardian/`. The guardian structures their
knowledge from them by voice or text; Urithi proposes a step or rule citing the exact passage
(page, timing), retains what matters in working memory, and waits for the guardian to save it.

**Talking and notes (decision 0016).** Anything the guardian says, shows, or answers is noted in
working memory (`WorkingMemory`) as a note or a proposal (`#proposals-box` and `#notes-box`),
never added to the knowledge by itself. Only the guardian's explicit save (`Save` on a proposal
or a `save` voice command, optionally after editing) writes a step or rule to the knowledge
(`#tree`), keeping the guardian's own words. **The debrief** tests the saved steps and rules like
code; every answer can be taken back and every rule removed (measured: a hurried yes, an invented
rule).

**The classroom mode** is a full-screen mode opened from `/teach/`: shared screen or camera in
the middle, teleprompter below, a board of saved steps and rules (`#tree`) beside Urithi's
proposals and notes, and Urithi asking at the pauses as an expert pupil (judging importance
`1..5` against the guardian's learned threshold, or deferring questions in silent mode). The
guardian holds the switches (decision 0013): the microphone is off until turned on, and listening
after a question and vision are theirs to toggle. Commands (`save`, `remember`, `example`,
`mistake`, `compare`, `forget`, `ask_pupil`) are understood by intent, with a region pointed at
on `#class-video`; a save always needs the guardian's own words ("save this", "can you save the
rule?"), never a model's reading; faces of others on a camera are blurred.

**The contents.** Before validating, the guardian orders the knowledge from top to bottom and
groups steps into sections. That order, not the order of speaking, is the learner's path.

## The learner's side

An interactive tutor **anchored to a path** that answers when asked and takes no unasked
initiative (decision 0014):
- **The contents, always in view**: sections, steps, rules, and decided cases (`not seen`,
  `learned`, `due`, `missed at the exam`).
- **The tutor**, on the part in view: answers from [B] only, quoting the guardian verbatim.
- **Prerequisites are reminded, not enforced** when opening a part, asking, or at the exam.
- **Modes**: read, listen (timed words), braille, practise, and see (diagram, illustration).
- **The notebook**: keep an answer whole, key points or an excerpt; export a revision sheet.
- **Reviews, exam, and offline**: FSRS, decided cases marked by code, and Ed25519-signed
  offline packages carrying only the parts and cited evidence excerpts this learner may see.
