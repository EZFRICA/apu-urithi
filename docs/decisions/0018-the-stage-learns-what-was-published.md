# 0018: The stage learns what was published, as /learn/ does

Decided: 2026-10-17, by the owner. Replaces the stage of the first version.

## Context
The stage (`/presentation/`) was built for the first version: an apprentice on a new hire's desk.
Checked on 2026-10-17, its three parts still worked that way:
- "Work Map" read a guardian's map, a draft or validated, never what was published;
- "The case" sent one invoice, hard-coded for every knowledge, to the guardian's review route;
- "Exam" read the cases from the map itself, with no access level, so a learner at the stage
  heard parts kept for members, and knowledge never published.

The way learning works since then (decisions 0002, 0016, 0017): a learner learns what a guardian
published, at their level, part by part, with practice and an exam marked by code, questions
answered with citations.

## Decision
The stage is the learner's page for someone who cannot see it. A learner is chosen (any learner,
`?learner=`), then a published knowledge (`?knowledge=`); every call is a learner's route.
- **1 · Path**: part by part (the arrows), heard in the guardian's words, printed in braille.
- **2 · Practice**: the cases the guardian decided for the part in view, answered yes or no by
  voice or key, graded by the server.
- **3 · Exam**: every case this learner may answer, marked only after the last answer.
- **Talk** asks a question aloud on the path, answered from what the learner may see, cited;
  **Keep** puts the last answer, or the part, in the notebook.

## Consequences
- Nothing unpublished, and no part above the learner's level, reaches the stage: the bridge
  calls `/api/learner` only, a test holds every route to the server's.
- A machine needs a published knowledge for the stage: `scripts/demo_map.py` teaches and
  publishes one, its rule on an unknown supplier for members.
- Live in Chrome: as a member, 3 parts, practice graded, the exam marked at the end, a question
  answered from the guardian's words and kept; as a visitor, 2 parts.
- The guardian's review route (`/api/guardian/review`), its spoken exam answer and
  `apu/ui/shared/practice.js` are no longer used by any page.

## Alternatives set aside
- Keeping a guardian's preview mode on the stage: it would show drafts on a learner's desk.
- Rewriting only practice and the exam on the guardian's map: still no access level.
