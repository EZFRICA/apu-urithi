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
  `knowledge` 10 min, `fundamental` 30 min, any other type 5 min) and bounded capacity (`256`
  entries, the least recently used let go first).
- **L2 (`DoublyLinkedList`):** typed memory blocks (`temporary` at the head, `project` or
  `knowledge` right after the head, `fundamental` right before the tail), plus `4` non-evictable
  fixed blocks per side. Beyond the cap of dynamic blocks (`5`, `URITHI_MAX_DYNAMIC_BLOCKS`), the
  least recently used one is paged out to L3.
- **L3 (`L3VectorStore`, `LanceDBDriver`):** long-term vector store using the local ONNX
  embedder (`384` dims). Search checks L1, L2, then L3, promoting the single best match to the
  head (`BMJ`) and paging in L3 hits (`page_in_from_l3`); what a turn leaves is written back by
  the extraction model, under the meter's budget (`apu/meter.py`).

**The guardian's memories (`guardian/memory/`):** the working memory [C], one per knowledge
(`working.py`), holds what Urithi noted in class: notes, proposals waiting, the question waiting,
rules noted, what was set aside. Two requests may hold it at once (a frame judged while the guardian
saves); each keeps the changes it made, and a save finding the list written meanwhile replays them on
the newer one, so neither undoes the other. The guardian's MMU (`mmu.py`) holds the class
(`temporary`), the knowledge being taught (`project`) and the guardian's profile (`fundamental`,
with `teaching_preferences` keeping their learned question threshold across knowledges).
**Persistent:** the map, written only by the guardian's explicit save (decision 0016), one writer at
a time per map, a save from an older copy refused.

```
 notes, proposals (working memory) ──"save this"──▶ the map, a draft part
     ──validate (teach-back heard)──▶ validated ──publish, with access levels──▶ published [B]
```

Validating needs the teach-back heard and confirmed. Publishing chooses who may learn each
part. Anything taught after validation sends the knowledge back to draft for that part.

**The learner's memories (`learner/memory/`):** fixed blocks (`current_session`,
`active_knowledge`, `learning_preferences`, `learner_profile`) and dynamic `temporary` (session),
`knowledge` (the open knowledge), and `fundamental` (preferences, what they found hard) blocks read
by the tutor; plus **persistent progress** (FSRS reviews, notebook, exams) on the device and on the
server.

**Per knowledge, traceable, readable (decision 0017).** A block about what is in progress or under
study carries the knowledge it was written on, and the context for an answer holds that
knowledge's blocks and the person's own, never another knowledge's. Every block keeps its source
(the words it was written from, when). The learner reads what is remembered about them on /learn/
(`GET /api/learner/memory`) and removes any of it from L1, L2 and L3.

**Searching [B].** Within one knowledge, parts are ranked by meaning and, when the question is in
the knowledge's language, by its words (BM25), fused by reciprocal rank (`library/keywords.py`, the
same code in both stores); the score an answer is held to stays the meaning's. Measured in
`docs/measured-search.md`.
