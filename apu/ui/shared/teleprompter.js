/**
 * The teleprompter: what is being said, in print, whenever a microphone or a voice is on.
 *
 * Someone who cannot hear reads what Urithi says, each word lit as the voice says it (the
 * server sends when every word is said: apu/modality/voice.py); someone speaking sees their
 * words appear as they say them (apu/modality/live.py), and can tell at once when one was
 * heard wrong. It appears when a microphone opens or a voice starts, and goes when both are
 * done. The words are set as text, never markup.
 *
 * The element: <div class="prompter" hidden><span class="who"></span><span class="words"></span></div>
 */

export class Teleprompter {
  constructor(element, labels) {
    this.el = element;
    this.who = element.querySelector(".who");
    this.words = element.querySelector(".words");
    this.labels = labels;
    this.timer = null;
    this.frame = null;
    element.setAttribute("role", "status");
    element.setAttribute("aria-live", "polite");
  }

  show(speaker, words, { linger = 0 } = {}) {
    this.stopClock();
    window.clearTimeout(this.timer);
    this.el.dataset.speaker = speaker;
    this.who.textContent = this.labels()[speaker] || speaker;
    this.words.textContent = words || "";
    this.el.hidden = false;
    if (linger) this.timer = window.setTimeout(() => this.hide(), linger);
  }

  listening() { this.show("you", this.labels().listeningWords || "…"); }

  /** What has been heard so far, while the person is still speaking. */
  partial(words) { this.show("you", words); }

  heard(words) { this.show("you", words, { linger: 6000 }); }

  speaking(words) { this.show("urithi", words, { linger: Math.max(5000, words.length * 70) }); }

  /**
   * Word by word, in time with a voice. `now()` is seconds into the audio. Returns a handle
   * whose done() lights every word and lets the band go a moment later. Without timings, the
   * sentence is shown whole, as before.
   */
  timed(words, text, now) {
    if (!words?.length) {
      this.speaking(text);
      return { done: () => {} };
    }
    this.show("urithi", "");
    // Read once, whole, by a screen reader; the lit words are for the eye.
    this.el.setAttribute("aria-label", text || words.map((w) => w.word).join(" "));
    const spans = words.map((w, i) => {
      const span = document.createElement("span");
      span.textContent = (i ? " " : "") + w.word;
      span.setAttribute("aria-hidden", "true");
      this.words.appendChild(span);
      return span;
    });
    const tick = () => {
      const t = now();
      spans.forEach((span, i) => span.classList.toggle("said", words[i].start <= t));
      this.frame = window.requestAnimationFrame(tick);
    };
    tick();
    return {
      done: () => {
        this.stopClock();
        spans.forEach((span) => span.classList.add("said"));
        this.timer = window.setTimeout(() => this.hide(), 2500);
      },
    };
  }

  /** For an <audio> element: shown while it plays, word by word when timings are known. */
  follow(audio, text, words = []) {
    let handle = null;
    audio.addEventListener("playing", () => { handle = this.timed(words, text, () => audio.currentTime); });
    audio.addEventListener("ended", () => (handle ? handle.done() : this.hide()));
    audio.addEventListener("pause", () => { if (!audio.ended) this.hide(); });
  }

  stopClock() {
    if (this.frame) window.cancelAnimationFrame(this.frame);
    this.frame = null;
    this.el.removeAttribute("aria-label");
  }

  hide() {
    this.stopClock();
    window.clearTimeout(this.timer);
    this.el.hidden = true;
  }
}
