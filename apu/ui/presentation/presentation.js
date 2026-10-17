/**
 * presentation.js - the page around the stage: the deck, the camera, the keyboard.
 *
 * What a key does lives in stage.js. This file only connects things to it: a click on the
 * 3D deck, a button in the list of parts, a key on the keyboard. All three reach the same
 * function, so the deck, the list and the keyboard cannot disagree about what a key does.
 */

import { CameraController } from "./camera.js";
import { PrompterController } from "./prompter.js";
import { KeynoteHardware3D, HARDWARE_PARTS_INFO } from "./hardware3d.js";
import { ApprenticeBridge } from "./bridge.js";
import { CHAPTERS, CHAPTER_NAMES, Stage } from "./stage.js";

const PARTS_LIST = [
  { id: "btn_talk", icon: "🎙️", name: "Talk", sub: "Hold Space, ask or answer out loud" },
  { id: "btn_read", icon: "≡", name: "Read", sub: "R, hear it in the guardian's words" },
  { id: "btn_book", icon: "✓", name: "Keep", sub: "Enter, into the notebook" },
  { id: "btn_braille", icon: "⠿", name: "Braille", sub: "B, print the part" },
  { id: "mode_wheel", icon: "◎", name: "Mode wheel", sub: "1 2 3, path, practice, exam" },
  { id: "port_embosser", icon: "⎙", name: "Embosser port", sub: "Prints the .BRF" },
  { id: "port_headphones", icon: "🎧", name: "Headphones", sub: "Private audio" },
  { id: "port_power", icon: "⚡", name: "USB-C", sub: "To the workstation" },
];

const STATUS_WORDS = { wired: "Works on this stage", simulated: "Simulated, and says so",
                       concept: "Hardware concept" };

class StagePage {
  constructor() {
    const $ = (id) => document.getElementById(id);
    this.dom = {
      video: $("camera-feed"),
      prompter: $("prompter-stage-container"),
      deck: $("equipment-3d-stage"),
      chapterTabs: document.querySelectorAll(".model-pill-btn"),
      mapSelect: $("map-select"),
      learnerSelect: $("learner-select"),
      statusPill: $("status-pill"),
      statusText: $("status-text"),
      talkBtn: $("toggle-mic-btn"),
      cameraBtn: $("toggle-camera-btn"),
      mirrorBtn: $("toggle-mirror-btn"),
      fullscreenBtn: $("toggle-fullscreen-btn"),
      drawerBtn: $("toggle-drawer-btn"),
      drawer: $("hardware-parts-drawer"),
      inspector: $("hardware-inspector-card"),
      inspectorBadge: $("inspector-badge"),
      inspectorStatus: $("inspector-status"),
      inspectorTitle: $("inspector-title"),
      inspectorKey: $("inspector-key"),
      inspectorCode: $("inspector-code"),
      inspectorDesc: $("inspector-desc"),
      partsList: $("parts-list"),
      shotBtns: document.querySelectorAll(".view-shot-btn"),
    };

    this.prompter = new PrompterController(this.dom.prompter);
    this.deck = new KeynoteHardware3D(
      this.dom.deck,
      (partId) => this._pressed(partId),
      (partId, info) => this._inspect(partId, info),
    );
    this.bridge = new ApprenticeBridge({
      onEvent: (type) => {
        if (type === "offline") this._status("offline", "Server not answering");
      },
    });
    this.stage = new Stage({
      lang: new URLSearchParams(window.location.search).get("lang") === "fr" ? "fr" : "en",
      bridge: this.bridge,
      prompter: this.prompter,
      device: {
        setInUse: (partId, on) => {
          this.deck.setButtonInUse(partId, on);
          this._markInUse(partId, on);
          if (partId === "btn_talk") this._pressedState(this.dom.talkBtn, on);
        },
      },
      onStatus: (state, text) => this._status(state, text),
    });

    this.camera = new CameraController(this.dom.video, () => {});
    this.camera.start()
      .then(() => this._pressedState(this.dom.cameraBtn, this.camera.isActive))
      .catch((error) => console.warn("Camera:", error));
    this._pressedState(this.dom.mirrorBtn, this.camera.isMirrored);
    this._pressedState(this.dom.drawerBtn, true);

    this._renderParts();
    this._bind();
    this._inspect("btn_talk", HARDWARE_PARTS_INFO.btn_talk);
    this._start();
  }

  async _start() {
    await this._fillLearners();
    const params = new URLSearchParams(window.location.search);
    if (await this.stage.load(params.get("knowledge"))) this._fillKnowledge();
    this._showChapter(this.stage.chapter);
  }

  /** Who learns on the stage: any learner, at their level; ?learner=visitor names one. */
  async _fillLearners() {
    const select = this.dom.learnerSelect;
    const learners = await this.bridge.learners();
    if (!select || !learners.length) return;
    select.innerHTML = "";
    for (const p of learners) {
      const option = document.createElement("option");
      option.value = `${p.person_id}@${p.organisation}`;
      option.textContent = `${p.name} · ${p.organisation_name}`;   // textContent: names are typed by people
      select.appendChild(option);
    }
    const asked = new URLSearchParams(window.location.search).get("learner");
    const values = learners.map((p) => `${p.person_id}@${p.organisation}`);
    const chosen = values.find((v) => v === asked || v.split("@")[0] === asked)
      || values.find((v) => v.split("@")[0] === this.bridge.person) || values[0];
    select.value = chosen;
    this._asLearner(chosen);
  }

  _asLearner(value) {
    const [person, organisation] = value.split("@");
    this.bridge.asLearner(person, organisation || null);
  }

  /** What this learner may learn, from every guardian who published. */
  _fillKnowledge() {
    const select = this.dom.mapSelect;
    if (!select) return;
    select.innerHTML = "";
    for (const body of this.stage.bodies) {
      const option = document.createElement("option");
      option.value = body.body_id;
      // textContent: a name and a guardian are typed by people, never markup.
      option.textContent = `${body.name} · ${body.guardian}`;
      option.selected = body.body_id === this.stage.bodyId;
      select.appendChild(option);
    }
  }

  _remember(key, value) {
    const url = new URL(window.location.href);
    url.searchParams.set(key, value);
    window.history.replaceState(null, "", url);
  }

  // ── what a part does ───────────────────────────────────────────────────────

  /** A part pressed on the deck or in the list. Talk toggles here; the keyboard holds it. */
  async _pressed(partId) {
    if (partId === "btn_talk") {
      if (this.bridge.isRecording) await this.stage.release();
      else await this.stage.talk();
    } else {
      await this.stage.press(partId);
    }
    this._showChapter(this.stage.chapter);
  }

  _inspect(partId, info) {
    if (!info) return;
    document.querySelectorAll(".part-btn-item").forEach((b) => {
      b.classList.toggle("active", b.dataset.part === partId);
    });
    this.dom.inspectorBadge.textContent = info.badge || "";
    this.dom.inspectorStatus.textContent = STATUS_WORDS[info.status] || "";
    this.dom.inspectorStatus.className = `inspector-status ${info.status || ""}`;
    this.dom.inspectorTitle.textContent = info.name || partId;
    this.dom.inspectorKey.textContent = info.key ? `Key: ${info.key}` : "";
    this.dom.inspectorKey.hidden = !info.key;
    this.dom.inspectorCode.textContent = info.codeRef || "";
    this.dom.inspectorDesc.textContent = info.desc || "";
  }

  _renderParts() {
    const list = this.dom.partsList;
    list.innerHTML = "";
    for (const part of PARTS_LIST) {
      const button = document.createElement("button");
      button.className = "part-btn-item";
      button.dataset.part = part.id;
      // Named out loud: these buttons are the only way to the deck for anyone not holding
      // a mouse, and the icon is decoration.
      button.setAttribute("aria-label", `${part.name}. ${part.sub}`);
      const icon = document.createElement("span");
      icon.className = "part-icon";
      icon.setAttribute("aria-hidden", "true");
      icon.textContent = part.icon;
      const info = document.createElement("div");
      info.className = "part-info";
      const name = document.createElement("span");
      name.className = "part-name";
      name.textContent = part.name;
      const sub = document.createElement("span");
      sub.className = "part-desc-short";
      sub.textContent = part.sub;
      info.append(name, sub);
      button.append(icon, info);
      button.addEventListener("click", () => this.deck.triggerPress(part.id));
      list.appendChild(button);
    }
  }

  _markInUse(partId, on) {
    document.querySelectorAll(".part-btn-item").forEach((b) => {
      if (b.dataset.part === partId) b.classList.toggle("in-use", Boolean(on));
    });
  }

  _showChapter(name) {
    this.dom.chapterTabs.forEach((tab) => {
      const on = tab.dataset.chapter === name;
      tab.classList.toggle("active", on);
      tab.setAttribute("aria-pressed", String(on));
    });
  }

  // ── the page's own controls ────────────────────────────────────────────────

  _bind() {
    this.dom.chapterTabs.forEach((tab) => {
      tab.addEventListener("click", async () => {
        await this.stage.setChapter(tab.dataset.chapter);
        this._showChapter(this.stage.chapter);
      });
    });

    this.dom.learnerSelect?.addEventListener("change", async (event) => {
      this._asLearner(event.target.value);
      this._remember("learner", event.target.value);
      const found = await this.stage.load(this.stage.bodyId);
      if (found) this._fillKnowledge();
      else if (this.dom.mapSelect) this.dom.mapSelect.innerHTML = "";
      this._showChapter(this.stage.chapter);
    });

    this.dom.mapSelect?.addEventListener("change", async (event) => {
      await this.stage.select(event.target.value);
      this._remember("knowledge", event.target.value);
      this._showChapter(this.stage.chapter);
    });

    this.dom.talkBtn?.addEventListener("click", () => this.deck.triggerPress("btn_talk"));

    this.dom.cameraBtn?.addEventListener("click", async () => {
      if (this.camera.isActive) this.camera.stop();
      else await this.camera.start();
      this._pressedState(this.dom.cameraBtn, this.camera.isActive);
    });
    this.dom.mirrorBtn?.addEventListener("click", () => {
      this.camera.toggleMirror();
      this._pressedState(this.dom.mirrorBtn, this.camera.isMirrored);
    });
    this.dom.fullscreenBtn?.addEventListener("click", () => {
      if (!document.fullscreenElement) document.documentElement.requestFullscreen().catch(() => {});
      else document.exitFullscreen().catch(() => {});
    });
    this.dom.drawerBtn?.addEventListener("click", () => {
      const collapsed = this.dom.drawer.classList.toggle("collapsed");
      this.dom.inspector.classList.toggle("collapsed", collapsed);
      // Out of sight is not out of the accessibility tree unless it is hidden there too.
      [this.dom.drawer, this.dom.inspector].forEach((panel) => { panel.hidden = collapsed; });
      this._pressedState(this.dom.drawerBtn, !collapsed);
    });
    this.dom.shotBtns.forEach((button) => {
      button.addEventListener("click", () => {
        this.dom.shotBtns.forEach((b) => {
          b.classList.toggle("active", b === button);
          b.setAttribute("aria-pressed", String(b === button));
        });
        this.deck.setShot(button.dataset.shot);
      });
    });

    // The deck on the stage is a canvas: no focus, no keys. The keyboard is its equivalent,
    // key for key, and Space is held like the Talk key is.
    window.addEventListener("keydown", (event) => this._keyDown(event));
    window.addEventListener("keyup", (event) => {
      if (event.key === " " && this.bridge.isRecording) {
        event.preventDefault();
        this.stage.release();
      }
    });
  }

  _keyDown(event) {
    if (event.metaKey || event.ctrlKey || event.altKey) return;
    const tag = document.activeElement?.tagName;
    if (["INPUT", "SELECT", "TEXTAREA"].includes(tag)) return;
    // On a focused button, Space and Enter press that button, as they always do.
    const onButton = tag === "BUTTON" || tag === "A";
    const key = event.key.length === 1 ? event.key.toLowerCase() : event.key;

    if (key === " " && !onButton) {
      event.preventDefault();
      if (!event.repeat && !this.bridge.isRecording) {
        this.deck.setButtonInUse("btn_talk", true);
        this.stage.talk().then((open) => {
          if (!open) this.deck.setButtonInUse("btn_talk", false);
        });
      }
    } else if (key === "Enter" && !onButton) {
      event.preventDefault();
      this.deck.triggerPress("btn_book");
    } else if (key === "ArrowRight" || key === "ArrowLeft") {
      event.preventDefault();
      this.stage.move(key === "ArrowRight" ? 1 : -1);
    } else if (key === "r") {
      this.deck.triggerPress("btn_read");
    } else if (key === "b") {
      this.deck.triggerPress("btn_braille");
    } else if (key === "y" || key === "n") {
      this.stage.answer({ said: key === "y" ? "yes" : "no" });
    } else if (["1", "2", "3"].includes(key)) {
      const chapter = CHAPTERS[Number(key) - 1];
      this.stage.setChapter(chapter).then(() => this._showChapter(chapter));
      this.prompter.announce(CHAPTER_NAMES[chapter]);
    } else if (key === "Escape" && this.prompter.sheetVisible) {
      this.prompter.closeSheet();
      this.deck.setButtonInUse("btn_braille", false);
      this._markInUse("btn_braille", false);
    }
  }

  _pressedState(element, on) {
    element?.setAttribute("aria-pressed", on ? "true" : "false");
    element?.classList.toggle("active", Boolean(on));
  }

  _status(state, text) {
    if (this.dom.statusPill) this.dom.statusPill.className = `status-pill ${state}`;
    if (this.dom.statusText) this.dom.statusText.textContent = text;
  }
}

window.addEventListener("DOMContentLoaded", () => { window.stagePage = new StagePage(); });
