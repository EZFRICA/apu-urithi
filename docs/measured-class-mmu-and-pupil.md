# Measured in class: the APU memory and the expert pupil

Part of [measured-class.md](measured-class.md).

Both sides now remember through the Agent Processor Unit memory (docs/decisions/0015): L1, an
in-process cache with per-type TTL (`temporary` 300 s, `knowledge` 600 s, `fundamental` 1800 s)
and a 256-entry LRU bound; L2, a doubly linked list of 4 fixed blocks (`current_class`,
`active_knowledge`, `teaching_preferences`, `guardian_profile` on `/teach/`; `current_session`,
`active_knowledge`, `learning_preferences`, `learner_profile` on `/learn/`) and up to 5 dynamic
blocks inserted by type (`temporary` at head, `project` and `knowledge` right after head,
`fundamental` just before tail); L3, a per-organisation, per-person LanceDB vector store using
the local 384-dimension multilingual MiniLM embedder; and BMJ routing with Semantic Page Fault
page-in. Measured with the real embedder and LanceDB: writing 6 dynamic blocks (`dyn_lockout`,
`dyn_voltage`, `dyn_gloves`, `dyn_grounding`, `dyn_arc`, `dyn_relay`) paged the oldest dynamic
block (`dyn_lockout`) out of L2 at the 5-block cap while keeping its row in L3; reading a block
took 0.03 to 0.16 ms from L1, 0.31 to 1.05 ms from L2 on disk, and 4.13 to 16.98 ms from L3;
searching for grounding promoted only the first relevant DLL block (`dyn_grounding`, certainty
0.719) to head in 37.3 ms (BMJ); searching for the paged-out lockout block matched it in L3
(certainty 0.874), paged it back into L2 via `page_in_block`, evicted the oldest L2 dynamic
block, and promoted `dyn_lockout` to head in 12.6 to 24.8 ms. Measured live on `/teach/` in
Chrome with the camera stream: passing "Why the pressure gauge reading rather than the relief
limit there?" on knowledge 1 saved `by_kind: {"reason": 6}` in `ezekias@urithi`'s fixed
`reason` question on a brand-new knowledge 2.

At a pause after a screen or camera change (and never on every frame), the expert pupil now
judges in a single JSON call to `QUESTION_MODEL` (`judge_learner_gap`, `guardian/engine/questions.py`)
whether a learner would miss something (`{"kind", "importance", "why", "question"}`), keeping the
deterministic ledger as a fallback if the model cannot be reached. Any question that invents a
number or quoted option not present in what was seen or said is discarded in favour of the
grounded fallback. Measured before and after on the same two classroom observations: on changing
the pressure relief limit from 10 bar to 25 bar, the deterministic ledger asked a `reason`
question (`importance=5`, no `why`) in 1299.3 ms, whereas `judge_learner_gap` returned
`{"kind": "limit", "importance": 4, "why": "The pressure relief limit was significantly increased,
which affects safety compliance for the community event.", "question": "Why set the pressure
relief limit there?"}` in 884.8 ms; on setting the escalation contact to `COC Lead` above 25 bar,
the old prompt invented an unshown `"Safety officer"` option (`"Why Escalation contact rather
than Safety officer..."`, 1126.1 ms), whereas `judge_learner_gap` returned a grounded `escalation`
question (`"Why assign the escalation contact to the COC Lead?"`, `importance=4`) with its `why`
in 921.8 ms. Measured live on `/teach/` in Chrome with `camera_p3.mjpeg`: at a 4.9 s pause, the
pupil judged `kind="skipped_step"`, `importance=4`, noted `WHY` (`"The sequence of operating the
vent bypass before the main valve is critical for safety."`) and `ASKED` (`"Why vent bypass
before opening main valve?"`) on `#class-board` and in the MMU; passing it raised `skipped_step`
to 5 in `teaching_preferences`; turning on silent mode at the next pause (28.0 s) judged
`kind="risk"`, `importance=4`, noted `WHY` and `DEBRIEF` (`"What happens if we miss the relief
limit?"`) on `#class-board`, and returned it in `/api/guardian/debrief`.

