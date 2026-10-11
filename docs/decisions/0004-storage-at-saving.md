# 0004: Deposited documents stay local until saving, and only cited ones are uploaded

Decided: 2026-10-05, by the owner.

## Context
A guardian deposits more than they use; uploading everything costs and keeps what nobody needs.

## Decision
Local storage is temporary while drafting. Saving uploads to Cloud Storage only the documents a validated part cites, under `organisation/guardian/`. Unused documents are purged locally after validation or a delay.

## Consequences
Evidence in the cloud is exactly what the knowledge rests on.

## Alternatives set aside
- Upload on deposit: pays for documents never used.
