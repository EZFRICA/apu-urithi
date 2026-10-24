/**
 * bridge.js - what a key on the Apprentice Deck asks Urithi, and nothing else.
 *
 * The stage is the learner's page for someone who cannot see it: every call here is a route
 * of the learner's side (/api/learner), the same ones /learn/ uses, on what a guardian
 * published, at this learner's access level. Nothing a guardian has not published, and no
 * part above the learner's level, ever reaches the deck. The microphone and the loudspeaker
 * are the shared ones in apu/ui/shared, so a defect fixed for one page is fixed for both.
 */

import { AudioPlayback, MicrophoneStream, wavBase64 } from "../shared/audio.js";

const API = "/api/learner";

export class ApprenticeBridge {
  constructor({ fetcher, onEvent, person = "member", organisation = null } = {}) {
    // Injected so the tests can run this file against a fake server.
    this.fetch = fetcher || ((...args) => window.fetch(...args));
    // Who is learning: a simulated identity, chosen on the page (asLearner). Every route
    // answers at that person's access level.
    this.person = person;
    this.organisation = organisation;
    this.onEvent = onEvent || (() => {});
    this.playback = new AudioPlayback();
    this.microphone = null;
    this.recorded = [];
    this.lastAudio = null;
    this.isOnline = false;
  }

  get isRecording() {
    return Boolean(this.microphone);
  }

  _url(path) {
    const org = this.organisation ? `&organisation=${encodeURIComponent(this.organisation)}` : "";
    return `${API}/${path}${path.includes("?") ? "&" : "?"}person_id=${encodeURIComponent(this.person)}${org}`;
  }

  /** Who the learner's routes are asked for, in a request body as well as in the address. */
  _me() {
    return { person_id: this.person, ...(this.organisation ? { organisation: this.organisation } : {}) };
  }

  /** Learn as another person from now on: the stage then offers what they may learn. */
  asLearner(person, organisation = null) {
    this.person = person;
    this.organisation = organisation;
  }

  /** Who may learn on the stage: every learner, once per organisation. */
  async learners() {
    try {
      const reply = await this._json(await this.fetch(`${API}/people`));
      return (reply.people || []).filter((p) => p.role === "learner");
    } catch {
      return [];
    }
  }

  async _get(path) {
    return this._json(await this.fetch(this._url(path)));
  }

  async _post(path, body) {
    return this._json(await this.fetch(this._url(path), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...this._me(), ...body }),
    }));
  }

  async _json(response) {
    if (!response.ok) {
      let detail = "";
      try { detail = (await response.json()).detail || ""; } catch { /* no body */ }
      if (response.status >= 500 && response.status !== 503) this._offline(`The server answered ${response.status}.`);
      const error = new Error(detail || `HTTP ${response.status}`);
      error.status = response.status;
      throw error;
    }
    this._online();
    return response.json();
  }

  _online() {
    if (!this.isOnline) {
      this.isOnline = true;
      this.onEvent("online");
    }
  }

  _offline(reason) {
    this.isOnline = false;
    this.onEvent("offline", { reason });
  }

  /** The published knowledge this learner may learn, from every guardian. */
  async bodies() {
    this.unanswered = "";
    try {
      return (await this._get("bodies")).bodies || [];
    } catch (error) {
      if (!error.status) this._offline(String(error));
      else this.unanswered = error.message;   // the server answered without the list: why is said
      return [];
    }
  }

  /** A knowledge's path: its parts in order, at this learner's level. */
  path(bodyId) {
    return this._get(`path/${encodeURIComponent(bodyId)}`);
  }

  /** One part: the guardian's words, and the cases to practise on it, without their answers. */
  unit(unitId) {
    return this._get(`unit/${encodeURIComponent(unitId)}`);
  }

  listen(unitId, lang = "en") {
    return this._get(`unit/${encodeURIComponent(unitId)}/listen?lang=${lang}`);
  }

  braille(unitId, grade = 2, lang = "en") {
    return this._get(`unit/${encodeURIComponent(unitId)}/braille?grade=${grade}&lang=${lang}`);
  }

  /** One case answered, graded by code against the guardian's decision: a key, words or a recording. */
  quiz(caseId, { answer = null, said = null, audio = null } = {}) {
    return this._post("quiz", { case_id: caseId, answer, said, audio });
  }

  exam(bodyId) {
    return this._get(`exam/${encodeURIComponent(bodyId)}`);
  }

  /** Every exam answer at once, marked only then: no answer is seen before the last question. */
  markExam(bodyId, answers) {
    return this._post(`exam/${encodeURIComponent(bodyId)}`, { answers });
  }

  /** A question said aloud, to its words. */
  hear(audio) {
    return this._post("hear", { audio });
  }

  /** A question to the knowledge: guarded, answered from what this learner may see, cited. */
  ask(bodyId, question, unitId = null, lang = "en") {
    return this._post("ask", { body_id: bodyId, question, lang, unit_id: unitId });
  }

  /** Kept in the learner's notebook, as on /learn/. */
  keep(bodyId, { kind, text, question = "", unitIds = [] }) {
    return this._post("notebook", { body_id: bodyId, kind, text, question, unit_ids: unitIds });
  }

  /** A sentence the stage already shows, read out. */
  async say(text) {
    const reply = await this._post("say", { text });
    this.play(reply.audio, reply.mime);
    return reply;
  }

  play(audio, mime = "audio/wav") {
    if (!audio) return false;
    this.lastAudio = { audio, mime };
    this.playback.enqueue(audio, mime);
    return true;
  }

  /** The last thing said, said again: what the loudspeaker key does. */
  replay() {
    return this.lastAudio ? this.play(this.lastAudio.audio, this.lastAudio.mime) : false;
  }

  /** Hold to talk. True if the microphone opened. */
  async startTalking() {
    if (this.microphone) return true;
    this.recorded = [];
    this.microphone = new MicrophoneStream({ onChunk: (chunk) => this.recorded.push(chunk) });
    if (await this.microphone.start()) return true;
    this.microphone = null;
    return false;
  }

  /** Let go. The recording as a WAV, or null if nothing was heard. */
  stopTalking() {
    if (!this.microphone) return null;
    this.microphone.stop();
    this.microphone = null;
    return this.recorded.length ? wavBase64(this.recorded) : null;
  }
}
