/**
 * bridge.js - what a key on the Apprentice Deck asks the apprentice, and nothing else.
 *
 * Every call here is a route the apprentice's own page uses, or one added beside them for
 * someone who cannot see that page: the stage invents no answer of its own. The microphone
 * and the loudspeaker are the shared ones in apu/ui/shared, so a defect fixed for one page
 * is fixed for both.
 */

import { AudioPlayback, MicrophoneStream, wavBase64 } from "../shared/audio.js";
import { PRACTICE_ACTION, PRACTICE_CASE } from "../shared/practice.js";

const API = "/api/guardian";

export class ApprenticeBridge {
  constructor({ fetcher, onEvent, person = "sabine", organisation = null } = {}) {
    // Injected so the tests can run this file against a fake server.
    this.fetch = fetcher || ((...args) => window.fetch(...args));
    // The stage presents one guardian's maps and asks as that guardian, a simulated identity,
    // since a guardian's routes answer that guardian alone (guardian/api/routes.py). Sabine
    // first; any other guardian is chosen on the page (asGuardian).
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

  /** Ask as another guardian from now on: the stage then presents their maps. */
  asGuardian(person, organisation = null) {
    this.person = person;
    this.organisation = organisation;
  }

  /** Who may be presented: every guardian, once per organisation they teach in. */
  async guardians() {
    try {
      const reply = await this._json(await this.fetch(`${API}/people`));
      return (reply.people || []).filter((p) => p.role === "guardian");
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
      body: JSON.stringify(body),
    }));
  }

  async _json(response) {
    if (!response.ok) {
      this._offline(`The server answered ${response.status}.`);
      throw new Error(`HTTP ${response.status}`);
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

  /** The maps on this machine, confirmed ones first: only those can be taught from. */
  async maps() {
    try {
      const reply = await this._get("maps");
      const maps = reply.maps || [];
      return [...maps.filter((m) => m.confirmed_at), ...maps.filter((m) => !m.confirmed_at)];
    } catch (error) {
      this._offline(String(error));
      return [];
    }
  }

  map(mapId) {
    return this._get(`map/${encodeURIComponent(mapId)}`);
  }

  teachBack(mapId) {
    return this._get(`map/${encodeURIComponent(mapId)}/teach-back?spoken=true`);
  }

  braille(mapId, grade = 2) {
    return this._get(`map/${encodeURIComponent(mapId)}/braille?grade=${grade}`);
  }

  exam(mapId) {
    return this._get(`exam/${encodeURIComponent(mapId)}`);
  }

  /** Book the practice case. The review runs before the save, never after it. */
  book(mapId) {
    return this._post("review", { map_id: mapId, case: PRACTICE_CASE, about_to: PRACTICE_ACTION });
  }

  /** One exam case answered: typed or keyed words, or a recording. */
  answer(mapId, rulingId, { said = null, audio = null } = {}) {
    return this._post("exam/answer", { map_id: mapId, ruling_id: rulingId, said, audio });
  }

  /** A sentence the stage already shows, read out. */
  async say(text) {
    const reply = await this._post("say", { text });
    this.play(reply.audio);
    return reply;
  }

  play(audio) {
    if (!audio) return false;
    this.lastAudio = audio;
    this.playback.enqueue(audio, "audio/wav");
    return true;
  }

  /** The last thing said, said again: what the loudspeaker key does. */
  replay() {
    return this.play(this.lastAudio);
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
