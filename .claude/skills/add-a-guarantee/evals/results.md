# add-a-guarantee: evaluation results

Run on 2026-10-05, dry runs (nothing executed), each case graded on its expected behaviours.

| Case | Without skill (Sonnet) | With skill (Sonnet) | With skill (Haiku) |
|---|---|---|---|
| 1. Fix the quotation check | 2/4: no "Measured" docstring, paragraph in the wrong document | 4/4 | 2/4: no "Measured" docstring, no count of the real run |
| 2. A mutant SKIPPED | 3/3 | 3/3 | 2/3: did not say a mutant is never deleted to pass |
| 3. Done on a green suite? | 3/3 | 3/3 | 3/3 |
| **Total** | **8/10** | **10/10** | **7/10** |

After the docstring example, the count format and the rule on SKIPPED mutants, Haiku again
(case 1 rewritten: questions over 1000 characters cut silently): 4/4 and 3/3, total **10/10**.
It wrote a measurement it had not run ("tested with 5 questions"); the skill now forbids it.

Case 1 depended on the repository's state (the fix exists, so agents reproduced first);
rewrite it to stand alone.
