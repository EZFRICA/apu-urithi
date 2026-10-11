/**
 * stage.js - what each key on the Apprentice Deck does, in each part of the job.
 *
 * The deck has three parts, chosen with the wheel: the Work Map, a case to book, and the
 * exam. A key means the same thing in all three where it can: Read reads what is in front
 * of the new hire, Braille prints the map, Book tries the save, Talk answers. Where a key
 * has nothing to do in a part, it says so out loud rather than doing nothing, because a
 * key that does nothing is indistinguishable, without sight, from a key that is broken.
 *
 * No DOM and no Three.js here, so node can run it against a fake server (tests/presentation).
 */

import { PRACTICE_CASE, caseAsSpeech } from "../shared/practice.js";

export const CHAPTERS = ["map", "case", "exam"];

export const CHAPTER_NAMES = {
  map: "The Work Map",
  case: "A case to book",
  exam: "The exam",
};

export class Stage {
  constructor({ bridge, prompter, device = {}, onStatus = () => {} }) {
    this.bridge = bridge;
    this.prompter = prompter;
    this.device = { setInUse: () => {}, ...device };
    this.onStatus = onStatus;
    this.maps = [];
    this.mapInfo = null;
    this.map = null;
    this.chapter = "map";
    this.exam = null;
    this.examIndex = 0;
    this.score = { right: 0, answered: 0 };
    this.busy = false;
  }

  get mapId() {
    return this.mapInfo?.map_id || null;
  }

  // ── loading ────────────────────────────────────────────────────────────────

  /** The maps on this machine, and the one to present: a confirmed one if there is any. */
  async load(mapId = null) {
    this.maps = await this.bridge.maps();
    if (!this.maps.length) {
      this.mapInfo = null;
      this.map = null;
      this.onStatus("offline", this.bridge.isOnline ? "No Work Map yet" : "Server not answering");
      this.prompter.showNotice(this.bridge.isOnline
        ? "There is no Work Map on this machine yet. An expert teaches one on the " +
          "apprentice's page first, by sharing their screen and working."
        : "The apprentice's server is not answering. Start it with scripts/serve.sh.");
      return false;
    }
    return this.select(mapId || this.maps[0].map_id);
  }

  async select(mapId) {
    this.mapInfo = this.maps.find((m) => m.map_id === mapId) || this.maps[0];
    this.map = await this.bridge.map(this.mapInfo.map_id);
    this.exam = null;
    this.examIndex = 0;
    this.score = { right: 0, answered: 0 };
    this.onStatus("connected", `${this.mapInfo.expert}'s map`);
    await this.setChapter("map", { speak: false });
    return true;
  }

  // ── the wheel ──────────────────────────────────────────────────────────────

  async turnWheel() {
    const next = CHAPTERS[(CHAPTERS.indexOf(this.chapter) + 1) % CHAPTERS.length];
    return this.setChapter(next);
  }

  async setChapter(name, { speak = true } = {}) {
    if (!CHAPTERS.includes(name)) return;
    this.chapter = name;
    this.prompter.closeSheet?.();
    if (!this.map) return;
    let text;
    if (name === "map") {
      text = this._mapSummary();
    } else if (name === "case") {
      text = caseAsSpeech(PRACTICE_CASE, "Press R to hear it again, Enter to book it.");
    } else {
      text = await this._examIntro();
    }
    this.prompter.show(text, "apprentice", CHAPTER_NAMES[name]);
    // Heard with the part's name first; on screen the name is already the label above it.
    if (speak) await this._say(`${CHAPTER_NAMES[name]}. ${text}`, { show: false });
  }

  _mapSummary() {
    const steps = this.map.steps?.length || 0;
    const rules = this.map.guardrails?.length || 0;
    const confirmed = this.mapInfo?.confirmed_at
      ? "confirmed by the expert" : "not yet confirmed by the expert";
    return `${this.map.task}, taught by ${this.map.expert}: ${steps} step${steps === 1 ? "" : "s"} ` +
      `and ${rules} rule${rules === 1 ? "" : "s"}, ${confirmed}. ` +
      "Press R to hear it, B to print it in braille.";
  }

  async _examIntro() {
    if (!this.exam) {
      const reply = await this.bridge.exam(this.mapId);
      this.exam = reply.items || [];
      this.examIndex = 0;
      this.score = { right: 0, answered: 0 };
    }
    if (!this.exam.length) {
      return "There is no exam yet: the expert has not decided any case in the debrief.";
    }
    return this._question();
  }

  _question() {
    if (this.examIndex >= this.exam.length) return this._result();
    const item = this.exam[this.examIndex];
    return `Case ${this.examIndex + 1} of ${this.exam.length}. ${item.question} ` +
      "Hold Space and say yes or no, or press Y or N.";
  }

  _result() {
    return `${this.score.right} of ${this.exam.length} right. ` +
      "Turn the wheel to go back to the map.";
  }

  // ── the keys ───────────────────────────────────────────────────────────────

  /** One press of one part of the deck. Talk is held, and handled by talk() and release(). */
  async press(partId) {
    if (partId === "btn_read") return this.read();
    if (partId === "btn_book") return this.book();
    if (partId === "btn_braille") return this.print();
    if (partId === "mode_wheel") return this.turnWheel();
    if (partId === "speaker_grille") return this.bridge.replay();
    return null;
  }

  /** Read whatever is in front of the new hire. */
  async read() {
    if (!this.map || this.busy) return;
    if (this.chapter === "map") {
      await this._working("btn_read", "Reading the map", async () => {
        const reply = await this.bridge.teachBack(this.mapId);
        if (reply.error) return this._notice(reply.error);
        this.prompter.show(reply.text, "apprentice", "The map, as the expert confirmed it");
        this.bridge.play(reply.audio);
      });
    } else if (this.chapter === "case") {
      await this._say(caseAsSpeech(PRACTICE_CASE, "Press Enter to book it."));
    } else {
      const text = this.exam?.length ? this._question() : await this._examIntro();
      this.prompter.show(text, "apprentice", CHAPTER_NAMES.exam);
      await this._say(text);
    }
  }

  /** Try the save. The apprentice answers before anything is booked. */
  async book() {
    if (!this.map || this.busy) return;
    if (this.chapter !== "case") await this.setChapter("case", { speak: false });
    await this._working("btn_book", "Checking against what the expert said", async () => {
      const reply = await this.bridge.book(this.mapId);
      if (reply.error) return this._notice(reply.error);
      const cleared = (reply.cleared || [])
        .map((c) => `Not stopped, because ${c.by} decided: "${c.said}"`);
      if (reply.allowed) {
        const text = ["Nothing the expert said stops this. Booked.", ...cleared].join(" ");
        this.prompter.show(text, "apprentice", "Booked");
        await this._say(text, { show: false });
        return;
      }
      const steps = reply.interventions || [];
      const text = [...steps.map((s) => s.says), ...cleared].join(" ");
      this.prompter.show(text, "expert", "Stopped before the save");
      for (const step of steps) this.bridge.play(step.audio);
      const pages = steps.flatMap((s) => s.slip || []);
      if (pages.length) {
        this.prompter.printSheet({
          title: "Warning slip", pages,
          note: "The same words, to keep on the desk",
        });
      }
    });
  }

  /** The Work Map, sent to the embosser. A second press puts the sheet away. */
  async print() {
    if (this.prompter.sheetVisible) {
      this.prompter.closeSheet();
      this.device.setInUse("btn_braille", false);
      return;
    }
    if (!this.map || this.busy) return;
    await this._working("btn_braille", "Embossing the map", async () => {
      const reply = await this.bridge.braille(this.mapId, 2);
      if (reply.error) return this._notice(reply.error);
      this.prompter.printSheet({
        title: "Work Map, Grade 2", pages: reply.pages_unicode || [], brf: reply.brf,
        filename: "work-map-grade-2.brf",
      });
      const count = reply.pages_unicode?.length || reply.pages || 0;
      await this._say(`The Work Map is on the embosser: ${count} page${count === 1 ? "" : "s"}.`,
                      { show: false });
    });
    this.device.setInUse("btn_braille", this.prompter.sheetVisible);
  }

  /** Talk, pressed. */
  async talk() {
    if (!this.map) return false;
    if (this.chapter !== "exam" || !this.exam?.length || this.examIndex >= this.exam.length) {
      await this._say(this.chapter === "exam"
        ? "There is nothing to answer. Turn the wheel to go back to the map."
        : "Talk answers the exam. Turn the wheel to the exam, or press 3.");
      return false;
    }
    if (!(await this.bridge.startTalking())) {
      this._notice("The microphone is not available. Press Y for yes, or N for no.");
      return false;
    }
    this.device.setInUse("btn_talk", true);
    this.onStatus("listening", "Listening");
    this.prompter.setSpeaker("listening");
    return true;
  }

  /** Talk, let go. */
  async release() {
    if (!this.bridge.isRecording) return;
    const audio = this.bridge.stopTalking();
    this.device.setInUse("btn_talk", false);
    if (!audio) {
      this.onStatus("connected", `${this.mapInfo.expert}'s map`);
      return;
    }
    await this.answer({ audio });
  }

  /** An exam answer, spoken or keyed. Unclear answers are asked again, never graded. */
  async answer(payload) {
    if (this.chapter !== "exam" || !this.exam?.length || this.examIndex >= this.exam.length) return;
    const item = this.exam[this.examIndex];
    await this._working("btn_talk", "Listening to the answer", async () => {
      const reply = await this.bridge.answer(this.mapId, item.ruling_id, payload);
      if (reply.error) return this._notice(reply.error);
      if (!reply.understood) {
        this.prompter.show(`Heard: "${reply.heard || ""}". ${reply.says}`, "apprentice");
        this.bridge.play(reply.audio);
        return;
      }
      this.score.answered += 1;
      this.score.right += reply.right ? 1 : 0;
      this.examIndex += 1;
      const next = this.examIndex < this.exam.length
        ? "Press R for the next case." : this._result();
      this.prompter.show(`${reply.says} ${next}`, "expert",
                         reply.right ? "Right" : "Not quite");
      this.bridge.play(reply.audio);
    });
  }

  // ── plumbing ───────────────────────────────────────────────────────────────

  async _working(partId, status, work) {
    this.busy = true;
    this.device.setInUse(partId, true);
    this.onStatus("thinking", status);
    try {
      await work();
    } catch (error) {
      this._notice("The apprentice's server did not answer. Is it running?");
    } finally {
      this.busy = false;
      if (partId !== "btn_braille") this.device.setInUse(partId, false);
      if (this.bridge.isOnline && this.mapInfo) {
        this.onStatus("connected", `${this.mapInfo.expert}'s map`);
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
