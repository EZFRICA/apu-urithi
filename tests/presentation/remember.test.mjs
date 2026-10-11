/** "Remember this", said in a class: the command taken off, what to remember kept. Run, not read. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const source = readFileSync(new URL("../../guardian/ui/teach/teach.js", import.meta.url), "utf8");
const literal = (name) => {
  const line = source.split("\n").find((l) => l.startsWith(`const ${name} = `));
  return eval(line.slice(`const ${name} = `.length).replace(/;$/, ""));
};
const REMEMBER = literal("REMEMBER");
const REMEMBER_ANYWHERE = literal("REMEMBER_ANYWHERE");
const rest = (said) => { const m = said.match(REMEMBER); return m ? said.slice(m[0].length).trim() : null; };

const cases = [];
const test = (name, fn) => cases.push([name, fn]);

test("the command alone keeps the screen and asks what to remember", () => {
  for (const said of ["Remember this.", "remember this screen", "Retiens ça.", "Retiens cet écran", "Please remember that"]) {
    assert.equal(rest(said), "", said);
  }
});

test("what follows the command is what to remember", () => {
  assert.equal(rest("Remember this: newcomers only read the public channel."), "newcomers only read the public channel.");
  assert.equal(rest("Retiens ça, on annonce toujours deux semaines avant."), "on annonce toujours deux semaines avant.");
  assert.equal(rest("Note that the venue holds sixty people"), "the venue holds sixty people");
});

test("a sentence that only mentions remembering is not a command", () => {
  assert.equal(rest("I always remember to confirm the speakers."), null);
  assert.equal(rest("Les membres retiennent mieux avec un rappel."), null);
  assert.equal(rest("Remembering names matters."), null);
});

test("a request to keep what is on screen is heard wherever it is said", () => {
  // The owner's own words, from a real class, where neither was heard as a request.
  for (const said of [
    "Okay, so I want you to keep the information on the part, uh, start to November meetup until the library has three free evenings left.",
    "I just want to keep, uh, uh, some information, like important when you want to create your event.",
    "Je veux que tu gardes ces informations pour la suite.",
    "Can you save this for the new organisers?",
    "Peux-tu retenir ça pour les nouveaux ?",
    "Keep this part, the venue and the format.",
  ]) assert.ok(REMEMBER_ANYWHERE.test(said), said);
});

test("teaching that mentions keeping is still teaching", () => {
  for (const said of [
    "We keep the venue booked two weeks ahead.",
    "Newcomers only read the public channel.",
    "I always note the number of people who came.",
    "We keep this channel public for newcomers.",
    "I keep that list in a spreadsheet, so nobody is forgotten.",
    "On garde cette salle deux semaines à l'avance.",
  ]) assert.ok(!REMEMBER_ANYWHERE.test(said), said);
});

const STRINGS = eval(`(${source.slice(source.indexOf("const STRINGS = {") + "const STRINGS = ".length, source.indexOf("\n};\n") + 2)})`);
const rememberScreenBody = source.slice(
  source.indexOf("  async rememberScreen("),
  source.indexOf("\n  }\n\n  /** The question, the microphone") + 4,
);
const makeTeach = (lang = "en") => {
  const dom = {
    "class-status": { textContent: "" },
    "class-question": { hidden: false, textContent: "" },
  };
  const $ = (id) => dom[id];
  const fn = new Function("$", `return ({ ${rememberScreenBody} }).rememberScreen;`)($);
  const teach = {
    lang,
    dom,
    t(key, ...args) {
      const v = STRINGS[this.lang][key] ?? STRINGS.en[key];
      return typeof v === "function" ? v(...args) : v;
    },
    note() {},
    classroom: {
      open: true,
      pending: null,
      async remember(words) {
        if (words) {
          dom["class-question"].hidden = true;
          return { step: { number: 2, title: words, reason: words } };
        }
        const next = { question: "What should I remember about this screen?" };
        this.pending = next;
        dom["class-question"].hidden = false;
        dom["class-question"].textContent = next.question;
        return next;
      },
    },
  };
  teach.rememberScreen = fn.bind(teach);
  return teach;
};

test("a question waiting is kept when the screen is kept with words and replaced when kept without", async () => {
  const waiting = { question: "Why did you choose #announcements?" };
  const en = makeTeach("en");
  en.classroom.pending = waiting;
  await en.rememberScreen("newcomers only read the public channel");
  assert.equal(en.classroom.pending, waiting);
  assert.equal(en.dom["class-question"].hidden, false);
  assert.equal(en.dom["class-question"].textContent, waiting.question);
  assert.equal(en.dom["class-status"].textContent, "Kept. Urithi's question still waits for you.");

  const fr = makeTeach("fr");
  fr.classroom.pending = waiting;
  await fr.rememberScreen("les nouveaux ne lisent que le canal public");
  assert.equal(fr.classroom.pending, waiting);
  assert.equal(fr.dom["class-status"].textContent, "Gardé. La question d'Urithi t'attend toujours.");

  await en.rememberScreen("");
  assert.equal(en.classroom.pending.question, "What should I remember about this screen?");
  assert.equal(en.dom["class-question"].textContent, "What should I remember about this screen?");
});

test("dragging on #class-video points at a region and shows #class-point, and a command notes each step and rule once", async () => {
  const html = readFileSync(new URL("../../guardian/ui/teach/index.html", import.meta.url), "utf8");
  assert.match(html, /<video\s+id="class-video"/, "classroom video must have id='class-video'");

  const { Classroom } = await import("../../guardian/ui/teach/classroom.js");
  const pointBox = { hidden: true, style: {} };
  const dialog = {
    open: true,
    close() { this.open = false; },
    querySelector(sel) { return sel === "#class-point" ? pointBox : null; },
  };
  const notes = [];
  const runCommandBody = source.slice(
    source.indexOf("  async runCommand("),
    source.indexOf("\n  }\n\n  // Seconds pass while a model words") + 4,
  );
  const dom = {
    "class-status": { textContent: "" },
    "class-question": { hidden: true, textContent: "" },
  };
  const $ = (id) => dom[id];
  const runCommandFn = new Function("$", `return ({ ${runCommandBody} }).runCommand;`)($);

  const posted = [];
  let classroom = null;
  const teach = {
    lang: "en",
    taught: "en",
    captured: 0,
    t(key, ...args) {
      const v = STRINGS[this.lang][key] ?? STRINGS.en[key];
      return typeof v === "function" ? v(...args) : v;
    },
    said(key, ...args) {
      const v = STRINGS[this.taught][key] ?? STRINGS.en[key];
      return typeof v === "function" ? v(...args) : v;
    },
    note(kind, text) { notes.push({ kind, text }); },
    voice() {},
    async refreshMap() {},
  };
  classroom = new Classroom({
    dialog,
    post: async (path, body) => {
      posted.push({ path, body });
      return {
        intent: "mistake",
        step: { number: 1, title: "Common mistake: skipping isolation", reason: body.said },
        guardrails: [{ when: "breaker is live", then: "isolate first", severity: "stop" }],
        noted: "Noted step 1.",
      };
    },
    mapId: () => "map-1",
    onCaptured: (reply) => {
      teach.captured += 1;
      teach.note("step", `${reply.step.number}. ${reply.step.title}: ${reply.step.reason}`);
      for (const rail of reply.guardrails || []) teach.note("rule", `${rail.when} -> ${rail.then}`);
    },
  });
  classroom.capture = { at: 12, source: "screen", async still() { return "jpeg-b64"; } };
  teach.classroom = classroom;
  teach.runCommand = runCommandFn.bind(teach);

  classroom.point({ x: 0.25, y: 0.1, w: 0.5, h: 0.4 });
  assert.equal(pointBox.hidden, false);
  assert.equal(pointBox.style.left, "25%");
  assert.equal(pointBox.style.width, "50%");

  await teach.runCommand("A common mistake is skipping isolation when the breaker is live.");
  assert.equal(posted.length, 1);
  assert.deepEqual(posted[0].body.region, { x: 0.25, y: 0.1, w: 0.5, h: 0.4 });
  assert.equal(classroom.pointed, null);
  assert.equal(pointBox.hidden, true);
  assert.equal(teach.captured, 1, "captured count incremented once, not twice");
  assert.equal(notes.filter((n) => n.kind === "step").length, 1, "step noted once, not twice");
  assert.equal(notes.filter((n) => n.kind === "rule").length, 1, "rule noted once, not twice");
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
