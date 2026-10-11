/**
 * The microphone, live: the words appear on the teleprompter as they are said.
 *
 * While the person holds Space, the microphone streams to /api/<side>/listen; each partial
 * transcript is shown at once, and when they let go the final words come back. Those words
 * then go through the page's ordinary route, as if typed: nothing is decided here.
 *
 * Without a live service (the server says "unavailable", or the socket fails), the recording
 * is kept and handed back whole, for the page to send the batch way as it always did.
 */

import { MicrophoneStream, wavBase64 } from "./audio.js";

export class LiveMicrophone {
  constructor({ url, onPartial, onRefused } = {}) {
    this.url = url;                     // () => the websocket address, with who is asking
    this.onPartial = onPartial || (() => {});
    this.onRefused = onRefused || (() => {});
    this.socket = null;
    this.live = false;
    this.recorded = [];
    this.microphone = null;
    this.final = null;
  }

  async start() {
    this.recorded = [];
    this.live = false;
    this.final = null;
    try {
      const scheme = location.protocol === "https:" ? "wss" : "ws";
      this.socket = new WebSocket(`${scheme}://${location.host}${this.url()}`);
      this.socket.binaryType = "arraybuffer";
      this.socket.onmessage = (event) => this.heard(JSON.parse(event.data));
      this.socket.onopen = () => { this.live = true; };
      this.socket.onerror = () => { this.live = false; };
    } catch { this.socket = null; }
    this.microphone = new MicrophoneStream({
      onChunk: (chunk) => {
        this.recorded.push(chunk);
        if (this.live && this.socket?.readyState === WebSocket.OPEN) this.socket.send(chunk);
      },
    });
    if (await this.microphone.start()) return true;
    this.microphone = null;
    this.close();
    return false;
  }

  heard(message) {
    if (message.type === "partial") this.onPartial(message.text);
    else if (message.type === "final") this.final?.(message.text);
    else if (message.type === "unavailable") this.live = false;
    else if (message.type === "refused") { this.live = false; this.onRefused(message); }
  }

  /** The words said: {text} from the live service, or {audio} to send the batch way. */
  async stop() {
    this.microphone?.stop();
    this.microphone = null;
    const audio = this.recorded.length ? wavBase64(this.recorded) : null;
    if (!this.live || this.socket?.readyState !== WebSocket.OPEN) {
      this.close();
      return { audio };
    }
    const text = await new Promise((resolve) => {
      this.final = resolve;
      this.socket.send(JSON.stringify({ type: "end" }));
      window.setTimeout(() => resolve(null), 4000);   // no final in time: the recording, whole
    });
    this.close();
    return text ? { text } : { audio };
  }

  close() {
    try { this.socket?.close(); } catch { /* already gone */ }
    this.socket = null;
  }
}
