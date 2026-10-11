# Measured in class: P1 to P3 completions and the full v1 run

Part of [measured-class.md](measured-class.md).

All remaining P1, P2, and P3 classroom findings were then fixed and measured live:
1. **Pointing at a region (`#class-video` and `#class-point`) and single-entry notes:** giving the
   classroom `<video>` element `id="class-video"` and removing the duplicate `onCaptured` call from
   `Classroom.command()` let a mouse drag from 20%, 15% to 70%, 65% on `/teach/` display
   `#class-point` (`left: 20%, top: 15%, width: 50%, height: 50%`), crop the frame for `"This is an
   example: when pressure exceeds 2.4 bar, open the relief valve immediately."` (7879.8 ms), hide
   `#class-point` afterwards, and record 1 step note and 1 rule note on `#class-board` instead of 2.
2. **`compare` against the frame before the last change (`vision.frame_before_change`) via
   `vision.compare_frames`:** keeping `_before_change` when a screen or camera change is observed
   prevented `"Compare with before"` (5403.6 ms) from comparing the current frame against itself;
   it described the two checklist items added between the first and second frames while keeping
   `step.reason` verbatim.
3. **Multiple silent-mode classes keeping all deferred questions:** indexing `deferred-{n}` past
   existing keys in working memory kept both deferred questions across two consecutive silent
   classes (`"How do we know when to trigger the vent bypass before opening the main valve?"` at
   10.0 s in class 1, and `"Why write log purge time in the shift book?"` at 8.0 s in class 2) in
   `/api/guardian/debrief` (`deferred_questions = 2`).
4. **Camera pixel-change threshold (`CAMERA_PIXEL_CHANGED = 32`, `CAMERA_MIN_CHANGED_PIXELS = 350`):**
   on a 1-minute camera class (30 frames at 2 s interval) with 2 px handheld sway (116 pixels above
   32) and one real whiteboard and gesture change (450 pixels above 32), the old screen threshold
   (`PIXEL_CHANGED = 12`, 1 pixel) sent 29 of 30 frames and made 28 vision calls per minute; the
   camera threshold sent 2 frames (the initial seed frame and the 1 real change) and made 1 vision
   call per minute (2433.5 ms), cutting camera vision calls by 96.4%.
5. **Foreign-script camera misreads withheld and 10-image camera reading benchmark:** stripping and
   flagging words read in another alphabet than the knowledge's (`strip_unconfirmed_camera_script`,
   `confirm_camera_rails`) prevented `"2.벤트 bypass"` from entering a step's title, observed text,
   decision, or rules without confirmation (`confirm_value = "벤트"`). Across 10 distinct camera
   whiteboard images (`"1. Isolate valve"`, `"2. Vent bypass"`, `"2.4 bar max"`, `"3.5 L/min"`,
   `"Temp 65 C"`, `"Wait 15 min"`, `"Check seal B2"`, `"Max 120 rpm"`, `"Drain line 4"`, `"Reset
   switch A1"`), `CLASS_VISION_MODEL` read 10 out of 10 accurately in a mean of 1652.4 ms (1264.2
   to 2593.9 ms).
6. **Pre-filtering spoken classroom sentences before command classification (`has_command_cue`):**
   calling `QUESTION_MODEL` on every spoken sentence in class cost a mean of 1105.8 ms per ordinary
   teaching sentence (5146.6 ms across 5 sentences: 3 ordinary teaching sentences and 2 commands);
   checking `has_command_cue` first returned `intent="none"` in a mean of 0.071 ms (0.061 to 0.080
   ms, 0 model calls) on ordinary teaching sentences while classifying the 2 commands in 855.0 ms
   and 999.0 ms (1854.3 ms total across the 5 sentences).

## Full v1 real-condition run, end to end

Run against the live server (`http://127.0.0.1:8790`), live Neo4j Aura (`8 passed` on contract
tests), ElevenLabs, Gemini, and Tavily, driven through headless Chrome and HTTP:

1. **As guardian (`/teach/`):** Sabine taught `"Préparation de la chaîne du froid"` in French (2
   steps, 1 rule, boundary case `"Exactement 8, c'est au-dessus, ou pas ?"`, teach-back 768 chars,
   25228.8 ms, then deleted) and `"Sterile hood preparation"` in English: typed turn (2430.0 ms),
   spoken turn synthesised and transcribed (`"When preparing more than five vials, log the batch
   number on the sterile sheet before starting"`, 2528.5 ms), cited PDF (`sterile-sop.pdf` page 1,
   700.2 ms), classroom in Chrome (`#class-mic` off and `#class-handsfree` disabled until mic turned
   on, `#class-pause` toggled, `#class-video` region pointed at `15%, 20%, 50%, 50%`), all 5
   commands (`remember`, `example`, `mistake`, `compare`, `forget`), expert pupil pause question
   (`importance = 5`, 3377.4 ms, passed to raise threshold in MMU), silent mode deferred question,
   public sources (`tavily`, 5 rules checked, 165689.9 ms), debrief (6 cases, first answer taken
   back via `/api/guardian/reask` and fixed), and published v1 (`12` units, `17` links, `6` cases,
   `1` source, `8` evidence excerpts; `step-2` set to `"community"` raised 4 repeating units with
   it, and `step-7` set to `"restricted"`).
2. **As learners (`/learn/`), visitor and member:** visitor saw 6 public units and 4 exam cases;
   member saw 11 units (6 public + 5 community) and 5 exam cases (scored 5/5); neither saw
   `restricted`. Listening returned 32 timed words (160.1 ms), braille 1 page (161 BRF chars),
   illustration 143.6 ms, typed and spoken quiz answers graded right. Covered questions answered in
   English (997.4 ms, 4 citations), French (584.6 ms, 4 citations), and by voice; off-topic refused
   (`off_topic`); distress answered with care (`welfare`). Asking about the closed `"five vials"`
   rule returned `nothing_yet` with 0 citations to the visitor (no leak, ticket issued) and a
   grounded answer citing `step-2` to the member. The Ed25519 package verified (`sig_valid = true`),
   rejected a 2-char edit (`tampered_rejected = true`), synced 1 offline review, and resumed on a
   second device (`state = "learned"`). Answering the inbox and publishing v2 kept all 5 community
   levels without re-specifying them; withdrawing and deleting left only the baseline data.
