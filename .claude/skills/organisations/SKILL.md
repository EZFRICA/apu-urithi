---
name: organisations
description: Multi-organisation rules in Urithi: the organisation as the top level, memberships with a role per organisation, isolation in every store and query, and grants between organisations. Use when adding a record, a query, a route, a storage path or a registry entry.
---

# Organisations

## The model

- **Organisation**: owns guardians, learners, knowledge, and its policy (languages, access
  levels, models, quotas, ceilings).
- **Membership**: (person, organisation, role, access level). A person may belong to several
  organisations, with a different role in each. Memberships come only from the registry,
  never from a request.
- **Identity is simulated** for now and every page says so; a real sign-in will replace how a
  person is identified, not the memberships.

## Isolation

- Every record carries `organisation`. Every store method takes it.
- Every query filters on it before anything else, including the Neo4j vector index filter.
- Storage paths start with it. Signed packages and exchange questions name it.
- The current organisation of a request is resolved from the person's membership, never
  taken as given.

## Tests, each with a deliberate defect

- A query without an organisation is refused.
- Two organisations with the same knowledge name and the same person: nothing read across.
- A person who is a guardian in one organisation and a learner in another gets each role only
  where it applies.

## Later

Sharing a knowledge with another organisation is an explicit, recorded grant, revocable, and
never implicit through a shared person.
