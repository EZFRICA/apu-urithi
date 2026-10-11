---
name: a11y-audit
description: The accessibility audit for Urithi's pages, for blind and low-vision learners, keyboard users and the hard of hearing. Use before finishing any change to a page, and for a full audit of the guardian's page, the learner's page, the classroom mode and the showcase.
---

# Accessibility audit

Urithi is built for people who learn by ear, by touch and by keyboard. A page that works only
with a mouse and a screen is broken here.

## Keyboard

- Every action has a key; Space talks; `?` lists the keys of the page.
- Keys never act while the focus is in a text field, and never override a browser shortcut.
- Focus is visible, follows the action, and never gets lost behind a modal.

## Screen readers

- Everything said by the page is also announced once, whole, in a live region.
- Every control has a name that says what it does; the selection of a simulated identity says
  it is simulated.
- Generated pictures are skipped (`alt=""`) because the words beside them say it all.
- Text from the server is set as text, never as markup.

## Hearing and reading

- The teleprompter shows what is said, both ways, whenever the microphone or the voice is on.
- No information only by colour or only by sound.

## Braille

- The braille on screen is the embosser's, page for page; the BRF downloads.

## How to audit

Drive the page with the keyboard only, then with a screen reader, then with the sound off.
Check contrast in light and dark modes, and at phone width. Write what failed and fix it
through `add-a-guarantee`.
