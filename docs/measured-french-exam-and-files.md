# Measured: teaching in French, the exam, and signed files

Part of [urithi-measured.md](urithi-measured.md).

## Teaching in French, measured

One live conversation in French, with the real models: three sentences, the debrief, the
teach-back. The questions came in French, the boundary was put as "prenons un cas à exactement
10", and the teach-back read every rule back in the guardian's words. One defect:

- **A habit became a rule.** "J'annonce chaque meetup deux semaines avant" came back as "when
  j'annonce chaque meetup, then l'annonces deux semaines avant": a habit with no condition,
  made into one about the speaker, which then met the other rules in two collision questions.
  The extractor is now told, in both languages, that a habit is a step and that a condition
  is about the case. Measured after: ten extractions in ten right, five sentences twice each,
  French and English, habits left out and "je ne connais pas le sponsor" read as "le sponsor
  n'est pas connu".

French numbers are read by code, as the English ones are: "moins de dix", "plus de cinq mille
euros", "quatre-vingts inscrits ou plus", "vingt et un jours ou moins", "1 250,50 euros". An
article is never a number: "un sponsor" is not one of anything.

**When a sentence was said** used to be seconds into the session, which start again at zero
in the next one: a part taught over two sessions showed "Sabine, at 0:00". Each sentence now
keeps its date, and the learner sees "Sabine, 5 October 2026".

## The learner's exam, measured

Passed in the browser as a community member on Sabine's library, then again offline from a
kept package (four of four, marked on the device, three reviews queued and sent on return).
The first run found three defects:

- **"You said that when..."** The cases are the questions put to the guardian in the debrief,
  so the learner was told they had said the rule. A learner now reads "Sabine said that
  when...", in English and in French ("Ezekias a dit").
- **"A, or B?"** A model-built case asked "should I tie it to an invoice, or is this the
  exception?", to be answered yes or no. Such a question is no longer asked.
- **Two answers to one case.** Exactly 5,000 euros was decided as capex in one session and as
  an expense in the next, by the person driving the test, answering a question the near miss
  should not have repeated (since fixed). The invented answer was removed and version 5
  published; the levels kept to the community stayed there. Two rulings that contradict each
  other are not yet found by code when one of them carries no amount.

## Knowledge handed on as a file, measured

In the browser, against the running server: knowledge kept by a visitor was saved, removed and
opened again from the file, and kept. The same file with one of Sabine's words and one quiz
answer changed was refused ("changed after the library signed it"); a file kept by a
community member was refused to the visitor ("made for an access level above yours"); a file
that is not a knowledge file was refused as such. The signature is checked by the browser itself
(WebCrypto, Ed25519) over the exact strings the library signed, so nothing is re-serialised
on the way. The library's key was made once, readable by its owner only, and is kept across
restarts; a server with no lasting disk is given one in `LEARNER_SIGNING_KEY`.
