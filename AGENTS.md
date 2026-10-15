# Working on Urithi: what an agent needs to know first

You are joining a project already well under way. Read this whole file before changing
anything, then `CLAUDE.md` and `.claude/skills/house-rules/SKILL.md`. Your changes will be
reviewed afterwards, file by file, against the rules below.

## What Urithi is

A system that passes knowledge on. A **guardian** (anyone who has knowledge to share) teaches;
Urithi structures what they say into steps and rules, in their own words; **learners** learn it.

- **The guardian's side** (`/teach/`): teaching by conversation, documents to cite (PDF by page,
  a recording by its moment, an image), and **the classroom mode**: the guardian shares a screen
  or a camera, Urithi asks at the pauses, the guardian can say "remember this" to keep a part of
  the screen. What Urithi hears and sees is a **note** or a **proposal** until the guardian says
  to save it (docs/decisions/0016); a saved part is a **draft** until the guardian validates it,
  then publishes it with an access level per part.
- **The library** (Neo4j): the validated knowledge, per organisation, each part at its level.
- **The learner's side** (`/learn/`): a path in the guardian's order; each part read, listened
  to (a teleprompter lights each word), in braille, illustrated, practised; questions typed or
  said aloud, answered from the guardian's words and checked against them; a notebook, a
  revision sheet, an exam, a signed package that works offline.
- We say **knowledge**, never a course or a lesson.

## The owner's first rule: every change verified, every change tested live

**No change is finished until it has been verified and then run live, every time.** Not once
at the end of a long piece of work: after each change.

1. **Verified:** `uv run pytest -q tests` green, `uv run ruff check .` clean, and for anything
   that promises behaviour, its deliberate defect in `scripts/mutate.py` caught on its own
   (`uv run python scripts/mutate.py --only "<label words>"`).
2. **Live:** `bash scripts/serve.sh`, then the change used for real through the pages, with
   the real services (models, speech, Neo4j), the way a guardian or a learner would. Use the
   browser; when a page needs a screen or a microphone the browser cannot give, feed it real
   inputs (captures of `tests/screens/` pages as the shared screen, synthesised speech as the
   microphone) and say so. `.claude/skills/real-condition-test` describes the full run.
3. **Measured:** say what happened with numbers (seconds, counts, what was seen, asked, kept),
   and what failed. A defect found live gets its own test and deliberate defect, then is run
   live again.
4. Name the data the live run created, and remove it unless the owner wants it kept.

A change that was not run live is reported as **not run live**, never as done.

**Every action is written in the journal as it is done** (`docs/journal/`, one file per day,
format in `docs/journal/README.md`): after each change, before the next one. Read the latest
day's file before you start; it says what was done last and what is left.

## The rules you must keep (the owner's, enforced by tests where they can be)

1. **Every command through `uv`**: `uv run pytest`, `uv run python ...`, `uv add ...`. Never
   `pip`, never a bare `python`.
2. **No commit, no push, no branch** until the owner says so. Leave every change uncommitted
   and report it.
3. **Never print a key, a token or any value from `.env`.** Check a setting by its name and
   whether it is set. Never write a model name that is not already in the repository: model
   choices go in `.env` only (some names are confidential).
4. **Repository content is in English** (code, comments, documents, interface strings, with
   the French strings beside the English ones). The owner is spoken to in French, with "tu".
5. **No em dash and no en dash in prose.** A colon, a comma, parentheses or two sentences.
6. **No Markdown file over 100 lines** (a test checks). Split a document rather than squeeze it.
7. **Port 8790 is this project's, and only it.** Another project runs on this machine:
   never start, stop or probe another port. Stop a server by its port, never by its name.
8. **Sibling projects in `../` are read only.** Never name them in this repository: a test
   refuses the name of the project this one was copied from.
9. **The guardian's side and the learner's side stay apart** (`.claude/skills/boundary-check`).
   The learner's side reads the library through `library/reader.py` only, never writes to it.
10. **Organisations are kept apart in every store, query and path**
    (`.claude/skills/organisations`). No record is created without its organisation.
11. **Every store sits behind an interface with a getter and a setter**
    (`.claude/skills/store-interfaces`); `tests/conftest.py` isolates each per test.
12. **Every costly call is metered** (`apu/meter.py`, `.claude/skills/metering-and-cost`).
13. **The person holds the switches** (docs/decisions/0013, 0014): nothing listens, records
    or reads aloud unless the person asked. In a class the microphone is off until the
    guardian turns it on; listening after a question and the vision are theirs to turn on
    and off. No feature may open a microphone or start a capture by itself.
14. **A guarantee is finished only with all four** (`.claude/skills/add-a-guarantee`): a test
    named as the sentence it proves; a deliberate defect in `scripts/mutate.py` that the tests
    catch; a real run with numbers; one paragraph in the measured documents. Never write a
    number you did not measure.
15. Data you create with the real services (a map, a published knowledge, a question) is
    removed afterwards, or named as left in place in your report. Never delete the meter's
    usage rows (`exchange/data/counters.sqlite3`), even after a live test: those calls were
    really paid for, and the meter is the only trace of the spend.

## Environment, layout, checks, and handover

- [docs/agents-environment-and-checks.md](docs/agents-environment-and-checks.md): the environment, the layout, and how to check your work.
- [docs/agents-work-ahead-and-handover.md](docs/agents-work-ahead-and-handover.md): what to read before the next work, known open points, and handing your work over for review.
