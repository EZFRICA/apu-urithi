/**
 * The deck's keys, run against a fake server.
 *
 * The fake bridge answers the way the real routes do (tests/test_apprentice.py checks
 * those), so what is proved here is the stage's own behaviour: which key calls what, in
 * which part of the job, and what a person without sight is told when a key has nothing
 * to do.
 */
import assert from "node:assert/strict";
import { installDom, buildPrompter } from "./dom_stub.mjs";

const { El, root } = installDom();
const { PrompterController } = await import("../../apu/ui/presentation/prompter.js");
const { Stage } = await import("../../apu/ui/presentation/stage.js");
const { PRACTICE_CASE } = await import("../../apu/ui/shared/practice.js");

const cases = [];
const test = (name, fn) => cases.push([name, fn]);

const MAP = {
  map_id: "m1", task: "Code a supplier invoice", expert: "Sabine",
  steps: [{ number: 1, title: "Check the supplier" }],
  guardrails: [{ id: "g1" }, { id: "g2" }],
};

class FakeBridge {
  constructor(overrides = {}) {
    this.calls = [];
    this.said = [];
    this.played = [];
    this.isOnline = true;
    this.isRecording = false;
    this.micWorks = true;
    this.maps_ = [{ map_id: "m1", task: MAP.task, expert: "Sabine", confirmed_at: "2026-10-04" }];
    this.examItems = [
      { ruling_id: "r1", question: "5,000 exactly. Does the rule apply?" },
      { ruling_id: "r2", question: "2,900 of equipment. Capex?" },
    ];
    this.answers = { r1: true, r2: true };
    Object.assign(this, overrides);
  }
  async maps() { this.calls.push("maps"); return this.maps_; }
  async map(id) { this.calls.push(`map ${id}`); return MAP; }
  async teachBack(id) { this.calls.push(`teach-back ${id}`); return { text: "Here is how I understand it.", audio: "T" }; }
  async braille(id, grade) {
    this.calls.push(`braille ${id} ${grade}`);
    return { pages_unicode: [["⠁⠃"], ["⠉"]], brf: "AB\fC", pages: 2 };
  }
  async exam(id) { this.calls.push(`exam ${id}`); return { items: this.examItems }; }
  async book(id) {
    this.calls.push(`review ${id}`);
    return this.review || { allowed: false, cleared: [], interventions: [
      { says: "Stop. Sabine said: check the bank details first.", audio: "A1", slip: [["⠎⠞⠕⠏"]] },
    ] };
  }
  async answer(id, rulingId, payload) {
    this.calls.push(`answer ${rulingId} ${payload.said ?? "audio"}`);
    const said = payload.said ?? "yes";
    if (!["yes", "no"].includes(said)) {
      return { heard: said, understood: false, says: "I did not catch a yes or a no.", audio: "Q" };
    }
    const right = (said === "yes") === this.answers[rulingId];
    return { heard: said, understood: true, right,
             says: `${right ? "Right" : "Not quite"}. Sabine said: so it is.`, audio: "F" };
  }
  async say(text) { this.said.push(text); return { audio: "S" }; }
  play(audio) { if (audio) this.played.push(audio); return Boolean(audio); }
  replay() { this.calls.push("replay"); return true; }
  async startTalking() { this.isRecording = this.micWorks; return this.micWorks; }
  stopTalking() { this.isRecording = false; return "UklGRg=="; }
}

const fresh = async (overrides) => {
  root.children = [];
  const dom = buildPrompter(El, root);
  const prompter = new PrompterController(dom.container);
  const bridge = new FakeBridge(overrides);
  const inUse = [];
  const statuses = [];
  const stage = new Stage({
    bridge, prompter,
    device: { setInUse: (part, on) => inUse.push([part, on]) },
    onStatus: (state, text) => statuses.push([state, text]),
  });
  await stage.load();
  return { stage, bridge, prompter, dom, inUse, statuses };
};

test("it opens on the confirmed map and says what it holds", async () => {
  const { stage, dom, statuses } = await fresh();
  assert.equal(stage.mapId, "m1");
  assert.equal(stage.chapter, "map");
  assert.match(dom.text.textContent, /Code a supplier invoice, taught by Sabine: 1 step and 2 rules, confirmed/);
  assert.deepEqual(statuses.at(-1), ["connected", "Sabine's map"]);
});

test("no map on the machine is said plainly, and no key pretends to work", async () => {
  const { stage, bridge, dom } = await fresh({ maps_: [] });
  assert.match(dom.text.textContent, /no Work Map on this machine yet/);
  await stage.press("btn_read");
  await stage.press("btn_book");
  assert.deepEqual(bridge.calls, ["maps"], "nothing was asked of a map that does not exist");
});

test("Read on the map plays the teach-back, the words the expert confirmed", async () => {
  const { stage, bridge, dom } = await fresh();
  await stage.press("btn_read");
  assert.ok(bridge.calls.includes("teach-back m1"));
  assert.equal(dom.text.textContent, "Here is how I understand it.");
  assert.deepEqual(bridge.played, ["T"]);
});

test("Braille sends the map to the embosser, and a second press puts the sheet away", async () => {
  const { stage, bridge, prompter, dom } = await fresh();
  await stage.press("btn_braille");
  assert.ok(bridge.calls.includes("braille m1 2"), "grade 2, what an embosser prints");
  assert.ok(prompter.sheetVisible);
  assert.equal(dom.slot.querySelector(".braille-page-label").textContent, "Page 1 of 2");
  assert.match(bridge.said.at(-1), /on the embosser: 2 pages/);
  await stage.press("btn_braille");
  assert.equal(prompter.sheetVisible, false);
});

test("Book tries the practice case, is stopped, says why, and prints the slip", async () => {
  const { stage, bridge, prompter, dom } = await fresh();
  await stage.press("btn_book");
  assert.equal(stage.chapter, "case", "booking moves to the case");
  assert.ok(bridge.calls.includes("review m1"));
  assert.match(dom.text.textContent, /check the bank details first/);
  assert.deepEqual(bridge.played, ["A1"], "the expert's sentence is heard");
  assert.ok(prompter.sheetVisible, "and printed, to stay on the desk");
});

test("a case the controller cleared says who cleared it, not just that it passed", async () => {
  const { stage, dom } = await fresh({ review: { allowed: true, interventions: [],
    cleared: [{ by: "Controller Weber", said: "Novak is approved." }] } });
  await stage.book();
  assert.match(dom.text.textContent, /Booked\. Not stopped, because Controller Weber decided: "Novak is approved\."/);
});

test("the wheel goes map, case, exam, and back to the map", async () => {
  const { stage, bridge, dom } = await fresh();
  await stage.press("mode_wheel");
  assert.equal(stage.chapter, "case");
  await stage.press("mode_wheel");
  assert.equal(stage.chapter, "exam");
  assert.ok(bridge.calls.includes("exam m1"));
  await stage.press("mode_wheel");
  assert.equal(stage.chapter, "map");
  assert.ok(bridge.said.some((t) => t.startsWith("The exam.")), "every turn says where it landed");
  assert.ok(!dom.text.textContent.startsWith("The Work Map."), "and the screen does not say it twice");
});

test("Talk outside the exam says what it is for, instead of doing nothing", async () => {
  const { stage, bridge } = await fresh();
  assert.equal(await stage.talk(), false);
  assert.match(bridge.said.at(-1), /Talk answers the exam/);
  assert.equal(bridge.isRecording, false, "the microphone was not opened");
});

test("the exam by voice: hold, answer, hear the expert's words, move on", async () => {
  const { stage, bridge, dom } = await fresh();
  await stage.setChapter("exam", { speak: false });
  assert.match(dom.text.textContent, /Case 1 of 2\. 5,000 exactly/);
  assert.equal(await stage.talk(), true);
  await stage.release();
  assert.ok(bridge.calls.includes("answer r1 audio"), "the recording was sent, not a guess");
  assert.match(dom.text.textContent, /Right\. Sabine said/);
  assert.equal(stage.examIndex, 1);
  await stage.answer({ said: "no" });
  assert.match(dom.text.textContent, /Not quite\..*1 of 2 right/);
});

test("an answer that is not clearly yes or no is asked again and never graded", async () => {
  const { stage, dom } = await fresh();
  await stage.setChapter("exam", { speak: false });
  await stage.answer({ said: "hmm, maybe" });
  assert.equal(stage.examIndex, 0, "still the same case");
  assert.equal(stage.score.answered, 0);
  assert.match(dom.text.textContent, /did not catch a yes or a no/);
});

test("no microphone: the keys Y and N are offered, out loud", async () => {
  const { stage, dom } = await fresh({ micWorks: false });
  await stage.setChapter("exam", { speak: false });
  assert.equal(await stage.talk(), false);
  assert.match(dom.text.textContent, /Press Y for yes, or N for no/);
});

test("the case read out is the same case the review is given", async () => {
  const { stage, bridge } = await fresh();
  await stage.setChapter("case", { speak: false });
  await stage.press("btn_read");
  const spoken = bridge.said.at(-1);
  for (const [key, value] of Object.entries(PRACTICE_CASE)) {
    assert.ok(spoken.includes(`${key.replace(/_/g, " ")}: ${value === null ? "none" : value}`),
              `${key} is read out`);
  }
});

test("a server that stops answering is said on the prompter, and the key is released", async () => {
  const { stage, dom, inUse } = await fresh();
  stage.bridge.teachBack = async () => { throw new Error("down"); };
  await stage.press("btn_read");
  assert.match(dom.text.textContent, /did not answer/);
  assert.deepEqual(inUse.at(-1), ["btn_read", false]);
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
