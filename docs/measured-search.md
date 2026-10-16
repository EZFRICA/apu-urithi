# Measured: search by words and meaning, memory per knowledge, saved notes

Three ideas taken from TencentDB Agent Memory (decision 0017), and one defect of saving, each
measured before and after on 2026-10-15 and 2026-10-16. Rerun the search: `uv run python
scripts/measure_search.py`.

## Searching a knowledge: the question's words beside its meaning

- **The questions.** 38, written before anything was built (`scripts/search_bench.json`): 18 on
  Ezekias's "a or an" (16 parts), 8 on a meetup knowledge (4), 12 on supplier invoices (6); 26 in
  English, 12 in French, some using the parts' words, some none of them. Each names the parts that
  answer it.
- **First, outside the stores** (the same embedder, BM25, reciprocal rank fusion with k = 60, the
  published constant, nothing tuned on these questions):

| Ranking | First | In four | MRR | French: first, MRR |
|---|---|---|---|---|
| Meaning alone (as it was) | 30/38 | 35/38 | 0.854 | 10/12, 0.873 |
| Fused | 30/38 | 36/38 | 0.864 | **8/12, 0.790** |
| Fused, keywords at half weight | 30/38 | 36/38 | 0.858 | 9/12, 0.831 |
| Fused in the knowledge's language only | **32/38** | **36/38** | **0.891** | 10/12, 0.873 |

  Across languages, short words matched by chance (French "on" for English "on", "a"), so words
  count only when the question is asked in the knowledge's language; across languages the
  meaning alone links them. No word list is left out: in a knowledge about "a" and "an", those
  are the words.
- **Through the real stores** (Neo4j for "a or an", memory for the others): first 30/38 before,
  32/38 after; in four 35 then 36; MRR 0.844 then 0.882; French unchanged (0.861).
- **Neo4j's full-text index did not hold the gain.** Lucene scored the text and the quote apart:
  through it, first stayed 30/38. The words are ranked by the same BM25 code in both stores
  (`library/keywords.py`), over the parts of the one knowledge searched. The index made for the
  trial was dropped.
- **Latency on Aura**, 18 searches: a second query took the median from 410 to 813 ms; read in one
  query with the vectors, 345 and 367 ms against 330 and 373 ms before.
- **Kept as it was**: a search across all of an organisation's knowledge (no knowledge named)
  ranks by meaning alone; it was not measured.

## A learner's memory, per knowledge

- **Before.** One memory per learner, shared by every knowledge; opening another changed only a
  block's label. Asked on invoices after a question on "a or an", the memory reaching the answer
  held 2 lines, both from "a or an", one labelled with the invoices. On 2026-10-15 such a memory
  made the answer model find a covered question unanswered 10 times in 10.
- **After.** Each block written on a knowledge carries it; an answer reads that knowledge's blocks
  and the person's own (profile, preferences). The same sequence: 0 lines from the other
  knowledge; a second question on invoices still read its 2 lines.
- **Limit, said plainly.** A fixed block (the current session) holds one knowledge's words at a
  time: back on "a or an" after invoices, its session line had been replaced, not set aside.
- **Live**, the full run below: on "a or an", 3 blocks, 1 its own, 0 of the invoices used.

## Readable and traceable memory

Each block keeps what it was written from (the learner's words, a session event) and when.
`GET /api/learner/memory` lists them with the knowledge they belong to and whether they reach
answers there; `DELETE /api/learner/memory/{block}` removes one from L1, L2 and L3. On /learn/,
"What Urithi remembers about you" shows them, each with a remove button that says what it
removes. Live: 4 blocks in 4 with a source, 4 with the words said; one removed in Chrome; the
run's 3 blocks removed at clean-up by the knowledge it made.

## A debrief answer saved as a case came back as a step

The notes judged again left out those saved as steps or rules, not as cases: a debrief answer
came back as a step proposal 2 times in 2 when a rule was said next ("save this" ambiguous, and
saving it made a step of Urithi's question). Now every save marks the note it came from, and a
marked note is not judged again. Live, the same sequence: 0 in 3, "save this" saved the rule.

## One sentence, two rules

A sentence with no condition whose reading lost a limit word ("only") falls back on the whole
sentence; read twice, it became two rules under two invented conditions ("really dry", "not
really dry"), and "save this" asked which: 2 rules in 3 runs of 5 on the garden sentence. Two
readings falling back on the same sentence are now one rule: 1 in each of 5 runs; 21 real rules in
21 still read with their limit words. Leaving such a sentence no rule at all was tried and set
aside: an unconditional prohibition ("we never water the leaves in full sun") came out 1 time in 3.

## The runs

- A new knowledge taught by Ezekias ("Code a supplier invoice") and learned by a member, through
  the API and in Chrome: 73 checks in 73, 0 server errors. The class as Ezekias: 19 in 19,
  69 frames. Library contract on live Neo4j: 37 in 37.
- Two more new knowledges, taught by Sabine and learned by a member and a visitor (API and Chrome):
  a vegetable garden, 72 in 72 after three runs whose failures were the script's waits and readings
  and this defect; a food bank, after the fix, 72 in 72 at the first run, "save this" asking 0 times.
  The class as Sabine: 19 in 19 twice (75 and 72 frames).
