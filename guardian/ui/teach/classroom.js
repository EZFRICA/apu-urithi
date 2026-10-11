/**
 * The classroom mode: the guardian in front of a class, Urithi the only pupil for now.
 *
 * A full-screen mode of the guardian's page (docs/decisions/0011), in place of the separate
 * screen-watching page: the shared screen or the camera in the middle, Urithi's question when
 * the guardian pauses (the measured pause detection: guardian/ui/teach/capture.js), a board
 * of what the class has noted, and the teleprompter below. The question, the microphone and
 * the notes can float in a small window kept above the guardian's work (teach.js, float), and
 * the microphone opens by itself once a question is asked. What is captured becomes draft
 * steps and rules in the map and goes to the working memory; nothing is validated, let alone
 * published, from here.
 */

import { ScreenCapture, VoiceActivity } from "./capture.js";

export class Classroom {
  /**
   * `post(path, body)` and `mapId()` from the page; `onQuestion(reply)` when Urithi asks;
   * `onCaptured(reply)` when an answer became a step; `onSaw(text, looked)` when the screen
   * changed; `onLooked(looked)` each time a changed frame went to be read.
   */
  constructor({ dialog, post, mapId, onQuestion, onCaptured, onSaw, onLooked, onDeferred, onEnd }) {
    this.dialog = dialog;
    this.post = post;
    this.mapId = mapId;
    this.onQuestion = onQuestion || (() => {});
    this.onCaptured = onCaptured || (() => {});
    this.onSaw = onSaw || (() => {});
    this.onLooked = onLooked || (() => {});
    this.onDeferred = onDeferred || (() => {});
    this.onEnd = onEnd || (() => {});
    this.capture = null;
    this.voice = null;
    this.pending = null;
    this.paused = false;
    this.silent = false;
    this.cameraWarned = false;
    this.clock = null;
    this.pointed = null;
  }

  get open() { return Boolean(this.capture); }

  point(region = null) {
    this.pointed = region;
    const box = this.dialog?.querySelector?.("#class-point");
    if (!box) return;
    if (!region) {
      box.hidden = true;
      return;
    }
    box.hidden = false;
    if (box.style) {
      box.style.left = `${Math.round(region.x * 100)}%`;
      box.style.top = `${Math.round(region.y * 100)}%`;
      box.style.width = `${Math.round(region.w * 100)}%`;
      box.style.height = `${Math.round(region.h * 100)}%`;
    }
  }

  /**
   * `listen`: whether the guardian has turned the microphone on. The class never opens it on its
   * own (the owner's rule: Urithi does not listen unless the guardian says so); without it, the
   * pauses are read from the screen alone.
   */
  async start(source = "screen", { listen = false } = {}) {
    this.capture = new ScreenCapture({ source, onFrame: (f) => this.frame(f) });
    this.cameraWarned = source === "camera" && !this.capture.blurredOnPage;
    try {
      await this.capture.start();
    } catch (error) {
      this.capture = null;
      throw error;
    }
    if (listen) await this.microphone(true);
    this.dialog.querySelector("video").srcObject = this.capture.stream;
    this.dialog.showModal();
    const clock = this.dialog.querySelector(".class-clock");
    this.clock = window.setInterval(() => {
      const seconds = Math.floor(this.capture?.at || 0);
      clock.textContent = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
    }, 500);
  }

  async frame({ at, frame, busy, blurredOnPage }) {
    // Urithi keeps watching while a question waits (the server asks no second one): measured live,
    // a question left unanswered while the guardian gave commands stopped the class seeing at all.
    if (this.paused || !this.capture) return;
    if (frame) this.onLooked(this.capture.sent);
    let reply;
    try {
      reply = await this.post("/api/guardian/observe", {
        map_id: this.mapId(), at, frame, typing: busy, scrolling: false, talking: Boolean(this.voice?.isTalking),
        silent: this.silent, source: this.capture?.source || "screen",
        camera_warned: this.cameraWarned,
        blurred_on_page: Boolean(blurredOnPage ?? this.capture?.blurredOnPage),
      });
    } catch { return; }      // one frame lost is one frame skipped
    if (reply.change) this.onSaw(reply.change, this.capture?.sent || 0);
    if (reply.deferred) this.onDeferred(reply);
    if (reply.question) {
      this.pending = reply;
      this.onQuestion(reply);
    }
  }

  /** P2: Pass the question waiting; Urithi clears it and learns a higher threshold. */
  async pass() {
    const reply = await this.post("/api/guardian/pass", { map_id: this.mapId() });
    this.pending = null;
    return reply;
  }

  /** P2: Silent mode keeps classroom questions for the debrief instead of asking aloud. */
  async setSilent(on) {
    this.silent = Boolean(on);
    if (this.mapId()) {
      await this.post("/api/guardian/silent", { map_id: this.mapId(), silent: this.silent }).catch(() => ({}));
    }
    return this.silent;
  }

  /** The guardian's answer to the question on screen: it becomes a proposal in working memory. */
  async answer({ said = null, audio = null }) {
    const reply = await this.post("/api/guardian/answer", { map_id: this.mapId(), said, audio });
    if (!reply.error && (reply.step || reply.proposal || reply.note)) {
      this.pending = null;
      this.onCaptured(reply);
      if (reply.question) this.onQuestion(reply);
    }
    return reply;
  }

  /**
   * "Remember this": the screen now, kept with what the guardian said of it. With words, a
   * proposal in working memory; without, Urithi asks what to remember.
   */
  async remember(said = "") {
    const frame = await this.capture?.still();
    if (!frame) return { error: "noFrame" };
    const region = this.pointed;
    this.point(null);
    const reply = await this.post("/api/guardian/remember", { map_id: this.mapId(), frame, said, at: this.capture?.at || 0, region, source: this.capture?.source || "screen" });
    if (reply.question) {
      this.pending = reply;
      this.onQuestion(reply);
    } else if (reply.step || reply.proposal) {
      this.onCaptured(reply);
    }
    return reply;
  }

  /** P1: a classroom command understood by intent ("remember", "example", "mistake", "compare", "forget"). */
  async command(said = "") {
    const frame = await this.capture?.still();
    const region = this.pointed;
    const reply = await this.post("/api/guardian/command", {
      map_id: this.mapId(), said, frame, at: this.capture?.at || 0, region,
      source: this.capture?.source || "screen",
    });
    if (reply.intent && reply.intent !== "none") {
      this.point(null);
    }
    return reply;
  }

  /** The guardian turns the microphone on or off; off, nothing of it stays open. True if on. */
  async microphone(on) {
    if (!on) {
      this.voice?.stop();
      this.voice?.stream?.getTracks().forEach((track) => track.stop());
      this.voice = null;
      return false;
    }
    if (this.voice) return true;
    try {
      this.voice = new VoiceActivity();
      await this.voice.start(await navigator.mediaDevices.getUserMedia({ audio: true }));
      return true;
    } catch {
      this.voice = null;   // no microphone: the pauses are read from the screen alone
      return false;
    }
  }

  /** The guardian turns the vision on or off: off, nothing of the screen is sent to be read. */
  pause(paused) { this.paused = paused; }

  end() {
    window.clearInterval(this.clock);
    this.capture?.stop();
    this.voice?.stop();
    this.voice?.stream?.getTracks().forEach((track) => track.stop());
    this.capture = null;
    this.voice = null;
    this.pending = null;
    this.point(null);
    if (this.dialog.open) this.dialog.close();
    this.onEnd();
  }
}
