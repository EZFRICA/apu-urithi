/** The stage's client, against a fake fetch: the routes it calls, and what it sends. */
import assert from "node:assert/strict";
import { installDom } from "./dom_stub.mjs";

installDom();
const { ApprenticeBridge } = await import("../../apu/ui/presentation/bridge.js");
const { PRACTICE_ACTION, PRACTICE_CASE } = await import("../../apu/ui/shared/practice.js");

const cases = [];
const test = (name, fn) => cases.push([name, fn]);

function server(replies = {}) {
  const requests = [];
  const fetcher = async (url, options = {}) => {
    requests.push({ url, method: options.method || "GET",
                    body: options.body ? JSON.parse(options.body) : null });
    const reply = replies[url.split("?")[0]];
    if (reply === "down") return { ok: false, status: 502, json: async () => ({}) };
    return { ok: true, status: 200, json: async () => reply ?? {} };
  };
  return { fetcher, requests };
}

test("confirmed maps come first: only those can be taught from", async () => {
  const { fetcher } = server({ "/api/guardian/maps": { maps: [
    { map_id: "a", confirmed_at: null }, { map_id: "b", confirmed_at: "2026-10-04" }] } });
  const maps = await new ApprenticeBridge({ fetcher }).maps();
  assert.deepEqual(maps.map((m) => m.map_id), ["b", "a"]);
});

test("Book sends the shared practice case and action, to the review route", async () => {
  const { fetcher, requests } = server();
  await new ApprenticeBridge({ fetcher }).book("m1");
  assert.equal(requests[0].url, "/api/guardian/review?person_id=sabine");
  assert.deepEqual(requests[0].body, { map_id: "m1", case: PRACTICE_CASE, about_to: PRACTICE_ACTION });
});

test("an exam answer goes to the exam answer route with what was said", async () => {
  const { fetcher, requests } = server();
  await new ApprenticeBridge({ fetcher }).answer("m1", "r1", { said: "yes" });
  assert.equal(requests[0].url, "/api/guardian/exam/answer?person_id=sabine");
  assert.deepEqual(requests[0].body, { map_id: "m1", ruling_id: "r1", said: "yes", audio: null });
});

test("the teach-back is asked for spoken, and a map id is escaped in the path", async () => {
  const { fetcher, requests } = server();
  await new ApprenticeBridge({ fetcher }).teachBack("a/b");
  assert.equal(requests[0].url, "/api/guardian/map/a%2Fb/teach-back?spoken=true&person_id=sabine");
});

test("a server that is down is reported, not taken for an empty list of maps", async () => {
  const events = [];
  const { fetcher } = server({ "/api/guardian/maps": "down" });
  const bridge = new ApprenticeBridge({ fetcher, onEvent: (type) => events.push(type) });
  assert.deepEqual(await bridge.maps(), []);
  assert.equal(bridge.isOnline, false);
  assert.ok(events.includes("offline"));
});

test("the loudspeaker key replays the last thing said, and nothing if nothing was", async () => {
  const bridge = new ApprenticeBridge({ fetcher: server().fetcher });
  const played = [];
  bridge.playback = { enqueue: (audio) => played.push(audio) };
  assert.equal(bridge.replay(), false);
  bridge.play("A");
  bridge.replay();
  assert.deepEqual(played, ["A", "A"]);
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
