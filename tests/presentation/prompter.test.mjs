/** The prompter and the embosser's sheet, run rather than read. */
import assert from "node:assert/strict";
import { installDom, buildPrompter } from "./dom_stub.mjs";

const { El, root } = installDom();
const { PrompterController } = await import("../../apu/ui/presentation/prompter.js");

const cases = [];
const test = (name, fn) => cases.push([name, fn]);
const fresh = () => {
  root.children = [];
  const dom = buildPrompter(El, root);
  return { p: new PrompterController(dom.container), dom };
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// Two real lines of contracted braille, as the server lays them out.
const PAGE = ["⠠⠱⠢⠀⠮⠀⠎⠥⠏⠏⠇⠊⠻⠀⠊⠎⠀⠝⠑⠺", "⠙⠑⠞⠁⠊⠇⠎⠀⠾⠀⠮⠀⠒⠞⠗⠕⠇⠇⠻"];

test("one sentence on screen: the next one replaces it", () => {
  const { p, dom } = fresh();
  p.show("The case. Invoice 9931.");
  p.show("Stopped before the save.");
  assert.equal(dom.text.textContent, "Stopped before the save.");
});

test("a sentence reaches the screen reader once, whole", async () => {
  const { p, dom } = fresh();
  p.show("When the supplier is new, check the bank details first.");
  await sleep(80);
  assert.equal(dom.announcer.textContent, "When the supplier is new, check the bank details first.");
});

test("the speaker's name is text, never markup", () => {
  const { p, dom } = fresh();
  p.show("Hello.", "expert", "<img src=x onerror=alert(1)>");
  assert.ok(!dom.badge.innerHTML.includes("<img"), "a label typed by a person is not parsed");
  assert.ok(dom.badge.textContent.includes("<img src=x"));
});

test("the sheet holds exactly the server's lines, in order", async () => {
  const { p, dom } = fresh();
  p.printSheet({ title: "Work Map, Grade 2", pages: [PAGE], brf: "X" });
  await sleep(400);   // the head moves down the paper one line at a time
  const page = dom.slot.querySelector(".braille-page");
  assert.equal(page.textContent, PAGE.join("\n"));
  assert.ok(p.sheetVisible);
});

test("cells are set as text: a cell string that looks like markup stays text", () => {
  const { p, dom } = fresh();
  p.printSheet({ title: "x", pages: [["<b>⠁</b>"]], brf: "" });
  const page = dom.slot.querySelector(".braille-page");
  assert.equal(page.children.length, 0, "nothing was parsed into elements");
});

test("no cells means a sheet that says nothing was embossed, never invented braille", () => {
  const { p, dom } = fresh();
  p.printSheet({ title: "Work Map", pages: [], brf: "" });
  const sub = dom.slot.querySelector(".braille-sub");
  assert.equal(sub.textContent, "Nothing was embossed");
  assert.equal(dom.slot.querySelector(".braille-page").textContent, "");
  assert.ok(dom.slot.querySelector(".btn-download-brf").disabled, "no file to download");
});

test("pages turn, and the last page has no next", async () => {
  const { p, dom } = fresh();
  p.printSheet({ title: "x", pages: [["⠁"], ["⠃"]], brf: "A\fB" });
  const [prev, next] = dom.slot.querySelectorAll(".braille-page-btn");
  assert.ok(prev.disabled);
  next.click();
  assert.equal(dom.slot.querySelector(".braille-page").textContent, "⠃");
  assert.equal(dom.slot.querySelector(".braille-page-label").textContent, "Page 2 of 2");
  assert.ok(next.disabled);
});

test("the sheet is put away, and nothing of it stays behind", () => {
  const { p, dom } = fresh();
  p.printSheet({ title: "x", pages: [PAGE], brf: "X" });
  p.closeSheet();
  assert.equal(p.sheetVisible, false);
  assert.equal(dom.slot.children.length, 0);
  assert.ok(!dom.container.classList.contains("braille-open"));
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
