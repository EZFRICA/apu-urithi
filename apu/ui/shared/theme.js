/**
 * Light, dark, or as the system says: the person's choice, kept on this device.
 *
 * Loaded as a plain script in the head, before the page paints, so a dark page never
 * flashes white. A button with the class `theme-toggle` cycles the three, and says which
 * one is on, in words.
 */
(function () {
  const KEY = "urithi.theme";
  const ORDER = ["system", "light", "dark"];
  const LABELS = {
    en: { system: "Theme: as the system", light: "Theme: light", dark: "Theme: dark" },
    fr: { system: "Thème : comme le système", light: "Thème : clair", dark: "Thème : sombre" },
  };
  const read = () => { try { return localStorage.getItem(KEY) || "system"; } catch { return "system"; } };
  const apply = (choice) => {
    if (choice === "system") delete document.documentElement.dataset.theme;
    else document.documentElement.dataset.theme = choice;
  };
  apply(read());

  window.addEventListener("DOMContentLoaded", () => {
    for (const button of document.querySelectorAll(".theme-toggle")) {
      const show = () => {
        const choice = read();
        const lang = (document.documentElement.lang || "en").slice(0, 2);
        const label = (LABELS[lang] || LABELS.en)[choice];
        button.setAttribute("aria-label", label);
        button.title = label;
        button.textContent = choice === "dark" ? "☾" : choice === "light" ? "☀" : "◐";
      };
      show();
      button.addEventListener("click", () => {
        const next = ORDER[(ORDER.indexOf(read()) + 1) % ORDER.length];
        try { localStorage.setItem(KEY, next); } catch { /* private mode: this page only */ }
        apply(next);
        show();
      });
      new MutationObserver(show).observe(document.documentElement, { attributes: true, attributeFilter: ["lang"] });
    }
  });
})();
