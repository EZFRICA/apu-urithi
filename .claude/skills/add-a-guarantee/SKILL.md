---
name: add-a-guarantee
description: How any new guarantee, rule or fix enters Urithi, with its test, its deliberate defect, a real run and a line of documentation. Use when adding a feature that promises something, fixing a defect, or reviewing whether a change is finished.
---

# Adding a guarantee

A guarantee is anything the system promises: a part a learner may not see is never returned,
a refused search is said as refused, distress is stored nowhere. A passing suite says the code
does something; it does not say the tests would notice if it stopped. So a guarantee is only
finished when all four of these exist.

## 1. The test

- Named as the sentence it proves: `test_a_case_that_names_what_was_kept_closed_is_raised_with_it`.
- Its docstring starts with what was measured when the defect was found, for example:

  ```python
  def test_quotations_are_paired_by_their_own_marks():
      """Measured: the words between two short quotations were read as a quotation, and refused."""
  ```
- It asserts the outcome a person would see, not an implementation detail.
- Models are faked; the test checks what code decides whatever the model says.
- A store-facing guarantee runs against every implementation of the store (the contract
  tests), including live ones behind an environment flag such as `URITHI_LIVE_NEO4J=1`.

## 2. The deliberate defect

Add an entry to `MUTANTS` in `scripts/mutate.py`: what it breaks, the file, the exact real
text, the broken text. The real text must occur exactly once in the file, or the mutant is
skipped. Check it alone, then run the whole set:

```bash
uv run python scripts/mutate.py --only "<words from its label>" --verbose
uv run python scripts/mutate.py
```

Do not apply a mutant by hand: the script restores the file whatever ends the run, and holds
the lock that stops a suite started meanwhile from reading the broken file.

A mutant nobody catches is a guarantee nobody is holding: write the missing test.
A mutant SKIPPED (its real text no longer occurs exactly once) is retargeted to the new line
and checked alone; **a mutant is never deleted or loosened to make a run pass**.

## 3. The real run

Run the feature with the real services (models, Neo4j, speech, search) and the real pages, as
the `real-condition-test` skill describes. Note the numbers as counts: "3 answers in 3 now
pass", "908 kB a part before, 153 after", "5 rules in 5, twice". A real run without a number
is not a measurement, and **a number not yet run is never written**: before the run, a test
docstring, a document or a message says what *will be* measured, never a result.

## 4. The documentation

One paragraph in `docs/urithi-measured.md` (or the measured file of the area): what failed,
measured how, and what holds now. The README and `docs/architecture.md` change only if the
promise itself is new.

## Finished means

`uv run pytest -q` green, `uv run ruff check .` clean, `uv run python scripts/mutate.py`
catching every mutant, no Markdown over 100 lines, no dash in prose, nothing committed.
