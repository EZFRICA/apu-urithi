# Measured: a library out of reach, said as such

Found on 2026-10-24: the Aura instance was paused, and every page reading the library broke. The
incident runbook (`.claude/skills/incident-runbook/SKILL.md`) promises otherwise: learners continue
from kept packages, publishing waits, and it is said. Measured before and after on this machine,
the server on 8790 pointed at a library that cannot answer in two ways: a port refused, and a
name that does not resolve. The figures are the same for both.

## Before

- **Five library routes in six answered 500** "Internal Server Error", in 2 to 4 ms: the
  learner's knowledge list, a path, the search, a question, and the guardian's knowledge.
  Only the guardian's maps (kept on this machine, not in the library) answered 200.
- **The server's log named the library's address five times,** in the driver's tracebacks.
- **The learner's page** opened a knowledge kept on the device (it falls back on any error),
  but a device keeping nothing read "Nothing has been published that you may see yet".
- **The stage** said "Nothing is published yet that this learner may learn".
- **The guardian's page** lost "Carry on teaching": the maps being taught vanished, because
  the list asks the library which version of each is published.

## After

- **The five routes answer 503 in 2 to 14 ms,** with one sentence: the library cannot be
  reached, nothing was read or changed, knowledge kept on a device still opens, publishing
  waits. The reply names the kind (`"unavailable": "library"`) so a page says it in its own
  language. Every query goes through one place in the Neo4j store, which turns a service
  unavailable, an expired session or refused credentials into that one error.
- **The log says the kind alone** ("The library cannot be reached (ServiceUnavailable)."):
  0 lines naming the address, 0 tracebacks, in both outages.
- **The learner's page,** in Chrome: the invoice knowledge kept while the library was up was
  listed "kept on this device" and opened on its path from the package; a device keeping
  nothing reads "The library cannot be reached just now. What this device keeps still opens".
  Offline (no answer at all) stays said by the network badge.
- **The stage** says the server's sentence, status "Knowledge not available".
- **The guardian's page** keeps the maps (200, version unknown) and says "your teaching is kept,
  and publishing waits until it is back"; a preview and a publication answer 503 and change
  nothing (the map is saved only after the library took the publication).
- **Pages in Chrome:** the learner's page, the guardian's page, the stage and the showcase, 0
  script errors.

## Held by

`tests/shared/test_library_unavailable.py` (the three kinds of failure, at the session and at the
query; every learner route; the guardian's maps and a publication that waits), the stage's and
its client's node suites, `tests/shared/test_pages.py`, and 13 mutants in `scripts/mutate.py`.
