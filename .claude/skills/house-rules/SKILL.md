---
name: house-rules
description: The standing rules of the Urithi repository (uv for every command, no commit without the owner, secrets never printed, English in the repository, no dashes, Markdown under 100 lines, ports, sibling projects read-only). Use before any change, command, commit, document or message in this project, and whenever unsure whether something is allowed.
---

# House rules

These come from the owner of the repository and hold for every task, every agent, every
session. When a rule and a request seem to conflict, ask; do not pick.

## Commands and changes

- **Every command runs through `uv`**: `uv run pytest`, `uv run python ...`, `uv add ...`.
  Never `pip`, never a bare `python`.
- **No commit, no push, no branch** until the owner says so in the conversation. A finished
  task is left uncommitted and reported.
- **Servers are stopped by their port, never by their name**: `scripts/serve.sh`, or
  `lsof -nP -iTCP:<port> -sTCP:LISTEN -t`. This project runs on 8790.
- **Only port 8790 is this project's.** Another project runs on this machine: never start,
  stop or probe a port that is not ours.
- **Sibling projects in `../` are read-only.** Read them for ideas; never change them.

## Secrets

- **Never print a key or a token**, nor any value from `.env`. To check configuration, print
  variable names and whether they are set, never their values.
- A machine's network address in an error message is redacted before it is shown or stored.
- The owner keeps a short list of confidential model names. They never appear in the
  repository, a commit, a screenshot, a post or a document. If unsure whether a name is on
  it, leave the name out and ask.

## Language and style

- **Repository content is in English**: code, comments, documents, interface strings
  (French interface strings live beside the English ones). **Conversation with the owner is
  in French.**
- **No em dash and no en dash in prose.** Use a colon, a comma, parentheses or two sentences.
- **No Markdown file longer than 100 lines.** A test enforces it; split the document rather
  than squeeze it.
- Say what was measured, with the number; never claim what was not run.
- We speak of *knowledge*, never of a *course* or a *lesson*.

## Every report to the owner

Before sending any message to the owner, check all four:

- [ ] Written in **French**, addressing the owner with **tu**.
- [ ] Says what was actually run, with numbers, and what was not run.
- [ ] Says plainly that **nothing is committed** (unless the owner asked for a commit).
- [ ] No key, token, `.env` value or network address in it.

## Every change: verified, then tested live

The owner's rule: **each change is verified and tested live, every time**, not once at the
end. Verified: the tests green, ruff clean, and the deliberate defect of any guarantee caught.
Live: the server restarted on 8790 and the change used through the pages with the real
services, as a guardian or a learner would (`real-condition-test` for the full run), with
what was measured in numbers. A change not run live is reported as not run live, never as
done.

## The journal

Every action is written in `docs/journal/YYYY-MM-DD.md` as it is done, by whoever does it:
what, why, the files, what was verified, what was run live with its numbers, the data created,
the result (format in `docs/journal/README.md`). Entries are added, never rewritten.

## Working

- Before reinventing something, look for what exists (libraries, services, the sibling
  projects) and say what was found.
- A guarantee is not added without its test, its deliberate defect and a real run: see the
  `add-a-guarantee` skill.
- The boundary between the guardian's side and the learner's side is not crossed: see the
  `boundary-check` skill.
- Data created for a test with the real services (a published knowledge, a map, a question)
  is removed afterwards, or named as left in place in the report. Never delete the meter's
  usage rows (`exchange/data/counters.sqlite3`), even after a live test: those calls were
  really paid for, and the meter is the only trace of the spend.
