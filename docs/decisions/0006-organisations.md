# 0006: The organisation is the top level

Decided: 2026-10-05, by the owner.

## Context
The tool is meant for many communities and companies at once.

## Decision
An organisation owns its guardians, learners, knowledge and policy. A person may belong to several, with a role in each, from the registry only. Every record carries its organisation and every query, the vector index included, filters on it.

## Consequences
Isolation is tested. Sharing between organisations is an explicit grant, later.

## Alternatives set aside
- One organisation per deployment: does not serve many communities on one platform.
