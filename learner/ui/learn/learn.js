/**
 * Urithi, the learner's page.
 *
 * One data layer, two sources: the server when it answers, a kept package when it does not.
 * What works offline is said, not implied: reading, listening (audio kept in the package),
 * braille, practising and rating all work; asking a question needs the server, and reviews
 * made offline are kept and sent when it answers again.
 */

import { KeyMap } from "../shared/keys.js";
import { LiveMicrophone } from "../shared/live.js";
import { Teleprompter } from "../shared/teleprompter.js";
import { KnowledgeTree } from "../shared/tree.js";

const STRINGS = {
  en: {
    skip: "Skip to the knowledge", whoLabel: "Learning as", simulated: "Simulated identity",
    homeTitle: "What you can learn", homeLead: "Each one was taught by a person, in their own words. Pick one to follow its path.",
    back: "Back", backToPath: "Back to the path", continue: "Continue", download: "Keep for offline",
    askTitle: "Ask about it", askLabel: "Your question", askPlaceholder: "Ask in English or French", askButton: "Ask",
    formRead: "Read", formListen: "Listen", formBraille: "Braille", formQuiz: "Practise", formSee: "See",
    whereTitle: "Where it sits, as taught", restsOn: "Rests on", thisPart: "This part", leadsTo: "Leads to",
    limitedBy: "Limited by", limits: "Limits", meets: "Can meet at the same time",
    nothingAround: "Nothing else rests on it or limits it yet.",
    pictureTitle: "Illustration", drawPicture: "Draw an illustration", drawing: "Drawing, about ten seconds...",
    pictureNote: (g) => `Drawn by a model from ${g}'s words, as a memory aid. It holds nothing of its own: the words are the knowledge.`,
    pictureOffline: "No illustration was kept for this part on this device.",
    play: "Play", grade1: "Grade 1", grade2: "Grade 2", brf: "Download for an embosser (.brf)",
    yes: "Yes", no: "No", holdToAnswer: "Hold to answer", listening: "Listening, let go when done",
    recallTitle: "How well did you know it?", again: "Again", hard: "Hard", good: "Good", easy: "Easy",
    examButton: "Test yourself", examTitle: "Test yourself",
    examLead: (n) => `${n} case${n === 1 ? "" : "s"} the guardian decided. Answer yes or no; the answers come at the end. Keys: Y, N, D for I don't know.`,
    examCount: (i, n) => `Question ${i} of ${n}`, examSkip: "I don't know",
    examScore: (c, n) => `${c} right out of ${n}.`,
    examAnswered: (a) => (a === true ? "You said yes." : a === false ? "You said no." : "Not answered."),
    examAgain: "Take it again", examNone: "No case has been decided for this yet.",
    examReview: "Parts with a wrong answer come back for review soon.",
    keyList: [["L", "Listen"], ["B", "Braille"], ["P", "Practise"], ["V", "See"], ["Y / N", "Answer yes or no"],
      ["1 to 4", "How well you knew it"], ["→", "Next part"], ["↑ ↓ ← →", "Move in the contents, open, close"]],
    next: "Next", keys: "Keys: L listen · B braille · P practise · V see · Y / N answer · 1 to 4 how well you knew it · → next · Esc back · ? keys",
    online: "Online", offline: "Offline: reading, listening, braille and practice work; questions wait",
    taughtBy: (g, n) => `Taught by ${g} · ${n} unit${n === 1 ? "" : "s"}`,
    pathLead: (n, due) => `${n} unit${n === 1 ? "" : "s"} in the order they build on each other.${due ? ` ${due} due for review.` : ""}`,
    nothingHere: "Nothing has been published that you may see yet.",
    kinds: { step: "Step", limit: "Limit", caution: "Caution" },
    states: { new: "new", due: "due", learned: "learned" },
    said: (g, at) => `${g}, at ${at}`, saidOn: (g, day) => `${g}, ${day}`, rests: "Rests on: ",
    refused: {
      questions: "You have reached today's limit for questions. It starts again tomorrow.",
      speech_chars: "You have reached today's limit for listening. Reading still works.",
      transcribed_seconds: "You have reached today's limit for speaking. Typing still works.",
      illustrations: "You have reached today's limit for illustrations.",
      model_cost: "Worded answers are paused for now; the guardian's own words still answer.",
    },
    nearLimit: "You are close to today's limit.",
    restsOnAnswer: (parts) => `This answer rests on ${parts}, which you have not learned yet. You may carry on.`,
    tryCase: "Try a case on this", reviewsDue: (n) => `${n} review${n === 1 ? " is" : "s are"} due.`,
    keepWhole: "Keep the answer", keepPoints: "Keep the key points", keepSelection: "Keep the selection",
    kept: "Kept in your notebook.", readAloud: "Read aloud", inBraille: "In braille",
    askVoice: "Hold to ask", noScreen: "No screen: read answers aloud", typeInstead: "Live speech is not available here: type the question.",
    resumePart: (t) => `Continue where you were: ${t}`, foundHard: "You found these hard",
    notebookTitle: "Your notebook", sheetScreen: "Revision sheet", sheetBraille: "Revision sheet in braille",
    noBraille: "Braille is not available on this machine.", forget: "Remove",
    rememberedTitle: "What Urithi remembers about you",
    rememberedLead: "Only what is about you or this knowledge reaches its answers. Remove anything you do not want kept.",
    aboutYou: "About you, for every knowledge", aboutThis: "About this knowledge", aboutOther: "About another knowledge, not used here",
    fromSaid: (said) => `From what you said: “${said}”`, forgetMemory: (what) => `Remove: ${what}`,
    evidenceFrom: (name, where) => `${name}, ${where}: `,
    cachedNote: "Answered before, from the same version of this knowledge.",
    steppedNote: "Given in the guardian's own words while worded answers are paused.",
    pictureDeferred: "Illustrations are paused for now; the words are all here.",
    contents: "Contents", contentsCount: (seen, all) => `Contents · ${seen} of ${all} learned`,
    treeKeys: "✓ learned · ↻ due · ○ new. Arrows move, Right opens, Enter reads.",
    goFirst: "Go there first", restsUnlearned: (what) => `This rests on ${what}, which you have not learned yet. You may carry on.`,
    marks: { learned: "✓", due: "↻", new: "○" },
    prompter: { you: "You", urithi: "Reading aloud", listeningWords: "Listening…" },
    sourceAgrees: "agrees", sourceDisagrees: "says something different",
    noQuiz: "There is no case to practise on for this one yet.",
    right: "Right.", wrong: "Not quite.", saidIt: (who, s) => `${who} said: "${s}"`,
    notUnderstood: "I did not catch a yes or a no. Answer again.",
    nextDue: (d) => `Next review: ${d}.`, kept: (n) => `Kept for offline: ${n} units.`,
    keptOffline: "This knowledge is kept on this device.",
    keptHere: "kept on this device",
    saveFile: "Save as a file", openFile: "Open a knowledge file",
    imported: (n) => `Kept on this device: ${n}.`,
    notPackage: "This is not a Urithi knowledge file.",
    unknownKey: "This file was not signed by a library this device knows. Open Urithi online once, then try again.",
    badSignature: "This file was changed after the library signed it, so it is not opened.",
    tooHigh: "This knowledge was packed for an access level above yours, so it is not opened.",
    fileExpired: (d) => `This file expired on ${d}. Connect to fetch the knowledge again.`,
    removedKept: (n) => `${n} kept knowledge file${n === 1 ? " was" : "s were"} removed from this device: no longer published for you.`,
    withdrawn: "This knowledge is no longer published for you, so the copy on this device was removed.",
    expired: (d) => `The copy kept on this device expired on ${d}. Connect once to fetch it again.`,
    expiredShort: (d) => `expired on ${d}, connect to renew`,
    refreshedKept: (v) => `The copy kept on this device was updated to version ${v}.`,
    askOffline: "Asking needs a connection. Your question is not lost: ask it again when you are back online.",
    myQuestions: "Your questions, passed on",
    ticketOpen: (g) => `Waiting for ${g}.`,
    ticketAnswered: (g, v) => `${g} answered it, in version ${v}.`,
    ticketDeclined: (g) => `${g} does not teach this.`,
    askAgain: "Ask it again", dismiss: "Remove",
    answeredNews: (n) => `${n} of your questions ${n === 1 ? "has" : "have"} an answer now.`,
    worded: (g) => `Worded from ${g}'s words, and checked against them.`,
    extractive: (g) => `${g}'s own words.`, sources: "From:",
    audioMissing: "There is no audio for this one on this device.",
    pages: (n) => `${n} page${n === 1 ? "" : "s"} when embossed, forty cells to a line.`,
    synced: (n) => `${n} review${n === 1 ? "" : "s"} made offline were sent.`,
    noMic: "The microphone is not available. Use Yes or No.",
  },
  fr: {
    skip: "Aller au savoir", whoLabel: "J'apprends en tant que", simulated: "Identité simulée",
    homeTitle: "Ce que tu peux apprendre", homeLead: "Chacun a été enseigné par une personne, avec ses mots. Choisis-en un pour suivre son parcours.",
    back: "Retour", backToPath: "Retour au parcours", continue: "Continuer", download: "Garder hors ligne",
    askTitle: "Poser une question", askLabel: "Ta question", askPlaceholder: "En français ou en anglais", askButton: "Demander",
    formRead: "Lire", formListen: "Écouter", formBraille: "Braille", formQuiz: "S'exercer", formSee: "Voir",
    whereTitle: "Où elle se place, telle qu'enseignée", restsOn: "Repose sur", thisPart: "Cette partie", leadsTo: "Mène à",
    limitedBy: "Limitée par", limits: "Limite", meets: "Peut arriver en même temps que",
    nothingAround: "Rien d'autre ne repose dessus ni ne la limite pour l'instant.",
    pictureTitle: "Illustration", drawPicture: "Dessiner une illustration", drawing: "Dessin en cours, une dizaine de secondes...",
    pictureNote: (g) => `Dessinée par un modèle à partir des mots de ${g}, pour aider à retenir. Elle n'ajoute rien : ce sont les mots qui comptent.`,
    pictureOffline: "Aucune illustration gardée pour cette partie sur cet appareil.",
    play: "Écouter", grade1: "Intégral", grade2: "Abrégé", brf: "Télécharger pour une embosseuse (.brf)",
    yes: "Oui", no: "Non", holdToAnswer: "Maintenir pour répondre", listening: "J'écoute, relâche quand tu as fini",
    recallTitle: "Le savais-tu bien ?", again: "À revoir", hard: "Difficile", good: "Bien", easy: "Facile",
    examButton: "Te tester", examTitle: "Te tester",
    examLead: (n) => `${n} cas tranché${n === 1 ? "" : "s"} par le gardien. Réponds oui ou non ; les réponses viennent à la fin. Touches : Y, N, D pour je ne sais pas.`,
    examCount: (i, n) => `Question ${i} sur ${n}`, examSkip: "Je ne sais pas",
    examScore: (c, n) => `${c} juste${c > 1 ? "s" : ""} sur ${n}.`,
    examAnswered: (a) => (a === true ? "Tu as dit oui." : a === false ? "Tu as dit non." : "Pas de réponse."),
    examAgain: "Recommencer", examNone: "Aucun cas n'a encore été tranché pour ceci.",
    examReview: "Les parties avec une réponse fausse reviendront bientôt en révision.",
    keyList: [["L", "Écouter"], ["B", "Braille"], ["P", "S'exercer"], ["V", "Voir"], ["Y / N", "Répondre oui ou non"],
      ["1 à 4", "Le savais-tu"], ["→", "Partie suivante"], ["↑ ↓ ← →", "Se déplacer dans le sommaire, ouvrir, fermer"]],
    next: "Suivant", keys: "Touches : L écouter · B braille · P s'exercer · V voir · Y / N répondre · 1 à 4 le savais-tu · → suivant · Échap retour · ? touches",
    online: "En ligne", offline: "Hors ligne : lire, écouter, braille et exercices fonctionnent ; les questions attendent",
    taughtBy: (g, n) => `Enseigné par ${g} · ${n} unité${n === 1 ? "" : "s"}`,
    pathLead: (n, due) => `${n} unité${n === 1 ? "" : "s"}, dans l'ordre où elles s'appuient l'une sur l'autre.${due ? ` ${due} à réviser.` : ""}`,
    nothingHere: "Rien n'a encore été publié que tu puisses voir.",
    kinds: { step: "Étape", limit: "Limite", caution: "Mise en garde" },
    states: { new: "nouveau", due: "à réviser", learned: "acquis" },
    said: (g, at) => `${g}, à ${at}`, saidOn: (g, day) => `${g}, le ${day}`, rests: "S'appuie sur : ",
    refused: {
      questions: "Tu as atteint la limite de questions pour aujourd'hui. Elle repart demain.",
      speech_chars: "Tu as atteint la limite d'écoute pour aujourd'hui. La lecture marche toujours.",
      transcribed_seconds: "Tu as atteint la limite de parole pour aujourd'hui. L'écrit marche toujours.",
      illustrations: "Tu as atteint la limite d'illustrations pour aujourd'hui.",
      model_cost: "Les réponses formulées sont en pause ; les mots du gardien répondent toujours.",
    },
    nearLimit: "Tu approches de la limite du jour.",
    restsOnAnswer: (parts) => `Cette réponse s'appuie sur ${parts}, que tu n'as pas encore appris. Tu peux continuer.`,
    tryCase: "Essayer un cas là-dessus", reviewsDue: (n) => `${n} révision${n > 1 ? "s" : ""} à faire.`,
    keepWhole: "Garder la réponse", keepPoints: "Garder les points clés", keepSelection: "Garder la sélection",
    kept: "Gardé dans ton carnet.", readAloud: "Lire à voix haute", inBraille: "En braille",
    askVoice: "Maintenir pour demander", noScreen: "Pas d'écran : lire les réponses à voix haute", typeInstead: "La parole en direct n'est pas disponible ici : écris la question.",
    resumePart: (t) => `Reprendre où tu en étais : ${t}`, foundHard: "Tu as trouvé ceci difficile",
    notebookTitle: "Ton carnet", sheetScreen: "Fiche de révision", sheetBraille: "Fiche de révision en braille",
    noBraille: "Le braille n'est pas disponible sur cette machine.", forget: "Retirer",
    rememberedTitle: "Ce dont Urithi se souvient sur toi",
    rememberedLead: "Seul ce qui te concerne ou concerne ce savoir sert à ses réponses. Retire ce que tu ne veux pas garder.",
    aboutYou: "Sur toi, pour tous les savoirs", aboutThis: "Sur ce savoir", aboutOther: "Sur un autre savoir, pas utilisé ici",
    fromSaid: (said) => `D'après ce que tu as dit : « ${said} »`, forgetMemory: (what) => `Retirer : ${what}`,
    evidenceFrom: (name, where) => `${name}, ${where} : `,
    cachedNote: "Déjà répondu, sur la même version de ce savoir.",
    steppedNote: "Donné avec les mots du gardien pendant que les réponses formulées sont en pause.",
    pictureDeferred: "Les illustrations sont en pause pour l'instant ; tous les mots sont là.",
    contents: "Sommaire", contentsCount: (seen, all) => `Sommaire · ${seen} sur ${all} appris`,
    treeKeys: "✓ appris · ↻ à revoir · ○ nouveau. Les flèches déplacent, Droite ouvre, Entrée lit.",
    goFirst: "Y aller d'abord", restsUnlearned: (what) => `Ceci s'appuie sur ${what}, que tu n'as pas encore appris. Tu peux continuer quand même.`,
    marks: { learned: "✓", due: "↻", new: "○" },
    prompter: { you: "Toi", urithi: "Lecture à voix haute", listeningWords: "J'écoute…" },
    sourceAgrees: "confirme", sourceDisagrees: "dit autre chose",
    noQuiz: "Il n'y a pas encore de cas pour s'exercer sur celle-ci.",
    right: "Juste.", wrong: "Pas tout à fait.", saidIt: (who, s) => `${who} a dit : « ${s} »`,
    notUnderstood: "Je n'ai pas compris un oui ou un non. Réponds à nouveau.",
    nextDue: (d) => `Prochaine révision : ${d}.`, kept: (n) => `Gardé hors ligne : ${n} unités.`,
    keptOffline: "Ce savoir est gardé sur cet appareil.",
    keptHere: "gardée sur cet appareil",
    saveFile: "Enregistrer dans un fichier", openFile: "Ouvrir un fichier de savoir",
    imported: (n) => `Gardée sur cet appareil : ${n}.`,
    notPackage: "Ce n'est pas un fichier de savoir Urithi.",
    unknownKey: "Ce fichier n'a pas été signé par une bibliothèque que cet appareil connaît. Ouvre Urithi en ligne une fois, puis réessaie.",
    badSignature: "Ce fichier a été modifié après sa signature par la bibliothèque, il n'est donc pas ouvert.",
    tooHigh: "Ce savoir a été préparé pour un niveau d'accès au-dessus du tien, il n'est donc pas ouvert.",
    fileExpired: (d) => `Ce fichier a expiré le ${d}. Connecte-toi pour récupérer le savoir.`,
    removedKept: (n) => `${n} savoir${n === 1 ? " gardé a été retiré" : "s gardés ont été retirés"} de cet appareil : plus publié${n === 1 ? "" : "s"} pour toi.`,
    withdrawn: "Ce savoir n'est plus publié pour toi, sa copie sur cet appareil a donc été retirée.",
    expired: (d) => `La copie gardée sur cet appareil a expiré le ${d}. Connecte-toi une fois pour la récupérer.`,
    expiredShort: (d) => `expirée le ${d}, connecte-toi pour la renouveler`,
    refreshedKept: (v) => `La copie gardée sur cet appareil a été mise à jour en version ${v}.`,
    askOffline: "Poser une question demande une connexion. Repose-la quand tu seras en ligne.",
    myQuestions: "Tes questions transmises",
    ticketOpen: (g) => `En attente de ${g}.`,
    ticketAnswered: (g, v) => `${g} y a répondu, dans la version ${v}.`,
    ticketDeclined: (g) => `${g} n'enseigne pas cela.`,
    askAgain: "La reposer", dismiss: "Retirer",
    answeredNews: (n) => `${n} de tes questions ${n === 1 ? "a" : "ont"} maintenant une réponse.`,
    worded: (g) => `Formulé à partir des mots de ${g}, et vérifié contre eux.`,
    extractive: (g) => `Les mots de ${g}.`, sources: "D'après :",
    audioMissing: "Pas d'audio pour celle-ci sur cet appareil.",
    pages: (n) => `${n} page${n === 1 ? "" : "s"} une fois embossé, quarante cellules par ligne.`,
    synced: (n) => `${n} révision${n === 1 ? "" : "s"} faite${n === 1 ? "" : "s"} hors ligne envoyée${n === 1 ? "" : "s"}.`,
    noMic: "Le micro n'est pas disponible. Utilise Oui ou Non.",
  },
};

const $ = (id) => document.getElementById(id);
const store = {
  get(key, fallback) { try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; } },
  set(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* private mode */ } },
};

// ── kept packages, in IndexedDB ────────────────────────────────────────────────
const db = {
  open() {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open("urithi", 1);
      request.onupgradeneeded = () => {
        request.result.createObjectStore("packages");
        request.result.createObjectStore("queue", { autoIncrement: true });
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  },
  async tx(name, mode, fn) {
    const handle = await this.open();
    return new Promise((resolve, reject) => {
      const t = handle.transaction(name, mode);
      const result = fn(t.objectStore(name));
      // A request resolves to its result, undefined when nothing is kept (never to the request).
      t.oncomplete = () => resolve(result instanceof IDBRequest ? result.result : result);
      t.onerror = () => reject(t.error);
    });
  },
  put: (key, value) => db.tx("packages", "readwrite", (s) => s.put(value, key)),
  del: (key) => db.tx("packages", "readwrite", (s) => s.delete(key)),
  async all() {
    const handle = await db.open();
    return new Promise((resolve) => {
      const t = handle.transaction("packages", "readonly");
      const keys = t.objectStore("packages").getAllKeys();
      const values = t.objectStore("packages").getAll();
      t.oncomplete = () => resolve(keys.result.map((key, i) => [key, values.result[i]]));
      t.onerror = () => resolve([]);
    });
  },
  get: (key) => db.tx("packages", "readonly", (s) => s.get(key)),
  queue: (entry) => db.tx("queue", "readwrite", (s) => s.add(entry)),
  async drain() {
    const handle = await db.open();
    return new Promise((resolve) => {
      const t = handle.transaction("queue", "readwrite");
      const all = t.objectStore("queue").getAll();
      all.onsuccess = () => { t.objectStore("queue").clear(); };
      t.oncomplete = () => resolve(all.result || []);
    });
  },
};

class Learn {
  constructor() {
    this.lang = store.get("urithi.lang", (navigator.language || "en").startsWith("fr") ? "fr" : "en");
    this.person = store.get("urithi.person", "visitor");
    this.organisation = store.get("urithi.organisation", "");
    this.online = navigator.onLine;
    this.path = null;
    this.unit = null;
    this.index = -1;
    this.form = "read";
    this.grade = 2;
    this.quiz = [];
    this.audio = null;
    this.listening = false;
    this.prompter = new Teleprompter($("prompter"), () => this.t("prompter"));
    // An answer said out loud appears as it is said (apu/modality/live.py).
    this.mic = new LiveMicrophone({
      url: () => `/api/learner/listen?${this.q({})}`,
      onPartial: (text) => this.prompter.partial(text),
      onRefused: (message) => this.say(this.t("refused")[message.refused] || message.detail),
    });
    this.keys = new KeyMap(() => this.t("keyList"));
    this.tree = new KnowledgeTree($("contents"), {
      label: this.t("contents"),
      onChoose: (node) => { if (node.index !== undefined) this.openUnit(node.index, { keepFocus: true }); },
    });
    // The contents stay open beside the part on a wide screen, folded above it on a phone.
    $("contents-box").open = window.matchMedia("(min-width: 900px)").matches;
    this.bind();
    this.applyLanguage();
    this.setNetwork(navigator.onLine);
    this.start();
  }

  t(key, ...args) {
    const value = STRINGS[this.lang][key] ?? STRINGS.en[key];
    return typeof value === "function" ? value(...args) : value;
  }

  say(text) {
    const node = $("announcer");
    node.textContent = "";
    window.setTimeout(() => { node.textContent = text; }, 60);
  }

  // ── data: the server, or the kept package ────────────────────────────────────
  async api(path, options = {}) {
    const response = await fetch(`/api/learner/${path}`, {
      headers: { "Content-Type": "application/json" }, ...options,
    });
    if (!response.ok) {
      const detail = await response.json().catch(() => ({}));
      // A refused budget is said in the page's language, from what ran out (apu/meter.py).
      const said = response.status === 429 && detail.refused ? this.t("refused")[detail.refused] : null;
      throw Object.assign(new Error(said || detail.detail || response.statusText), { status: response.status });
    }
    return response.json();
  }

  q(params) {
    return new URLSearchParams({ person_id: this.person, organisation: this.organisation, ...params }).toString();
  }

  // Who is asking, in which organisation: in every request that names a person.
  me() { return { person_id: this.person, organisation: this.organisation }; }

  // Kept per person and organisation: the same knowledge name in two organisations is two packages.
  packageKey(bodyId) { return `${this.person}|${this.organisation}|${bodyId}`; }

  async kept(bodyId) {
    try { return this.inflate(await db.get(this.packageKey(bodyId))); } catch { return null; }
  }

  // ── signed packages ─────────────────────────────────────────────────────────
  // A package is kept as the library signed it: the manifest and the content as the exact
  // strings it signed, and the signature. It is checked on the way in (from the server or
  // from a file), with the library's public key, which a device keeps once it has met the
  // library. The content is parsed when it is read.
  inflate(raw) {
    if (raw && raw.signed && !raw.content) return { ...raw, content: JSON.parse(raw.signed.content_json) };
    return raw;
  }

  async learnKey() {
    try {
      const key = await this.api("key");
      store.set("urithi.libraryKeys", { ...store.get("urithi.libraryKeys", {}), [key.key_id]: key.public_key });
    } catch { /* offline: the keys already kept are used */ }
  }

  async unpack(signed) {
    if (!signed || signed.format !== 2 || !signed.manifest_json || !signed.content_json || !signed.signature) {
      throw new Error(this.t("notPackage"));
    }
    const publicKey = store.get("urithi.libraryKeys", {})[signed.key_id];
    if (!publicKey) throw new Error(this.t("unknownKey"));
    const bytes = (b64) => Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    const utf8 = (text) => new TextEncoder().encode(text);
    const key = await crypto.subtle.importKey("raw", bytes(publicKey), { name: "Ed25519" }, false, ["verify"]);
    const signedBytes = utf8(`${signed.manifest_json}\n${signed.content_json}`);
    if (!await crypto.subtle.verify({ name: "Ed25519" }, key, bytes(signed.signature), signedBytes)) {
      throw new Error(this.t("badSignature"));
    }
    const manifest = JSON.parse(signed.manifest_json);
    const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", utf8(signed.content_json)));
    if ([...digest].map((b) => b.toString(16).padStart(2, "0")).join("") !== manifest.sha256) {
      throw new Error(this.t("badSignature"));
    }
    const { format, manifest_json, content_json, signature, key_id } = signed;
    return { manifest, signed: { format, manifest_json, content_json, signature, key_id } };
  }

  async exportKept() {
    const kept = await this.kept(this.path.body.body_id);
    if (!kept?.signed) return;
    const link = document.createElement("a");
    link.href = URL.createObjectURL(new Blob([JSON.stringify(kept.signed)], { type: "application/json" }));
    link.download = `${kept.manifest.body_id}.urithi.json`;
    link.click();
  }

  async importFile(file) {
    let packed;
    try {
      let signed;
      try { signed = JSON.parse(await file.text()); } catch { throw new Error(this.t("notPackage")); }
      packed = await this.unpack(signed);
      const { manifest } = packed;
      if (this.expired(packed)) throw new Error(this.t("fileExpired", this.day(manifest.valid_until)));
      // A file handed on is opened at the level of whoever opens it, never above.
      const levels = ["public", "community", "restricted"];
      const mine = store.get("urithi.people", []).find((p) => p.person_id === this.person)?.access || "public";
      if (Math.max(...manifest.access.map((l) => levels.indexOf(l))) > levels.indexOf(mine)) {
        throw new Error(this.t("tooHigh"));
      }
      await db.put(this.packageKey(manifest.body_id), packed);
    } catch (error) {
      this.say(error.message);
      $("import-note").textContent = error.message;
      return;
    }
    const name = JSON.parse(packed.signed.content_json).body.name;
    $("import-note").textContent = this.t("imported", name);
    this.say(this.t("imported", name));
    await this.showHome();
  }

  // A kept package lives as long as the library says it may. It expires at its valid_until,
  // when the device must ask again; and once the library answers without it (withdrawn, or no
  // longer this person's to see), it leaves the device. Withdrawing reaches everywhere the
  // knowledge was kept, at the next moment the device is online.
  async keptAll() {
    try {
      const prefix = `${this.person}|`;
      return (await db.all()).filter(([key]) => String(key).startsWith(prefix)).map(([, value]) => this.inflate(value));
    } catch { return []; }
  }

  expired(pkg) { return new Date(pkg.manifest.valid_until) <= new Date(); }

  day(iso) { return new Date(iso).toLocaleDateString(this.lang); }

  async forgetKept(bodyId) {
    try { await db.del(this.packageKey(bodyId)); } catch { /* nothing kept */ }
  }

  async reconcileKept(bodies) {
    const listed = Object.fromEntries(bodies.map((b) => [b.body_id, b]));
    let removed = 0;
    for (const pkg of await this.keptAll()) {
      const bodyId = pkg.manifest.body_id;
      if (!listed[bodyId]) {
        await this.forgetKept(bodyId);
        removed += 1;
      } else if (listed[bodyId].version !== pkg.manifest.version || this.soon(pkg)) {
        this.refreshKept(bodyId);
      }
    }
    if (removed) this.say(this.t("removedKept", removed));
  }

  soon(pkg) { return new Date(pkg.manifest.valid_until) - new Date() < 7 * 24 * 3600 * 1000; }

  async refreshKept(bodyId) {
    // Once at a time: opening a body and the home page both ask, and each build reads every
    // part aloud. Measured: the same knowledge was fetched twice and announced twice.
    this.refreshing ??= new Set();
    if (this.refreshing.has(bodyId)) return;
    this.refreshing.add(bodyId);
    try { await this.refreshOnce(bodyId); } finally { this.refreshing.delete(bodyId); }
  }

  async refreshOnce(bodyId) {
    const old = await this.kept(bodyId);
    if (!old) return;
    try {
      const pkg = await this.api(`package/${encodeURIComponent(bodyId)}?${this.q({ lang: old.manifest.language || this.lang, audio: true })}`);
      await this.learnKey();
      const packed = await this.unpack(pkg);
      await db.put(this.packageKey(bodyId), packed);
      if (packed.manifest.version !== old.manifest.version) this.say(this.t("refreshedKept", packed.manifest.version));
    } catch { /* kept as it was until the next time */ }
  }

  // ── start ──────────────────────────────────────────────────────────────────
  async start() {
    try {
      const reply = await (await fetch("/api/learner/people")).json();
      store.set("urithi.people", reply.people.map((p) => ({ person_id: p.person_id, access: p.access })));
      this.learnKey();
      $("person").innerHTML = "";
      // One entry per membership: who one is, in which organisation, and what one may see there.
      for (const p of reply.people) {
        const option = document.createElement("option");
        option.value = `${p.person_id}@${p.organisation}`;
        option.textContent = `${p.name} · ${p.organisation_name} (${p.access})`;
        option.selected = p.person_id === this.person && (!this.organisation || p.organisation === this.organisation);
        $("person").appendChild(option);
      }
      [this.person, this.organisation] = ($("person").value || `${this.person}@`).split("@");
    } catch {
      const option = document.createElement("option");
      option.value = this.person;
      option.textContent = this.person;
      $("person").appendChild(option);
    }
    await this.syncQueued();
    const hash = new URLSearchParams(location.hash.slice(1));
    if (hash.get("body")) await this.openPath(hash.get("body"));
    else await this.showHome();
  }

  show(section, { keepFocus = false } = {}) {
    $("home").hidden = section !== "home";
    $("knowledge").hidden = section === "home";
    $("main").classList.toggle("wide", section !== "home");
    for (const id of ["path", "unit", "exam"]) $(id).hidden = id !== section;
    if (section === "home") this.prompter.hide();
    // On a phone the contents fold above the part being read, and open over the whole knowledge.
    if (!window.matchMedia("(min-width: 900px)").matches) $("contents-box").open = section === "path";
    if (!keepFocus) $("main").focus();
  }

  // The knowledge as a tree: the guardian's steps in the order they build, each rule under
  // the step it rests on, and where this learner stands on every part, in a mark and a word.
  renderContents() {
    const units = this.path.units;
    const index = new Map(units.map((u, i) => [u.unit_id, i]));
    const parentOf = new Map();
    for (const link of this.links) {
      const from = units[index.get(link.source_id)];
      const to = units[index.get(link.target_id)];
      if (link.type === "PREREQUISITE_OF" && from?.kind === "step" && to && to.kind !== "step" && !parentOf.has(to.unit_id)) {
        parentOf.set(to.unit_id, from.unit_id);
      }
    }
    const current = !$("unit").hidden ? units[this.index]?.unit_id : null;
    const node = (u) => {
      const state = u.progress?.state || "new";
      return {
        id: u.unit_id, index: index.get(u.unit_id), label: u.text, state, mark: this.t("marks")[state] || "○",
        tag: this.t("states")[state], current: u.unit_id === current,
        children: units.filter((c) => parentOf.get(c.unit_id) === u.unit_id).map(node),
      };
    };
    // Sections, as the guardian grouped the contents: a section opens on its steps, in order.
    const roots = [];
    const sections = new Map();
    for (const u of units.filter((x) => !parentOf.has(x.unit_id))) {
      if (!u.section) { roots.push(node(u)); continue; }
      if (!sections.has(u.section)) {
        const section = { id: `section:${u.section}`, label: u.section, mark: "§", state: "section", children: [], open: true };
        sections.set(u.section, section);
        roots.push(section);
      }
      sections.get(u.section).children.push(node(u));
    }
    for (const section of sections.values()) {
      const learned = section.children.filter((c) => c.state === "learned").length;
      section.tag = `${learned}/${section.children.length}`;
    }
    if (current) this.tree.reveal(current);
    this.tree.render(roots);
    const learned = units.filter((u) => u.progress?.state === "learned").length;
    $("contents-summary").textContent = this.t("contentsCount", learned, units.length);
  }

  async showHome() {
    this.show("home");
    history.replaceState(null, "", "#");
    const list = $("bodies");
    list.innerHTML = "";
    let bodies;
    try {
      bodies = (await this.api(`bodies?${this.q({})}`)).bodies;
      await this.reconcileKept(bodies);
    } catch {
      // No answer from the library: what this device keeps, said as such.
      bodies = (await this.keptAll()).map((pkg) => ({
        body_id: pkg.manifest.body_id, name: pkg.content.body.name, guardian: pkg.content.body.guardian,
        units: pkg.content.units.length, kept: true, expired: this.expired(pkg) ? pkg.manifest.valid_until : null,
      }));
    }
    if (!bodies.length) {
      const li = document.createElement("li");
      li.className = "empty";
      li.textContent = this.t("nothingHere");
      list.appendChild(li);
      return;
    }
    for (const body of bodies) {
      const li = document.createElement("li");
      const button = document.createElement("button");
      const title = document.createElement("span");
      title.className = "title";
      title.textContent = body.name;
      const meta = document.createElement("span");
      meta.className = "meta";
      meta.textContent = this.t("taughtBy", body.guardian, body.units) +
        (body.kept ? ` · ${body.expired ? this.t("expiredShort", this.day(body.expired)) : this.t("keptHere")}` : "");
      button.append(title, meta);
      button.disabled = Boolean(body.expired);
      button.addEventListener("click", () => this.openPath(body.body_id));
      li.appendChild(button);
      list.appendChild(li);
    }
  }

  async openPath(bodyId) {
    let path;
    try {
      path = await this.api(`path/${encodeURIComponent(bodyId)}?${this.q({})}`);
      path.source = "server";
    } catch (error) {
      if (error.status === 404 || error.status === 403) {
        // The library answered, and this is not there for this person: withdrawn, or no longer theirs.
        if (await this.kept(bodyId)) this.say(this.t("withdrawn"));
        else this.say(error.message);
        await this.forgetKept(bodyId);
        return this.showHome();
      }
      const kept = await this.kept(bodyId);
      if (!kept) { this.say(error.message); return this.showHome(); }
      if (this.expired(kept)) { this.say(this.t("expired", this.day(kept.manifest.valid_until))); return this.showHome(); }
      path = this.pathFromPackage(kept);
    }
    if (path.source === "server") {
      const kept = await this.kept(bodyId);
      if (kept && (kept.manifest.version !== path.body.version || this.soon(kept))) this.refreshKept(bodyId);
    }
    this.path = path;
    history.replaceState(null, "", `#body=${encodeURIComponent(bodyId)}`);
    this.show("path");
    $("path-title").textContent = path.body.name;
    $("exam-start").hidden = !path.cases;
    $("export").hidden = true;
    this.kept(bodyId).then((kept) => { $("export").hidden = !kept?.signed; });
    $("path-lead").textContent = this.t("pathLead", path.units.length, path.due) +
      (path.source === "package" ? ` ${this.t("keptOffline")}` : "");
    this.renderContents();
    this.loadSession();
    this.loadNotebook();
    this.loadRemembered();
    $("answer").hidden = true;
    this.say(`${path.body.name}. ${$("path-lead").textContent}`);
    this.refreshQuestions();
  }

  // ── the learner's own questions ─────────────────────────────────────────────
  // A question passed to the guardian comes back with a ticket. The ticket stays on this
  // device: the server keeps the question without a name, and only the ticket says whose it was.
  questionsKey() { return `urithi.questions.${this.person}`; }

  async refreshQuestions() {
    if (!this.path) return;
    const bodyId = this.path.body.body_id;
    const list = store.get(this.questionsKey(), []);
    const waiting = list.filter((q) => q.body_id === bodyId && q.status === "open");
    if (waiting.length && this.path.source === "server" && navigator.onLine) {
      try {
        const reply = await this.api("tickets", { method: "POST", body: JSON.stringify({ tickets: waiting.map((q) => q.ticket) }) });
        let news = 0;
        for (const found of reply.tickets) {
          const entry = list.find((q) => q.ticket === found.ticket);
          if (entry && found.status !== "open") {
            Object.assign(entry, { status: found.status, version: found.version });
            news += found.status === "answered";
          }
        }
        store.set(this.questionsKey(), list);
        if (news) this.say(this.t("answeredNews", news));
      } catch { /* shown as it was last known */ }
    }
    this.showQuestions(list.filter((q) => q.body_id === bodyId));
  }

  showQuestions(mine) {
    const box = $("my-questions");
    const list = $("ticket-list");
    list.innerHTML = "";
    const guardian = this.path.body.guardian;
    for (const entry of mine) {
      const li = document.createElement("li");
      const question = document.createElement("q");
      question.textContent = entry.question;
      const status = document.createElement("span");
      status.className = `ticket ${entry.status}`;
      status.textContent = entry.status === "answered" ? this.t("ticketAnswered", guardian, entry.version)
        : entry.status === "declined" ? this.t("ticketDeclined", guardian) : this.t("ticketOpen", guardian);
      li.append(question, status);
      if (entry.status !== "open") {
        const button = document.createElement("button");
        button.className = entry.status === "answered" ? "primary" : "quiet";
        button.textContent = entry.status === "answered" ? this.t("askAgain") : this.t("dismiss");
        button.addEventListener("click", () => {
          this.forget(entry.ticket);
          if (entry.status === "answered") {
            $("question").value = entry.question;
            this.ask(entry.question);
          } else {
            this.refreshQuestions();
          }
        });
        li.appendChild(button);
      }
      list.appendChild(li);
    }
    box.hidden = !mine.length;
  }

  remember(question, ticket) {
    const list = store.get(this.questionsKey(), []);
    list.push({ ticket, question, body_id: this.path.body.body_id, status: "open", at: new Date().toISOString() });
    store.set(this.questionsKey(), list.slice(-50));
  }

  forget(ticket) {
    store.set(this.questionsKey(), store.get(this.questionsKey(), []).filter((q) => q.ticket !== ticket));
  }

  pathFromPackage(kept) {
    const progress = store.get(`urithi.offline.${this.person}`, {});
    return {
      source: "package", body: kept.content.body, package: kept,
      units: kept.content.units.map((u) => ({ ...u, progress: progress[u.unit_id] || { state: "new" },
        quizzes: kept.content.cases.filter((c) => c.decides.includes(u.unit_id)).length })),
      due: 0, cases: kept.content.cases.length,
    };
  }

  // ── the exam: every case the guardian decided, answered, then marked ───────
  async openExam() {
    const bodyId = this.path.body.body_id;
    let cases;
    if (this.path.source === "server") {
      try {
        cases = (await this.api(`exam/${encodeURIComponent(bodyId)}?${this.q({})}`)).cases;
      } catch (error) { this.say(error.message); return; }
    } else {
      const place = Object.fromEntries(this.path.units.map((u, i) => [u.unit_id, i]));
      const first = (c) => Math.min(...c.decides.map((id) => place[id] ?? Infinity));
      cases = [...this.path.package.content.cases].sort((a, b) => first(a) - first(b));
    }
    this.exam = { cases, answers: {}, at: 0 };
    this.show("exam");
    $("exam-result").hidden = true;
    $("exam-ask").hidden = !cases.length;
    $("exam-lead").textContent = cases.length ? this.t("examLead", cases.length) : this.t("examNone");
    if (cases.length) this.examNext(); else this.say(this.t("examNone"));
  }

  examNext() {
    const { cases, at } = this.exam;
    if (at >= cases.length) return this.markExam();
    $("exam-count").textContent = this.t("examCount", at + 1, cases.length);
    $("exam-question").textContent = cases[at].question;
    $("exam-yes").focus();
    this.say(`${$("exam-count").textContent}. ${cases[at].question}`);
  }

  examAnswer(value) {
    if (!this.exam || $("exam").hidden || $("exam-ask").hidden) return;
    this.exam.answers[this.exam.cases[this.exam.at].case_id] = value;
    this.exam.at += 1;
    this.examNext();
  }

  async markExam() {
    const { answers } = this.exam;
    let reply;
    if (this.path.source === "server") {
      try {
        reply = await this.api(`exam/${encodeURIComponent(this.path.body.body_id)}`, {
          method: "POST", body: JSON.stringify({ ...this.me(), answers }) });
      } catch (error) { this.say(error.message); return; }
    } else {
      // Marked on the device, from the kept package, the way the server marks it.
      const outcome = {};
      const feedback = this.exam.cases.map((c) => {
        const right = answers[c.case_id] !== undefined && answers[c.case_id] !== null && answers[c.case_id] === c.applies;
        for (const uid of c.decides) outcome[uid] = (outcome[uid] ?? true) && right;
        return { case_id: c.case_id, question: c.question, right, answered: answers[c.case_id] ?? null,
          expected: c.applies, by: c.by, said: c.said };
      });
      for (const [uid, right] of Object.entries(outcome)) await this.rateOffline(uid, right ? 3 : 1);
      reply = { correct: feedback.filter((f) => f.right).length, total: feedback.length, feedback };
    }
    $("exam-ask").hidden = true;
    $("exam-result").hidden = false;
    $("exam-score").textContent = this.t("examScore", reply.correct, reply.total) +
      (reply.correct < reply.total ? ` ${this.t("examReview")}` : "");
    const list = $("exam-feedback");
    list.innerHTML = "";
    for (const item of reply.feedback) {
      const li = document.createElement("li");
      li.className = item.right ? "right" : "wrong";
      const question = document.createElement("p");
      question.className = "q";
      question.textContent = item.question;
      const verdict = document.createElement("p");
      verdict.textContent = `${item.right ? this.t("right") : this.t("wrong")} ${this.t("examAnswered", item.answered)}`;
      const why = document.createElement("p");
      why.className = "why";
      why.textContent = this.t("saidIt", item.by, item.said);
      li.append(question, verdict, why);
      list.appendChild(li);
    }
    $("exam-score").focus();
    this.say($("exam-score").textContent);
  }

  nextIndex() {
    const units = this.path.units;
    const due = units.findIndex((u) => u.progress.state === "due");
    if (due >= 0) return due;
    const fresh = units.findIndex((u) => u.progress.state === "new");
    return fresh >= 0 ? fresh : 0;
  }

  // ── a unit ─────────────────────────────────────────────────────────────────
  async openUnit(index, { keepFocus = false } = {}) {
    const listed = this.path.units[index];
    if (!listed) return;
    this.index = index;
    let detail;
    if (this.path.source === "server") {
      try {
        detail = await this.api(`unit/${encodeURIComponent(listed.unit_id)}?${this.q({})}`);
      } catch (error) {
        this.say(error.message);
        return;
      }
    } else {
      const content = this.path.package.content;
      const byId = Object.fromEntries(content.units.map((u) => [u.unit_id, u]));
      detail = {
        unit: listed, guardian: content.body.guardian,
        prerequisites: content.links.filter((l) => l.type === "PREREQUISITE_OF" && l.target_id === listed.unit_id)
          .map((l) => byId[l.source_id]).filter(Boolean),
        sources: content.sources.filter((s) => s.unit_id === listed.unit_id),
        evidence: (content.evidence || []).filter((e) => e.unit_id === listed.unit_id),
        quiz: content.cases.filter((c) => c.decides.includes(listed.unit_id)),
      };
    }
    this.unit = detail;
    this.quiz = detail.quiz;
    this.show("unit", { keepFocus });
    const unit = detail.unit;
    $("unit-kind").textContent = this.t("kinds")[unit.kind] || unit.kind;
    $("unit-title").textContent = unit.text;
    $("unit-quote").textContent = unit.quote;
    $("unit-said").textContent = this.when(detail.guardian, unit);
    // Reminded, never enforced (docs/architecture.md, docs/architecture-sides.md): only a prerequisite not learned yet is said.
    const states = new Map(this.path.units.map((u, i) => [u.unit_id, { state: u.progress?.state, i }]));
    const unlearned = detail.prerequisites.filter((p) => states.get(p.unit_id)?.state !== "learned");
    $("unit-prereq").hidden = !unlearned.length;
    $("prereq-text").textContent = unlearned.length ? this.t("restsUnlearned", unlearned.map((p) => `“${p.text}”`).join(", ")) : "";
    this.prereqIndex = unlearned.length ? states.get(unlearned[0].unit_id)?.i : null;
    $("prereq-go").hidden = this.prereqIndex === null || this.prereqIndex === undefined;
    this.renderContents();
    const sources = $("unit-sources");
    sources.innerHTML = "";
    for (const source of detail.sources) {
      const li = document.createElement("li");
      li.className = source.relation === "DISAGREES" ? "disagrees" : "";
      li.textContent = `${source.domain}: ${source.relation === "DISAGREES" ? this.t("sourceDisagrees") : this.t("sourceAgrees")}` +
        (source.says ? ` ("${source.says}")` : "");
      sources.appendChild(li);
    }
    // The guardian's own documents this part rests on: the passage, and where it is.
    for (const found of detail.evidence || []) {
      const li = document.createElement("li");
      li.className = "evidence";
      const where = document.createElement("span");
      where.className = "where";
      where.textContent = this.t("evidenceFrom", found.name, found.where);
      const excerpt = document.createElement("q");
      excerpt.textContent = found.excerpt;
      li.append(where, excerpt);
      sources.appendChild(li);
    }
    $("recall-note").textContent = "";
    this.setForm("read");
    this.say(`${$("unit-kind").textContent}. ${unit.text}. ${$("unit-said").textContent}: ${unit.quote}`);
  }

  setForm(form) {
    this.form = form;
    for (const tab of document.querySelectorAll(".forms [role=tab]")) {
      tab.setAttribute("aria-selected", String(tab.dataset.form === form));
    }
    for (const name of ["read", "listen", "braille", "quiz", "see"]) $(`panel-${name}`).hidden = name !== form;
    if (form === "braille") this.showBraille();
    if (form === "quiz") this.showQuiz();
    if (form === "see") this.showSee();
    if (form === "listen") $("listen-note").textContent = "";
  }

  // ── see: where the part sits, and an illustration ──────────────────────────
  // The diagram is built from the guardian's own links between parts, by code, and works
  // offline from a kept package. The illustration is a model's drawing: drawn on request,
  // labelled as what it is, and skipped by a screen reader, since the words say it all.
  get links() {
    return (this.path.source === "server" ? this.path.links : this.path.package.content.links) || [];
  }

  around(unitId) {
    const links = this.links;
    const ends = (type, from) => links.filter((l) => l.type === type && l[from ? "source_id" : "target_id"] === unitId)
      .map((l) => l[from ? "target_id" : "source_id"]);
    const limitedBy = ends("LIMITS", false);
    const limits = ends("LIMITS", true);
    return {
      restsOn: ends("PREREQUISITE_OF", false).filter((id) => !limits.includes(id)),
      leadsTo: ends("PREREQUISITE_OF", true).filter((id) => !limitedBy.includes(id)),
      limitedBy, limits,
      meets: [...ends("MEETS", true), ...ends("MEETS", false)],
    };
  }

  showSee() {
    const unit = this.unit.unit;
    const flow = $("see-flow");
    flow.innerHTML = "";
    const index = Object.fromEntries(this.path.units.map((u, i) => [u.unit_id, i]));
    const group = (key, ids, cls) => {
      const shown = ids.filter((id) => id in index);
      if (!shown.length) return null;
      const section = document.createElement("section");
      section.className = `flow-group ${cls}`;
      const title = document.createElement("h3");
      title.textContent = this.t(key);
      const list = document.createElement("ul");
      for (const id of shown) {
        const li = document.createElement("li");
        const button = document.createElement("button");
        button.className = `node ${this.path.units[index[id]].kind}`;
        button.textContent = this.path.units[index[id]].text;
        button.addEventListener("click", () => this.openUnit(index[id]).then(() => this.setForm("see")));
        li.appendChild(button);
        list.appendChild(li);
      }
      section.append(title, list);
      return section;
    };
    const arrow = () => {
      const node = document.createElement("div");
      node.className = "flow-arrow";
      node.setAttribute("aria-hidden", "true");
      return node;
    };
    const near = this.around(unit.unit_id);
    const before = group("restsOn", near.restsOn, "before");
    const after = group("leadsTo", near.leadsTo, "after");
    const self = document.createElement("section");
    self.className = "flow-group this";
    const title = document.createElement("h3");
    title.textContent = this.t("thisPart");
    const node = document.createElement("p");
    node.className = `node current ${unit.kind}`;
    node.textContent = unit.text;
    self.append(title, node);
    for (const side of [group("limitedBy", near.limitedBy, "limit"), group("limits", near.limits, "limit"),
      group("meets", near.meets, "meets")]) if (side) self.appendChild(side);
    if (before) flow.append(before, arrow());
    flow.appendChild(self);
    if (after) flow.append(arrow(), after);
    $("see-empty").hidden = Boolean(before || after || self.children.length > 2);
    this.showPicture();
  }

  async showPicture(draw = false) {
    const unit = this.unit.unit;
    const figure = $("see-picture");
    const image = $("picture-image");
    $("picture-note").textContent = "";
    image.hidden = true;
    let found = unit.picture && unit.picture.image ? unit.picture : null;   // kept in the package
    const online = this.path.source === "server";
    $("draw").hidden = !online || Boolean(found) || this.unit.picture === true;
    if (!found && online && (draw || this.unit.picture === true)) {
      $("draw").hidden = true;
      $("picture-note").textContent = this.t("drawing");
      try {
        found = await this.api(`unit/${encodeURIComponent(unit.unit_id)}/picture?${this.q({})}`);
        if (found.deferred) {
          $("picture-note").textContent = this.t("pictureDeferred");
          figure.hidden = false;
          return;
        }
        this.unit.picture = true;
      } catch (error) {
        $("picture-note").textContent = error.message;
        $("draw").hidden = false;
        return;
      }
      if (this.unit.unit.unit_id !== unit.unit_id) return;   // moved on while it was drawn
    }
    if (found) {
      image.src = `data:${found.mime};base64,${found.image}`;
      image.hidden = false;
      $("picture-note").textContent = this.t("pictureNote", this.unit.guardian);
    } else if (!online) {
      $("picture-note").textContent = this.t("pictureOffline");
    }
    figure.hidden = false;
  }

  async play() {
    const unit = this.unit.unit;
    let base64 = unit.audio || null;
    let mime = unit.audio_mime || "audio/wav";
    let words = unit.audio_words || [];
    let spoken = unit.quote || unit.text;
    if (!base64 && this.path.source === "server") {
      try {
        const reply = await this.api(`unit/${encodeURIComponent(unit.unit_id)}/listen?${this.q({ lang: this.lang })}`);
        base64 = reply.audio;
        mime = reply.mime || mime;
        words = reply.words || [];
        spoken = reply.text || spoken;
      } catch (error) {
        $("listen-note").textContent = error.message;
        return;
      }
    }
    if (!base64) { $("listen-note").textContent = this.t("audioMissing"); return; }
    this.audio?.pause();
    this.audio = new Audio(`data:${mime};base64,${base64}`);
    // Each word lit as it is said, from the times the voice was made with.
    this.prompter.follow(this.audio, spoken, words);
    this.audio.play().catch(() => {});
  }

  async showBraille() {
    const unit = this.unit.unit;
    let pages = null;
    let brf = null;
    if (this.path.source === "server") {
      try {
        const reply = await this.api(`unit/${encodeURIComponent(unit.unit_id)}/braille?${this.q({ grade: this.grade, lang: this.lang })}`);
        pages = reply.pages_unicode;
        brf = reply.brf;
      } catch (error) {
        $("braille-note").textContent = error.message;
      }
    } else if (this.grade === 2) {
      pages = unit.braille;
    }
    $("braille-page").textContent = pages ? pages.map((p) => p.join("\n")).join("\n\n") : "";
    $("braille-note").textContent = pages ? this.t("pages", pages.length) : $("braille-note").textContent;
    this.brf = brf;
    $("brf").disabled = !brf;
  }

  showQuiz() {
    const has = this.quiz.length > 0;
    $("quiz-question").textContent = has ? this.quiz[0].question : this.t("noQuiz");
    for (const id of ["quiz-yes", "quiz-no", "quiz-voice"]) $(id).hidden = !has;
    $("quiz-feedback").hidden = true;
    if (has) this.say(this.quiz[0].question);
  }

  async answer(payload) {
    if (!this.quiz.length) return;
    const item = this.quiz[0];
    let reply;
    if (this.path.source === "server") {
      try {
        reply = await this.api("quiz", { method: "POST", body: JSON.stringify({ ...this.me(), case_id: item.case_id, ...payload }) });
      } catch (error) { this.say(error.message); return; }
    } else {
      if (payload.answer === undefined) { this.say(this.t("noMic")); return; }
      reply = { understood: true, right: payload.answer === item.applies, by: item.by, said: item.said };
      for (const uid of item.decides) await this.rateOffline(uid, reply.right ? 3 : 1);
    }
    if (reply.heard) this.prompter.heard(reply.heard);
    else if (payload.audio) this.prompter.hide();
    const box = $("quiz-feedback");
    box.hidden = false;
    if (!reply.understood) {
      box.className = "feedback";
      box.textContent = this.t("notUnderstood");
    } else {
      box.className = `feedback ${reply.right ? "right" : "wrong"}`;
      box.textContent = `${reply.right ? this.t("right") : this.t("wrong")} ${this.t("saidIt", reply.by, reply.said)}`;
      this.quiz = [...this.quiz.slice(1), item];
    }
    this.say(box.textContent);
  }

  async holdToAnswer(start) {
    if (start) {
      if (this.listening || this.path?.source !== "server") return;
      this.listening = true;
      if (await this.mic.start()) {
        $("quiz-voice").classList.add("recording");
        $("quiz-voice").textContent = this.t("listening");
        this.prompter.listening();
      } else {
        this.listening = false;
        this.say(this.t("noMic"));
      }
      return;
    }
    if (!this.listening) return;
    this.listening = false;
    $("quiz-voice").classList.remove("recording");
    $("quiz-voice").textContent = this.t("holdToAnswer");
    const said = await this.mic.stop();
    if (said.text) await this.answer({ said: said.text });
    else if (said.audio) await this.answer({ audio: said.audio });
    else this.prompter.hide();
  }

  async rate(rating) {
    const unitId = this.unit.unit.unit_id;
    if (this.path.source === "server") {
      try {
        const reply = await this.api("review", { method: "POST", body: JSON.stringify({ ...this.me(), unit_id: unitId, rating }) });
        const due = new Date(reply.due).toLocaleString(this.lang);
        $("recall-note").textContent = this.t("nextDue", due);
        this.path.units[this.index].progress = { state: "learned", due: reply.due };
        this.renderContents();
      } catch (error) { this.say(error.message); return; }
    } else {
      await this.rateOffline(unitId, rating);
      $("recall-note").textContent = "";
    }
    this.say($("recall-note").textContent || this.t("good"));
  }

  async rateOffline(unitId, rating) {
    await db.queue({ person: this.person, unit_id: unitId, rating, at: new Date().toISOString() });
    const progress = store.get(`urithi.offline.${this.person}`, {});
    progress[unitId] = { state: "learned" };
    store.set(`urithi.offline.${this.person}`, progress);
  }

  async syncQueued() {
    if (!navigator.onLine) return;
    let queued = [];
    try { queued = await db.drain(); } catch { return; }
    const mine = queued.filter((e) => e.person === this.person);
    const others = queued.filter((e) => e.person !== this.person);
    for (const entry of others) await db.queue(entry);
    if (!mine.length) return;
    try {
      const reply = await this.api("sync", { method: "POST", body: JSON.stringify({ ...this.me(), reviews: mine }) });
      this.say(this.t("synced", reply.applied));
    } catch {
      for (const entry of mine) await db.queue(entry);
    }
  }

  async download() {
    if (!this.path || this.path.source !== "server") return;
    try {
      const pkg = await this.api(`package/${encodeURIComponent(this.path.body.body_id)}?${this.q({ lang: this.lang, audio: true })}`);
      await this.learnKey();
      const packed = await this.unpack(pkg);
      await db.put(this.packageKey(this.path.body.body_id), packed);
      const units = JSON.parse(pkg.content_json).units.length;
      this.say(this.t("kept", units));
      $("path-lead").textContent = `${this.t("pathLead", this.path.units.length, this.path.due)} ${this.t("kept", units)}`;
      $("export").hidden = false;
    } catch (error) { this.say(error.message); }
  }

  async ask(question) {
    if (!question.trim() || !this.path) return;
    const box = $("answer");
    box.hidden = false;
    box.innerHTML = "";
    if (!navigator.onLine || this.path.source !== "server") {
      box.textContent = this.t("askOffline");
      this.say(box.textContent);
      return;
    }
    let reply;
    try {
      const inView = !$("unit").hidden && this.unit ? this.unit.unit.unit_id : null;
      reply = await this.api("ask", { method: "POST", body: JSON.stringify({ ...this.me(), body_id: this.path.body.body_id, question, lang: this.lang, unit_id: inView }) });
    } catch (error) { box.textContent = error.message; this.say(error.message); return; }
    if (reply.ticket) {
      this.remember(question.trim(), reply.ticket);
      this.refreshQuestions();
    }
    const text = document.createElement("p");
    text.textContent = reply.text;
    box.appendChild(text);
    for (const [shown, key] of [[reply.cached, "cachedNote"], [reply.stepped_down, "steppedNote"], [reply.warning, "nearLimit"]]) {
      if (!shown) continue;
      const note = document.createElement("p");
      note.className = "how";
      note.textContent = this.t(key);
      box.appendChild(note);
    }
    if (reply.citations?.length) {
      const how = document.createElement("p");
      how.className = "how";
      const guardian = reply.citations[0].guardian;
      how.textContent = reply.kind === "worded" ? this.t("worded", guardian) : this.t("extractive", guardian);
      const list = document.createElement("ol");
      for (const c of reply.citations) {
        const li = document.createElement("li");
        li.textContent = `${c.text} (${this.when(c.guardian, c)})`;
        list.appendChild(li);
      }
      box.append(how, list);
    }
    this.onThePath(box, reply, question);
    this.say(reply.text);
    if ($("no-screen").checked) this.readAloud(reply.text);
  }

  // What the tutor brings of the path: what the answer rests on, a case to try, reviews due;
  // and what can be done with the answer: keep it, hear it, read it in braille.
  onThePath(box, reply, question) {
    const index = new Map(this.path.units.map((u, i) => [u.unit_id, i]));
    if (reply.rests_on_unlearned?.length) {
      const note = document.createElement("div");
      note.className = "prereq";
      const text = document.createElement("span");
      text.textContent = this.t("restsOnAnswer", reply.rests_on_unlearned.map((r) => `“${r.text}”`).join(", "));
      const go = document.createElement("button");
      go.type = "button";
      go.className = "primary";
      go.textContent = this.t("goFirst");
      go.addEventListener("click", () => this.openUnit(index.get(reply.rests_on_unlearned[0].unit_id)));
      note.append(text, go);
      box.appendChild(note);
    }
    const row = document.createElement("div");
    row.className = "answer-actions";
    const button = (label, act) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "quiet small";
      b.textContent = this.t(label);
      b.addEventListener("click", act);
      row.appendChild(b);
    };
    const cited = (reply.citations || []).map((c) => c.unit_id);
    const keep = async (kind, text) => {
      try {
        await this.api("notebook", { method: "POST", body: JSON.stringify({ ...this.me(), body_id: this.path.body.body_id,
          kind, text, question, unit_ids: cited }) });
        this.say(this.t("kept"));
        this.loadNotebook();
      } catch (error) { this.say(error.message); }
    };
    if (reply.text && reply.kind !== "nothing_yet") {
      button("keepWhole", () => keep("whole", reply.text));
      if (cited.length) button("keepPoints", () => keep("key_points", ""));
      button("keepSelection", () => {
        const chosen = String(window.getSelection() || "").trim();
        if (chosen) keep("excerpt", chosen);
      });
      button("readAloud", () => this.readAloud(reply.text));
      button("inBraille", () => this.brailleOf(reply.text, box));
    }
    // A case of the part in view, to try at once in its Practise form.
    if (reply.try_case && this.unit && !$("unit").hidden) button("tryCase", () => this.setForm("quiz"));
    box.appendChild(row);
    if (reply.due) {
      const due = document.createElement("p");
      due.className = "how";
      due.textContent = this.t("reviewsDue", reply.due);
      box.appendChild(due);
    }
  }

  async readAloud(text) {
    try {
      const spoken = await this.api("say", { method: "POST", body: JSON.stringify({ ...this.me(), text: text.slice(0, 600) }) });
      this.audio?.pause();
      this.audio = new Audio(`data:${spoken.mime};base64,${spoken.audio}`);
      this.prompter.follow(this.audio, spoken.text, spoken.words);
      this.audio.play().catch(() => {});
    } catch (error) { this.say(error.message); }
  }

  async brailleOf(text, box) {
    try {
      const reply = await this.api("braille", { method: "POST", body: JSON.stringify({ ...this.me(), text, lang: this.lang }) });
      const pre = document.createElement("pre");
      pre.className = "sheet";
      pre.tabIndex = 0;
      pre.textContent = reply.pages.map((page) => page.join("\n")).join("\n\f\n");
      box.appendChild(pre);
      pre.focus();
    } catch (error) { this.say(error.message || this.t("noBraille")); }
  }

  // Where this learner was, and what they found hard (learner/memory/notebook.py), on any device.
  async loadSession() {
    if (this.path?.source !== "server") { $("where-was").hidden = true; return; }
    const session = await this.api(`session/${encodeURIComponent(this.path.body.body_id)}?${this.q({})}`).catch(() => null);
    const index = new Map(this.path.units.map((u, i) => [u.unit_id, i]));
    const on = session?.on && index.has(session.on) ? this.path.units[index.get(session.on)] : null;
    $("resume-part").hidden = !on;
    if (on) {
      $("resume-part").textContent = this.t("resumePart", on.text);
      $("resume-part").onclick = () => this.openUnit(index.get(on.unit_id));
    }
    const list = $("hard-list");
    list.innerHTML = "";
    const seen = new Set();
    for (const hard of [...(session?.hard || [])].reverse()) {
      if (seen.has(hard.unit_id) || !index.has(hard.unit_id)) continue;
      seen.add(hard.unit_id);
      const li = document.createElement("li");
      const b = document.createElement("button");
      b.type = "button";
      b.className = "quiet";
      b.textContent = this.path.units[index.get(hard.unit_id)].text;
      b.addEventListener("click", () => this.openUnit(index.get(hard.unit_id)));
      li.appendChild(b);
      list.appendChild(li);
    }
    $("found-hard").hidden = !list.children.length;
    $("where-was").hidden = !on && !list.children.length;
  }

  async loadNotebook() {
    if (this.path?.source !== "server") { $("notebook").hidden = true; return; }
    const reply = await this.api(`notebook?${this.q({ body_id: this.path.body.body_id })}`).catch(() => ({ entries: [] }));
    const list = $("notebook-list");
    list.innerHTML = "";
    for (const entry of reply.entries) {
      const li = document.createElement("li");
      const text = document.createElement("span");
      text.className = entry.kind === "excerpt" ? "said" : "";
      text.textContent = entry.text;
      const forget = document.createElement("button");
      forget.type = "button";
      forget.className = "quiet small";
      forget.textContent = this.t("forget");
      forget.addEventListener("click", async () => {
        await fetch(`/api/learner/notebook/${encodeURIComponent(entry.entry_id)}?${this.q({})}`, { method: "DELETE" });
        this.loadNotebook();
      });
      li.append(text, forget);
      list.appendChild(li);
    }
    $("notebook").hidden = !reply.entries.length;
  }

  // What the memory holds about this learner, readable and removable by them (apu/mmu, decision 0015).
  async loadRemembered() {
    if (this.path?.source !== "server") { $("remembered").hidden = true; return; }
    const bodyId = this.path.body.body_id;
    const reply = await this.api(`memory?${this.q({ body_id: bodyId })}`).catch(() => ({ blocks: [] }));
    const list = $("remembered-list");
    list.innerHTML = "";
    for (const block of reply.blocks) {
      const li = document.createElement("li");
      const text = document.createElement("span");
      text.textContent = block.content;
      const about = document.createElement("span");
      about.className = "note";
      about.textContent = block.knowledge_id ? (block.in_context ? this.t("aboutThis") : this.t("aboutOther")) : this.t("aboutYou");
      if (block.source?.said) about.textContent += ` · ${this.t("fromSaid", block.source.said)}`;
      const forget = document.createElement("button");
      forget.type = "button";
      forget.className = "quiet small";
      forget.textContent = this.t("forget");
      forget.setAttribute("aria-label", this.t("forgetMemory", block.content.slice(0, 80)));
      forget.addEventListener("click", async () => {
        await fetch(`/api/learner/memory/${encodeURIComponent(block.block_id)}?${this.q({})}`, { method: "DELETE" });
        this.loadRemembered();
      });
      li.append(text, document.createElement("br"), about, forget);
      list.appendChild(li);
    }
    $("remembered").hidden = !reply.blocks.length;
  }

  async showSheet(braille) {
    const reply = await this.api(`notebook/sheet/${encodeURIComponent(this.path.body.body_id)}?${this.q({ lang: this.lang })}`)
      .catch((error) => ({ text: error.message, braille_pages: [] }));
    const sheet = $("sheet");
    sheet.hidden = false;
    sheet.textContent = braille
      ? (reply.braille_pages.length ? reply.braille_pages.map((page) => page.join("\n")).join("\n\f\n") : this.t("noBraille"))
      : reply.text;
    sheet.focus();
  }

  // ── chrome ─────────────────────────────────────────────────────────────────
  applyLanguage() {
    document.documentElement.lang = this.lang;
    $("lang").textContent = this.lang === "en" ? "FR" : "EN";
    $("lang").setAttribute("aria-label", this.lang === "en" ? "Lire en français" : "Read in English");
    for (const node of document.querySelectorAll("[data-i18n]")) node.textContent = this.t(node.dataset.i18n);
    for (const node of document.querySelectorAll("[data-i18n-placeholder]")) node.placeholder = this.t(node.dataset.i18nPlaceholder);
    $("contents").setAttribute("aria-label", this.t("contents"));
    this.setNetwork(this.online);
  }

  setNetwork(online) {
    this.online = online;
    $("network").textContent = online ? this.t("online") : this.t("offline");
    $("network").classList.toggle("offline", !online);
  }

  // When the words were said: the date, when the library knows it. Seconds into a session
  // start again at zero in the next one, so they are shown only when there is nothing else.
  when(guardian, unit) {
    if (unit.said_at) {
      const day = new Date(unit.said_at).toLocaleDateString(this.lang, { day: "numeric", month: "long", year: "numeric" });
      return this.t("saidOn", guardian, day);
    }
    return this.t("said", guardian, this.mmss(unit.at));
  }

  mmss(seconds) {
    const s = Math.max(0, Math.floor(seconds || 0));
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  }

  bind() {
    $("person").addEventListener("change", (e) => {
      [this.person, this.organisation] = e.target.value.split("@");
      store.set("urithi.person", this.person);
      store.set("urithi.organisation", this.organisation);
      this.showHome();
    });
    $("lang").addEventListener("click", () => {
      this.lang = this.lang === "en" ? "fr" : "en";
      store.set("urithi.lang", this.lang);
      this.applyLanguage();
      // What was built from the server is built again in the new language. Measured: the home
      // page said "Enseigné par" nowhere, "Taught by Ezekias" stayed. A unit or an exam under
      // way is left as it is, rather than lose the learner's place.
      if (!$("home").hidden) this.showHome();
      else if (!$("path").hidden && this.path) this.openPath(this.path.body.body_id);
      else if (!$("unit").hidden && this.path) this.renderContents();
    });
    window.addEventListener("online", () => { this.setNetwork(true); this.syncQueued(); });
    window.addEventListener("offline", () => this.setNetwork(false));
    for (const button of document.querySelectorAll("[data-go]")) {
      button.addEventListener("click", () => (button.dataset.go === "home" ? this.showHome() : this.openPath(this.path.body.body_id)));
    }
    $("continue").addEventListener("click", () => this.openUnit(this.nextIndex()));
    $("sheet-screen").addEventListener("click", () => this.showSheet(false));
    $("sheet-braille").addEventListener("click", () => this.showSheet(true));
    const askMic = new LiveMicrophone({ url: () => `/api/learner/listen?${this.q({})}`,
      onPartial: (text) => this.prompter.partial(text) });
    let asking = false;
    $("ask-voice").addEventListener("pointerdown", async () => {
      if (asking) return;
      asking = await askMic.start();
      if (asking) this.prompter.listening(); else this.say(this.t("noMic"));
    });
    const stopAsking = async () => {
      if (!asking) return;
      asking = false;
      const said = await askMic.stop();
      // No live words: the recording is heard rather than thrown away (learner/api/routes.py, hear).
      if (!said.text && said.audio) {
        const heard = await this.api("hear", { method: "POST", body: JSON.stringify({ ...this.me(), audio: said.audio }) }).catch(() => ({}));
        if (heard.said) said.text = heard.said;
      }
      if (said.text) { this.prompter.heard(said.text); $("question").value = said.text; this.ask(said.text); }
      else { this.prompter.hide(); this.say(this.t("typeInstead")); }
    };
    $("ask-voice").addEventListener("pointerup", stopAsking);
    $("ask-voice").addEventListener("pointerleave", stopAsking);
    $("prereq-go").addEventListener("click", () => { if (this.prereqIndex != null) this.openUnit(this.prereqIndex); });
    $("download").addEventListener("click", () => this.download());
    $("export").addEventListener("click", () => this.exportKept());
    $("import").addEventListener("change", (e) => { if (e.target.files[0]) this.importFile(e.target.files[0]); e.target.value = ""; });
    $("exam-start").addEventListener("click", () => this.openExam());
    $("exam-yes").addEventListener("click", () => this.examAnswer(true));
    $("exam-no").addEventListener("click", () => this.examAnswer(false));
    $("exam-skip").addEventListener("click", () => this.examAnswer(null));
    $("exam-again").addEventListener("click", () => this.openExam());
    $("next").addEventListener("click", () => {
      if (this.index + 1 < this.path.units.length) this.openUnit(this.index + 1);
      else this.openPath(this.path.body.body_id);
    });
    for (const tab of document.querySelectorAll(".forms [role=tab]")) {
      tab.addEventListener("click", () => this.setForm(tab.dataset.form));
    }
    $("play").addEventListener("click", () => this.play());
    $("draw").addEventListener("click", () => this.showPicture(true));
    for (const button of document.querySelectorAll(".grades button")) {
      button.addEventListener("click", () => {
        this.grade = Number(button.dataset.grade);
        for (const b of document.querySelectorAll(".grades button")) b.setAttribute("aria-pressed", String(b === button));
        this.showBraille();
      });
    }
    $("brf").addEventListener("click", () => {
      if (!this.brf) return;
      const link = document.createElement("a");
      link.href = URL.createObjectURL(new Blob([this.brf], { type: "text/plain" }));
      link.download = "urithi-unit.brf";
      link.click();
    });
    $("quiz-yes").addEventListener("click", () => this.answer({ answer: true }));
    $("quiz-no").addEventListener("click", () => this.answer({ answer: false }));
    $("quiz-voice").addEventListener("pointerdown", () => this.holdToAnswer(true));
    $("quiz-voice").addEventListener("pointerup", () => this.holdToAnswer(false));
    $("quiz-voice").addEventListener("pointerleave", () => this.holdToAnswer(false));
    for (const button of document.querySelectorAll("[data-rating]")) {
      button.addEventListener("click", () => this.rate(Number(button.dataset.rating)));
    }
    $("ask-form").addEventListener("submit", (e) => { e.preventDefault(); this.ask($("question").value); });

    // The keyboard is the page, key for key. Never while typing, never over a browser shortcut.
    window.addEventListener("keydown", (event) => {
      if (event.metaKey || event.ctrlKey || event.altKey || event.repeat) return;
      const tag = document.activeElement?.tagName;
      if (["INPUT", "SELECT", "TEXTAREA"].includes(tag)) return;
      const onUnit = !$("unit").hidden;
      const key = event.key.length === 1 ? event.key.toLowerCase() : event.key;
      if (!$("exam").hidden) {
        if (key === "Escape") this.openPath(this.path.body.body_id);
        else if (key === "y") this.examAnswer(true);
        else if (key === "n") this.examAnswer(false);
        else if (key === "d") this.examAnswer(null);
        return;
      }
      if (key === "Escape") {
        if (onUnit) this.openPath(this.path.body.body_id);
        else if (!$("path").hidden) this.showHome();
      } else if (!onUnit) {
        return;
      } else if (key === "l") { this.setForm("listen"); this.play(); }
      else if (key === "b") { this.setForm("braille"); }
      else if (key === "p") { this.setForm("quiz"); }
      else if (key === "v") { this.setForm("see"); }
      else if (key === "y" && this.form === "quiz") { this.answer({ answer: true }); }
      else if (key === "n" && this.form === "quiz") { this.answer({ answer: false }); }
      else if (["1", "2", "3", "4"].includes(key)) { this.rate(Number(key)); }
      else if (key === "ArrowRight") { $("next").click(); }
      else if (key === " " && this.form === "quiz" && tag !== "BUTTON") { event.preventDefault(); this.holdToAnswer(true); }
    });
    window.addEventListener("keyup", (event) => {
      if (event.key === " " && this.listening) { event.preventDefault(); this.holdToAnswer(false); }
    });
  }
}

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("sw.js").catch(() => { /* the page works without it, online */ });
}
window.addEventListener("DOMContentLoaded", () => { window.learn = new Learn(); });
