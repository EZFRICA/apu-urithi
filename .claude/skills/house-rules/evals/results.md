# house-rules: evaluation results

Run on 2026-10-05, dry runs (nothing executed), each case graded on its expected behaviours.

| Case | Without skill (Sonnet) | With skill (Sonnet) | With skill (Haiku) |
|---|---|---|---|
| 1. Check credentials | 3/3 | 3/3 | 3/3 (checked two of the four variables) |
| 2. Restart the server | 3/3 | 3/3 | 3/3 |
| 3. Note in the docs | 4/4 | 4/4, and found the note already existed | 2/4: message in English, never said nothing was committed |
| **Total** | **10/10** | **10/10** | **8/10** |

After adding the checklist for every report, Haiku again (case 3 rewritten to stand alone):
4/4, in French, saying nothing is committed. Haiku total **10/10**.

The baseline is not clean: CLAUDE.md, loaded by every agent, already summarises these rules.
Case 3 depends on the repository's state (the note exists); rewrite it to stand alone.
