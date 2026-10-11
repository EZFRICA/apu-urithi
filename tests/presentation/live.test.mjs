/** The live microphone: what reaches the transcription relay, run against a stub browser. */
import assert from "node:assert/strict";

const sockets = [];
class FakeSocket {
  static OPEN = 1;
  constructor(url) { this.url = url; this.readyState = 0; this.sent = []; sockets.push(this); }
  open() { this.readyState = 1; this.onopen?.(); }
  send(data) { this.sent.push(data); }
  close() { this.readyState = 3; }
}
let processor = null;
class FakeContext {
  constructor() { this.sampleRate = 48000; this.state = "running"; this.destination = {}; }
  createMediaStreamSource() { return { connect() {} }; }
  createScriptProcessor() { processor = { connect() {}, disconnect() {}, onaudioprocess: null }; return processor; }
  createGain() { return { gain: { value: 1 }, connect() {}, disconnect() {} }; }
  async resume() {}
  async close() {}
}
globalThis.window = globalThis;
globalThis.WebSocket = FakeSocket;
globalThis.AudioContext = FakeContext;
globalThis.location = { protocol: "http:", host: "localhost:8790" };
Object.defineProperty(globalThis, "navigator", { value: { mediaDevices: { getUserMedia: async () => ({ getTracks: () => [] }) } }, configurable: true });

const { LiveMicrophone } = await import("../../apu/ui/shared/live.js");
const cases = [];
const test = (name, fn) => cases.push([name, fn]);
const speech = () => { const b = new Float32Array(4096); for (let i = 0; i < b.length; i++) b[i] = 0.3 * Math.sin(i / 8); return b; };

test("each piece of speech reaches the relay as audio bytes", async () => {
  // Measured in a live run: every piece went as the string "undefined", the relay heard
  // nothing, no word appeared while the guardian spoke, and only the recording, sent whole at
  // the end, was ever transcribed.
  const mic = new LiveMicrophone({ url: () => "/api/guardian/listen" });
  assert.ok(await mic.start());
  sockets.at(-1).open();
  processor.onaudioprocess({ inputBuffer: { getChannelData: speech } });
  const [piece] = sockets.at(-1).sent;
  assert.ok(piece instanceof ArrayBuffer, `sent ${Object.prototype.toString.call(piece)}`);
  assert.equal(piece.byteLength, 1365 * 2, "4096 samples at 48 kHz, 16-bit at 16 kHz");
  mic.close();
});

test("the words heard live are the answer, not the recording", async () => {
  const mic = new LiveMicrophone({ url: () => "/api/guardian/listen" });
  await mic.start();
  const socket = sockets.at(-1);
  socket.open();
  processor.onaudioprocess({ inputBuffer: { getChannelData: speech } });
  const said = mic.stop();
  socket.onmessage({ data: JSON.stringify({ type: "final", text: "Newcomers only read the public channel." }) });
  assert.deepEqual(await said, { text: "Newcomers only read the public channel." });
});

let failed = 0;
for (const [name, fn] of cases) {
  try {
    await fn();
    console.log(`ok   ${name}`);
  } catch (err) {
    failed++;
    console.log(`FAIL ${name}\n     ${err.message.split("\n")[0]}`);
  }
}
console.log(`\n${cases.length - failed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
