/**
 * The deck's keys, run against a fake server.
 *
 * The fake bridge answers the way the learner's routes do (tests/learner checks those), so
 * what is proved here is the stage's own behaviour: which key calls what, in which part of
 * learning, and what a person without sight is told when a key has nothing to do.
 *
 * Found on 2026-10-17: the stage still taught the first version's way, a guardian's draft map,
 * an invoice case hard-coded for every knowledge, and an exam read straight from the map with
 * no access level. It now learns what was published, at the learner's level, as /learn/ does.
 */
import assert from "node:assert/strict";
import { installDom, buildPrompter } from "./dom_stub.mjs";

const { El, root } = installDom();
const { PrompterController } = await import("../../apu/ui/presentation/prompter.js");
const { Stage, yesOrNo } = await import("../../apu/ui/presentation/stage.js");

const cases = [];
const test = (name, fn) => cases.push([name, fn]);

const BODY = { body_id: "b1", name: "Ferment cocoa beans", guardian: "Akosua" };
const UNITS = [
  { unit_id: "b1:step-1", text: "Heap the beans on banana leaves", quote: "We heap the beans on banana leaves." },
  { unit_id: "b1:rule-turn", text: "When the heap has fermented two days, turn it", quote: "We turn it on day two." },
];

class FakeBridge {
  constructor(overrides = {}) {
    this.calls = [];
    this.said = [];
    this.played = [];
    this.isOnline = true;
    this.isRecording = false;
    this.micWorks = true;
    this.bodies_ = [BODY];
    this.quizzes = { "b1:step-1": [], "b1:rule-turn": [{ case_id: "c1", question: "Exactly two days: turn it?" }] };
    this.examCases = [{ case_id: "c1", question: "Exactly two days: turn it?" }, { case_id: "c2", question: "One day: turn it?" }];
    this.decided = { c1: true, c2: false };
    this.heard = "yes";
    Object.assign(this, overrides);
  }
  async bodies() { this.calls.push("bodies"); return this.bodies_; }
  async path(id) { this.calls.push(`path ${id}`); return { body: BODY, units: UNITS }; }
  async unit(id) { this.calls.push(`unit ${id}`); return { unit: UNITS.find((u) => u.unit_id === id), quiz: this.quizzes[id] || [] }; }
  async listen(id) { this.calls.push(`listen ${id}`); return { text: "Akosua said: we heap the beans.", audio: "L", mime: "audio/mpeg" }; }
  async braille(id, grade) { this.calls.push(`braille ${id} ${grade}`); return { pages_unicode: [["⠁⠃"]], brf: "AB", pages: 1 }; }
  async quiz(caseId, given) {
    this.calls.push(`quiz ${caseId} ${JSON.stringify(given)}`);
    const said = given.answer ?? given.said ?? (given.audio ? this.heard : null);
    const answer = typeof said === "boolean" ? said : yesOrNo(said);
    if (answer === null) return { understood: false, heard: said };
    return { understood: true, right: answer === this.decided[caseId], by: "Akosua", said: "Yes, on day two exactly." };
  }
  async exam(id) { this.calls.push(`exam ${id}`); return { cases: this.examCases }; }
  async markExam(id, answers) {
    this.calls.push(`mark ${id} ${JSON.stringify(answers)}`);
    const feedback = this.examCases.map((c) => ({ case_id: c.case_id, question: c.question, right: answers[c.case_id] === this.decided[c.case_id],
                                                    by: "Akosua", said: "So it is." }));
    return { correct: feedback.filter((f) => f.right).length, total: feedback.length, feedback };
  }
  async hear() { this.calls.push("hear"); return { said: this.heard }; }
  async ask(id, question, unitId) {
    this.calls.push(`ask ${id} ${question} ${unitId}`);
    return { kind: "worded", text: "Turn it on day two [1].", citations: [{ unit_id: "b1:rule-turn" }] };
  }
  async keep(id, kept) { this.calls.push(`keep ${id} ${kept.kind} ${kept.unitIds.join(",")}`); return { entry: {} }; }
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

test("it opens a published knowledge on its path and says what it holds", async () => {
  const { stage, bridge, dom, statuses } = await fresh();
  assert.equal(stage.bodyId, "b1");
  assert.equal(stage.chapter, "path");
  assert.deepEqual(bridge.calls, ["bodies", "path b1"], "the learner's routes, nothing of a guardian's map");
  assert.match(dom.text.textContent, /Ferment cocoa beans, taught by Akosua: 2 parts\. Part 1 of 2: Heap the beans/);
  assert.deepEqual(statuses.at(-1), ["connected", "Akosua's knowledge"]);
});

test("nothing published for this learner is said plainly, and no key pretends to work", async () => {
  const { stage, bridge, dom } = await fresh({ bodies_: [] });
  assert.match(dom.text.textContent, /Nothing is published yet that this learner may learn/);
  await stage.press("btn_read");
  await stage.press("btn_book");
  assert.deepEqual(bridge.calls, ["bodies"], "nothing was asked of a knowledge that is not there");
});

test("Read plays the part in the guardian's own words", async () => {
  const { stage, bridge, dom } = await fresh();
  await stage.press("btn_read");
  assert.ok(bridge.calls.includes("listen b1:step-1"));
  assert.equal(dom.text.textContent, "Akosua said: we heap the beans.");
  assert.deepEqual(bridge.played, ["L"]);
});

test("the arrows move along the path, and say where the path ends", async () => {
  const { stage, bridge, dom } = await fresh();
  await stage.move(1);
  assert.equal(stage.index, 1);
  assert.match(dom.text.textContent, /Part 2 of 2: When the heap has fermented/);
  await stage.move(1);
  assert.equal(stage.index, 1);
  assert.match(bridge.said.at(-1), /This is the last part/);
});

test("Braille prints the part in front of the learner, and a second press puts the sheet away", async () => {
  const { stage, bridge, prompter } = await fresh();
  await stage.press("btn_braille");
  assert.ok(bridge.calls.includes("braille b1:step-1 2"), "grade 2, what an embosser prints");
  assert.ok(prompter.sheetVisible);
  assert.match(bridge.said.at(-1), /Part 1 is on the embosser: 1 page/);
  await stage.press("btn_braille");
  assert.equal(prompter.sheetVisible, false);
});

test("practice puts the part's own cases, graded by the server, in the guardian's words", async () => {
  const { stage, bridge, dom } = await fresh();
  await stage.move(1);
  await stage.setChapter("practice", { speak: false });
  assert.ok(bridge.calls.includes("unit b1:rule-turn"), "the cases decided for this part");
  assert.match(dom.text.textContent, /Exactly two days: turn it\?/);
  await stage.answer({ answer: true });
  assert.ok(bridge.calls.includes('quiz c1 {"answer":true}'), "graded on the server, never on the page");
  assert.match(dom.text.textContent, /Right\. Akosua said: "Yes, on day two exactly\."/);
});

test("a part with no case says so in practice, and Talk there does not open the microphone", async () => {
  const { stage, bridge, dom } = await fresh();
  await stage.setChapter("practice", { speak: false });
  assert.match(dom.text.textContent, /decided no case on this part/);
  assert.equal(await stage.talk(), false);
  assert.equal(bridge.isRecording, false);
  assert.match(bridge.said.at(-1), /no case to answer on this part\. On the path, Talk asks a question/,
               "a key with nothing to do says so, out loud");
});

test("practice by voice: hold, answer, and an unclear answer is asked again, never graded", async () => {
  const { stage, bridge, dom } = await fresh({ heard: "hmm, maybe" });
  await stage.move(1);
  await stage.setChapter("practice", { speak: false });
  assert.equal(await stage.talk(), true);
  await stage.release();
  assert.ok(bridge.calls.some((c) => c.startsWith("quiz c1") && c.includes("audio")), "the recording was sent");
  assert.match(dom.text.textContent, /did not catch a yes or a no/);
});

test("the exam is answered case by case and marked only at the end", async () => {
  const { stage, bridge, dom } = await fresh();
  await stage.setChapter("exam", { speak: false });
  assert.match(dom.text.textContent, /Case 1 of 2\. Exactly two days/);
  await stage.answer({ said: "yes" });
  assert.ok(!bridge.calls.some((c) => c.startsWith("mark")), "nothing marked before the last answer");
  await stage.answer({ said: "oui" });
  assert.ok(bridge.calls.includes('mark b1 {"c1":true,"c2":true}'));
  assert.match(dom.text.textContent, /1 of 2 right\. One day: turn it\? Akosua said: "So it is\."/);
});

test("an exam answer that is not yes or no is asked again, and not recorded", async () => {
  const { stage, dom } = await fresh();
  await stage.setChapter("exam", { speak: false });
  await stage.answer({ said: "perhaps" });
  assert.equal(stage.examIndex, 0);
  assert.deepEqual(stage.examAnswers, {});
  assert.match(dom.text.textContent, /did not catch a yes or a no/);
});

test("on the path, Talk asks a question aloud: heard, answered with citations, and kept on Enter", async () => {
  const { stage, bridge, dom } = await fresh({ heard: "When do we turn the heap?" });
  assert.equal(await stage.talk(), true);
  await stage.release();
  assert.ok(bridge.calls.includes("hear"));
  assert.ok(bridge.calls.includes("ask b1 When do we turn the heap? b1:step-1"), "asked from the part in view");
  assert.match(dom.text.textContent, /Turn it on day two \[1\]\. Press Enter to keep it\./);
  await stage.press("btn_book");
  assert.ok(bridge.calls.includes("keep b1 whole b1:rule-turn"), "the answer whole, with the parts it cites");
});

test("Keep with no answer keeps the part in the guardian's words", async () => {
  const { stage, bridge } = await fresh();
  await stage.press("btn_book");
  assert.ok(bridge.calls.includes("keep b1 excerpt b1:step-1"));
  assert.match(bridge.said.at(-1), /Part 1 is kept in your notebook/);
});

test("no microphone: the keys Y and N are offered, out loud", async () => {
  const { stage, dom } = await fresh({ micWorks: false });
  await stage.setChapter("exam", { speak: false });
  assert.equal(await stage.talk(), false);
  assert.match(dom.text.textContent, /Press Y for yes, or N for no/);
});

test("the wheel goes path, practice, exam, and back, saying where it landed", async () => {
  const { stage, bridge } = await fresh();
  await stage.press("mode_wheel");
  assert.equal(stage.chapter, "practice");
  await stage.press("mode_wheel");
  assert.equal(stage.chapter, "exam");
  assert.ok(bridge.calls.includes("exam b1"));
  await stage.press("mode_wheel");
  assert.equal(stage.chapter, "path");
  assert.ok(bridge.said.some((t) => t.startsWith("The exam.")));
});

test("a server that stops answering is said on the prompter, and the key is released", async () => {
  const { stage, dom, inUse } = await fresh();
  stage.bridge.listen = async () => { throw new Error("down"); };
  stage.bridge.say = async () => { throw new Error("down"); };
  await stage.press("btn_read");
  assert.match(dom.text.textContent, /We heap the beans|did not answer/);
  assert.deepEqual(inUse.at(-1), ["btn_read", false]);
});

test("yes or no is decided by code, in English and in French", () => {
  assert.equal(yesOrNo("Yes, turn it"), true);
  assert.equal(yesOrNo("non"), false);
  assert.equal(yesOrNo("yes and no"), null);
  assert.equal(yesOrNo("perhaps"), null);
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
