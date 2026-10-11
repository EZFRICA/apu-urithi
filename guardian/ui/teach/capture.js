/**
 * The screen, and whether the person in front of it is busy.
 *
 * How does the apprentice know the expert has paused? It cannot read their keyboard:
 * they are working in another window, and a browser tab sees none of it. What it can see is
 * the screen they shared and hear the microphone they opened, so that is what is measured.
 *
 * Busy is a number, not a guess. Each frame is drawn small and compared with the one before
 * it; the mean absolute difference per pixel is how much the screen is moving. A person typing
 * moves it constantly, a person reading barely at all. The microphone gives the second signal:
 * speech is loud against the room's floor.
 *
 * Measured in a real class: the guardian works in the window they share, so this page sits in
 * a background tab, where the browser slows its timers and may stop drawing its video. The
 * frames sent were then all alike and nothing was ever seen. So the clock runs in a worker,
 * which a background tab does not slow, and each frame is taken from the shared stream itself
 * (ImageCapture) rather than from a video on this page. And a frame goes to the model only when
 * some part of the screen changed: the model takes seconds to read a pair, and a screen nobody
 * touched has nothing to tell it.
 *
 * Both thresholds are tunable and both are reported to the page, so a presenter can show
 * the number rising and falling rather than asserting that the pause detection works.
 */

const THUMB_WIDTH = 160;
const THUMB_HEIGHT = 90;

// Mean absolute difference, 0 to 255 per channel. Measured on real screens: reading sits
// under 1, a cursor blinking around 1, typing and scrolling well above 3.
export const MOTION_BUSY = 2.5;
// A camera always moves (sensor noise, breathing, handheld sway): a higher bar lets pauses be
// read while gestures, objects and writing on a whiteboard still register as busy.
export const CAMERA_MOTION_BUSY = 8.0;
// Microphone RMS, 0 to 1. Room noise sits under 0.01; speech is an order of magnitude up.
export const VOICE_BUSY = 0.02;
// One small pixel counts as changed past this mean difference: a menu choice or a word typed
// in a field changes a few of them a lot, while a whole screen at rest changes none.
export const PIXEL_CHANGED = 12;
// A camera's sensor noise and 1 to 2 px handheld sway jitter edge pixels on every frame.
// Measured on 160x90 camera thumbnails: a 2 px sway changes ~215 pixels above 32, while
// writing on a whiteboard, pointing a hand, or moving an object changes 450+.
export const CAMERA_PIXEL_CHANGED = 32;
export const CAMERA_MIN_CHANGED_PIXELS = 350;

export function isBusy(motion, source = "screen") {
  return motion >= (source === "camera" ? CAMERA_MOTION_BUSY : MOTION_BUSY);
}

export function hasChanged(changed, source = "screen") {
  return changed >= (source === "camera" ? CAMERA_MIN_CHANGED_PIXELS : 1);
}

/**
 * Two small frames (RGBA bytes) compared: how much the screen moves, and how many of its
 * pixels changed. Pure, so it is tested as it runs (tests/presentation/capture.test.mjs).
 */
export function compare(previous, current, source = "screen") {
  if (!previous || previous.length !== current.length) return { motion: 0, changed: 0 };
  let total = 0;
  let changed = 0;
  const pixelThreshold = source === "camera" ? CAMERA_PIXEL_CHANGED : PIXEL_CHANGED;
  // Three channels of four: the alpha byte is always 255 and averaging it in would
  // quarter every reading for no information.
  for (let i = 0; i < current.length; i += 4) {
    const d = Math.abs(current[i] - previous[i]) + Math.abs(current[i + 1] - previous[i + 1])
            + Math.abs(current[i + 2] - previous[i + 2]);
    total += d;
    if (d / 3 > pixelThreshold) changed += 1;
  }
  return {
    motion: total / ((current.length / 4) * 3),
    changed: hasChanged(changed, source) ? changed : 0,
  };
}

export async function blurOtherFacesOnCanvas(canvas, FaceDetectorClass = globalThis.FaceDetector) {
  if (typeof FaceDetectorClass !== "function" || !canvas) {
    return { blurredOnPage: false, otherFaces: 0 };
  }
  try {
    const detector = new FaceDetectorClass();
    const found = await detector.detect(canvas);
    const faces = Array.isArray(found) ? [...found] : [];
    faces.sort((a, b) => (b.boundingBox.width * b.boundingBox.height) - (a.boundingBox.width * a.boundingBox.height));
    const others = faces.slice(1);
    if (others.length > 0) {
      const ctx = canvas.getContext("2d");
      for (const face of others) {
        const { x, y, width, height } = face.boundingBox;
        ctx.save();
        ctx.filter = "blur(18px)";
        ctx.drawImage(canvas, x, y, width, height, x, y, width, height);
        ctx.restore();
      }
    }
    return { blurredOnPage: true, otherFaces: others.length };
  } catch {
    return { blurredOnPage: false, otherFaces: 0 };
  }
}

// A timer a background tab does not slow: setInterval in a worker, posting a tick.
const TICKER = "let t = null; onmessage = (e) => { clearInterval(t); if (e.data > 0) t = setInterval(() => postMessage(0), e.data); };";

export class ScreenCapture {
  /** `source`: "screen" (the guardian shares a window) or "camera" (a desk, a whiteboard, hands at work). */
  constructor({ onFrame, intervalMs = 2000, source = "screen" } = {}) {
    this.onFrame = onFrame || (() => {});
    this.source = source;
    this.intervalMs = intervalMs;
    this.stream = null;
    this.video = document.createElement("video");
    this.video.muted = true;
    this.video.playsInline = true;

    this.full = document.createElement("canvas");
    this.thumb = document.createElement("canvas");
    this.thumb.width = THUMB_WIDTH;
    this.thumb.height = THUMB_HEIGHT;
    this.previousThumb = null;
    this.lastSentThumb = null;

    this.timer = null;
    this.ticker = null;
    this.grabber = null;
    this.grabbing = false;
    this.startedAt = 0;
    this.motion = 0;
    this.sent = 0;            // frames that went to the model
    this.blurredOnPage = typeof globalThis.FaceDetector === "function";
  }

  get isSharing() {
    return Boolean(this.stream);
  }

  async start() {
    this.stream = this.source === "camera"
      ? await navigator.mediaDevices.getUserMedia({ video: { frameRate: 2 }, audio: false })
      : await navigator.mediaDevices.getDisplayMedia({ video: { frameRate: 2 }, audio: false });
    this.video.srcObject = this.stream;
    await this.video.play();

    // The person can stop sharing from the browser's own bar, which is not our button.
    const track = this.stream.getVideoTracks()[0];
    track.addEventListener("ended", () => this.stop());
    if (window.ImageCapture) this.grabber = new window.ImageCapture(track);

    this.startedAt = performance.now();
    try {
      this.ticker = new Worker(URL.createObjectURL(new Blob([TICKER], { type: "text/javascript" })));
      this.ticker.onmessage = () => this._grab();
      this.ticker.postMessage(this.intervalMs);
    } catch {
      this.ticker = null;
      this.timer = window.setInterval(() => this._grab(), this.intervalMs);
    }
    return true;
  }

  stop() {
    if (this.ticker) {
      this.ticker.postMessage(0);
      this.ticker.terminate();
      this.ticker = null;
    }
    if (this.timer) {
      window.clearInterval(this.timer);
      this.timer = null;
    }
    if (this.stream) {
      this.stream.getTracks().forEach((track) => track.stop());
      this.stream = null;
    }
    this.grabber = null;
    this.previousThumb = null;
    this.lastSentThumb = null;
  }

  /** Seconds since the session began: the clock every step and quote is stamped with. */
  get at() {
    return this.startedAt ? (performance.now() - this.startedAt) / 1000 : 0;
  }

  /** The frame now, from the stream itself when the browser can; else from the video. */
  async _image() {
    if (this.grabber) {
      try { return await this.grabber.grabFrame(); } catch { /* the video, then */ }
    }
    return this.video.videoWidth ? this.video : null;
  }

  async _grab() {
    if (this.grabbing || !this.stream) return;
    this.grabbing = true;
    try {
      const image = await this._image();
      const width = image?.width || image?.videoWidth;
      const height = image?.height || image?.videoHeight;
      if (!width || !height) return;

      const context = this.thumb.getContext("2d", { willReadFrequently: true });
      context.drawImage(image, 0, 0, THUMB_WIDTH, THUMB_HEIGHT);
      const current = context.getImageData(0, 0, THUMB_WIDTH, THUMB_HEIGHT).data;
      const first = !this.previousThumb;
      const { motion } = compare(this.previousThumb, current, this.source);
      const { changed } = compare(this.lastSentThumb || this.previousThumb, current, this.source);
      this.previousThumb = current;
      this.motion = motion;

      // The frame that goes to the model, capped so a 4K screen is not uploaded every 2 s;
      // only the first one, and one in which something changed.
      let frame = null;
      if (first || changed > 0) {
        this.lastSentThumb = current;
        const scale = Math.min(1, 1280 / width);
        this.full.width = Math.round(width * scale);
        this.full.height = Math.round(height * scale);
        this.full.getContext("2d").drawImage(image, 0, 0, this.full.width, this.full.height);
        if (this.source === "camera") {
          const blur = await blurOtherFacesOnCanvas(this.full);
          this.blurredOnPage = blur.blurredOnPage;
        }
        // JPEG at 0.7: readable enough for a field value, small enough to send.
        frame = this.full.toDataURL("image/jpeg", 0.7).split(",")[1];
        this.sent += 1;
      }
      image.close?.();
      this.onFrame({
        at: this.at, motion, changed, busy: isBusy(motion, this.source),
        source: this.source, blurredOnPage: this.blurredOnPage, frame,
      });
    } finally {
      this.grabbing = false;
    }
  }

  /** The screen now, as base64 JPEG, sharp enough to read: what "remember this" keeps. */
  async still() {
    const image = await this._image();
    const width = image?.width || image?.videoWidth;
    const height = image?.height || image?.videoHeight;
    if (!width || !height) return null;
    const canvas = document.createElement("canvas");
    const scale = Math.min(1, 1600 / width);
    canvas.width = Math.round(width * scale);
    canvas.height = Math.round(height * scale);
    canvas.getContext("2d").drawImage(image, 0, 0, canvas.width, canvas.height);
    if (this.source === "camera") {
      const blur = await blurOtherFacesOnCanvas(canvas);
      this.blurredOnPage = blur.blurredOnPage;
    }
    image.close?.();
    return canvas.toDataURL("image/jpeg", 0.85).split(",")[1];
  }

  /** A still of this moment, for the Work Map to show beside a step. */
  snapshot() {
    return this.full.width ? this.full.toDataURL("image/jpeg", 0.5) : null;
  }
}

/** Is someone speaking? The second half of "is the expert busy". */
export class VoiceActivity {
  constructor() {
    this.context = null;
    this.analyser = null;
    this.buffer = null;
    this.stream = null;
    this.level = 0;
  }

  async start(stream) {
    this.stream = stream;
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    this.context = new AudioCtx();
    const source = this.context.createMediaStreamSource(stream);
    this.analyser = this.context.createAnalyser();
    this.analyser.fftSize = 512;
    this.buffer = new Float32Array(this.analyser.fftSize);
    source.connect(this.analyser);
  }

  /** Root mean square of the last frame of audio: loudness, not pitch. */
  read() {
    if (!this.analyser) return 0;
    this.analyser.getFloatTimeDomainData(this.buffer);
    let sum = 0;
    for (const sample of this.buffer) sum += sample * sample;
    this.level = Math.sqrt(sum / this.buffer.length);
    return this.level;
  }

  get isTalking() {
    return this.read() >= VOICE_BUSY;
  }

  stop() {
    if (this.context) {
      this.context.close().catch(() => {});
      this.context = null;
    }
    this.analyser = null;
  }
}
