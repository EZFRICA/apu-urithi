# Urithi: safety and honest limits

Part of [README.md](../README.md).

## Safety

Carried over from the education tutor this line descends from:

- **An input guard** classifies every question before anything else: on topic, off topic,
  or distress. Distress gets a caring reply that points to a person, and is never counted or
  stored. If the classifier is down, nothing is answered.
- **A proof of a validated turn**, which only the guard can issue: an answer cannot be composed
  without it, and it is bound to that question and that body of knowledge.
- **A faithful output rail**: the model may word an answer, code checks that every sentence
  cites a passage and every quotation is verbatim; a wording that fails is replaced by the
  guardian's own words. Measured: a cut-off answer and a "the passages do not say" that cited
  a passage anyway were both caught.

**An illustration says nothing of its own.** It is drawn from a part's words, always shown
beside them, and skipped by a screen reader. The model is asked for no writing and no count
of anything the rule turns on, and a second model looks at every drawing: one with a word, a
digit or a sign in it is drawn again, then refused. If the look cannot be had, there is no
picture. Drawn once per version of a part, and carried in packages. Knowledge about writing
itself ("a" or "an") is drawn with letters every time, so it gets no picture.

**Identities are simulated** (`registries/people.json`): who someone is, is chosen, not
proven. Roles and access levels come only from the registry, never from a request, and every
reply and both pages say "simulated identity". A real sign-in replaces how the person is
identified; nothing downstream changes.

## Honest limits

- **Identity is simulated.** The organisations, roles and access levels are enforced from an
  identity that is chosen (registries/people.json).
- **Prices are ours.** No provider returns a price; the meter costs each role from the prices
  set in configuration, and a role without one is costed at zero.
- **Every model is online today.** The capabilities sit behind interfaces so local ones (Whisper,
  Piper, a small local model) can be measured and added; the development machine cannot run them.
- **A package can be read by its holder**, quiz answers included: it is for learning, not for
  an exam that counts. A withdrawal reaches a device at its next synchronisation.
- **No Web Unlocker zone is set up**, so a page that refuses a plain fetch is read from its
  search snippet, which may confirm a rule but never contradicts one. When Bright Data fails,
  sources come from Tavily, a search index, and every citation says which service it came from.
- **A small model asks faster, and sometimes guesses.** A classroom question that invents a
  number or a quoted label not on the screen is caught by `_question_grounded` and falls back
  to the deterministic question; a learner's answer is checked against the guardian's parts.
- **The free Neo4j instance** pauses after three days without activity and is deleted after
  thirty; packages double as a backup.
