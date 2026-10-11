/**
 * The microphone and the loudspeaker, for both pages: the apprentice and the stage.
 *
 * One copy, because two copies of audio plumbing drift: the decimation that folded half
 * the spectrum back into the speech, and the microphone wired to the speakers of the room
 * it records, are both defects that were fixed in one copy and still running in another.
 * Plumbing that knows the format and nothing about the decor belongs in one place.
 */

const TARGET_RATE = 16000;

/**
 * Float samples at any rate, to 16 kHz signed 16-bit PCM.
 *
 * The low-pass is the point. 16 kHz cannot carry what 48 kHz holds, and whatever is left
 * above 8 kHz comes back as a false low tone in the middle of the speech. Taking one
 * sample in three keeps that tone at full strength; the mean of each window divides it by
 * three; these triangular weights, spread over twice the window, take it down by more than
 * twenty, for six multiplications per output sample.
 */
export function downsampleTo16k(buffer, sampleRate) {
  if (sampleRate === TARGET_RATE) {
    const pcm16 = new Int16Array(buffer.length);
    for (let i = 0; i < buffer.length; i++) {
      const sample = Math.max(-1, Math.min(1, buffer[i]));
      pcm16[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
    }
    return pcm16.buffer;
  }

  const ratio = sampleRate / TARGET_RATE;
  const newLength = Math.floor(buffer.length / ratio);
  const result = new Int16Array(newLength);

  for (let i = 0; i < newLength; i++) {
    const centre = i * ratio;
    const first = Math.max(0, Math.ceil(centre - ratio));
    const last = Math.min(buffer.length - 1, Math.floor(centre + ratio));
    let sum = 0;
    let weightSum = 0;
    for (let j = first; j <= last; j++) {
      const weight = 1 - Math.abs(j - centre) / ratio;
      if (weight <= 0) continue;
      sum += buffer[j] * weight;
      weightSum += weight;
    }
    const mean = weightSum > 0 ? sum / weightSum : 0;
    const clamped = Math.max(-1, Math.min(1, mean));
    result[i] = clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff;
  }
  return result.buffer;
}

/** The microphone, as 16 kHz PCM chunks handed to a callback. */
export class MicrophoneStream {
  constructor({ onChunk } = {}) {
    this.onChunk = onChunk || (() => {});
    this.audioContext = null;
    this.mediaStream = null;
    this.processor = null;
    this.sink = null;
    this.isRecording = false;
  }

  /** True if the microphone is open. Never throws: a refused microphone is an answer. */
  async start() {
    if (this.isRecording) return true;

    try {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        throw new Error("This browser does not expose a microphone.");
      }

      this.mediaStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: { ideal: TARGET_RATE },
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });

      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      this.audioContext = new AudioCtx();
      if (this.audioContext.state === "suspended") {
        await this.audioContext.resume();
      }

      const source = this.audioContext.createMediaStreamSource(this.mediaStream);
      const inputRate = this.audioContext.sampleRate;
      this.processor = this.audioContext.createScriptProcessor(4096, 1, 1);

      this.processor.onaudioprocess = (event) => {
        if (!this.isRecording) return;
        const chunk = downsampleTo16k(event.inputBuffer.getChannelData(0), inputRate);
        if (chunk && chunk.byteLength > 0) this.onChunk(chunk);
      };

      source.connect(this.processor);
      // Silent sink: the node only runs if something downstream pulls it, and sending a
      // live microphone to the speakers of the room it is recording is a feedback loop.
      this.sink = this.audioContext.createGain();
      this.sink.gain.value = 0;
      this.processor.connect(this.sink);
      this.sink.connect(this.audioContext.destination);

      this.isRecording = true;
      return true;
    } catch (err) {
      console.warn("Microphone unavailable:", err);
      this.stop();
      this.isRecording = false;
      return false;
    }
  }

  stop() {
    this.isRecording = false;

    if (this.processor) {
      this.processor.disconnect();
      this.processor = null;
    }
    if (this.sink) {
      this.sink.disconnect();
      this.sink = null;
    }
    if (this.audioContext) {
      this.audioContext.close().catch(() => {});
      this.audioContext = null;
    }
    if (this.mediaStream) {
      this.mediaStream.getTracks().forEach((track) => track.stop());
      this.mediaStream = null;
    }
  }
}

/** The apprentice's voice, played in the order it arrives. */
export class AudioPlayback {
  constructor() {
    this.context = null;
    this.queue = [];
    this.isPlaying = false;
  }

  /** `on`: {start(now), end()}; now() is seconds into the clip, for the teleprompter's words. */
  enqueue(base64Data, mimeType = "audio/wav", on = {}) {
    if (!base64Data) return;
    this.queue.push({ base64Data, mimeType, on });
    if (!this.isPlaying) this._playNext();
  }

  async _playNext() {
    if (this.queue.length === 0) {
      this.isPlaying = false;
      return;
    }

    this.isPlaying = true;
    const item = this.queue.shift();

    try {
      const binary = atob(item.base64Data);
      const bytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);

      if (!this.context || this.context.state === "closed") {
        this.context = new (window.AudioContext || window.webkitAudioContext)();
      }

      const buffer = await this.context.decodeAudioData(bytes.buffer.slice(0));
      const source = this.context.createBufferSource();
      source.buffer = buffer;
      source.connect(this.context.destination);
      source.onended = () => { item.on.end?.(); this._playNext(); };
      source.start();
      const startedAt = this.context.currentTime;
      item.on.start?.(() => this.context.currentTime - startedAt);
    } catch (err) {
      // One clip that will not decode must not stop the ones behind it.
      console.warn("Audio decoding error:", err);
      this._playNext();
    }
  }

  stop() {
    this.queue = [];
    if (this.context) {
      this.context.close().catch(() => {});
      this.context = null;
    }
    this.isPlaying = false;
  }
}


/**
 * 16 kHz mono PCM chunks, from MicrophoneStream, into one WAV as base64: what the
 * transcriber takes, and what both pages send when someone answers out loud.
 */
export function wavBase64(chunks) {
  const total = chunks.reduce((n, c) => n + c.byteLength, 0);
  const out = new Uint8Array(44 + total);
  const view = new DataView(out.buffer);
  const ascii = (offset, text) => [...text].forEach((c, i) => view.setUint8(offset + i, c.charCodeAt(0)));
  ascii(0, "RIFF"); view.setUint32(4, 36 + total, true); ascii(8, "WAVEfmt ");
  view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
  view.setUint32(24, TARGET_RATE, true); view.setUint32(28, TARGET_RATE * 2, true);
  view.setUint16(32, 2, true); view.setUint16(34, 16, true);
  ascii(36, "data"); view.setUint32(40, total, true);
  let at = 44;
  for (const chunk of chunks) { out.set(new Uint8Array(chunk), at); at += chunk.byteLength; }
  let binary = "";
  for (const byte of out) binary += String.fromCharCode(byte);
  return btoa(binary);
}
