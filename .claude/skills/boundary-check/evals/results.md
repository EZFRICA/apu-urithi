# boundary-check: evaluation results

Run on 2026-10-05, dry runs (nothing executed), each case graded on its expected behaviours.

| Case | Without skill (Sonnet) | With skill (Sonnet) | With skill (Haiku) |
|---|---|---|---|
| 1. Guardian answers from the inbox | 1/3: put the guardian route in the learner's routes | 3/3: under the guardian's API | 1/3: in the learner's routes |
| 2. heard_yes_no from the guardian's engine | 3/3: moved to the shared core | 3/3 | 3/3 |
| 3. Every unit of a body for the tutor | 3/3 | 3/3, flagged the missing organisation filter | 1/3: no access filter at all, a leak to the model |
| **Total** | **7/9** | **9/9** | **5/9** |

After the two never-bent rules were added, Haiku again: case 1 2/3 (guardian's side, but it
still imported the learner's store, now said in the skill), case 3 2/3 (access filtered inside
the query, no leak; organisation not yet in the store). Haiku total **7/9**.

Haiku case 3 was the dangerous failure: it proposed returning every unit "without filtering
by access level" for the tutor. The skill must say there is no unfiltered read on the
learner's side.
