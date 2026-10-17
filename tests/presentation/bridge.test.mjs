/** The stage's client, against a fake fetch: the routes it calls, and what it sends. */
import assert from "node:assert/strict";
import { installDom } from "./dom_stub.mjs";

installDom();
const { ApprenticeBridge } = await import("../../apu/ui/presentation/bridge.js");

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

test("the stage learns through the learner's routes: what was published, at this learner's level", async () => {
  // Found on 2026-10-17: the stage asked a guardian's routes for a draft map, and its exam had
  // no access level. Every call is now one /learn/ makes.
  const { fetcher, requests } = server({ "/api/learner/bodies": { bodies: [{ body_id: "b1" }] } });
  const bridge = new ApprenticeBridge({ fetcher });
  assert.deepEqual((await bridge.bodies()).map((b) => b.body_id), ["b1"]);
  await bridge.path("b1");
  await bridge.unit("b1:step-1");
  await bridge.exam("b1");
  assert.deepEqual(requests.map((r) => r.url), [
    "/api/learner/bodies?person_id=member", "/api/learner/path/b1?person_id=member",
    "/api/learner/unit/b1%3Astep-1?person_id=member", "/api/learner/exam/b1?person_id=member"]);
  assert.ok(requests.every((r) => !r.url.includes("/api/guardian/")), "nothing of a guardian's side");
});

test("any learner can sit at the stage: it asks as the one chosen, in their organisation", async () => {
  const { fetcher, requests } = server({ "/api/learner/people": { people: [
    { person_id: "ezekias", role: "guardian", organisation: "urithi" },
    { person_id: "member", role: "learner", organisation: "urithi" },
    { person_id: "visitor", role: "learner", organisation: "urithi" }] } });
  const bridge = new ApprenticeBridge({ fetcher });
  assert.deepEqual((await bridge.learners()).map((p) => p.person_id), ["member", "visitor"], "learners only");
  bridge.asLearner("visitor", "urithi");
  await bridge.bodies();
  assert.equal(requests.at(-1).url, "/api/learner/bodies?person_id=visitor&organisation=urithi");
});

test("a practice answer goes to the quiz route, graded there, with who is answering", async () => {
  const { fetcher, requests } = server();
  const bridge = new ApprenticeBridge({ fetcher });
  bridge.asLearner("member", "urithi");
  await bridge.quiz("b1:case-1", { said: "yes" });
  assert.equal(requests[0].url, "/api/learner/quiz?person_id=member&organisation=urithi");
  assert.deepEqual(requests[0].body, { person_id: "member", organisation: "urithi", case_id: "b1:case-1",
                                       answer: null, said: "yes", audio: null });
});

test("the exam is marked once, every answer together", async () => {
  const { fetcher, requests } = server();
  await new ApprenticeBridge({ fetcher }).markExam("b1", { c1: true, c2: false });
  assert.equal(requests[0].url, "/api/learner/exam/b1?person_id=member");
  assert.deepEqual(requests[0].body, { person_id: "member", answers: { c1: true, c2: false } });
});

test("a question asked aloud is heard, then asked from the part in view", async () => {
  const { fetcher, requests } = server();
  const bridge = new ApprenticeBridge({ fetcher });
  await bridge.hear("UklGRg==");
  await bridge.ask("b1", "When do we turn it?", "b1:step-1", "fr");
  assert.equal(requests[0].url, "/api/learner/hear?person_id=member");
  assert.deepEqual(requests[1].body, { person_id: "member", body_id: "b1", question: "When do we turn it?",
                                       lang: "fr", unit_id: "b1:step-1" });
});

test("a server that is down is reported, not taken for nothing to learn", async () => {
  const events = [];
  const { fetcher } = server({ "/api/learner/bodies": "down" });
  const bridge = new ApprenticeBridge({ fetcher, onEvent: (type) => events.push(type) });
  assert.deepEqual(await bridge.bodies(), []);
  assert.equal(bridge.isOnline, false);
  assert.ok(events.includes("offline"));
});

test("the loudspeaker key replays the last thing said, and nothing if nothing was", async () => {
  const bridge = new ApprenticeBridge({ fetcher: server().fetcher });
  const played = [];
  bridge.playback = { enqueue: (audio) => played.push(audio) };
  assert.equal(bridge.replay(), false);
  bridge.play("A", "audio/mpeg");
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
