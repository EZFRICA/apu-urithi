/**
 * One keyboard map for every page, and ? to list the keys of the page.
 *
 * The keys every page shares are here, so Space always talks and Escape always goes back;
 * each page adds its own. ? opens a dialog that lists them in words, in the page's language;
 * Escape or ? again closes it, and focus returns where it was.
 */

const SHARED = {
  en: [["Space", "Hold to talk, let go to send"], ["?", "These keys"], ["Esc", "Back, or close"]],
  fr: [["Espace", "Maintenir pour parler, relâcher pour envoyer"], ["?", "Ces touches"], ["Échap", "Retour, ou fermer"]],
};
const TITLE = { en: "Keys on this page", fr: "Les touches de cette page" };
const CLOSE = { en: "Close", fr: "Fermer" };

export class KeyMap {
  /** `own`: (lang) => [[key, what it does], ...], the page's keys beside the shared ones. */
  constructor(own) {
    this.own = own || (() => []);
    this.dialog = null;
    window.addEventListener("keydown", (event) => {
      if (event.key !== "?" || event.metaKey || event.ctrlKey || event.altKey) return;
      if (["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName)) return;
      event.preventDefault();
      this.toggle();
    });
  }

  lang() { return (document.documentElement.lang || "en").slice(0, 2) === "fr" ? "fr" : "en"; }

  list() {
    const lang = this.lang();
    return [...SHARED[lang], ...this.own(lang)];
  }

  toggle() {
    if (this.dialog?.open) { this.dialog.close(); return; }
    this.returnTo = document.activeElement;
    const lang = this.lang();
    if (!this.dialog) {
      this.dialog = document.createElement("dialog");
      this.dialog.className = "keys-dialog";
      this.dialog.setAttribute("aria-labelledby", "keys-dialog-title");
      this.dialog.addEventListener("close", () => this.returnTo?.focus?.());
      document.body.appendChild(this.dialog);
    }
    this.dialog.innerHTML = "";
    const title = document.createElement("h2");
    title.id = "keys-dialog-title";
    title.textContent = TITLE[lang];
    const table = document.createElement("dl");
    for (const [key, what] of this.list()) {
      const dt = document.createElement("dt");
      const kbd = document.createElement("kbd");
      kbd.textContent = key;
      dt.appendChild(kbd);
      const dd = document.createElement("dd");
      dd.textContent = what;
      table.append(dt, dd);
    }
    const close = document.createElement("button");
    close.type = "button";
    close.className = "primary";
    close.textContent = CLOSE[lang];
    close.addEventListener("click", () => this.dialog.close());
    this.dialog.append(title, table, close);
    this.dialog.showModal();
    close.focus();
  }
}
