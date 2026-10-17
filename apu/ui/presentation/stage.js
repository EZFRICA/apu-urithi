/**
 * stage.js - what each key on the Apprentice Deck does, in each part of learning.
 *
 * The deck is the learner's page for someone who cannot see it. It learns what a guardian
 * published, at this learner's level, the way /learn/ does: the path part by part (read in
 * the guardian's words, heard, in braille), practice on the cases the guardian decided for
 * a part, graded by code, and the exam, marked only at the end. Questions can be asked out
 * loud anywhere on the path, and are answered from what the learner may see, cited.
 *
 * Three parts, chosen with the wheel: the path, practice, the exam. A key means the same
 * thing in all three where it can: Read reads what is in front of the learner, Braille
 * prints it, Keep puts it in the notebook, Talk asks or answers. Where a key has nothing to
 * do in a part, it says so out loud rather than doing nothing, because a key that does
 * nothing is indistinguishable, without sight, from a key that is broken.
 *
 * No DOM and no Three.js here, so node can run it against a fake server (tests/presentation).
 */

export const CHAPTERS = ["path", "practice", "exam"];

export const CHAPTER_NAMES = {
  path: "The path",
  practice: "Practice",
  exam: "The exam",
};

/** Yes or no in what was said, or null: decided by code, never guessed. */
export function yesOrNo(said) {
  const words = String(said || "").toLowerCase().match(/[\p{L}']+/gu) || [];
  const yes = words.some((w) => ["yes", "yeah", "yep", "oui", "ouais"].includes(w));
  const no = words.some((w) => ["no", "nope", "non"].includes(w));
  return yes === no ? null : yes;
}

export class Stage {
  constructor({ bridge, prompter, device = {}, onStatus = () => {}, lang = "en" }) {
    this.bridge = bridge;
    this.prompter = prompter;
    this.device = { setInUse: () => {}, ...device };
    this.onStatus = onStatus;
    this.lang = lang;
    this.bodies = [];
    this.body = null;
    this.units = [];
    this.index = 0;
    this.chapter = "path";
    this.quiz = [];
    this.exam = null;
    this.examIndex = 0;
    this.examAnswers = {};
    this.lastAnswer = null;
    this.talking = null;
    this.busy = false;
  }

  get bodyId() {
    return this.body?.body_id || null;
  }

  get unit() {
    return this.units[this.index] || null;
  }

  // ── loading ────────────────────────────────────────────────────────────────

  /** What this learner may learn, and the knowledge to open: the one named, else the first. */
  async load(bodyId = null) {
    this.bodies = await this.bridge.bodies();
    if (!this.bodies.length) {
      this.body = null;
      this.units = [];
      this.onStatus("offline", this.bridge.isOnline ? "Nothing to learn yet" : "Server not answering");
      this.prompter.showNotice(this.bridge.isOnline
        ? "Nothing is published yet that this learner may learn. Choose another learner above, " +
          "or a guardian publishes a knowledge first (scripts/demo_map.py teaches and publishes one)."
        : "Urithi's server is not answering. Start it with scripts/serve.sh.");
      return false;
    }
    return this.select(this.bodies.some((b) => b.body_id === bodyId) ? bodyId : this.bodies[0].body_id);
  }

  async select(bodyId) {
    const path = await this.bridge.path(bodyId);
    this.body = path.body || this.bodies.find((b) => b.body_id === bodyId);
    this.units = path.units || [];
    this.index = 0;
    this.quiz = [];
    this.exam = null;
    this.lastAnswer = null;
    this.onStatus("connected", `${this.body.guardian}'s knowledge`);
    await this.setChapter("path", { speak: false });
    return true;
  }

  // ── the wheel, and moving along the path ───────────────────────────────────

  async turnWheel() {
    const next = CHAPTERS[(CHAPTERS.indexOf(this.chapter) + 1) % CHAPTERS.length];
    return this.setChapter(next);
  }

  async setChapter(name, { speak = true } = {}) {
    if (!CHAPTERS.includes(name)) return;
    this.chapter = name;
    this.prompter.closeSheet?.();
    if (!this.body) return;
    let text;
    if (name === "path") text = this._pathSummary();
    else if (name === "practice") text = await this._practiceIntro();
    else text = await this._examIntro();
    this.prompter.show(text, "apprentice", CHAPTER_NAMES[name]);
    // Heard with the part's name first; on screen the name is already the label above it.
    if (speak) await this._say(`${CHAPTER_NAMES[name]}. ${text}`, { show: false });
  }

  /** The next part, or the one before: arrows on the keyboard. Practice follows the part. */
  async move(step) {
    if (!this.body || this.chapter === "exam") {
      if (this.body) await this._say("The exam takes the parts in order. Turn the wheel to the path.");
      return;
    }
    const to = this.index + step;
    if (to < 0 || to >= this.units.length) {
      await this._say(to < 0 ? "This is the first part." : "This is the last part. Turn the wheel to the exam.");
      return;
    }
    this.index = to;
    this.quiz = [];
    await this.setChapter(this.chapter);
  }

  _partLine() {
    const unit = this.unit;
    if (!unit) return "This knowledge has no part this learner may read.";
    return `Part ${this.index + 1} of ${this.units.length}: ${unit.text}`;
  }

  _pathSummary() {
    const parts = this.units.length;
    return `${this.body.name}, taught by ${this.body.guardian}: ${parts} part${parts === 1 ? "" : "s"}. ` +
      `${this._partLine()} Press R to hear it in ${this.body.guardian}'s words, B for braille, ` +
      "the arrows for another part. Hold Space to ask a question.";
  }

  async _practiceIntro() {
    if (!this.unit) return this._partLine();
    if (!this.quiz.length) {
      const reply = await this.bridge.unit(this.unit.unit_id);
      this.quiz = reply.quiz || [];
    }
    if (!this.quiz.length) {
      return `${this._partLine()} ${this.body.guardian} decided no case on this part. ` +
        "The arrows go to another part.";
    }
    return `${this._partLine()} ${this.quiz[0].question} Hold Space and say yes or no, or press Y or N.`;
  }

  async _examIntro() {
    if (!this.exam) {
      const reply = await this.bridge.exam(this.bodyId);
      this.exam = reply.cases || [];
      this.examIndex = 0;
      this.examAnswers = {};
    }
    if (!this.exam.length) {
      return `There is no exam yet: ${this.body.guardian} has decided no case this learner may answer.`;
    }
    return this._question();
  }

  _question() {
    const item = this.exam[this.examIndex];
    return `Case ${this.examIndex + 1} of ${this.exam.length}. ${item.question} ` +
      "Hold Space and say yes or no, or press Y or N. It is marked at the end.";
  }

  // ── the keys ───────────────────────────────────────────────────────────────

  /** One press of one part of the deck. Talk is held, and handled by talk() and release(). */
  async press(partId) {
    if (partId === "btn_read") return this.read();
    if (partId === "btn_book") return this.keep();
    if (partId === "btn_braille") return this.print();
    if (partId === "mode_wheel") return this.turnWheel();
    if (partId === "speaker_grille") return this.bridge.replay();
    return null;
  }

  /** Read whatever is in front of the learner: the part, heard in the guardian's words. */
  async read() {
    if (!this.body || this.busy) return;
    if (this.chapter === "path") {
      if (!this.unit) return this._say(this._partLine());
      await this._working("btn_read", "Reading the part", async () => {
        const words = `${this.unit.text}. ${this.body.guardian} said: "${this.unit.quote}"`;
        try {
          const reply = await this.bridge.listen(this.unit.unit_id, this.lang);
          this.prompter.show(reply.text || words, "expert", `Part ${this.index + 1}`);
          this.bridge.play(reply.audio, reply.mime);
        } catch {
          // No voice here: the guardian's words, on screen and read by the stage's own voice.
          await this._say(words);
        }
      });
    } else if (this.chapter === "practice") {
      await this._say(await this._practiceIntro());
    } else {
      const text = this.exam?.length && this.examIndex < this.exam.length ? this._question() : await this._examIntro();
      this.prompter.show(text, "apprentice", CHAPTER_NAMES.exam);
      await this._say(text, { show: false });
    }
  }

  /** The part in front of the learner, sent to the embosser. A second press puts the sheet away. */
  async print() {
    if (this.prompter.sheetVisible) {
      this.prompter.closeSheet();
      this.device.setInUse("btn_braille", false);
      return;
    }
    if (!this.body || this.busy) return;
    if (this.chapter === "exam" || !this.unit) {
      await this._say("Braille prints a part. Turn the wheel to the path.");
      return;
    }
    await this._working("btn_braille", "Embossing the part", async () => {
      const reply = await this.bridge.braille(this.unit.unit_id, 2, this.lang);
      this.prompter.printSheet({
        title: `Part ${this.index + 1}, Grade 2`, pages: reply.pages_unicode || [], brf: reply.brf,
        filename: `part-${this.index + 1}-grade-2.brf`,
      });
      const count = reply.pages_unicode?.length || reply.pages || 0;
      await this._say(`Part ${this.index + 1} is on the embosser: ${count} page${count === 1 ? "" : "s"}.`,
                      { show: false });
    });
    this.device.setInUse("btn_braille", this.prompter.sheetVisible);
  }

  /** Keep, as on /learn/: the last answer whole, or else the part in the guardian's words. */
  async keep() {
    if (!this.body || this.busy) return;
    if (!this.lastAnswer && !this.unit) return this._say("There is nothing to keep yet.");
    await this._working("btn_book", "Keeping it in the notebook", async () => {
      const kept = this.lastAnswer
        ? { kind: "whole", text: this.lastAnswer.text, question: this.lastAnswer.question, unitIds: this.lastAnswer.unitIds }
        : { kind: "excerpt", text: this.unit.quote || this.unit.text, unitIds: [this.unit.unit_id] };
      await this.bridge.keep(this.bodyId, kept);
      const what = this.lastAnswer ? "The answer" : `Part ${this.index + 1}`;
      this.lastAnswer = null;
      await this._say(`${what} is kept in your notebook.`);
    });
  }

  /** Talk, pressed: on the path it asks a question; in practice and the exam it answers. */
  async talk() {
    if (!this.body) return false;
    const answering = this.chapter !== "path";
    if (this.chapter === "practice" && !this.quiz.length) {
      await this._say("There is no case to answer on this part. On the path, Talk asks a question.");
      return false;
    }
    if (this.chapter === "exam" && (!this.exam?.length || this.examIndex >= this.exam.length)) {
      await this._say("There is nothing to answer. Turn the wheel to the path.");
      return false;
    }
    if (!(await this.bridge.startTalking())) {
      this._notice(answering
        ? "The microphone is not available. Press Y for yes, or N for no."
        : "The microphone is not available here, so questions cannot be asked aloud on this stage.");
      return false;
    }
    this.talking = answering ? "answer" : "ask";
    this.device.setInUse("btn_talk", true);
    this.onStatus("listening", answering ? "Listening to the answer" : "Listening to the question");
    this.prompter.setSpeaker("listening");
    return true;
  }

  /** Talk, let go. */
  async release() {
    if (!this.bridge.isRecording) return;
    const audio = this.bridge.stopTalking();
    const what = this.talking;
    this.talking = null;
    this.device.setInUse("btn_talk", false);
    if (!audio) {
      this.onStatus("connected", `${this.body.guardian}'s knowledge`);
      return;
    }
    if (what === "ask") await this.ask({ audio });
    else await this.answer({ audio });
  }

  /** A question, said or typed, answered from what this learner may see, every sentence cited. */
  async ask({ question = "", audio = null } = {}) {
    if (!this.body) return;
    await this._working("btn_talk", "Answering the question", async () => {
      let asked = question.trim();
      if (!asked && audio) asked = ((await this.bridge.hear(audio)).said || "").trim();
      if (!asked) return this._say("I did not hear a question. Hold Space and ask again.");
      const reply = await this.bridge.ask(this.bodyId, asked, this.unit?.unit_id || null, this.lang);
      const cited = (reply.citations || []).map((c) => c.unit_id);
      this.lastAnswer = reply.kind === "worded" || reply.kind === "extractive"
        ? { text: reply.text, question: asked, unitIds: cited } : null;
      const keep = this.lastAnswer ? " Press Enter to keep it." : "";
      this.prompter.show(`"${asked}" ${reply.text}${keep}`, reply.citations?.length ? "expert" : "apprentice",
                         reply.citations?.length ? `From ${this.body.guardian}'s words` : "Asked");
      await this._say(`${reply.text}${keep}`, { show: false });
    });
  }

  /** An answer, spoken or keyed. Unclear answers are asked again, never graded. */
  async answer(payload) {
    if (this.chapter === "practice") return this._answerCase(payload);
    if (this.chapter === "exam") return this._answerExam(payload);
  }

  async _answerCase(payload) {
    const item = this.quiz[0];
    if (!item) return;
    await this._working("btn_talk", "Checking against what the guardian decided", async () => {
      const reply = await this.bridge.quiz(item.case_id, this._given(payload));
      if (!reply.understood) {
        await this._say(`Heard: "${reply.heard || ""}". I did not catch a yes or a no. Say yes, or no.`);
        return;
      }
      this.quiz = [...this.quiz.slice(1), item];
      const verdict = `${reply.right ? "Right" : "Not quite"}. ${reply.by} said: "${reply.said}"`;
      this.prompter.show(`${verdict} Press R for the next case, or the arrows for another part.`, "expert",
                         reply.right ? "Right" : "Not quite");
      await this._say(verdict, { show: false });
    });
  }

  async _answerExam(payload) {
    if (!this.exam?.length || this.examIndex >= this.exam.length) return;
    await this._working("btn_talk", "Listening to the answer", async () => {
      let given = payload.answer ?? yesOrNo(payload.said);
      if (given === null && payload.audio) given = yesOrNo((await this.bridge.hear(payload.audio)).said);
      if (given === null) {
        await this._say("I did not catch a yes or a no. Say yes, or no.");
        return;
      }
      this.examAnswers[this.exam[this.examIndex].case_id] = given;
      this.examIndex += 1;
      if (this.examIndex < this.exam.length) {
        await this._say(this._question());
        return;
      }
      const marked = await this.bridge.markExam(this.bodyId, this.examAnswers);
      const wrong = (marked.feedback || []).filter((f) => !f.right)
        .map((f) => `${f.question} ${f.by} said: "${f.said}"`);
      const text = `${marked.correct} of ${marked.total} right.` +
        (wrong.length ? ` ${wrong.join(" ")} Those parts come back for review soon.` : "") +
        " Turn the wheel to go back to the path.";
      this.prompter.show(text, "expert", "Marked");
      await this._say(text, { show: false });
    });
  }

  /** Practice is graded by the server from a key, words or a recording. */
  _given({ answer = null, said = null, audio = null }) {
    if (answer !== null && answer !== undefined) return { answer };
    if (said) return { said };
    return { audio };
  }

  // ── plumbing ───────────────────────────────────────────────────────────────

  async _working(partId, status, work) {
    this.busy = true;
    this.device.setInUse(partId, true);
    this.onStatus("thinking", status);
    try {
      await work();
    } catch (error) {
      this._notice(error?.status && error.status < 500
        ? String(error.message || "That was refused.")
        : "Urithi's server did not answer. Is it running?");
    } finally {
      this.busy = false;
      if (partId !== "btn_braille") this.device.setInUse(partId, false);
      if (this.bridge.isOnline && this.body) {
        this.onStatus("connected", `${this.body.guardian}'s knowledge`);
      }
    }
  }

  /** Shown and spoken: everything the deck says can also be read. */
  async _say(text, { show = true } = {}) {
    if (show) this.prompter.show(text, "apprentice");
    try {
      await this.bridge.say(text);
    } catch (error) {
      // The words are on screen and with the screen reader; a silent deck is still usable.
    }
  }

  _notice(message) {
    this.prompter.showNotice(message);
    this.onStatus("error", "Something needs attention");
  }
}
