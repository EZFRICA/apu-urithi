# Measured: saving and forgetting (review of 2026-10-14)

Part of [urithi-measured.md](urithi-measured.md). A code review of decision 0016 (only the
guardian's explicit word saves) found seven defects; a test written for them found an eighth,
and a real class a ninth. Each has a test in `tests/guardian/test_saving_and_forgetting.py` and a deliberate
defect in `scripts/mutate.py`.

## What failed, and what holds now

- **A step saved with no rule was given every rule.** `/save` linked all the rules of the
  knowledge to it, so the library linked each rule to that step, and "forget the saved step"
  deleted every rule and its cases. A step now holds only the rules said with it, and forgetting
  a step keeps any rule another step holds.
- **Two requests undid each other.** The working memory was written back whole: a frame judged
  for seconds of model calls wrote over a save, an ignore or a note made meanwhile. A memory now
  keeps what it changed, and the store replays those changes on the newer list; proposals judged
  again from the notes are dropped on such a conflict and judged again at the next look.
- **A forgotten rule came back.** "Forget that" dropped the proposal and kept the rule in the
  notes. What is forgotten is now set aside with the rules said with it (a saved rule stays).
- **A rule changed before saving was saved in its first wording,** and a changed step was lost
  when the judge chose another note. A changed rule is now read again from the guardian's
  corrected words, its id kept; a changed proposal stays until saved, ignored or forgotten.
- **`/command` saved on a model's guess.** Every line said in class reaches it first; it now
  saves only on the same explicit words `/tell` and `/answer` require, and "save this" names
  nothing the model read into it.
- **The judge's "none" proposed the latest note.** It now means no step, as "" does.
- **A follow-up asked by `/tell` in class was not the question waiting:** the screen could ask a
  second one over it, and it could not be passed. It is now pending on the class clock, shown
  with Pass.
- **A rule without a severity could not be saved:** the default, "warning", is refused by the
  map. The default is now "check".
- **Found live: a saved step forgotten came back as a proposal,** its note judged again once the
  step was gone. Its note now goes aside with it.

## Measured

- Suite: 558 passed, 7 skipped (545 before the review); ruff clean.
- Deliberate defects: 14 new ones, each caught alone; two older ones retargeted to the moved
  lines. The full run: 308 in 308 caught (an earlier full run of 307 had one time out under the
  load of 8 parallel copies, caught alone).
- Live, `/teach/` in Chrome as Ezekias, real models, the shared screen fed with real desk
  screenshots, 99 frames observed, 2 questions asked by the screen, 0 server errors: 12 checks in
  12 passed on the third run. "Save the rule." saved 1 rule; a step saved after it held 0 rules;
  "Forget the saved step." left 0 steps and 1 rule; a rule said then forgotten was not proposed
  after more teaching and 12 s of frames; a rule changed on the page was saved as "a sponsor asks
  for a talk slot to pitch their product -> decline and offer a sponsor table instead"; no saved
  item came back as waiting after 8 s of frames, twice. The first two runs stopped on the test
  script (its timing, then the class window covering the page); the second showed the forgotten
  step coming back.
- Not seen live: the model never answered "save" to "Saving the agenda early helps newcomers."
  (it answered "none"), and `/tell` asked no follow-up in the run; both are held by tests only.

## The second review, the same day

A review of the fixes above found four more defects and three small ones; the live runs found two more.

- **A step proposal could vanish while the screen changed.** Any write counted as a conflict, so a
  frame noting what it saw dropped the step just said back as proposed. Derived changes are now
  dropped only when what they were judged from (notes, proposals, rules, what was set aside)
  changed meanwhile. A list deleted meanwhile is no longer written again.
- **A polite save was not a save.** "Can you save this?", "Could you save the rule?", "Peux-tu
  garder ça ?" are now read as the explicit save they are, by the server and by the class page;
  the guardian's words win over the model's reading. "sauvegarder" had named "r la règle".
- **Forgetting a step deleted a rule saved on its own** and attached to it: only the rules said
  with the step (the same moment) go now.
- **"save this" saved a note just ignored,** or with the latest note set aside, an older one: now
  only the latest note, and never one set aside, by its words either.
- Small ones: a saved step's note is found by its id, not only by its words; a rule corrected
  into two rules keeps both.
- **Found live:** a polite save went to "remember this screen", which dropped the question waiting
  and said nothing back. The page now sends it as a save, and keeps any question waiting unless the
  reply asked another.

Measured: 575 passed, 7 skipped; ruff clean; deliberate defects 319 in 319 caught (316 in the
full run; two found uncovered got their tests, one moved line was retargeted). Live as Ezekias,
the shared screen changing every 3 s: 16 checks in 16 (89 frames, 0 server errors), among them
a step and a rule said while the screen changed both waiting, "Can you save this?" saving through
`/command`, a rule saved alone kept after "Forget the saved step.", an ignored proposal not saved
by "Save this." Live as Sabine: a follow-up asked by `/tell` after 2 lines ("How long do we wait
before we decide a speaker is late?") shown with Pass, still waiting after "Can you save this?"
(which asked which of 2 rules), then passed (`passed: true`). An earlier run's checks read the
page too early or checked nothing (no proposal to ignore); they were rewritten, not the product.
