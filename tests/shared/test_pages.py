"""
The guardian's and the learner's pages: what they must never do.

Target: guardian/ui/teach/, learner/ui/learn/

The behaviour is proved against the routes in tests/learner/ and tests/guardian/; these
check the pages hold the rules that live only in the browser.
"""

import pathlib
import re

from fastapi.testclient import TestClient

ROOT = pathlib.Path(__file__).resolve().parents[2]
LEARN_HTML = (ROOT / "learner/ui/learn/index.html").read_text(encoding="utf-8")
LEARN_JS = (ROOT / "learner/ui/learn/learn.js").read_text(encoding="utf-8")
SW = (ROOT / "learner/ui/learn/sw.js").read_text(encoding="utf-8")
TEACH_HTML = (ROOT / "guardian/ui/teach/index.html").read_text(encoding="utf-8")
TEACH_JS = (ROOT / "guardian/ui/teach/teach.js").read_text(encoding="utf-8")


def test_both_pages_say_the_identity_is_simulated():
    for page in (LEARN_HTML, TEACH_HTML):
        assert 'class="badge simulated"' in page and "Simulated identity" in page
        assert 'aria-describedby="simulated"' in page, "the selector itself says it"


def test_text_from_the_server_is_never_markup():
    """A guardian's words, a unit, an answer: all set as text. innerHTML only ever clears."""
    for name, source in (("learn.js", LEARN_JS), ("teach.js", TEACH_JS)):
        for assignment in re.findall(r"innerHTML\s*=\s*([^;]+);", source):
            assert assignment.strip() == '""', f"{name} writes markup: innerHTML = {assignment}"


def test_the_keyboard_never_acts_while_someone_is_typing():
    for name, source in (("learn.js", LEARN_JS), ("teach.js", TEACH_JS)):
        handler = source[source.index('addEventListener("keydown"'):][:900]
        assert '"INPUT"' in handler and '"TEXTAREA"' in handler, name
    assert "event.metaKey || event.ctrlKey || event.altKey" in LEARN_JS, "browser shortcuts are not ours"


def test_holding_space_to_talk_is_released_on_key_up():
    for source in (LEARN_JS, TEACH_JS):
        assert 'addEventListener("keyup"' in source


def test_the_offline_cache_never_answers_for_the_server():
    """An old answer served as fresh is worse than an honest "offline"."""
    assert 'url.pathname.startsWith("/api/")) return;' in SW
    assert "/api/" not in SW.split("const FILES")[1].split("]")[0], "no API response is precached"


def test_offline_says_what_works_and_what_waits():
    assert "questions wait" in LEARN_JS and "les questions attendent" in LEARN_JS
    assert "askOffline" in LEARN_JS


def test_both_languages_carry_every_string():
    for name, source in (("learn.js", LEARN_JS), ("teach.js", TEACH_JS)):
        blocks = re.split(r"\n  fr: \{", source.split("const STRINGS = {")[1].split("\n};")[0])
        # A key starts a line or follows a comma, and its value starts right after it.
        keys = [set(re.findall(r"(?m)(?:^|,|\{)\s*([a-zA-Z_]+):\s*[\"(`{\[]", block)) - {"en", "fr"} for block in blocks]
        assert keys[0] == keys[1], f"{name}, missing in one language: {keys[0] ^ keys[1]}"
        used = set(re.findall(r"""this\.t\("([a-zA-Z]+)\"""", source))
        html = TEACH_HTML if name == "teach.js" else LEARN_HTML
        used |= set(re.findall(r'data-i18n(?:-placeholder)?="([a-zA-Z]+)"', html))
        assert used <= keys[0], f"{name} uses strings it does not define: {used - keys[0]}"


def test_a_learners_ticket_is_sent_without_their_name():
    """The server keeps the question without a name; the ticket on the device is the only tie."""
    call = LEARN_JS[LEARN_JS.index('this.api("tickets"'):].split("\n")[0]
    assert "tickets:" in call and "person" not in call
    assert "urithi.questions.${this.person}" in LEARN_JS, "kept on the device, per person"


def test_teaching_a_task_again_continues_its_map_and_answers_close_after_publishing():
    start = TEACH_JS[TEACH_JS.index("  async start(task)"):][:500]
    assert "slug(m.task) === slug(task)" in start and "this.resume(existing)" in start
    publish = TEACH_JS[TEACH_JS.index("  async publish()"):]
    assert publish.index("/api/guardian/publish") < publish.index("/answered"), "closed only once published"


def test_the_pages_are_served_with_their_files():
    from server import app

    client = TestClient(app)
    for path in ("/learn/", "/learn/learn.js", "/learn/learn.css", "/learn/sw.js",
                 "/learn/manifest.webmanifest", "/teach/", "/teach/teach.js", "/teach/teach.css"):
        assert client.get(path).status_code == 200, path


def test_a_kept_package_leaves_the_device_when_the_library_no_longer_shows_it():
    """Withdrawing reaches every device that kept the knowledge, the next time it is online."""
    reconcile = LEARN_JS[LEARN_JS.index("  async reconcileKept(bodies)"):][:700]
    assert "if (!listed[bodyId])" in reconcile and "this.forgetKept(bodyId)" in reconcile
    opening = LEARN_JS[LEARN_JS.index("  async openPath(bodyId)"):][:1400]
    assert "error.status === 404" in opening and "this.forgetKept(bodyId)" in opening
    home = LEARN_JS[LEARN_JS.index("  async showHome()"):][:900]
    assert home.index("this.reconcileKept(bodies)") < home.index("catch"), \
        "only an answer from the library removes anything, never a failure to reach it"


def test_an_expired_package_is_not_opened_and_a_new_version_replaces_the_kept_one():
    assert "new Date(pkg.manifest.valid_until) <= new Date()" in LEARN_JS
    opening = LEARN_JS[LEARN_JS.index("  async openPath(bodyId)"):][:1400]
    assert "if (this.expired(kept))" in opening
    assert "kept.manifest.version !== path.body.version" in opening


def test_nothing_kept_reads_as_nothing():
    """Measured: a missing package read back as the IndexedDB request itself, which is truthy."""
    assert "result?.result ?? result" not in LEARN_JS
    assert "result instanceof IDBRequest ? result.result : result" in LEARN_JS


def test_the_exam_marks_only_at_the_end_and_offline_as_the_server_does():
    """No answer is shown before the last question; a kept package is marked on the device."""
    answer = LEARN_JS[LEARN_JS.index("  examAnswer(value) {"):][:400]
    assert "this.examNext()" in answer and "said" not in answer, "nothing of the guardian's answer mid-exam"
    mark = LEARN_JS[LEARN_JS.index("  async markExam() {"):][:1600]
    assert "this.rateOffline(uid, right ? 3 : 1)" in mark, "offline marks move the reviews too"
    keys = LEARN_JS[LEARN_JS.index('if (!$("exam").hidden) {'):][:400]
    assert all(f'key === "{k}"' in keys for k in ("y", "n", "d", "Escape"))


def test_a_package_is_checked_before_it_is_kept_from_the_server_or_a_file():
    """Signature and hash on the way in; a file opens at its reader's level, never above."""
    unpack = LEARN_JS[LEARN_JS.index("  async unpack(signed) {"):][:1600]
    assert 'crypto.subtle.verify({ name: "Ed25519" }' in unpack and "manifest.sha256" in unpack
    assert unpack.index("crypto.subtle.verify") < unpack.index("return { manifest"), "nothing returned unchecked"
    for name in ("  async download() {", "  async refreshKept(bodyId) {", "  async importFile(file) {"):
        body = LEARN_JS[LEARN_JS.index(name):][:1400]
        assert body.index("this.unpack(") < body.index("db.put("), f"{name.strip()} keeps only what it checked"
    imported = LEARN_JS[LEARN_JS.index("  async importFile(file) {"):][:1400]
    assert 'this.t("tooHigh")' in imported and "this.expired(packed)" in imported


def test_a_question_being_answered_is_not_forgotten_by_going_back_to_the_inbox():
    resume = TEACH_JS[TEACH_JS.index("  async resume(m, question) {"):][:900]
    assert "store.get(`urithi.answering.${m.map_id}`" in resume
    assert "store.set(`urithi.answering.${this.mapId}`, this.answering)" in resume


def test_a_kept_lesson_is_refreshed_once_at_a_time():
    """Measured: opening a lesson and the home page both refreshed it, building it twice."""
    refresh = LEARN_JS[LEARN_JS.index("  async refreshKept(bodyId) {"):][:500]
    assert "this.refreshing.has(bodyId)" in refresh and "finally { this.refreshing.delete(bodyId); }" in refresh


FORBIDDEN = re.compile(r"\b(lessons?|courses?|leçons?)\b|(?<!en )(?<!au )\bcours\b", re.IGNORECASE)


def test_what_is_handed_on_is_knowledge_never_a_lesson():
    """Measured: the learner's page offered to "Open a lesson file", eleven strings in two
    languages. What a guardian hands on is knowledge (docs/architecture.md), in every word a
    person reads and every word written about it."""
    found = []
    for package in ("apu", "library", "exchange", "guardian", "learner"):
        for path in (ROOT / package).rglob("*"):
            if path.suffix not in (".py", ".js", ".html", ".json") or "__pycache__" in path.parts:
                continue
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if FORBIDDEN.search(line.replace("of course", "")):
                    found.append(f"{path.relative_to(ROOT)}:{number}")
    assert not found, found


def test_switching_language_rebuilds_what_the_server_sent():
    """Measured: switched to French, the home page still said "Taught by Ezekias · 13 units"."""
    start = LEARN_JS.index('$("lang").addEventListener("click"')
    handler = LEARN_JS[start:LEARN_JS.index("\n    });", start)]
    assert "this.showHome()" in handler and "this.openPath(" in handler


def test_every_guardian_page_says_who_is_asking():
    """A guardian's routes answer that guardian alone; a page that does not say who is asking
    is refused on every call. The guardian's page (classroom included) and the stage each send
    `person_id` from one helper."""
    classroom = (ROOT / "guardian/ui/teach/classroom.js").read_text(encoding="utf-8")
    bridge = (ROOT / "apu/ui/presentation/bridge.js").read_text(encoding="utf-8")
    assert "const post = (path, body) => fetch(withWho(path)" in TEACH_JS
    assert "post, mapId: () => this.mapId" in TEACH_JS, "the classroom posts through the page's helper"
    assert "fetch(" not in classroom, "the classroom never calls the server on its own"
    assert "this.fetch(this._url(path)" in bridge
    for call in re.findall(r"fetch\(\s*`/api/guardian/(?:map|exam)[^`]*`", TEACH_JS):
        raise AssertionError(f"teach.js asks without saying who: {call}")


def test_the_classroom_is_a_mode_of_the_guardians_page():
    """Step 4: the separate screen-watching page is gone; the class opens over the guardian's page."""
    assert not (ROOT / "guardian/ui/apprentice").exists()
    assert '<dialog id="classroom"' in TEACH_HTML and 'id="class-prompter" class="prompter"' in TEACH_HTML
    classroom = (ROOT / "guardian/ui/teach/classroom.js").read_text(encoding="utf-8")
    assert 'this.post("/api/guardian/observe"' in classroom and 'this.post("/api/guardian/answer"' in classroom
    # One question at a time is the server's (it asks none while one waits); the class keeps
    # sending what it sees, so an answer is about what the guardian did since the question.
    assert "if (this.paused || !this.capture) return;" in classroom, "the class keeps watching while a question waits"
    routes_py = (ROOT / "guardian/api/routes.py").read_text(encoding="utf-8")
    assert 'if session["pending"] or not session["detector"].is_pause(at):' in routes_py, "one question at a time"
    assert "if (this.classroom.pending) {\n        const reply = await this.classroom.answer(" in TEACH_JS


def test_a_class_can_be_talked_to_and_read_from_beside_the_guardians_work():
    """Measured in a real class: the guardian worked in the window they shared, so this page sat
    behind it; frames stopped changing, no question came, and there was no way to answer but to
    go back to the tab. The capture now runs from a worker and the stream itself; the question
    opens the microphone; the question, the microphone and the notes float above the work."""
    capture = (ROOT / "guardian/ui/teach/capture.js").read_text(encoding="utf-8")
    assert "new Worker(URL.createObjectURL(new Blob([TICKER]" in capture, "a clock a background tab does not slow"
    assert "await this.grabber.grabFrame()" in capture, "the frame from the stream, not from a hidden video"
    assert "if (first || changed > 0) {" in capture, "only a changed screen is sent to be read"
    assert "this.voice(reply.audio, reply.words, reply.question, () => this.listenForAnswer());" in TEACH_JS
    asking = TEACH_JS[TEACH_JS.index("      onQuestion: (reply) => {"):][:900]
    assert "if (this.listening) {" in asking and "this.waitingQuestion = reply;" in asking, \
        "measured: a question was said over the guardian speaking; it waits"
    assert "if (waiting && this.classroom.open) this.classroom.onQuestion(waiting);" in TEACH_JS
    assert "if (text !== heard) { heard = text; spoke = true; last = performance.now(); }" in TEACH_JS, \
        "measured: the same words sent again through the silence kept the answer from ever ending"
    assert "documentPictureInPicture.requestWindow(" in TEACH_JS and 'id="class-float"' in TEACH_HTML
    assert 'id="class-talk"' in TEACH_HTML and 'id="class-say"' in TEACH_HTML, "an answer from inside the class"
    assert 'if (this.classroom?.open) this.note(who === "guardian" ? "said" : (/\\?\\s*$/.test(text) ? "asked" : "urithi"), text);' in TEACH_JS
    assert "this.note(\"saw\", change);" in TEACH_JS, "what Urithi saw stays on the notes, not one line"


def test_a_guardian_can_ask_urithi_to_remember_the_screen():
    """Asked by the owner after a real class: a button and a spoken "remember this" keep the
    screen with what was said of it, even while a question waits."""
    assert 'id="class-remember"' in TEACH_HTML and "Retiens cet écran" in TEACH_JS
    assert "if (remembered) return await this.rememberScreen(said.slice(remembered[0].length).trim());" in TEACH_JS
    assert "if (this.classroom.open && said && REMEMBER_ANYWHERE.test(said)) return await this.rememberScreen(said);" in TEACH_JS, \
        "measured: a request in the middle of a sentence was taught as a rule, and asked about"
    assert 'const heard = await post("/api/guardian/hear", { map_id: this.mapId, audio: said.audio })' in TEACH_JS, \
        "measured: a recording with no live words became an answer; it is heard first"
    assert "      if (heard.said) said.text = heard.said;\n    }\n    if (said.text) {" in TEACH_JS
    assert TEACH_JS.index("if (remembered) return") < TEACH_JS.index("if (this.classroom.pending) {"), \
        "remembering comes before answering the question waiting"
    classroom = (ROOT / "guardian/ui/teach/classroom.js").read_text(encoding="utf-8")
    assert 'this.post("/api/guardian/remember", { map_id: this.mapId(), frame, said' in classroom


def test_a_knowledge_can_be_deleted_from_the_guardians_page_with_a_second_press():
    """Asked by the owner: there was no way to delete a knowledge. Two presses, as withdrawing."""
    assert "li.appendChild(this.deleteButton(m));" in TEACH_JS
    handler = TEACH_JS[TEACH_JS.index("  deleteButton(m) {"):][:1200]
    assert "if (!armed) {" in handler and '{ method: "DELETE" }' in handler
    assert 'button.textContent = this.t("deleteIt"); }, 4000);\n        return;' in handler, \
        "the first press only asks; nothing is deleted until the second"
    assert "Le supprimer pour de bon ? Appuie encore" in TEACH_JS


def test_a_learner_asking_aloud_is_heard_without_live_words():
    assert 'const heard = await this.api("hear", { method: "POST", body: JSON.stringify({ ...this.me(), audio: said.audio }) })' in LEARN_JS
    assert "        if (heard.said) said.text = heard.said;\n      }\n      if (said.text) { this.prompter.heard(said.text); $(\"question\").value" in LEARN_JS, \
        "what was heard is the question asked"


def test_a_question_waiting_is_not_forgotten_when_the_screen_is_kept():
    """Found in review: "keep this" while a question waited dropped it on the page and not on the
    server, and the class never asked again. Widened in the second review of 2026-10-14: a save made
    from there dropped it too; now any reply that asks nothing else keeps it."""
    keeping = TEACH_JS[TEACH_JS.index("  async rememberScreen("):TEACH_JS.index("  async float()")]
    assert "const asked = this.classroom.pending;" in keeping
    assert "if (asked && !this.classroom.pending && !reply.question) {\n      this.classroom.pending = asked;" in keeping
    assert '$("class-question").hidden = false;' in keeping and '$("class-question").textContent = asked.question;' in keeping
    assert '$("class-status").textContent = this.t("stillAsking");' in keeping
    assert "Kept. Urithi's question still waits for you." in TEACH_JS
    assert "Gardé. La question d'Urithi t'attend toujours." in TEACH_JS


def test_the_guardian_holds_the_switches_and_urithi_never_listens_on_its_own():
    """docs/decisions/0013, decided by the owner: no microphone unless the guardian turns it on;
    listening after a question only while that is on too; the vision on and off by them."""
    classroom = (ROOT / "guardian/ui/teach/classroom.js").read_text(encoding="utf-8")
    starting = classroom[classroom.index("  async start("):][:700]
    assert "getUserMedia" not in starting and "if (listen) await this.microphone(true);" in starting, \
        "the class does not open the microphone by itself"
    assert 'this.micOn = store.get("urithi.class.mic", false);' in TEACH_JS, "off until the guardian turns it on"
    listening = TEACH_JS[TEACH_JS.index("  async listenForAnswer("):][:700]
    assert 'if (!this.micOn) { $("class-status").textContent = this.t("micIsOff"); return; }' in listening
    assert "if (!byHand && !this.handsFree) return;" in listening
    assert 'if (this.classroom?.open && !this.micOn) { $("class-status").textContent = this.t("micIsOff"); return; }' in TEACH_JS, \
        "holding Space does not open a microphone the guardian turned off"
    for switch in ('id="class-mic"', 'id="class-handsfree"', 'id="class-pause" class="quiet switch" aria-pressed'):
        assert switch in TEACH_HTML, switch
    assert "Micro : coupé" in TEACH_JS and "Vision : coupée" in TEACH_JS


def test_an_answer_in_class_never_leaves_listening_on_screen():
    """Measured in a real class: the live words were unavailable, "Listening…" stayed while
    the recording was heard, and an answer that could not be heard said nothing at all."""
    assert 'this.prompter.show("you", this.t("writingDown"), { linger: 15000 });' in TEACH_JS
    assert 'if (reply.error) { this.line("apprentice", reply.error); this.prompter.speaking(reply.error); }' in TEACH_JS
    assert "Entendu. Je le note" in TEACH_JS


# ── the redesign: one look, two sides, a tree ────────────────────────────────

TREE_JS = (ROOT / "apu/ui/shared/tree.js").read_text(encoding="utf-8")
SHOWCASE = (ROOT / "apu/ui/showcase/index.html").read_text(encoding="utf-8")


def test_the_guardians_page_loads_nothing_from_the_learners_side():
    """Measured: the guardian's page drew its look from ../learn/learn.css, a crossing in the
    pages that no import test could see. Both now share apu/ui/shared/urithi.css."""
    assert "learn/" not in re.sub(r'href="/learn/"', "", TEACH_HTML), "teach/index.html reaches into learn/"
    for page in (TEACH_HTML, LEARN_HTML, SHOWCASE):
        assert '<link rel="stylesheet" href="/shared/urithi.css">' in page


def test_the_theme_is_chosen_before_the_page_paints():
    """A dark page that flashes white is a page someone with light sensitivity closes."""
    for page in (TEACH_HTML, LEARN_HTML, SHOWCASE):
        head = page.split("</head>")[0]
        assert '<script src="/shared/theme.js"></script>' in head, "theme.js runs in the head, not as a module"
        assert 'class="quiet theme-toggle"' in page


def test_the_tree_answers_the_whole_keyboard():
    """The WAI-ARIA tree's keys; Space is left to the microphone."""
    for key in ("ArrowDown", "ArrowUp", "ArrowRight", "ArrowLeft", "Home", "End", "Enter"):
        assert f'case "{key}"' in TREE_JS, key
    assert 'case " "' not in TREE_JS
    assert 'setAttribute("role", "tree")' in TREE_JS and 'setAttribute("role", "treeitem")' in TREE_JS
    assert "label.textContent = node.label" in TREE_JS, "a person's words, set as text"


def test_only_a_prerequisite_not_learned_is_reminded_and_never_enforced():
    """docs/architecture.md (docs/architecture-sides.md): prerequisites are reminded, not enforced."""
    assert 'detail.prerequisites.filter((p) => states.get(p.unit_id)?.state !== "learned")' in LEARN_JS
    opening = LEARN_JS[LEARN_JS.index("  async openUnit(index"):][:3000]
    assert "return" not in opening.split("unlearned")[1].split("this.renderContents()")[0], "never blocks"


def test_the_showcase_calls_no_side():
    assert "/api/" not in SHOWCASE and "<script type=\"module\"" not in SHOWCASE


# ── step 1: the words, and the teleprompter ──────────────────────────────────

PROMPTER_JS = (ROOT / "apu/ui/shared/teleprompter.js").read_text(encoding="utf-8")
KEYS_JS = (ROOT / "apu/ui/shared/keys.js").read_text(encoding="utf-8")


def test_each_page_listens_live_on_its_own_side():
    """A guardian's words go to the guardian's ear, a learner's to the learner's; never across."""
    assert 'url: () => withWho("/api/guardian/listen")' in TEACH_JS and "/api/learner/listen" not in TEACH_JS
    assert "url: () => `/api/learner/listen?${this.q({})}`" in LEARN_JS and "/api/guardian/listen" not in LEARN_JS
    for source in (TEACH_JS, LEARN_JS):
        assert "onPartial: (text) => this.prompter.partial(text)" in source


def test_the_words_of_a_voice_are_lit_by_its_own_clock():
    """Each word lit when the audio reaches it, not on a guess: the clock is the audio's."""
    assert 'span.classList.toggle("said", words[i].start <= t)' in PROMPTER_JS
    assert "this.timed(words, text, () => audio.currentTime)" in PROMPTER_JS
    assert "handle = this.prompter.timed(words || [], text, now)" in TEACH_JS
    assert "this.prompter.follow(this.audio, spoken, words)" in LEARN_JS


def test_question_mark_lists_the_keys_and_never_while_typing():
    assert 'if (event.key !== "?"' in KEYS_JS and '"INPUT", "TEXTAREA", "SELECT"' in KEYS_JS
    assert "this.dialog.showModal()" in KEYS_JS and "kbd.textContent = key" in KEYS_JS
    for source in (TEACH_JS, LEARN_JS):
        assert "new KeyMap(" in source



def test_the_learners_contents_open_on_the_guardians_sections():
    """Step 2: the path follows the contents the guardian set, sections included."""
    assert "label: u.section" in LEARN_JS and 'id: `section:${u.section}`' in LEARN_JS
    assert "if (node.index !== undefined) this.openUnit" in LEARN_JS, "a section opens, it is not a part to read"


def test_the_guardian_sets_the_contents_and_withdraws_from_the_page():
    assert 'post("/api/guardian/contents"' in TEACH_JS
    assert "withWho(`/api/guardian/body/${encodeURIComponent(m.body_id)}`), { method: \"DELETE\" }" in TEACH_JS
    assert "withdrawSure" in TEACH_JS, "two presses, so a slip does not withdraw a knowledge"
    assert "await this.whereWeWere();" in TEACH_JS



def test_the_learners_tutor_is_anchored_and_brings_the_path():
    """Step 5: the question names the part in view; the answer brings back what it rests on."""
    assert "unit_id: inView" in LEARN_JS
    assert "reply.rests_on_unlearned?.length" in LEARN_JS and 'this.t("goFirst")' in LEARN_JS
    assert '"notebook", { method: "POST"' in LEARN_JS and "this.loadSession();" in LEARN_JS
    assert 'if ($("no-screen").checked) this.readAloud(reply.text);' in LEARN_JS



def test_the_showcase_shows_what_is_inside():
    """Step 6: the four memories, the boundary, offline, braille, the guard; links to both sides and the stage."""
    for words in ("The guardian&#39;s working memory", "The library", "The learner&#39;s session", "The learner&#39;s progress"):
        assert words.replace("&#39;", "'") in SHOWCASE, words
    for words in ("Two sides, one boundary", "The guard", "Braille", "Offline", "never writes to the library"):
        assert words in SHOWCASE, words
    for link in ('href="/teach/"', 'href="/learn/"', 'href="/presentation/"'):
        assert link in SHOWCASE, link


def test_the_question_which_proposal_to_save_is_written_in_the_conversation():
    """Measured live: with two proposals waiting, "save this" asked which one aloud and on the class
    board, but the conversation showed nothing after the guardian's words."""
    branch = TEACH_JS[TEACH_JS.index("if (reply.ambiguous) {"):]
    branch = branch[:branch.index("return reply;")]
    assert 'this.line("apprentice", msg)' in branch


def test_a_class_reply_that_is_only_noted_is_written_where_the_guardian_looks():
    """Measured live: a sentence answering a waiting question got "Noted. Carry on." aloud, shown
    nowhere, so it read as a silence."""
    handler = TEACH_JS[TEACH_JS.index("onCaptured: (reply) => {"):]
    handler = handler[:handler.index("onEnd:")]
    written = handler[handler.index("if (spoken) {"):]
    written = written[:written.index("}")]
    assert 'this.line("apprentice", spoken)' in written and '$("class-status").textContent = spoken' in written
    assert 'const spoken = reply.question ? "" : (reply.answer || reply.noted || "");' in handler


def test_the_waiting_question_stays_in_view_with_pass_after_anything_else_done_in_class():
    """Measured live: a command and a pointed region hid the question while it still waited, so
    Pass could not be reached and the class stopped asking."""
    sync = TEACH_JS[TEACH_JS.index("  syncPending() {"):]
    sync = sync[:sync.index("\n  }\n")]
    assert '$("class-pass").hidden = !waiting;' in sync and '$("class-question").hidden = !waiting;' in sync
    send = TEACH_JS[TEACH_JS.index("  async send(said, audio) {"):]
    assert "this.syncPending();" in send[:send.index("\n  }\n")]
    point = TEACH_JS[TEACH_JS.index("  pointScreen(region) {"):]
    assert "this.syncPending();" in point[:point.index("\n  }\n")]


def test_every_page_declares_its_icon():
    """Measured live on 2026-10-15: the showcase and the teach page asked the server for /favicon.ico,
    which does not exist, and the browser logged a 404 error on every visit."""
    for path in ("apu/ui/showcase/index.html", "guardian/ui/teach/index.html", "learner/ui/learn/index.html",
                 "apu/ui/presentation/index.html"):
        assert 'rel="icon"' in (ROOT / path).read_text(encoding="utf-8"), path


def test_the_learner_can_read_and_remove_what_is_remembered_about_them():
    page = (ROOT / "learner/ui/learn/index.html").read_text(encoding="utf-8")
    js = (ROOT / "learner/ui/learn/learn.js").read_text(encoding="utf-8")
    assert 'id="remembered"' in page and 'aria-labelledby="remembered-title"' in page and 'id="remembered-list"' in page
    opening = js[js.index("    this.loadSession();\n    this.loadNotebook();"):][:120]
    assert "async loadRemembered()" in js and "this.loadRemembered();" in opening, "shown whenever a knowledge opens"
    remembered = js[js.index("async loadRemembered()"):js.index("async showSheet(")]
    assert "memory?${this.q({ body_id: bodyId })}" in remembered and '{ method: "DELETE" }' in remembered
    assert 'setAttribute("aria-label", this.t("forgetMemory"' in remembered, "each remove button says what it removes"
    for key in ("rememberedTitle", "rememberedLead", "aboutYou", "aboutThis", "aboutOther", "fromSaid", "forgetMemory"):
        assert js.count(f"{key}:") == 2, key                     # English and French


def test_the_stage_offers_every_guardian_not_sabine_alone():
    """Found on 2026-10-17: the stage presented Sabine's maps only."""
    page = (ROOT / "apu/ui/presentation/index.html").read_text(encoding="utf-8")
    js = (ROOT / "apu/ui/presentation/presentation.js").read_text(encoding="utf-8")
    assert '<label for="guardian-select">' in page and 'id="guardian-select"' in page
    assert "await this._fillGuardians();" in js and 'get("guardian")' in js
    change = js[js.index('this.dom.guardianSelect?.addEventListener("change"'):][:500]
    assert "this._asGuardian(event.target.value);" in change and "await this.stage.load();" in change
