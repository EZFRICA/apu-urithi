/**
 * prompter.js - what is being said, in print, and what the embosser printed, in braille.
 *
 * One sentence on screen at a time: the one the deck just said, or the one the new hire
 * just said. Under it, when the braille key or a stopped save sends something to the
 * embosser, the sheet that comes out.
 *
 * Nothing here makes braille. The cells come from the server, laid out by the same code
 * that writes the .BRF an embosser prints from; with no cells, the sheet says so, and is
 * never filled with something that only looks like braille.
 */

const SPEAKERS = {
  apprentice: "Urithi",
  hire: "The learner",
  expert: "In the guardian's own words",
};

export class PrompterController {
  constructor(containerEl) {
    this.container = containerEl;
    this.badgeEl = containerEl.querySelector(".prompter-speaker-badge");
    this.textWindow = containerEl.querySelector(".prompter-text-window");
    this.textEl = containerEl.querySelector(".prompter-text");
    this.cardSlot = containerEl.querySelector(".prompter-card-slot");
    this.announcerEl = containerEl.querySelector("#prompter-announcer");
    this.currentSpeaker = "idle";
    this.activeText = "";
    this.sheet = null;
    this.sheetVisible = false;
    this._printTimer = null;
  }

  setSpeaker(speaker, label) {
    this.currentSpeaker = speaker;
    if (!this.badgeEl) return;
    this.badgeEl.className = `prompter-speaker-badge ${speaker}`;
    // textContent: a label can carry a person's name, which is never markup.
    this.badgeEl.textContent = "";
    if (speaker === "listening") {
      const pulse = document.createElement("span");
      pulse.className = "badge-pulse";
      this.badgeEl.appendChild(pulse);
    }
    const text = document.createElement("span");
    text.textContent = label || SPEAKERS[speaker] || (speaker === "listening"
      ? "Listening, let go when done" : "Ready");
    this.badgeEl.appendChild(text);
  }

  /**
   * One whole sentence on screen, replacing the one before. Read once to a screen reader,
   * whole, because a live region that is written into piece by piece is read piece by piece.
   */
  show(text, speaker = "apprentice", label) {
    this.setSpeaker(speaker, label);
    this.activeText = text || "";
    if (this.textEl) {
      this.textEl.classList.toggle("empty", !this.activeText);
      this.textEl.textContent = this.activeText;
      if (this.textWindow) this.textWindow.scrollTop = 0;
    }
    this._announce(this.activeText);
  }

  /** Something went wrong, on the prompter and to the screen reader, not in a corner. */
  showNotice(message) {
    this.show(message, "idle", "Note");
    this.textEl?.classList.add("empty");
  }

  /**
   * The embosser's output: pages of cells as the paper holds them.
   *
   * `pages` is a list of pages, each a list of lines, exactly as the server laid them out:
   * forty cells to a line, twenty-five lines to a page. The lines are revealed one after
   * the other, the way an embosser actually produces a page, unless the viewer asked for
   * less motion, in which case the page is simply there.
   */
  printSheet({ title, pages, brf, filename, note }) {
    this.sheet = { title, pages: pages || [], brf: brf || "", filename, note };
    this.sheetVisible = true;
    this.container?.classList.add("braille-open");
    this._renderSheet();
    return true;
  }

  closeSheet() {
    this.sheetVisible = false;
    window.clearInterval(this._printTimer);
    this.container?.classList.remove("braille-open");
    if (this.cardSlot) this.cardSlot.innerHTML = "";
    return false;
  }

  _renderSheet() {
    if (!this.cardSlot || !this.sheet) return;
    window.clearInterval(this._printTimer);
    this.cardSlot.innerHTML = "";
    const { title, pages, brf, filename, note } = this.sheet;

    const card = document.createElement("section");
    card.className = "braille-keynote-card";
    card.setAttribute("role", "region");
    card.setAttribute("aria-label", "Braille, as embossed");

    const header = document.createElement("div");
    header.className = "braille-card-header";
    const group = document.createElement("div");
    group.className = "braille-title-group";
    const tag = document.createElement("span");
    tag.className = "braille-tag";
    tag.textContent = title || "Embossed";
    const sub = document.createElement("span");
    sub.className = "braille-sub";
    sub.textContent = pages.length
      ? `${pages.length} page${pages.length > 1 ? "s" : ""}, forty cells to a line` +
        (note ? `. ${note}` : "")
      : "Nothing was embossed";
    group.append(tag, sub);
    const close = document.createElement("button");
    close.className = "braille-close-btn";
    close.setAttribute("aria-label", "Put the sheet away");
    close.title = "Put the sheet away (Escape)";
    close.textContent = "X";
    close.addEventListener("click", () => this.closeSheet());
    header.append(group, close);

    const paper = document.createElement("div");
    paper.className = "braille-sheet";
    paper.tabIndex = 0;
    paper.setAttribute("role", "group");
    paper.setAttribute("aria-label", pages.length
      ? `Braille page, ${pages.length} in all` : "Nothing was embossed");
    const pageEl = document.createElement("div");
    pageEl.className = "braille-page as-printed";
    paper.appendChild(pageEl);

    const footer = document.createElement("div");
    footer.className = "braille-card-footer";
    const nav = document.createElement("div");
    nav.className = "braille-page-nav";
    const prev = this._button("braille-page-btn", "<", "Previous page");
    const label = document.createElement("span");
    label.className = "braille-page-label";
    label.setAttribute("aria-live", "polite");
    const next = this._button("braille-page-btn", ">", "Next page");
    nav.append(prev, label, next);
    const actions = document.createElement("div");
    actions.className = "braille-actions";
    const download = this._button("btn-download-brf", ".BRF", "Download the embosser file");
    download.title = "The file a braille embosser prints from";
    download.disabled = !brf;
    download.addEventListener("click", () => this._download(brf, filename || "work-map.brf"));
    actions.appendChild(download);
    footer.append(nav, actions);

    card.append(header, paper, footer);
    this.cardSlot.appendChild(card);

    let page = 0;
    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    const render = (animate) => {
      window.clearInterval(this._printTimer);
      const lines = pages[page] || [];
      label.textContent = pages.length ? `Page ${page + 1} of ${pages.length}` : "";
      prev.disabled = page === 0;
      next.disabled = page >= pages.length - 1;
      if (!animate || reduced || lines.length < 2) {
        pageEl.textContent = lines.join("\n");
        return;
      }
      // Line by line, the way the head moves down the paper.
      let shown = 0;
      pageEl.textContent = "";
      this._printTimer = window.setInterval(() => {
        shown += 1;
        pageEl.textContent = lines.slice(0, shown).join("\n");
        if (shown >= lines.length) window.clearInterval(this._printTimer);
      }, 70);
    };
    prev.addEventListener("click", () => { page = Math.max(0, page - 1); render(false); });
    next.addEventListener("click", () => { page = Math.min(pages.length - 1, page + 1); render(false); });
    render(true);
  }

  _button(className, text, ariaLabel) {
    const button = document.createElement("button");
    button.className = className;
    button.textContent = text;
    button.setAttribute("aria-label", ariaLabel);
    return button;
  }

  _download(content, filename) {
    if (!content) return;
    const url = URL.createObjectURL(new Blob([content], { type: "text/plain;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  /** Say it once, whole. The empty write first, so the same sentence twice is read twice. */
  _announce(text) {
    if (!this.announcerEl || !text) return;
    window.clearTimeout(this._announceTimer);
    this.announcerEl.textContent = "";
    this._announceTimer = window.setTimeout(() => {
      this.announcerEl.textContent = text;
    }, 60);
  }

  /** Said to a screen reader only: a key's name, a chapter, a state. */
  announce(text) {
    this._announce(text);
  }
}
