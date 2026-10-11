---
name: i18n
description: How Urithi carries several languages: interface strings, the apprentice's wording, thresholds read in words, braille tables and tests. Use when adding a language, adding a string, or changing anything the apprentice or the tutor says.
---

# Languages

English and French today. A guardian teaches in one language; a learner may read the page in
another and ask in either.

## Interface strings

- Every page has `STRINGS = { en: {...}, fr: {...} }` with the same keys; a test checks both
  carry every key and that every key used exists.
- Functions for plurals and values, never string concatenation in the page code.

## What the apprentice says

- Code-built questions and the teach-back live in `wording.py`, one set per language.
- A model asked to word something is told the language; its fallbacks exist in every language.
- The extractor keeps a rule in the guardian's language; `then` reads after the pronoun of
  that language ("you", "tu").

## Numbers

- Thresholds are read by code in every language: comparators and number words
  (`thresholds.py`); amounts written the way the language writes them.

## Braille and speech

- The braille table follows the language; the voice reads the language it is given.

## Adding a language

Strings, wording, fallbacks, comparators and number words, braille table, the yes and no
words, tests for each, and one real conversation in that language through
`real-condition-test`.
