# 0015: Both sides remember through the APU memory: L1, L2, L3 and BMJ

Decided: 2026-10-08, by the owner.

## Context
Urithi belongs to the Agent Processor Unit line of projects, whose memory is a memory
management unit (MMU): L1, an in-process cache with a lifetime per block type; L2, a doubly
linked list (DLL) of typed memory blocks, each type inserted at its place, capped, the least
recently used paged out to L3; L3, a vector store that keeps what was paged out and can bring
it back; and BMJ routing (Bidirectional Metadata Jump), which moves the first relevant block
of the DLL to its head on every search, so memory follows what is used. Urithi had pieces
only: the guardian's working memory is a DLL of 200 blocks that drops its oldest block, the
learner's session is a plain list, the caches are separate, and nothing is ever paged out,
paged in or promoted. The owner found the architecture missing.

## Decision
1. **Both sides** remember through the MMU: the guardian (the class, the knowledge being
   taught, the guardian themselves) and the learner (the session, the knowledge in view, the
   learner themselves). Each side owns its memory; neither reads the other's.
2. **L3 is a vector store behind an interface**, LanceDB first (embedded, files on disk or on
   the bucket, as in the reference APU), with the same local embedder as the library.
3. **The library stays in Neo4j** and is not the MMU's L3: the learner's side never writes to
   the library (0001), and the guardian's memory is not knowledge until it is validated (0002).
4. **Before the bug-fixing phase**, since several defects found in P2 belong to memory (a
   threshold lost with the oldest blocks, questions kept for the debrief overwritten).

## Consequences
- The MMU's code is shared (`apu/mmu/`: blocks, the DLL, L1, BMJ, the L3 interface and its
  LanceDB implementation) and stores nothing itself: each side's storage sits under its own
  data directory, per organisation and per person, behind getters and setters.
- Every search through the MMU goes L1, then L2, then L3, and promotes one block (BMJ); every
  turn ends with a memory write-back, metered like any model call.
- A block paged out is found again in L3 and paged back in when it is used.

## Alternatives set aside
- The library as L3: it would let the learner's side write to it, and mix drafts with
  validated knowledge.
- Neo4j for L3 now: possible behind the same interface later, if links between blocks are
  needed; the free instance would fill with per-person memory.
