# Urithi: the build plan

The order in which [architecture.md](architecture.md) is built. Each step ends with the suite
green, a deliberate defect for each new guarantee in `scripts/mutate.py`, a real run with the
real services, and what it measured written down. Nothing is committed until the guardian of
this repository says so.

## Decisions taken

| | Decided |
|---|---|
| Packages | `apu/` (shared core), `library/`, `exchange/`, `guardian/`, `learner/`, each side built like `apu` |
| Boundary | the two sides never import each other; only the guardian writes to the library |
| States | notes and proposals (working memory); saved by the guardian's word, a draft until validated (0016); validated, the guardian's only; published (with access) |
| Prerequisites | reminded, not enforced |
| Classroom mode | a full-screen mode of the guardian's page; Urithi the only pupil at first |
| Learner's page | the current web page, offline and installable, with the school tutor's features; not Streamlit |
| Sources | audio, PDF and images now, visible to learners at the level of the part they support; offline, cited excerpts only |
| Video | later, a project of its own |
| Learner's progress | on the device, with a server copy apart from the guardian's side |
| Deployment | decided later; nothing assumes one process |
| Resources | a deployment choice: SQLite and local disk locally, managed services in production, behind one interface each |
| Storage | local and temporary while drafting; saving uploads to Cloud Storage only the documents a validated part cites |
| Organisations | the top level; a person may belong to several, with a role in each |
| Quotas, cost | quotas per person and role; ceilings per request, person, organisation, platform; set by the platform, narrowed by each organisation; stepping down before refusing |
| Vocabulary | *knowledge*, never *course* or *lesson* |

The completed foundation steps are in [plan-done.md](plan-done.md) (steps 0 to 2) and [plan-steps-3-to-8.md](plan-steps-3-to-8.md) (steps 3 to 8). The guardian's expert pupil (P1 to P3) is done and measured in [measured-class-p1-p3-and-v1.md](measured-class-p1-p3-and-v1.md).

## Later, each a project of its own

- Video sources, and whether a filmed class itself is made available online.
- Learners joining the classroom live: set aside for now (docs/decisions/0014).
- An extension or an add-on for video meetings; sharing the meeting's tab works today.
- Deployment: two services, or one; the learner's service read-only on the library; the
  production resources behind each interface.
- A real sign-in in place of the simulated identity.
- Local models, each measured in its role before it is a default.
- A Web Unlocker zone, so pages that refuse a plain fetch are read in full.

Done since, each measured: words beside meaning in search, a learner's memory per knowledge,
readable and removable by them (docs/decisions/0017, [measured-search.md](measured-search.md)).
