# Architecture: the memories and the APU memory hierarchy

Part of [architecture.md](architecture.md).

## Memory

```
 GUARDIAN SIDE (guardian/)                        LEARNER SIDE (learner/)
 ─────────────────────────                        ───────────────────────
 [A] evidence                                     [D] working memory: the session
     sources deposited, transcripts,                  with the tutor, what it retains
     what was said, verbatim                      [D] progress: FSRS reviews,
 [C] working memory, per knowledge                    notebook, exam results
     what Urithi retained: passages, open
     questions, drafts, cases to test
 validated maps (persistent)
        │ publish (guardian only)                        ▲ read, filtered by access
        ▼                                                │
 ════════════ [B] THE LIBRARY (library/, Neo4j) ══════════════════════════════════
        ▲ answered, or declined                          │ a question, no name
        └──────────── exchange/ (the question box) ◀─────┘
```

**Two crossings, one way each.** The guardian publishes to [B]; the learner reads it, never
writes. A learner's question reaches the guardian through `exchange/` without the learner's
name; the learner keeps a ticket on their device, the only thing that ties the question to
them. Nothing else crosses.

### The APU MMU and the two sides' memories

Both sides use the shared memory management unit in `apu/mmu/` (decision 0015), keeping their
stores apart per organisation and per person:
- **L1 (`L1Cache`):** in-memory cache with a lifetime per block type (`temporary` 5 min,
  `project`/`course` 30 min, `fundamental` 2 h) and bounded capacity (`10` entries).
- **L2 (`DoublyLinkedList`):** typed memory blocks (`temporary` at the head, `project` or
  `course` right after the head, `fundamental` right before the tail), plus `3` non-evictable
  fixed blocks per side. Beyond the cap (`50`), the least recently used block is paged out to L3.
- **L3 (`L3VectorStore`, `LanceDBDriver`):** long-term vector store using the local ONNX
  embedder (`384` dims). Search checks L1, L2, then L3, promoting the single best match to the
  head (`BMJ`), paging in L3 hits (`page_in_from_l3`), and writing back via `apu/meter.py`.

**The guardian's memories (`guardian/memory/`):** working memory [C] holds the classroom
(`temporary`), the knowledge being taught (`project`: said, seen, kept, deferred questions),
and the guardian's profile (`fundamental` and fixed `teaching_preferences`, keeping their
learned question threshold across knowledges). **Persistent:** what the guardian validated.

```
 draft (working memory) ──validate──▶ saved (persistent, the guardian's only)
                                          ──publish, with access levels──▶ published [B]
```

Validating needs the teach-back heard and confirmed. Publishing chooses who may learn each
part. Anything taught after validation sends the knowledge back to draft for that part.

**The learner's memories (`learner/memory/`):** fixed blocks (`learner_profile`,
`active_course`, `session_scratchpad`) and dynamic `temporary` (session), `course` (the open
knowledge), and `fundamental` (preferences, what they found hard) blocks read by the tutor;
plus **persistent progress** (FSRS reviews, notebook, exams) on the device and on the server.
