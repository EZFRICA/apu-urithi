# The journal: every action, as it happens

Asked by the owner on 2026-10-08: one place where every action on the project is recorded as it
is done, by whoever does it (any agent, any editor, the owner). It is the running record; the
measured documents (`docs/measured-*.md`) keep what was learned, the decisions
(`docs/decisions/`) keep why.

## Where

One file per day, `docs/journal/YYYY-MM-DD.md`. No Markdown file goes over 100 lines (a test
checks): past that, the day continues in `YYYY-MM-DD-2.md`, `YYYY-MM-DD-3.md`, and so on.

## When

After each action that changes the project or its data, before starting the next one: a code
change, a fix, a test or a deliberate defect added, a document written, a dependency added,
data created or removed with the real services, a review, a decision taken by the owner. An
entry is added at the end of the day's file and never rewritten; a correction is a new entry
that says what it corrects. **Read the day's files before writing: if a file exists, append to
it; never create it again** (an entry was lost that way on 2026-10-08).

## How

```markdown
## HH:MM, <who>: <the action, in one line>

- **Why:** the request or the defect it answers.
- **Files:** every file created, changed or deleted (none: say so).
- **Verified:** tests passed and skipped, ruff, the deliberate defects added and whether each is
  caught.
- **Live:** what was done on which page, with which real services and inputs, and what was
  measured, in numbers; or "not run live", and why.
- **Data:** what was created with the real services, and whether it was removed.
- **Result:** done, partly done (what is left), or failed (what failed).
```

`<who>` names the agent or the person: the owner, the reviewing agent, the coding editor.
Nothing in an entry is a key, a token, a value from `.env` or a network address. Nothing is
committed unless the owner said so; an entry about a commit names who asked for it.
