# Urithi: completed steps (0 to 2)

Part of [plan.md](plan.md). Continued in [plan-steps-3-to-8.md](plan-steps-3-to-8.md).

## Step 0: the separation, with no change of behaviour (done)

Move the code into the packages, so that everything after is born on the right side.

- `apu/` keeps the shared core: inference, modality (speech, braille, pictures), embeddings,
  plain text, logging, base configuration.
- `library/`: the store, the model, the publication from a validated map, the access registry.
- `exchange/`: the question box, out of the learners' database into its own.
- `guardian/`: the engine (`guardian/engine/`), the work maps, the public sources, the
  guardian's routes and pages, the screen-watching page until step 4 absorbs it.
- `learner/`: path, guard, answers, packages, signing, FSRS, the learner's routes and page.
- Routes become `/api/guardian/...` and `/api/learner/...`; the pages follow.
- Data under `guardian/data/` and `learner/data/` (gitignored); settings `GUARDIAN_*` and
  `LEARNER_*` beside the shared ones.
- **Tests**: `tests/guardian/`, `tests/learner/`, `tests/shared/`; new architecture tests for
  every boundary rule; every existing test passes unchanged in what it asserts.
- **Done when**: the a/an knowledge is taught, published and learned again end to end, as in
  the last real test, through the new routes.

## Step 0b: the foundations of scale (done)

What 10 million people need from the design, before features are added on top of it.

- **Every store behind an interface**: maps, working memories, progress, the question box,
  counters, renderings, the state of a session in progress (today a dictionary in the server
  process). A local implementation (SQLite, local disk) and the contract tests every other
  implementation must pass.
- **Organisations**: the organisation on every record and in every query, the vector index
  filtered on it, storage prefixes `organisation/...`, memberships with a role per
  organisation in the registry. Tests for every crossing that must not happen.
- **The meter**: one place in `apu/` that grants a budget before any costly call, counts what
  was spent, and refuses plainly without one; distress and offline work exempt.
- **The cost ceiling**: prices per model in configuration, the estimate before and the record
  after each call, ceilings at four levels, and the step-down: cached answer, cheaper model,
  the guardian's own words, deferred work, refusal.
- **Measured**: the a/an knowledge under two organisations at once, nothing crossing; a
  person brought to their quota and a platform to its ceiling, and what each one sees.

## Step 1: the words, and the teleprompter (done)

- The vocabulary: *knowledge* everywhere, English and French.
- **The teleprompter**, one component for every page: what Urithi says shown word by word in
  time with its voice (ElevenLabs returns each word's timing), what the person says shown as
  they say it (streamed transcription, as measured in the school tutor's live voice lab).
- **The keyboard**, one map across the pages, and `?` listing the keys of the page.
- **Measured**: the delay between a word heard and the word shown, in both directions.

## Step 2: the guardian's two memories and three states (done)

- **The working memory per knowledge**, on the doubly linked list of memory blocks from the
  school tutor: what Urithi retained, open questions, drafts, cases to test. "Carry on
  teaching" reopens it.
- **Validated and saved**, apart from published. Validating needs the teach-back confirmed;
  publishing chooses the levels. Anything taught after validation returns that part to draft.
- **The contents**: the guardian orders the knowledge top to bottom and groups steps into
  sections before validating; the learner's path follows that order.
- Withdrawing from the guardian's page (today only through the API).
- **Measured**: a knowledge taught over three sessions, with the server restarted between
  them, reopens where it was left.
