# 0016: Urithi notes anything; only the guardian saves knowledge

Decided: 2026-10-10, by the owner. Refines 0002: its draft state now holds only what the
guardian saved.

## Context
In a real class on a shared screen, every sentence the guardian said became a step of the
knowledge, word for word: hesitations ("So, um, I want to, to share, uh"), questions put to
Urithi ("give me the rule"), corrections ("I said rule, not room"). Twelve sentences, twelve
steps, none of them knowledge. Filtering sentence by sentence would treat a symptom: the
system decided on its own what entered the knowledge.

## Decision
Urithi keeps two things apart. Its notes hold anything it hears, sees and infers in a class or
a conversation: free, unstructured, never shown as knowledge. The knowledge (the tree of
steps, rules and cases) changes only when the guardian explicitly asks to save something, by
voice ("save this", "garde ça"), by typing or with a button. Urithi may propose what to save,
structured from its notes in the guardian's words (a step, a reason, a rule), and the proposal
stays a proposal until the guardian accepts or changes it. Removing or changing a saved item is
also the guardian's explicit act. Validating and publishing (0002) then apply as before, to
what was saved. The learner's notebook already works this way: nothing is kept unless the
learner saves it.

## Consequences
- No route writes a step, a rule or a case on its own: conversation, class answers, the five
  commands, documents and the debrief produce notes or proposals; saving is one action.
- The tree shows only saved items; the notes and pending proposals are shown apart.
- A question put to Urithi, a hesitation or a correction never needs a special case: it stays
  in the notes unless the guardian saves something from it.
- Tests: a whole class without a save leaves the knowledge empty; a save without the
  guardian's request cannot happen.
- The guardian takes one more action per item; proposals keep it short.

## Alternatives set aside
- Filtering sentences that do not teach: case by case, and the system still decides alone.
- Saving everything and letting the guardian delete: the tree fills with noise, as measured.
