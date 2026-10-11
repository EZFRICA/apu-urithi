---
name: security-checklist
description: The security review checklist for Urithi, covering access leaks, prompt injection, authorization, secrets, signed packages, uploads and supply chain. Use before finishing any change that touches routes, models, retrieval, storage, uploads or packages.
---

# Security checklist

## Access and leaks

- Is access (organisation, level, status) decided before retrieval, inside the query?
- Can a hidden part, case, source or link reach a learner through any route, package, exam,
  quiz, search result, error message or count?
- Is "not found" indistinguishable from "not allowed" (404, same message)?

## Models

- Is every user text passed to a model as data, inside delimiters, with the instruction that it
  is not an instruction?
- Does every answer go through the guard before and the faithful rail after?
- Can a source page (searched, deposited) carry instructions into a prompt? It is data.
- Is every costly call metered (`metering-and-cost`)?

## Authorization

- Roles and memberships from the registry only. Guardian routes refuse learners; learner
  routes expose nothing of the guardian's side.

## Secrets and personal data

- No key, token or `.env` value printed, logged or stored. Network addresses redacted.
- Distress is stored nowhere. Questions in `exchange` carry no person.

## Files

- Uploads: type checked by content, size limited, stored under the owner's prefix, never
  executed, never served from the application origin without a safe content type.
- Signed packages: Ed25519 over the exact strings; a changed file is refused offline.

## Supply chain

- New dependencies through `uv add`, pinned in `uv.lock`, from known projects; scripts loaded
  by pages only from the allowed origins.
