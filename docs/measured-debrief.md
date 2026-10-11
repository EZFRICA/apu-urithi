# Measured: the debrief, probes, and rulings

Part of [measurements.md](measurements.md).

## The debrief, measured

Every number below is a repeated run of the same input, because a single run of a model
says nothing about the next one.

| What was measured | Before | After | What changed |
|---|---|---|---|
| Rules extracted from Sabine's two-rule sentence | 0 of 8 runs found both | **8 of 8** | asked for every conditional rule, not only "where they stop" |
| ...and from a sentence with no rule in it | 0 rules | **0 rules, 4 of 4** | nothing invented by the wider ask |
| Actions extracted as an instruction | "it is always capex" seen on screen | **16 of 16** start with a verb | asked for an instruction, because "you" is put in front of it |
| Her "yes, we follow the law" read as yes | 0 of 6 | **6 of 6**, then 24 of 24 across six phrasings | asked what she would *do*, not whether her rule applies; a condition the question settled counts as met |
| ...and a condition the question did *not* settle | | **unclear, 4 of 4** | the fix did not simply make the reader say yes |
| Is 2,400 euros "over five thousand"? | no, unsure, unsure, no | **no, 4 of 4**, no model call | arithmetic in code |
| Provenance finds the German 800 euro threshold | 3 of 5 | **5 of 5**, nine German sources | searched in English and in German, with the country in the query |

### The probes, built by code

On Sabine's map the debrief asks three questions and **none comes from a model**:

```
[source]    built by code   case: 2,900 EUR   (midpoint of 800 and 5,000, where they disagree)
[boundary]  built by code   case: 5,000 EUR   (the exact number the rule turns on)
[collision] built by code   case: 7,500 EUR, unknown supplier   (both rules at once)
```

The source case was first built around **2,026** euros, the year in "unchanged in 2026, at
800 euros". Money is now read beside its currency, and a test pins the midpoint at 2,900.

### What one ruling does

She ruled on one invoice. The tutor's decisions on cases she never saw, before and after:

| Case | Before her rulings | After |
|---|---|---|
| 5,000 EUR, known supplier | nothing (5,000 is not *over* 5,000) | capex, citing her: "Exactly five thousand counts." |
| 1,500 EUR, known supplier | nothing | capex, citing her decision against the public source |
| 600 EUR, known supplier | nothing | nothing |
| 1,500 EUR, unknown supplier | stopped | stopped, **supplier first**, as she said she works |
| the same, after Controller Weber cleared the supplier | stopped | **booked**, and the new hire is told who cleared it and why |

### The guarantees, broken on purpose

`scripts/mutate.py` now holds 60 mutants and catches 60, across the engine, the library, the
learner's side and the server. Two needed new tests before they were caught: the sorting of the probes, which on Sabine's map happened to come out in the
right order without being sorted, and the German decimal comma, which no test had used.

It also now writes a `.mutating` lock and the suite refuses to run while it exists. A suite
started by hand during a mutation run read a deliberately broken file, reported a failure
that was not real, and cost a wrong diagnosis before the cause was found.

### Another server on the same machine

**This server was once started with the same command as another project's,** and stopping
one by name stopped both, several times, before it was noticed. It is `python -m server`
now, on its own port, listening on loopback, reading only `APPRENTICE_` settings, and
`scripts/serve.sh` stops whatever holds that port and nothing else. Each of those is a test
in `tests/shared/test_architecture.py`, and the last two are mutants as well. The port mutant
survived at first: the test looked for the `lsof` call, which the wait loop also makes, so
swapping the kill for a `pgrep` by name passed. The test now reads what the kill loop kills.
