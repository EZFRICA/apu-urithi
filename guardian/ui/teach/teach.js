/**
 * Urithi, the guardian's page: teach by talking, test the rules, hear it back, publish.
 *
 * One input for the whole conversation. While the debrief is on, what the guardian says
 * answers the case in front of them; otherwise it teaches. Everything is said out loud by
 * the apprentice and written down here, and nothing reaches the library before the guardian
 * has heard the teach-back and confirmed it.
 *
 * Teaching a body again continues its map, never a fresh one: a new version replaces the old
 * whole. That is also how a learner's question is answered: the guardian opens it from the
 * inbox, answers it as they would teach anything, and publishing closes it against the new
 * version, which is what the learner holding its ticket is then told.
 */

import { AudioPlayback } from "../shared/audio.js";
import { KeyMap } from "../shared/keys.js";
import { LiveMicrophone } from "../shared/live.js";
import { Teleprompter } from "../shared/teleprompter.js";
import { KnowledgeTree } from "../shared/tree.js";
import { Classroom } from "./classroom.js";

const STRINGS = {
  en: {
    brand: "Urithi · Teach", skip: "Skip to the conversation", whoLabel: "Teaching as", simulated: "Simulated identity",
    learn: "Learn", watch: "Watch me work", back: "Back",
    setupTitle: "Teach what you know",
    setupLead: "Talk the way you would to someone new. Urithi asks why at the right moment, writes down your rules in your words, tests them with you, and nothing is published until you have heard it back and said it is right.",
    taskLabel: "What are you teaching?", start: "Start", teachIn: "I teach in", inEnglish: "English", inFrench: "French",
    resumeTitle: "Carry on teaching", resume: "Continue",
    libraryDown: "The library cannot be reached just now: your teaching is kept, and publishing waits until it is back.",
    mapLine: (m) => `${m.language === "fr" ? "In French" : "In English"}, ${m.steps} step${m.steps === 1 ? "" : "s"}, ${m.rules} rule${m.rules === 1 ? "" : "s"}, ` +
      (m.published ? `version ${m.published} in the library` : "not published yet"),
    inboxTitle: "What learners asked that you have not covered",
    inboxLead: "Who asked is not kept, only the question. Answer it the way you would teach it: once you publish, the learner is told the answer is there.",
    answerIt: "Answer it", decline: "Not something I teach",
    declined: "Marked as not something you teach. The learner is told, rather than left waiting.",
    noMap: "This was published from another machine, so there is no conversation here to continue.",
    youSay: "What you say", placeholder: "Say it, or type it (Enter sends, Shift+Enter for a new line)",
    hold: "Hold to talk (Space)", listening: "Listening, let go when done", send: "Send",
    mapTitle: "The knowledge, as a tree", treeLabel: "What Urithi understood",
    treeKeys: "Arrows move, Right opens, Left closes.",
    counts: (s, r, c) => `${s} step${s === 1 ? "" : "s"} · ${r} rule${r === 1 ? "" : "s"} · ${c} case${c === 1 ? "" : "s"}`,
    otherRules: "Rules not tied to a step yet",
    severity: { stop: "stop", check: "check" },
    applies: { yes: "applies", no: "does not apply", none: "decided" },
    stateLabel: "Where this knowledge stands",
    states: { draft: "Draft", confirmed: "Validated", published: (v) => `Published v${v}`, since: (v) => `changed since v${v}` },
    prompter: { you: "You", urithi: "Urithi", listeningWords: "Listening…" },
    keys: [["Enter", "Send what you typed"], ["Shift+Enter", "A new line"], ["↑ ↓ ← →", "Move in the tree, open, close"]],
    classScreen: "Classroom: show my screen", classCamera: "Classroom: camera", inClass: "In class",
    onePupil: "1 pupil: Urithi", classPause: "Pause", classResume: "Carry on", classEnd: "End the class",
    classWaits: "Waits for a pause, then asks why.", classBoard: "Noted in this class",
    classDraft: "Drafts, until you validate them on your page.", saw: (c) => `Saw: ${c}`,
    classSwitches: "What Urithi may use", classMicOn: "Microphone: on", classMicOff: "Microphone: off",
    classHandsFreeOn: "Listen after a question: on", classHandsFreeOff: "Listen after a question: off",
    classSilentOn: "Silent mode: on", classSilentOff: "Silent mode: off",
    classVisionOn: "Vision: on", classVisionOff: "Vision: off", micIsOff: "The microphone is off: turn it on to answer aloud, or type.",
    classFloat: "Keep Urithi beside my work", noFloat: "This browser cannot keep a window on top. Put this tab beside your work instead.",
    classTalk: "Answer aloud", classTalking: "Listening… stop talking when you are done", classType: "Or type your answer",
    classPass: "Pass this question", classPassed: "Question passed.", classDeferred: "Kept for the debrief.",
    classLater: "Answer when you are ready: Answer aloud, or type it.",
    classWatching: (n) => `Watching your screen: ${n} change${n === 1 ? "" : "s"} looked at so far.`,
    noted: { saw: "Saw", asked: "Asked", urithi: "Urithi", why: "Why", said: "You", step: "Step", rule: "Rule", kept: "Kept", example: "Example", mistake: "Mistake", compare: "Compare", forget: "Forgot", passed: "Passed", deferred: "Debrief", proposed: "Proposed", saved: "Saved" },
    classRemember: "Remember this screen", remembering: "Keeping the screen…", stillAsking: "Kept. Urithi's question still waits for you.", keptScreen: "The screen, as it is now",
    cameraFaceWarning: "Camera on: this browser has no local FaceDetector, so frames go to the vision model before other people's faces are blurred.",
    pointed: "Part of the screen selected.", nothingToForget: "Nothing to forget.",
    writingDown: "Heard. Writing it down…",
    classEnded: (n) => `Class ended: ${n} step${n === 1 ? "" : "s"} captured, as drafts to validate.`,
    noScreen: "The screen or the camera was not shared.",
    deposit: "Document", sourcesTitle: "Your documents",
    sourcesLead: "Kept for this draft; only what a validated part cites is saved.",
    depositing: "Reading the document...", deposited: (name, n) => `${name}: ${n} passage${n === 1 ? "" : "s"} read.`,
    makeStep: "Make a step of this", proposing: "Making a step of that passage...",
    proposed: (t, where) => `From ${where}, I would make this step: "${t}". Shall I keep it?`,
    accept: "Keep it", notThis: "Not this", accepted: "Kept, as a draft. It is published once validated.",
    describeFirst: "Say what this image shows you, in your words, then make a step of it.",
    proposalsTitle: "Proposed to save",
    proposalsLead: "Nothing enters the knowledge tree until you save it.",
    notesTitle: "Urithi's notes",
    notesLead: "What Urithi heard and saw in this session, kept in working memory.",
    saveProposal: "Save", changeProposal: "Change", ignoreProposal: "Ignore",
    savedProposal: (t) => `Saved to knowledge: ${t}`, ignoredProposal: "Ignored proposal.",
    draftTag: "draft", lastAsked: (q) => `Last time, I asked: ${q}`,
    casesLeft: (n) => `${n} case${n === 1 ? "" : "s"} still to test, kept from last time.`,
    moveUp: (t) => `Move up: ${t}`, moveDown: (t) => `Move down: ${t}`,
    sectionLabel: (t) => `Section of: ${t}`, sectionPlaceholder: "Section",
    withdraw: "Withdraw from the library", withdrawSure: "Withdraw it? Press again",
    deleteIt: "Delete", deleteSure: "Delete it for good? Press again",
    deleted: (task) => `Deleted: ${task}. Nothing of it is kept, and learners no longer see it.`,
    withdrawn: "Withdrawn: learners no longer see it, and kept copies go at their next connection.",
    sources: "Check against public sources", debrief: "Test my rules",
    confirmTitle: "Is this how it works?", yes: "Yes, that is right", correctionPlaceholder: "Or say what is wrong", correct: "Correct it",
    publishTitle: "Who may learn each part?",
    publishLead: "Public: anyone. Community: members. Restricted: only those you trust with it. A part that repeats the words of a more restricted part is raised to that level, so a sentence is never open in one place and closed in another.",
    publish: "Publish",
    opening: "Tell me how you do it, the way you would tell someone new. I will ask why when it matters.",
    resumed: (n) => `You have taught ${n} step${n === 1 ? "" : "s"} here. Carry on where you left off.`,
    learnerAsked: (q) => `A learner asked: "${q}". Answer it the way you would answer them.`,
    answering: (n) => `Answering ${n} learner question${n === 1 ? "" : "s"} in this session.`,
    ready: "Ready to test and confirm.",
    retest: "Something new was taught: test your rules and hear it back again before publishing.",
    lookingUp: "Looking each rule up in public sources...",
    conflicts: (n) => `${n} of your rules disagree with a public source. Your rule stays as you said it; the learner is told.`,
    noConflicts: "No public source contradicts your rules.",
    testing: (kind, remaining) => `Testing your rules: ${kind}` + (remaining ? `, ${remaining} more after this.` : ", the last one."),
    kinds: { boundary: "a boundary", collision: "two rules at once", source: "a public source", near_miss: "close but not it" },
    kept: "Kept as your correction. Tell me more, then test the rules again.",
    confirmed: "Confirmed. Now decide who may learn each part.",
    whoMay: (text) => `Who may learn: ${text}`,
    levels: { public: "public", community: "community", restricted: "restricted" },
    raised: (level) => `Raised to ${level}: it repeats the words of a more restricted part.`,
    published: (r) => `Published, version ${r.version}: ${r.units} parts, ${r.cases} decided cases. `,
    openAsLearner: "Open it as a learner",
    closed: (n, v) => `${n} learner question${n === 1 ? " is" : "s are"} answered in version ${v}. Whoever asked is told.`,
    noMic: "The microphone is not available. Type instead.",
    verdicts: { corroborated: "a public source agrees", conflicted: "a public source says otherwise",
      house_rule: "your own rule, no public source", unchecked: "not checked" },
    when: (w, t) => `When ${w}, ${t}.`,
    removeRule: "Not a rule I gave", removeSure: "Remove it? Press again", removed: "Removed. Test your rules and hear it back again before publishing.",
    answersTitle: "Your answers to the test cases", answerAgain: "Answer it again",
    removeLabel: (w) => `Remove the rule: when ${w}`, againLabel: (q) => `Answer again: ${q}`,
    thinking: "Urithi is thinking...", finding: "Finding the cases where your rules are least clear...",
  },
  fr: {
    brand: "Urithi · Enseigner", skip: "Aller à la conversation", whoLabel: "Enseigner en tant que", simulated: "Identité simulée",
    learn: "Apprendre", watch: "Regarde-moi travailler", back: "Retour",
    setupTitle: "Enseigne ce que tu sais",
    setupLead: "Parle comme tu le ferais à quelqu'un de nouveau. Urithi demande pourquoi au bon moment, écrit tes règles avec tes mots, les teste avec toi, et rien n'est publié avant que tu l'aies réentendu et dit que c'est juste.",
    taskLabel: "Qu'est-ce que tu enseignes ?", start: "Commencer", teachIn: "J'enseigne en", inEnglish: "anglais", inFrench: "français",
    resumeTitle: "Continuer d'enseigner", resume: "Continuer",
    libraryDown: "La bibliothèque est injoignable pour l'instant : ton enseignement est gardé, et la publication attend son retour.",
    mapLine: (m) => `${m.language === "fr" ? "En français" : "En anglais"}, ${m.steps} étape${m.steps > 1 ? "s" : ""}, ${m.rules} règle${m.rules > 1 ? "s" : ""}, ` +
      (m.published ? `version ${m.published} dans la bibliothèque` : "pas encore publié"),
    inboxTitle: "Ce que les apprenants ont demandé et que tu n'as pas couvert",
    inboxLead: "Qui a demandé n'est pas gardé, seulement la question. Réponds comme tu l'enseignerais : une fois publié, l'apprenant apprend que la réponse est là.",
    answerIt: "Y répondre", decline: "Je n'enseigne pas cela",
    declined: "Noté comme hors de ce que tu enseignes. L'apprenant le saura, au lieu d'attendre.",
    noMap: "Ceci a été publié depuis une autre machine : il n'y a pas de conversation à reprendre ici.",
    youSay: "Ce que tu dis", placeholder: "Dis-le ou écris-le (Entrée envoie, Maj+Entrée pour une nouvelle ligne)",
    hold: "Maintenir pour parler (Espace)", listening: "J'écoute, relâche quand tu as fini", send: "Envoyer",
    mapTitle: "Le savoir, en arbre", treeLabel: "Ce qu'Urithi a compris",
    treeKeys: "Les flèches déplacent, Droite ouvre, Gauche ferme.",
    counts: (s, r, c) => `${s} étape${s > 1 ? "s" : ""} · ${r} règle${r > 1 ? "s" : ""} · ${c} cas`,
    otherRules: "Règles pas encore liées à une étape",
    severity: { stop: "arrêt", check: "vérification" },
    applies: { yes: "s'applique", no: "ne s'applique pas", none: "tranché" },
    stateLabel: "Où en est ce savoir",
    states: { draft: "Brouillon", confirmed: "Validé", published: (v) => `Publié v${v}`, since: (v) => `modifié depuis la v${v}` },
    prompter: { you: "Toi", urithi: "Urithi", listeningWords: "J'écoute…" },
    keys: [["Entrée", "Envoyer ce que tu as écrit"], ["Maj+Entrée", "Une nouvelle ligne"], ["↑ ↓ ← →", "Se déplacer dans l'arbre, ouvrir, fermer"]],
    classScreen: "Classe : montrer mon écran", classCamera: "Classe : caméra", inClass: "En classe",
    onePupil: "1 élève : Urithi", classPause: "Pause", classResume: "Reprendre", classEnd: "Finir la classe",
    classWaits: "Attend une pause, puis demande pourquoi.", classBoard: "Noté pendant cette classe",
    classDraft: "Des brouillons, jusqu'à ce que tu les valides sur ta page.", saw: (c) => `Vu : ${c}`,
    classSwitches: "Ce qu'Urithi peut utiliser", classMicOn: "Micro : activé", classMicOff: "Micro : coupé",
    classHandsFreeOn: "Écoute après une question : activée", classHandsFreeOff: "Écoute après une question : coupée",
    classSilentOn: "Mode silencieux : activé", classSilentOff: "Mode silencieux : coupé",
    classVisionOn: "Vision : activée", classVisionOff: "Vision : coupée", micIsOff: "Le micro est coupé : active-le pour répondre à voix haute, ou écris.",
    classFloat: "Garder Urithi à côté de mon travail", noFloat: "Ce navigateur ne peut pas garder une fenêtre au premier plan. Mets plutôt cet onglet à côté de ton travail.",
    classTalk: "Répondre à voix haute", classTalking: "J'écoute… arrête de parler quand tu as fini", classType: "Ou écris ta réponse",
    classPass: "Passer cette question", classPassed: "Question passée.", classDeferred: "Gardée pour le débrief.",
    classLater: "Réponds quand tu es prêt : Répondre à voix haute, ou écris-le.",
    classWatching: (n) => `Je regarde ton écran : ${n} changement${n > 1 ? "s" : ""} examiné${n > 1 ? "s" : ""} jusqu'ici.`,
    noted: { saw: "Vu", asked: "Demandé", urithi: "Urithi", why: "Pourquoi", said: "Toi", step: "Étape", rule: "Règle", kept: "Gardé", example: "Exemple", mistake: "Erreur", compare: "Comparé", forget: "Oublié", passed: "Passé", deferred: "Débrief", proposed: "Proposé", saved: "Enregistré" },
    classRemember: "Retiens cet écran", remembering: "Je garde l'écran…", stillAsking: "Gardé. La question d'Urithi t'attend toujours.", keptScreen: "L'écran, tel qu'il est",
    cameraFaceWarning: "Caméra active : ce navigateur n'ayant pas de FaceDetector local, les images vont au modèle de vision avant le floutage des visages tiers.",
    pointed: "Partie de l'écran choisie.", nothingToForget: "Rien à oublier.",
    writingDown: "Entendu. Je le note…",
    classEnded: (n) => `Classe finie : ${n} étape${n > 1 ? "s" : ""} captée${n > 1 ? "s" : ""}, en brouillon à valider.`,
    noScreen: "L'écran ou la caméra n'a pas été partagé.",
    deposit: "Document", sourcesTitle: "Tes documents",
    sourcesLead: "Gardés pour ce brouillon ; seul ce qu'une partie validée cite est enregistré.",
    depositing: "Je lis le document...", deposited: (name, n) => `${name} : ${n} passage${n > 1 ? "s" : ""} lu${n > 1 ? "s" : ""}.`,
    makeStep: "En faire une étape", proposing: "Je fais une étape de ce passage...",
    proposed: (t, where) => `À partir de ${where}, je ferais cette étape : « ${t} ». Je la garde ?`,
    accept: "La garder", notThis: "Pas ça", accepted: "Gardée, en brouillon. Elle est publiée une fois validée.",
    describeFirst: "Dis ce que cette image te montre, avec tes mots, puis fais-en une étape.",
    proposalsTitle: "Proposé à enregistrer",
    proposalsLead: "Rien n'entre dans l'arbre du savoir tant que tu ne l'enregistres pas.",
    notesTitle: "Notes d'Urithi",
    notesLead: "Ce qu'Urithi a entendu et vu pendant cette séance, gardé en mémoire de travail.",
    saveProposal: "Enregistrer", changeProposal: "Modifier", ignoreProposal: "Ignorer",
    savedProposal: (t) => `Enregistré dans le savoir : ${t}`, ignoredProposal: "Proposition ignorée.",
    draftTag: "brouillon", lastAsked: (q) => `La dernière fois, j'ai demandé : ${q}`,
    casesLeft: (n) => `${n} cas encore à tester, gardé${n > 1 ? "s" : ""} depuis la dernière fois.`,
    moveUp: (t) => `Monter : ${t}`, moveDown: (t) => `Descendre : ${t}`,
    sectionLabel: (t) => `Section de : ${t}`, sectionPlaceholder: "Section",
    withdraw: "Retirer de la bibliothèque", withdrawSure: "Le retirer ? Appuie encore",
    deleteIt: "Supprimer", deleteSure: "Le supprimer pour de bon ? Appuie encore",
    deleted: (task) => `Supprimé : ${task}. Rien n'en est gardé, et les apprenants ne le voient plus.`,
    withdrawn: "Retiré : les apprenants ne le voient plus, et les copies gardées partent à leur prochaine connexion.",
    sources: "Vérifier dans les sources publiques", debrief: "Tester mes règles",
    confirmTitle: "Est-ce que ça marche comme ça ?", yes: "Oui, c'est juste", correctionPlaceholder: "Ou dis ce qui ne va pas", correct: "Corriger",
    publishTitle: "Qui peut apprendre chaque partie ?",
    publishLead: "Public : tout le monde. Communauté : les membres. Réservé : seulement ceux à qui tu le confies. Une partie qui répète les mots d'une partie plus réservée est relevée à ce niveau : une phrase n'est jamais ouverte à un endroit et fermée à un autre.",
    publish: "Publier",
    opening: "Dis-moi comment tu fais, comme tu le dirais à quelqu'un de nouveau. Je demanderai pourquoi quand ça compte.",
    resumed: (n) => `Tu as enseigné ${n} étape${n > 1 ? "s" : ""} ici. Reprends où tu t'étais arrêté.`,
    learnerAsked: (q) => `Un apprenant a demandé : « ${q} ». Réponds comme tu lui répondrais.`,
    answering: (n) => `${n} question${n > 1 ? "s" : ""} d'apprenant en cours de réponse dans cette session.`,
    ready: "Prêt à tester et confirmer.",
    retest: "Quelque chose de nouveau a été enseigné : teste tes règles et réentends-le avant de publier.",
    lookingUp: "Je cherche chaque règle dans les sources publiques...",
    conflicts: (n) => `${n} de tes règles ne sont pas d'accord avec une source publique. Ta règle reste comme tu l'as dite ; l'apprenant en est informé.`,
    noConflicts: "Aucune source publique ne contredit tes règles.",
    testing: (kind, remaining) => `Test de tes règles : ${kind}` + (remaining ? `, encore ${remaining} après celle-ci.` : ", la dernière."),
    kinds: { boundary: "une limite", collision: "deux règles à la fois", source: "une source publique", near_miss: "proche mais pas ça" },
    kept: "Gardé comme ta correction. Dis-m'en plus, puis teste à nouveau les règles.",
    confirmed: "Confirmé. Décide maintenant qui peut apprendre chaque partie.",
    whoMay: (text) => `Qui peut apprendre : ${text}`,
    levels: { public: "public", community: "communauté", restricted: "réservé" },
    raised: (level) => `Relevée à « ${level} » : elle répète les mots d'une partie plus réservée.`,
    published: (r) => `Publié, version ${r.version} : ${r.units} parties, ${r.cases} cas tranchés. `,
    openAsLearner: "L'ouvrir en tant qu'apprenant",
    closed: (n, v) => `${n} question${n > 1 ? "s" : ""} d'apprenant ${n > 1 ? "ont" : "a"} sa réponse dans la version ${v}. Qui a demandé en est informé.`,
    noMic: "Le micro n'est pas disponible. Écris plutôt.",
    verdicts: { corroborated: "une source publique est d'accord", conflicted: "une source publique dit autre chose",
      house_rule: "ta propre règle, pas de source publique", unchecked: "pas vérifiée" },
    when: (w, t) => `Quand ${w}, tu ${t}.`,
    removeRule: "Ce n'est pas ma règle", removeSure: "La retirer ? Appuie encore", removed: "Retirée. Teste tes règles et réentends-le avant de publier.",
    answersTitle: "Tes réponses aux cas testés", answerAgain: "Y répondre à nouveau",
    removeLabel: (w) => `Retirer la règle : quand ${w}`, againLabel: (q) => `Répondre à nouveau : ${q}`,
    thinking: "Urithi réfléchit...", finding: "Je cherche les cas où tes règles sont le moins claires...",
  },
};

// The classroom's notes can sit in a floating window beside the guardian's work (Classroom.float):
// an element moved there is looked for there too.
let floating = null;
const $ = (id) => document.getElementById(id) || floating?.document.getElementById(id);
// Hands free: an answer ends when the guardian has been quiet this long after speaking, and
// the microphone closes if nothing at all is said this long after the question.
const ANSWER_QUIET_MS = 1800;
// "Remember this", said in a class, in either language: what follows is what to remember.
// Said anywhere in a sentence, as people do: "so I want you to keep the information on the
// part from…". Measured in a real class: only a sentence starting with the command was heard
// as one, and two requests to keep what was on screen became questions about thresholds. Said
// to Urithi ("you", "tu"), as a wish ("want to keep"), with "please", or as the first word:
// found in review, "we keep this channel public" was a request too, and it is teaching.
const REMEMBER_ANYWHERE = /(?:(?<![\wÀ-ÿ])(?:you|tu|vous)(?![\wÀ-ÿ])[^.?!]{0,25}?|(?<![\wÀ-ÿ])(?:want|need|wanna|like)\s+to\s+|(?<![\wÀ-ÿ])please[\s,]+|^[\s,]*(?:(?:ok(?:ay)?|so|alors|bon|euh)[\s,]+)*)(?:remember|keep|save|note|reten\w*|retien\w*|gard(?:e|es|ez|er)|sauvegard(?:e|es|ez|er)|not(?:e|es|ez|er))(?![\wÀ-ÿ])[^.?!]{0,40}?(?<![\wÀ-ÿ])(?:this|that|these|the information|information|informations|the screen|ça|ca|ceci|cela|cette information|ces informations|l'information|les informations|cet écran|l'écran)(?![\wÀ-ÿ])/i;
const REMEMBER = /^\s*(?:please\s+)?(?:remember|keep in mind|retiens|retenez|garde en m[ée]moire|note)\b(?:\s+(?:this|that|ceci|ça|ca|cela|cet)\b)?(?:\s+(?:screen|écran|ecran)\b)?[\s,.:;!-]*/i;
const ASK_PUPIL = /\b(?:did|do|can|could|have)\s+you(?:\s*,\s*(?:uh+|um+|euh+)\s*,\s*|\s+)(?:see|seen|read|catch|caught|notice|get|give|tell|show|remind|remember\s+me)\b|\b(?:did|do|have)\s+you\s+(?:keep|kept)\b|\bwhat\s+(?:is\s+the\s+)?information\s+(?:do\s+)?you\s+(?:keep|kept|have|see|saw)\b|\b(?:give|tell|remind)\s+me\s+(?:the\s+(?:rule|role|room|question|step|information)|information\s+about)\b|\bwhat\s+(?:is\s+the\s+|rule\b|role\b|room\b|question\b)[^.?!]{0,45}\byou(?:'re|\s+are)?\s+(?:talk(?:ing)?|ask(?:ing)?|speak(?:ing)?)\s+about\b|\bneed\s+the\s+(?:rule|role|room|whole)\s+(?:you\s+|to\s+)?talk(?:ing)?\s+about\b|\bi\s+said\s+[\w'-]+\s*,\s*not\s+[\w'-]+\b|\bwhat\s+would\s+you\s+(?:save|keep|propose)\b|\bque\s+(?:garderais|proposerais|sauvegarderais)-tu\b|\b(?:as-tu|vois-tu|quelle\s+r[èe]gle|donne-moi|rappelle-moi|j'ai\s+dit)\b/i;
// Plain or polite ("can you save this?", "peux-tu garder ça ?"), as the server reads it: measured in
// the second review of 2026-10-14, a polite save went to "remember this screen" and dropped the question.
const SAVE_COMMAND = /^\s*(?:(?:please|ok(?:ay)?|so|alors|bon|s'il\s+te\s+pla[iî]t)[\s,]+)*(?:(?:can|could|would|will)\s+you\s+(?:please\s+)?|(?:peux-tu|pourrais-tu|tu\s+peux|est-ce\s+que\s+tu\s+peux)\s+)?(?:save|keep|garde|gardes|gardez|garder|sauvegarde|sauvegarder|sauvegardez|enregistre|enregistrer|enregistrez)(?:\s+(?:this|that|it|this\s+one|that\s+one|the\s+proposal|the\s+step|the\s+rule|as\s+a\s+step|ça|ca|ceci|cela|la\s+proposition|la\s+règle|cette\s+étape|l'étape))?(?:[\s,]+(?:please|for\s+me|s'il\s+te\s+pla[iî]t|pour\s+moi))?\s*[.?!]*$/i;
const PASS_QUESTION = /^\s*(?:pass|skip(?:\s+it|\s+this)?|next(?:\s+question)?|passe|passons|suivante?)\s*[.?!]*$/i;
const ANSWER_WAIT_MS = 12000;
const store = {
  get(key, fallback) { try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; } },
  set(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* private mode */ } },
};
// Who is asking travels with every call: a guardian's routes answer that guardian alone
// (guardian/api/routes.py). Set when a guardian is chosen; simulated, as the badge says.
let asking = "";
let actingIn = "";   // the organisation the guardian acts in: one of their memberships
const withWho = (path) => `${path}${path.includes("?") ? "&" : "?"}person_id=${encodeURIComponent(asking)}` +
  `&organisation=${encodeURIComponent(actingIn)}`;
const post = (path, body) => fetch(withWho(path), {
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
}).then(async (r) => {
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || r.statusText);
  return data;
});
const slug = (text) => text.toLowerCase().normalize("NFKD").replace(/[^a-z0-9]+/g, " ").trim();

class Teach {
  constructor() {
    this.lang = store.get("urithi.lang", (navigator.language || "en").startsWith("fr") ? "fr" : "en");
    this.person = null;
    this.mapId = null;
    this.bodyId = null;
    this.probe = null;
    this.access = {};
    this.maps = [];
    this.answering = [];          // the inbox questions this session answers: [{id, question}]
    this.taught = this.lang;      // the language of the knowledge being taught, not of the page
    this.playback = new AudioPlayback();
    this.listening = false;
    this.published = 0;
    this.prompter = new Teleprompter($("prompter"), () => this.t("prompter"));
    // The words appear as they are said (apu/modality/live.py); the recording goes whole without it.
    this.mic = new LiveMicrophone({
      url: () => withWho("/api/guardian/listen"),
      onPartial: (text) => this.prompter.partial(text),
      onRefused: (message) => this.say(message.detail),
    });
    this.keys = new KeyMap(() => this.t("keys"));
    this.pagePrompter = this.prompter;
    this.classPrompter = new Teleprompter($("class-prompter"), () => this.t("prompter"));
    this.captured = 0;
    // The guardian's switches for a class, kept for the next one: the microphone off until
    // they turn it on; once on, listening after a question unless they turn that off.
    this.micOn = store.get("urithi.class.mic", false);
    this.handsFree = store.get("urithi.class.handsFree", true);
    this.silentMode = store.get("urithi.class.silent", false);
    this.classroom = new Classroom({
      dialog: $("classroom"), post, mapId: () => this.mapId,
      onQuestion: (reply) => {
        // Measured in a live run: a question came while the guardian was speaking, said over
        // them, and what they were saying would have been taken as its answer. It waits until
        // what they say has gone where it goes, then is asked.
        if (this.listening) {
          this.classroom.pending = null;
          this.waitingQuestion = reply;
          return;
        }
        this.classroom.pending = reply;
        const box = $("class-question");
        box.hidden = false;
        box.textContent = reply.question;
        if ($("class-pass")) $("class-pass").hidden = false;
        if (reply.why) this.note("why", reply.why);
        this.line("apprentice", reply.question);
        this.say(reply.question);
        // Asked aloud, then the microphone opens by itself: the guardian answers without
        // leaving the window they work in.
        this.voice(reply.audio, reply.words, reply.question, () => this.listenForAnswer());
        if (!reply.audio) this.listenForAnswer();
      },
      onSaw: (change, looked) => {
        $("class-saw").textContent = this.t("saw", change);
        this.note("saw", change);
        $("class-status").textContent = this.t("classWatching", looked);
      },
      onLooked: (looked) => { $("class-status").textContent = this.t("classWatching", looked); },
      onDeferred: (reply) => {
        if (reply.why) this.note("why", reply.why);
        this.note("deferred", reply.deferred);
        $("class-status").textContent = this.t("classDeferred");
      },
      onCaptured: (reply) => {
        $("class-question").hidden = true;
        if ($("class-pass")) $("class-pass").hidden = true;
        if (reply.step) {
          this.captured += 1;
          this.note("step", `${reply.step.number}. ${reply.step.title}: ${reply.step.reason}`);
          for (const rail of reply.guardrails || []) this.note("rule", this.said("when", rail.when, rail.then));
        } else if (reply.proposal) {
          this.note("proposed", `${reply.proposal.title}: ${reply.proposal.reason}`);
          for (const rail of reply.proposal.rules || []) this.note("rule", this.said("when", rail.when, rail.then));
        }
        // A reply that is only "noted" is written where the guardian looks, not only said: measured
        // live, an answer to a waiting question was heard but shown nowhere.
        const spoken = reply.question ? "" : (reply.answer || reply.noted || "");
        if (spoken) {
          this.line("apprentice", spoken);
          $("class-status").textContent = spoken;
        }
        this.voice(reply.audio, reply.words, reply.noted);
        this.refreshMap();
      },
      onEnd: () => {
        floating?.close();
        if ($("class-pass")) $("class-pass").hidden = true;
        this.prompter = this.pagePrompter;
        this.line("apprentice", this.t("classEnded", this.captured));
        this.refreshMap();
      },
    });
    this.classroom.silent = this.silentMode;
    this.tree = new KnowledgeTree($("tree"), { label: this.t("treeLabel") });
    this.bind();
    this.applyLanguage();
    $("taught").value = this.lang;   // until the guardian says otherwise, they teach in the page's language
    this.loadPeople();
  }

  t(key, ...args) {
    const value = STRINGS[this.lang][key] ?? STRINGS.en[key];
    return typeof value === "function" ? value(...args) : value;
  }

  // What Urithi says in the conversation is in the language being taught, whatever the page.
  said(key, ...args) {
    const value = STRINGS[this.taught]?.[key] ?? STRINGS.en[key];
    return typeof value === "function" ? value(...args) : value;
  }

  say(text) {
    const node = $("announcer");
    node.textContent = "";
    window.setTimeout(() => { node.textContent = text; }, 60);
  }

  get guardianName() {
    return $("person").selectedOptions[0]?.dataset.name || "";
  }

  async loadPeople() {
    const reply = await (await fetch("/api/guardian/people")).json();
    // One entry per membership: a guardian of two organisations chooses which one they teach in.
    const guardians = reply.people.filter((p) => p.role === "guardian");
    $("person").innerHTML = "";
    for (const p of guardians) {
      const option = document.createElement("option");
      option.value = `${p.person_id}@${p.organisation}`;
      option.textContent = `${p.name} · ${p.organisation_name}`;
      option.dataset.name = p.name;
      $("person").appendChild(option);
    }
    const kept = store.get("urithi.guardian", null);
    const values = guardians.map((p) => `${p.person_id}@${p.organisation}`);
    this.choose(values.includes(kept) ? kept : values[0]);
    $("person").value = `${this.person}@${this.organisation}`;
    await this.loadHome();
  }

  choose(value) {
    [this.person, this.organisation] = (value || "@").split("@");
    asking = this.person;
    actingIn = this.organisation;
  }

  // ── home: carry on, start, the inbox ────────────────────────────────────────
  async loadHome() {
    const reply = await (await fetch(`/api/guardian/knowledge?person_id=${encodeURIComponent(this.person)}&organisation=${encodeURIComponent(this.organisation)}`)).json().catch(() => ({ maps: [] }));
    this.maps = reply.maps || [];
    // The library out of reach (server.py): the maps still come, said as not knowing what is published.
    $("resume-note").textContent = reply.unavailable === "library" ? this.t("libraryDown") : "";
    $("resume-note").hidden = reply.unavailable !== "library";
    const list = $("resume-list");
    list.innerHTML = "";
    for (const m of this.maps) {
      const li = document.createElement("li");
      const text = document.createElement("div");
      const name = document.createElement("strong");
      name.textContent = m.task;
      const line = document.createElement("span");
      line.className = "note";
      line.textContent = this.t("mapLine", m);
      text.append(name, line);
      const button = document.createElement("button");
      button.textContent = this.t("resume");
      button.setAttribute("aria-label", `${this.t("resume")}: ${m.task}`);
      button.addEventListener("click", () => this.resume(m));
      li.append(text, button);
      if (m.published) li.appendChild(this.withdrawButton(m));
      li.appendChild(this.deleteButton(m));
      list.appendChild(li);
    }
    $("resume").hidden = !this.maps.length;
    await this.loadInbox();
  }

  withdrawButton(m) {
    const button = document.createElement("button");
    button.className = "quiet";
    button.textContent = this.t("withdraw");
    let armed = false;
    button.addEventListener("click", async () => {
      if (!armed) {
        armed = true;
        button.textContent = this.t("withdrawSure");
        window.setTimeout(() => { armed = false; button.textContent = this.t("withdraw"); }, 4000);
        return;
      }
      const reply = await fetch(withWho(`/api/guardian/body/${encodeURIComponent(m.body_id)}`), { method: "DELETE" });
      this.say(reply.ok ? this.t("withdrawn") : (await reply.json().catch(() => ({}))).detail || reply.statusText);
      await this.loadHome();
    });
    return button;
  }

  /** Deleting a knowledge: two presses, since nothing of it is kept (library_routes.delete_knowledge). */
  deleteButton(m) {
    const button = document.createElement("button");
    button.className = "quiet danger";
    button.textContent = this.t("deleteIt");
    button.setAttribute("aria-label", `${this.t("deleteIt")}: ${m.task}`);
    let armed = false;
    button.addEventListener("click", async () => {
      if (!armed) {
        armed = true;
        button.textContent = this.t("deleteSure");
        window.setTimeout(() => { armed = false; button.textContent = this.t("deleteIt"); }, 4000);
        return;
      }
      const reply = await fetch(withWho(`/api/guardian/map/${encodeURIComponent(m.map_id)}`), { method: "DELETE" });
      this.say(reply.ok ? this.t("deleted", m.task) : (await reply.json().catch(() => ({}))).detail || reply.statusText);
      await this.loadHome();
    });
    return button;
  }

  async loadInbox() {
    const list = $("inbox-list");
    list.innerHTML = "";
    for (const m of this.maps.filter((x) => x.published)) {
      const reply = await (await fetch(`/api/guardian/questions/${encodeURIComponent(m.body_id)}?person_id=${encodeURIComponent(this.person)}&organisation=${encodeURIComponent(this.organisation)}`)).json().catch(() => ({ questions: [] }));
      for (const q of reply.questions || []) list.appendChild(this.inboxItem(m, q));
    }
    $("inbox").hidden = !list.children.length;
  }

  inboxItem(m, q) {
    const li = document.createElement("li");
    const text = document.createElement("div");
    const question = document.createElement("q");
    question.textContent = q.question;
    question.lang = q.language;
    const where = document.createElement("span");
    where.className = "note";
    where.textContent = `${m.task} · ${new Date(q.asked_at).toLocaleDateString(this.lang)}`;
    text.append(question, where);
    const actions = document.createElement("div");
    actions.className = "inbox-actions";
    const answer = document.createElement("button");
    answer.className = "primary";
    answer.textContent = this.t("answerIt");
    answer.addEventListener("click", () => this.resume(m, q));
    const decline = document.createElement("button");
    decline.className = "quiet";
    decline.textContent = this.t("decline");
    decline.addEventListener("click", async () => {
      try {
        await post(`/api/guardian/questions/${encodeURIComponent(m.body_id)}/declined`, { person_id: this.person, organisation: this.organisation, ids: [q.id] });
        li.remove();
        this.say(this.t("declined"));
        $("inbox").hidden = !$("inbox-list").children.length;
      } catch (error) { this.say(error.message); }
    });
    actions.append(answer, decline);
    li.append(text, actions);
    return li;
  }

  // ── the conversation ─────────────────────────────────────────────────────────
  line(who, text) {
    const li = document.createElement("li");
    li.className = who;
    const label = document.createElement("span");
    label.className = "who";
    label.textContent = who === "guardian" ? this.guardianName : "Urithi";
    const body = document.createElement("span");
    body.textContent = text;
    li.append(label, body);
    $("transcript").appendChild(li);
    li.scrollIntoView({ block: "nearest" });
    // Only a question is "Asked" on the board; a reply is Urithi's (measured live: "Noted. Carry on."
    // was labelled ASKED).
    if (this.classroom?.open) this.note(who === "guardian" ? "said" : (/\?\s*$/.test(text) ? "asked" : "urithi"), text);
  }

  /** One line of the class's notes, with the class clock: what Urithi saw, asked, kept. */
  note(kind, text) {
    const board = $("class-board");
    if (!board || !text) return;
    if (kind === "asked" && board.lastElementChild?.dataset.text === text) return;
    const seconds = Math.floor(this.classroom?.capture?.at || 0);
    const li = document.createElement("li");
    li.className = `note-${kind}`;
    li.dataset.text = text;
    const when = document.createElement("span");
    when.className = "when";
    when.textContent = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
    const label = document.createElement("span");
    label.className = "kind";
    label.textContent = this.t("noted")[kind] || kind;
    const body = document.createElement("span");
    body.textContent = text;
    li.append(when, label, body);
    board.appendChild(li);
    li.scrollIntoView({ block: "nearest" });
  }

  /**
   * Hands free: the microphone opens, and the answer ends when the guardian has spoken and
   * then been quiet a moment; it goes to Urithi as if they had let go of the talk key.
   */
  async listenForAnswer({ byHand = false } = {}) {
    if (this.listening || !this.classroom.open) return;
    // The guardian decides: the microphone opens only while their switch is on, and by itself
    // after a question only while "listen after a question" is on too (docs/decisions/0013).
    if (!this.micOn) { $("class-status").textContent = this.t("micIsOff"); return; }
    if (!byHand && !this.handsFree) return;
    let spoke = false;
    let last = performance.now();
    const began = last;
    const partial = this.mic.onPartial;
    // Measured in a live run: the live service sends the same words again through the silence
    // after them, and each one put the end of the answer off; it never ended. Only new words count.
    let heard = "";
    this.mic.onPartial = (text) => {
      if (text !== heard) { heard = text; spoke = true; last = performance.now(); }
      this.prompter.partial(text);
    };
    await this.hold(true);
    if (!this.listening) { this.mic.onPartial = partial; return; }
    $("class-talk").textContent = this.t("classTalking");
    $("class-talk").classList.add("recording");
    const watch = window.setInterval(async () => {
      if (!this.listening) {   // let go by hand: what was said has gone already
        window.clearInterval(watch);
        this.mic.onPartial = partial;
        $("class-talk").textContent = this.t("classTalk");
        $("class-talk").classList.remove("recording");
        return;
      }
      if (this.classroom.voice?.isTalking) { spoke = true; last = performance.now(); }
      const now = performance.now();
      const finished = spoke ? now - last > ANSWER_QUIET_MS : now - began > ANSWER_WAIT_MS;
      if (!finished) return;
      window.clearInterval(watch);
      this.mic.onPartial = partial;
      $("class-talk").textContent = this.t("classTalk");
      $("class-talk").classList.remove("recording");
      if (spoke) { await this.hold(false); return; }
      // Nothing said: the question waits, and the microphone does not stay open on the room.
      this.listening = false;
      $("hold").classList.remove("recording");
      $("hold").textContent = this.t("hold");
      await this.mic.stop();
      this.prompter.hide();
      $("class-status").textContent = this.t("classLater");
    }, 250);
  }

  /** The three switches say what they are now, in words and in aria-pressed. */
  showSwitches() {
    const show = (id, on, onKey, offKey) => {
      $(id).setAttribute("aria-pressed", String(on));
      $(id).textContent = this.t(on ? onKey : offKey);
    };
    show("class-mic", this.micOn, "classMicOn", "classMicOff");
    show("class-handsfree", this.handsFree, "classHandsFreeOn", "classHandsFreeOff");
    $("class-handsfree").disabled = !this.micOn;
    $("class-talk").disabled = !this.micOn;
    if ($("class-silent")) show("class-silent", this.silentMode, "classSilentOn", "classSilentOff");
    show("class-pause", !this.classroom.paused, "classVisionOn", "classVisionOff");
  }

  /** "Remember this screen", by the button or by voice, with what to remember when said. */
  async rememberScreen(words = "") {
    if (!this.classroom.open) return null;
    $("class-status").textContent = this.t("remembering");
    this.note("kept", words || this.t("keptScreen"));   // noted at once, before Urithi answers
    // A question waiting is not forgotten: found in review, the page dropped it while the
    // server still held it, and the class never asked again. Kept with words, the screen is
    // a step of its own and the question still waits; kept alone, Urithi asks about it instead.
    const asked = this.classroom.pending;
    this.classroom.pending = null;
    const reply = await this.classroom.remember(words);
    if (reply.intent === "save" || reply.intent === "ask_pupil") {
      // Said back like any other save or answer, not left silent.
      const text = reply.noted || reply.answer || "";
      if (text) {
        this.line("apprentice", text);
        this.say(text);
        $("class-status").textContent = text;
        this.voice(reply.audio, reply.words, text);
      }
      await this.refreshMap();
    }
    // The question still waits unless this reply asked another: the server still holds it, and a page
    // that forgets it leaves the class silent (found in the second review of 2026-10-14, after a save).
    if (asked && !this.classroom.pending && !reply.question) {
      this.classroom.pending = asked;
      $("class-question").hidden = false;
      $("class-question").textContent = asked.question;
      if (!reply.noted && !reply.answer) $("class-status").textContent = this.t("stillAsking");
      return reply;
    }
    $("class-status").textContent = this.t(reply.error ? "noScreen" : "classWaits");
    return reply;
  }

  /** The question, the microphone and the notes, in a small window kept above every other. */
  async float() {
    if (floating) { floating.focus(); return; }
    if (!window.documentPictureInPicture) { this.say(this.t("noFloat")); $("class-status").textContent = this.t("noFloat"); return; }
    const pip = await window.documentPictureInPicture.requestWindow({ width: 420, height: 640 });
    for (const node of document.querySelectorAll('link[rel="stylesheet"], style')) pip.document.head.appendChild(node.cloneNode(true));
    pip.document.documentElement.lang = document.documentElement.lang;
    if (document.documentElement.dataset.theme) pip.document.documentElement.dataset.theme = document.documentElement.dataset.theme;
    pip.document.title = "Urithi";
    pip.document.body.className = "class-float";
    const pupil = $("class-pupil");
    const prompter = $("class-prompter");
    const homes = [[pupil, pupil.parentNode], [prompter, prompter.parentNode]];
    pip.document.body.append(pupil, prompter);
    floating = pip;
    pip.addEventListener("pagehide", () => {
      for (const [node, home] of homes) home.appendChild(node);
      floating = null;
    });
    pip.addEventListener("keydown", (e) => {
      const typing = ["INPUT", "TEXTAREA", "SELECT"].includes(e.target.tagName);
      if (e.key === " " && !typing && !e.repeat) { e.preventDefault(); this.hold(true); }
    });
    pip.addEventListener("keyup", (e) => {
      if (e.key === " " && this.listening) { e.preventDefault(); this.hold(false); }
    });
  }

  /** Point at a part of the shared screen so the next command keeps or reads that part. */
  pointScreen(region) {
    this.classroom.point(region);
    if (region) $("class-status").textContent = this.t("pointed");
    this.syncPending();
  }

  /** P2: Pass the question waiting; Urithi clears it and learns the guardian's threshold. */
  async passQuestion() {
    if (!this.classroom.open || !this.classroom.pending) return null;
    const asked = this.classroom.pending.question;
    const reply = await this.classroom.pass();
    $("class-question").hidden = true;
    if ($("class-pass")) $("class-pass").hidden = true;
    this.note("passed", asked || this.t("classPassed"));
    $("class-status").textContent = this.t("classPassed");
    return reply;
  }

  /** P1: Understand the guardian's classroom command by intent with QUESTION_MODEL. */
  async runCommand(said = "") {
    if (!this.classroom.open || !said) return null;
    const asked = this.classroom.pending;
    const reply = await this.classroom.command(said).catch(() => ({ intent: "none" }));
    if (!reply || !reply.intent || reply.intent === "none") return null;
    if (reply.intent === "ask_pupil") {
      const text = reply.answer || reply.noted || "";
      if (text) {
        this.line?.("apprentice", text);
        this.say?.(text);
        $("class-status").textContent = text;
        this.voice(reply.audio, reply.words, text);
      }
      if (reply.proposal) await this.refreshMap();
      return reply;
    }
    if (reply.intent === "remember") {
      this.note("kept", said);
      if (reply.step || reply.proposal) {
        if (reply.step) {
          this.captured += 1;
          this.note("step", `${reply.step.number}. ${reply.step.title}`);
        } else if (reply.proposal) {
          this.note("proposed", `${reply.proposal.title}`);
        }
        for (const g of (reply.guardrails?.length ? reply.guardrails : reply.proposal?.rules) || []) this.note("rule", `${g.when} -> ${g.then}`);
        if (asked) {
          this.classroom.pending = asked;
          $("class-question").hidden = false;
          $("class-question").textContent = asked.question;
          $("class-status").textContent = this.t("stillAsking");
        } else {
          $("class-status").textContent = this.t("classWaits");
        }
      } else if (reply.question) {
        this.classroom.onQuestion(reply);
      }
      await this.refreshMap();
      return reply;
    }
    if (reply.intent === "forget") {
      this.note("forget", reply.forgotten || this.t("nothingToForget"));
      if (reply.removed_number && this.captured > 0) this.captured -= 1;
      if (reply.noted) {
        $("class-status").textContent = reply.noted;
        this.voice(reply.audio, reply.words, reply.noted);
      }
      await this.refreshMap();
      return reply;
    }
    if (reply.ambiguous) {
      const msg = reply.question || reply.noted || reply.answer || "";
      this.note("question", msg || said);
      if (msg) {
        // In the conversation too, like every other reply: the guardian reads back what was asked.
        this.line("apprentice", msg);
        this.say(msg);
        $("class-status").textContent = msg;
        this.voice(reply.audio, reply.words, msg);
      }
      await this.refreshMap();
      return reply;
    }
    const item = reply.step || reply.proposal;
    this.note(reply.intent, item?.title || reply.guardrails?.[0]?.when || said);
    if (reply.step) {
      this.captured += 1;
      this.note("step", `${reply.step.number}. ${reply.step.title}`);
    } else if (reply.proposal) {
      this.note("proposed", `${reply.proposal.title}`);
    }
    for (const g of (reply.guardrails?.length ? reply.guardrails : reply.proposal?.rules) || []) this.note("rule", `${g.when} -> ${g.then}`);
    if (reply.noted) {
      $("class-status").textContent = reply.noted;
      this.voice(reply.audio, reply.words, reply.noted);
    }
    await this.refreshMap();
    return reply;
  }

  // Seconds pass while a model words a question or reads an answer: said, not left blank.
  async busy(key, work) {
    const li = document.createElement("li");
    li.className = "apprentice pending";
    li.setAttribute("aria-busy", "true");
    li.textContent = this.t(key);
    $("transcript").appendChild(li);
    li.scrollIntoView({ block: "nearest" });
    for (const id of ["said", "debrief", "sources"]) $(id).disabled = true;
    this.say(this.t(key));
    try {
      return await work();
    } finally {
      li.remove();
      for (const id of ["said", "debrief", "sources"]) $(id).disabled = false;
      $("said").focus();
    }
  }

  open(task) {
    $("setup").hidden = true;
    $("session").hidden = false;
    $("talk-title").textContent = task;
    $("transcript").innerHTML = "";
    $("confirm").hidden = true;
    $("publish").hidden = true;
    $("publish-note").textContent = "";
  }

  async start(task) {
    // The same task again continues its map: a fresh one would publish less than the library holds.
    const existing = this.maps.find((m) => slug(m.task) === slug(task));
    if (existing) return this.resume(existing);
    const started = await post("/api/guardian/start", { task, expert: this.guardianName, language: $("taught").value });
    this.mapId = started.map_id;
    this.published = 0;
    this.taught = started.language;
    this.open(task);
    this.line("apprentice", this.said("opening"));
    this.say(this.said("opening"));
    await this.refreshMap();
    $("said").focus();
  }

  async resume(m, question) {
    if (!m.map_id) { this.say(this.t("noMap")); return; }
    if (this.mapId !== m.map_id) {
      this.mapId = m.map_id;
      this.published = m.published || 0;
      this.taught = m.language || "en";
      // Kept per map: going back to the inbox for another question must not forget this one.
      this.answering = store.get(`urithi.answering.${m.map_id}`, []);
      this.open(m.task);
      this.line("apprentice", this.said("resumed", m.steps));
      await this.whereWeWere();
      await this.loadSources();
    }
    if (question && !this.answering.some((a) => a.id === question.id)) {
      this.answering.push({ id: question.id, question: question.question });
      store.set(`urithi.answering.${this.mapId}`, this.answering);
      this.line("apprentice", this.said("learnerAsked", question.question));
      this.say(this.said("learnerAsked", question.question));
    }
    this.showAnswering();
    await this.refreshMap();
    if (m.confirmed) {
      // Heard back and confirmed in an earlier session, and nothing taught since.
      $("publish").hidden = false;
      await this.preview();
    }
    $("said").focus();
  }

  showAnswering() {
    $("answering").textContent = this.answering.length ? this.t("answering", this.answering.length) : "";
  }

  /** The question that waits stays in view, with Pass, after anything else done in class. Measured
   * live: a command or a pointed region hid it while it still waited, and Pass could not be reached. */
  syncPending() {
    if (!this.classroom?.open) return;
    const waiting = this.classroom.pending;
    $("class-question").hidden = !waiting;
    if (waiting) $("class-question").textContent = waiting.question || "";
    if ($("class-pass")) $("class-pass").hidden = !waiting;
  }

  async send(said, audio) {
    const reply = await this.sendNow(said, audio);
    this.syncPending();
    return reply;
  }

  async sendNow(said, audio) {
    if (!said && !audio) return;
    if (said) this.line("guardian", said);
    $("said").value = "";
    try {
      if (this.classroom.open && said && ASK_PUPIL.test(said)) {
        const acted = await this.runCommand(said);
        if (acted) return acted;
      }
      if (this.classroom.open && said && SAVE_COMMAND.test(said)) {
        const acted = await this.runCommand(said);
        if (acted) return acted;
      }
      const remembered = this.classroom.open ? said?.match(REMEMBER) : null;
      if (remembered) return await this.rememberScreen(said.slice(remembered[0].length).trim());
      if (this.classroom.open && said && REMEMBER_ANYWHERE.test(said)) return await this.rememberScreen(said);
      if (this.classroom.open && said) {
        const acted = await this.runCommand(said);
        if (acted) return acted;
      }
      if (this.classroom.pending && said && PASS_QUESTION.test(said)) return await this.passQuestion();
      if (this.classroom.pending) {
        const reply = await this.classroom.answer({ said: said || null, audio: audio || null });
        // Not heard, or not kept: said where the guardian is looking, and the question still waits.
        if (reply.error) { this.line("apprentice", reply.error); this.prompter.speaking(reply.error); }
        else if (reply.intent === "ask_pupil" && (reply.answer || reply.noted)) {
          const text = reply.answer || reply.noted;
          this.line("apprentice", text);
          this.say(text);
          $("class-status").textContent = text;
          this.voice(reply.audio, reply.words, text);
          await this.refreshMap();
        } else {
          this.prompter.hide();
          await this.refreshMap();
        }
        return reply;
      }
      if (this.probe) return await this.busy("thinking", () => this.answerProbe(said, audio));
      if (said && this.sources?.length && /\bpage\s+\d+\b|\b\d{1,2}:\d{2}\b/i.test(said)) {
        return await this.propose(this.sources[this.sources.length - 1], { said });
      }
      const reply = await this.busy("thinking", () => post("/api/guardian/tell", { map_id: this.mapId, said: said || null, audio: audio || null }));
      if (reply.error) { this.line("apprentice", reply.error); return; }
      if (!said && (reply.step?.reason || reply.proposal?.reason || reply.note?.text || reply.heard)) {
        const heardText = reply.step?.reason || reply.proposal?.reason || reply.note?.text || reply.heard;
        this.line("guardian", heardText);
        this.prompter.heard(heardText);
      }
      if (reply.intent === "ask_pupil" && (reply.answer || reply.noted)) {
        const text = reply.answer || reply.noted;
        this.line("apprentice", text);
        this.say(text);
        if (this.classroom.open) $("class-status").textContent = text;
        this.voice(reply.audio, reply.words, text);
        await this.refreshMap();
        return reply;
      }
      if (reply.intent === "save") {
        if (reply.noted) {
          this.line("apprentice", reply.noted);
          this.say(reply.noted);
          if (this.classroom.open) $("class-status").textContent = reply.noted;
          this.voice(reply.audio, reply.words, reply.noted);
        }
        await this.refreshMap();
        return reply;
      }
      if (!reply.step && !reply.proposal && !reply.note) return reply;
      if (this.classroom.open) {
        if (reply.step) {
          this.captured += 1;
          this.note("step", `${reply.step.number}. ${reply.step.title}`);
        } else if (reply.proposal) {
          this.note("proposed", `${reply.proposal.title}: ${reply.proposal.reason}`);
        }
        for (const g of (reply.guardrails?.length ? reply.guardrails : reply.proposal?.rules) || []) this.note("rule", `${g.when} -> ${g.then}`);
        $("class-status").textContent = reply.question || reply.answer || reply.noted || this.t("classWaits");
        if (reply.question) {
          // A follow-up waits like any class question: shown with Pass, answered next.
          this.classroom.onQuestion(reply);
          await this.refreshMap();
          return reply;
        }
      }
      if (reply.step && (!$("confirm").hidden || !$("publish").hidden)) {
        // The server unconfirmed the map; the page says so instead of offering a publish that fails.
        $("confirm").hidden = true;
        $("publish").hidden = true;
        $("mode-note").textContent = this.t("retest");
      }
      const spokenText = reply.question || reply.answer || reply.noted;
      if (spokenText) {
        this.line("apprentice", spokenText);
        this.say(spokenText);
        this.voice(reply.audio, reply.words, spokenText);
      }
      await this.refreshMap();
      return reply;
    } catch (error) {
      this.line("apprentice", error.message);
    }
  }

  async refreshMap() {
    const map = await (await fetch(withWho(`/api/guardian/map/${this.mapId}`))).json();
    $("teachable").textContent = map.teachable ? this.t("ready") : (map.why_not || "");
    this.rulings = map.rulings || [];
    this.showStates(map.confirmed);
    this.validated = map.validated;
    this.renderProposals(map.proposals || []);
    this.renderNotes(map.notes || []);
    const byId = new Map(map.guardrails.map((g) => [`${g.when}|${g.then}`, g]));
    const placed = new Set();
    const ruleNode = (rail) => {
      placed.add(rail.id);
      const severity = this.t("severity")[rail.severity] || rail.severity;
      const verdict = this.t("verdicts")[rail.provenance?.verdict];
      const draft = map.states?.[`rule:${rail.id}`] === "draft" ? ` · ${this.t("draftTag")}` : "";
      return {
        id: `r-${rail.id}`, label: this.said("when", rail.when, rail.then), state: rail.severity,
        mark: rail.severity === "stop" ? "■" : "◆", tag: (verdict ? `${severity} · ${verdict}` : severity) + draft,
        extra: (li) => li.appendChild(this.removeButton(rail)),
        children: this.rulings.filter((r) => r.guardrail_id === rail.id).map((r) => ({
          id: `c-${r.ruling_id}`, mark: "◇",
          label: `${r.question} “${r.said}”`,
          tag: this.t("applies")[r.applies === true ? "yes" : r.applies === false ? "no" : "none"],
        })),
      };
    };
    this.contents = { order: map.order || map.steps.map((st) => st.step_id), sections: map.sections || [] };
    const nodes = map.steps.map((step, i) => ({
      id: `s-${step.number}`, mark: String(step.number), label: step.title, state: "step",
      tag: [step.section, map.states?.[`step:${step.step_id}`] === "draft" ? this.t("draftTag") : ""].filter(Boolean).join(" · "),
      extra: (li) => li.appendChild(this.contentsControls(step, i, map.steps.length)),
      children: step.guardrails.map((g) => byId.get(`${g.when}|${g.then}`)).filter(Boolean).map(ruleNode),
    }));
    const loose = map.guardrails.filter((g) => !placed.has(g.id));
    if (loose.length) nodes.push({ id: "loose", mark: "·", label: this.t("otherRules"), children: loose.map(ruleNode) });
    this.tree.render(nodes);
    $("map-count").textContent = this.t("counts", map.steps.length, map.guardrails.length, this.rulings.length);
  }

  renderProposals(proposals) {
    const box = $("proposals-box");
    const list = $("proposals-list");
    if (!box || !list) return;
    list.innerHTML = "";
    for (const p of proposals) {
      const li = document.createElement("li");
      li.className = "proposal-card";
      li.dataset.proposalId = p.proposal_id;
      li.dataset.proposalKind = p.kind || "step";
      const title = document.createElement("strong");
      title.textContent = p.title || "";
      const reason = document.createElement("p");
      reason.className = "said";
      reason.textContent = p.reason || "";
      li.append(title, reason);
      if (p.kind !== "rule" && p.rules?.length) {
        const rulesList = document.createElement("ul");
        rulesList.className = "proposal-rules";
        for (const r of p.rules) {
          const rli = document.createElement("li");
          rli.textContent = this.said("when", r.when, r.then);
          rulesList.appendChild(rli);
        }
        li.appendChild(rulesList);
      }
      const editBox = document.createElement("div");
      editBox.className = "proposal-edit";
      editBox.hidden = true;
      const input = document.createElement("textarea");
      input.rows = 2;
      input.value = p.reason || "";
      editBox.appendChild(input);
      const actions = document.createElement("div");
      actions.className = "proposal-actions";
      const saveBtn = document.createElement("button");
      saveBtn.type = "button";
      saveBtn.className = "primary small proposal-save";
      saveBtn.textContent = this.t("saveProposal");
      saveBtn.addEventListener("click", () => this.saveProposal(p.proposal_id, editBox.hidden ? null : input.value.trim()));
      const changeBtn = document.createElement("button");
      changeBtn.type = "button";
      changeBtn.className = "quiet small proposal-change";
      changeBtn.textContent = this.t("changeProposal");
      changeBtn.addEventListener("click", async () => {
        if (editBox.hidden) {
          editBox.hidden = false;
          input.focus();
        } else {
          await this.changeProposal(p.proposal_id, input.value.trim());
        }
      });
      const ignoreBtn = document.createElement("button");
      ignoreBtn.type = "button";
      ignoreBtn.className = "quiet small proposal-ignore";
      ignoreBtn.textContent = this.t("ignoreProposal");
      ignoreBtn.addEventListener("click", () => this.ignoreProposal(p.proposal_id));
      actions.append(saveBtn, changeBtn, ignoreBtn);
      li.append(editBox, actions);
      list.appendChild(li);
    }
    box.hidden = !proposals.length;
  }

  renderNotes(notes) {
    const box = $("notes-box");
    const list = $("notes-list");
    if (!box || !list) return;
    list.innerHTML = "";
    for (const n of notes) {
      const li = document.createElement("li");
      li.className = "note-item";
      const text = document.createElement("span");
      text.textContent = n.text || n.title || "";
      li.appendChild(text);
      list.appendChild(li);
    }
    box.hidden = !notes.length;
  }

  async saveProposal(proposalId, reason = null) {
    try {
      const body = { map_id: this.mapId, proposal_id: proposalId };
      if (reason) body.reason = reason;
      const reply = await post("/api/guardian/save", body);
      const title = reply.step?.title || (reply.guardrails?.[0] ? `${reply.guardrails[0].when} -> ${reply.guardrails[0].then}` : "") || reply.ruling?.said || "";
      this.say(this.t("savedProposal", title));
      if (!$("confirm").hidden || !$("publish").hidden) {
        $("confirm").hidden = true;
        $("publish").hidden = true;
        $("mode-note").textContent = this.t("retest");
      }
      await this.refreshMap();
      return reply;
    } catch (error) { this.say(error.message); return null; }
  }

  async changeProposal(proposalId, reason) {
    if (!reason) return null;
    try {
      const reply = await post("/api/guardian/proposal/change", { map_id: this.mapId, proposal_id: proposalId, reason });
      await this.refreshMap();
      return reply;
    } catch (error) { this.say(error.message); return null; }
  }

  async ignoreProposal(proposalId) {
    try {
      const reply = await post("/api/guardian/proposal/ignore", { map_id: this.mapId, proposal_id: proposalId });
      this.say(this.t("ignoredProposal"));
      await this.refreshMap();
      return reply;
    } catch (error) { this.say(error.message); return null; }
  }

  // The contents, set by the guardian: a step moved up or down, put in a section by name.
  contentsControls(step, index, count) {
    const box = document.createElement("div");
    box.className = "contents-controls";
    const move = (delta, label, glyph, disabled) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "quiet small";
      button.textContent = glyph;
      button.disabled = disabled;
      button.setAttribute("aria-label", this.t(label, step.title));
      button.addEventListener("click", () => this.moveStep(step.step_id, delta));
      return button;
    };
    const section = document.createElement("input");
    section.value = step.section || "";
    section.placeholder = this.t("sectionPlaceholder");
    section.setAttribute("aria-label", this.t("sectionLabel", step.title));
    section.addEventListener("change", () => this.setSection(step.step_id, section.value.trim()));
    box.append(move(-1, "moveUp", "↑", index === 0), move(1, "moveDown", "↓", index === count - 1), section);
    return box;
  }

  async saveContents(order, sections) {
    try {
      await post("/api/guardian/contents", { map_id: this.mapId, order, sections });
      $("confirm").hidden = true;
      $("publish").hidden = true;
      await this.refreshMap();
    } catch (error) { this.say(error.message); }
  }

  moveStep(stepId, delta) {
    const order = [...this.contents.order];
    const at = order.indexOf(stepId);
    const to = at + delta;
    if (at < 0 || to < 0 || to >= order.length) return;
    [order[at], order[to]] = [order[to], order[at]];
    this.saveContents(order, this.contents.sections);
  }

  setSection(stepId, title) {
    const sections = this.contents.sections.map((sec) => ({ ...sec, steps: sec.steps.filter((id) => id !== stepId) }))
      .filter((sec) => sec.steps.length);
    if (title) {
      const found = sections.find((sec) => sec.title === title);
      if (found) found.steps.push(stepId); else sections.push({ title, steps: [stepId] });
    }
    this.saveContents(this.contents.order, sections);
  }

  // ── sources: a document deposited, read into passages, a step made of one ────
  async deposit(file) {
    if (!file || !this.mapId) return;
    const data = await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result).split(",")[1]);
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
    try {
      const reply = await this.busy("depositing", () => post("/api/guardian/sources", {
        map_id: this.mapId, name: file.name, mime: file.type || "application/octet-stream", data }));
      this.line("apprentice", this.t("deposited", reply.source.name, reply.source.passages.length));
      await this.loadSources();
    } catch (error) { this.line("apprentice", error.message); }
  }

  async loadSources() {
    const reply = await (await fetch(withWho(`/api/guardian/sources/${this.mapId}`))).json().catch(() => ({ sources: [] }));
    this.sources = reply.sources || [];
    const list = $("sources-list");
    list.innerHTML = "";
    for (const source of this.sources) {
      const li = document.createElement("li");
      const name = document.createElement("strong");
      name.textContent = source.name;
      const passages = document.createElement("ol");
      for (const passage of source.passages) {
        const item = document.createElement("li");
        const where = document.createElement("span");
        where.className = "note";
        where.textContent = `${passage.where} · `;
        const text = document.createElement("span");
        text.className = "said";
        text.textContent = passage.text.length > 220 ? `${passage.text.slice(0, 220)}…` : passage.text;
        const make = document.createElement("button");
        make.type = "button";
        make.className = "quiet small";
        make.textContent = this.t("makeStep");
        make.setAttribute("aria-label", `${this.t("makeStep")}: ${source.name}, ${passage.where}`);
        make.addEventListener("click", () => this.propose(source, { passage: passage.n, described: passage.described }));
        item.append(where, text, make);
        passages.appendChild(item);
      }
      li.append(name, passages);
      list.appendChild(li);
    }
    $("sources-box").hidden = !this.sources.length;
  }

  async propose(source, { passage = null, said = "", described = false } = {}) {
    if (described && !said && !$("said").value.trim()) { this.line("apprentice", this.t("describeFirst")); return; }
    try {
      const reply = await this.busy("proposing", () => post("/api/guardian/sources/propose", {
        map_id: this.mapId, source_id: source.source_id, passage, said: said || $("said").value.trim() }));
      const proposal = reply.proposal;
      const li = document.createElement("li");
      li.className = "apprentice";
      const who = document.createElement("span");
      who.className = "who";
      who.textContent = "Urithi";
      const text = document.createElement("span");
      text.textContent = this.said("proposed", proposal.title, `${proposal.cites[0].name}, ${proposal.cites[0].where}`);
      const keep = document.createElement("button");
      keep.type = "button";
      keep.className = "primary small";
      keep.textContent = this.t("accept");
      const drop = document.createElement("button");
      drop.type = "button";
      drop.className = "quiet small";
      drop.textContent = this.t("notThis");
      keep.addEventListener("click", async () => {
        await post("/api/guardian/sources/accept", { map_id: this.mapId, proposal_id: proposal.proposal_id });
        li.remove();
        this.line("apprentice", this.said("accepted"));
        await this.refreshMap();
      });
      drop.addEventListener("click", () => li.remove());
      li.append(who, text, keep, drop);
      $("transcript").appendChild(li);
      this.say(text.textContent);
    } catch (error) { this.line("apprentice", error.message); }
  }

  // Where it was left: the question still open, the cases still to test (guardian/memory/working.py).
  async whereWeWere() {
    const memory = await (await fetch(withWho(`/api/guardian/memory/${this.mapId}`))).json().catch(() => ({}));
    if (memory.question?.text) this.line("apprentice", this.said("lastAsked", memory.question.text));
    const cases = (memory.blocks || []).filter((b) => b.kind === "open" && b.ref.startsWith("case-"));
    if (cases.length) {
      this.probe = cases[0].content;
      $("mode-note").textContent = this.t("casesLeft", cases.length);
      this.line("apprentice", this.probe.question);
    }
  }

  // Draft, validated, published: where this knowledge stands, in words.
  showStates(confirmed) {
    const states = this.t("states");
    const list = $("states");
    list.innerHTML = "";
    const add = (text, current) => {
      const li = document.createElement("li");
      li.textContent = text;
      if (current) li.setAttribute("aria-current", "step");
      list.appendChild(li);
    };
    add(states.draft, !confirmed);
    add(states.confirmed, confirmed);
    if (this.published) add(`${states.published(this.published)}${confirmed ? "" : ` · ${states.since(this.published)}`}`, false);
  }

  // A rule read out of what the guardian said that they did not give, or gave twice. Two
  // presses, so a slip of the finger does not take a rule away.
  removeButton(rail) {
    const button = document.createElement("button");
    button.className = "quiet small";
    button.textContent = this.t("removeRule");
    button.setAttribute("aria-label", this.t("removeLabel", rail.when));
    let armed = false;
    button.addEventListener("click", async () => {
      if (!armed) {
        armed = true;
        button.textContent = this.t("removeSure");
        window.setTimeout(() => { armed = false; button.textContent = this.t("removeRule"); }, 4000);
        return;
      }
      try {
        await post("/api/guardian/forget-rule", { map_id: this.mapId, guardrail_id: rail.id });
        $("confirm").hidden = true;
        $("publish").hidden = true;
        $("mode-note").textContent = this.t("removed");
        this.say(this.t("removed"));
        await this.refreshMap();
      } catch (error) { this.say(error.message); }
    });
    return button;
  }

  showAnswers() {
    const list = $("answers");
    list.innerHTML = "";
    for (const r of this.rulings || []) {
      const li = document.createElement("li");
      const question = document.createElement("p");
      question.textContent = r.question;
      const said = document.createElement("p");
      said.className = "note";
      said.textContent = `"${r.said}"`;
      const again = document.createElement("button");
      again.className = "quiet small";
      again.textContent = this.t("answerAgain");
      again.setAttribute("aria-label", this.t("againLabel", r.question));
      again.addEventListener("click", async () => {
        try {
          const reply = await post("/api/guardian/reask", { map_id: this.mapId, ruling_id: r.ruling_id });
          $("confirm").hidden = true;
          $("publish").hidden = true;
          this.showProbe(reply);
          $("said").focus();
        } catch (error) { this.say(error.message); }
      });
      li.append(question, said, again);
      list.appendChild(li);
    }
    $("answers-box").hidden = !list.children.length;
  }

  async checkSources() {
    try {
      const reply = await this.busy("lookingUp", () => post("/api/guardian/provenance", { map_id: this.mapId }));
      const conflicts = reply.conflicts?.length || 0;
      this.line("apprentice", conflicts ? this.said("conflicts", conflicts) : this.said("noConflicts"));
      await this.refreshMap();
    } catch (error) { this.line("apprentice", error.message); }
  }

  // ── the debrief, in the same conversation ────────────────────────────────────
  async debrief() {
    try {
      this.showProbe(await this.busy("finding", () => post("/api/guardian/debrief", { map_id: this.mapId })));
    } catch (error) { this.line("apprentice", error.message); }
  }

  showProbe(reply) {
    if (reply.error) { this.line("apprentice", reply.error); return; }
    if (reply.probe) {
      this.probe = reply.probe;
      const kind = this.t("kinds")[reply.probe.kind] || reply.probe.kind.replace("_", " ");
      $("mode-note").textContent = this.t("testing", kind, reply.probe.remaining);
      this.line("apprentice", reply.probe.question);
      this.say(reply.probe.question);
      this.voice(reply.probe.audio, reply.probe.words, reply.probe.question);
    }
    if (reply.done) {
      this.probe = null;
      $("mode-note").textContent = "";
      $("confirm").hidden = false;
      this.refreshMap().then(() => this.showAnswers());
      $("teach-back").textContent = reply.teach_back;
      $("teach-back").focus();
      this.say(reply.teach_back);
      this.voice(reply.audio, reply.words, reply.teach_back);
    }
  }

  async answerProbe(said, audio) {
    const reply = await post("/api/guardian/rule", {
      map_id: this.mapId, probe_id: this.probe.probe_id, said: said || null, audio: audio || null,
    });
    if (!said && reply.ruling?.said) { this.line("guardian", reply.ruling.said); this.prompter.heard(reply.ruling.said); }
    this.showProbe(reply);
  }

  async confirm(yes) {
    let reply;
    try {
      reply = await post("/api/guardian/confirm", {
        map_id: this.mapId, confirmed: yes, correction: yes ? "" : $("correction").value,
      });
    } catch (error) {
      this.line("apprentice", error.message);
      this.say(error.message);
      return;
    }
    if (!reply.confirmed) {
      if (reply.error) {
        this.line("apprentice", reply.error);
        this.say(reply.error);
        return;
      }
      this.line("apprentice", this.said("kept"));
      $("confirm").hidden = true;
      return;
    }
    this.line("apprentice", this.said("confirmed"));
    $("publish").hidden = false;
    await this.preview();
    $("publish").scrollIntoView({ behavior: "smooth" });
  }

  // ── publishing ──────────────────────────────────────────────────────────────
  async preview() {
    try {
      const reply = await post("/api/guardian/preview", { map_id: this.mapId, person_id: this.person, organisation: this.organisation, access: this.access });
      this.bodyId = reply.body_id;
      const list = $("publish-units");
      list.innerHTML = "";
      const levels = this.t("levels");
      for (const unit of reply.units) {
        const li = document.createElement("li");
        const row = document.createElement("div");
        row.className = "row";
        const text = document.createElement("span");
        text.className = "text";
        text.textContent = unit.text;
        const select = document.createElement("select");
        select.setAttribute("aria-label", this.t("whoMay", unit.text.replace(/[.\s]+$/, "")));
        for (const level of ["public", "community", "restricted"]) {
          const option = document.createElement("option");
          option.value = level;
          option.textContent = levels[level];
          option.selected = level === unit.access;   // what it will really get
          select.appendChild(option);
        }
        select.addEventListener("change", () => { this.access[unit.unit_id] = select.value; this.preview(); });
        row.append(text, select);
        li.appendChild(row);
        if (unit.raised) {
          const note = document.createElement("span");
          note.className = "raised";
          note.textContent = this.t("raised", levels[unit.access]);
          li.appendChild(note);
        }
        list.appendChild(li);
      }
    } catch (error) { $("publish-note").textContent = error.message; }
  }

  async publish() {
    try {
      const reply = await post("/api/guardian/publish", { map_id: this.mapId, person_id: this.person, organisation: this.organisation, access: this.access });
      this.published = reply.version;
      this.showStates(true);
      const note = $("publish-note");
      note.innerHTML = "";
      note.append(this.t("published", reply));
      const a = document.createElement("a");
      a.href = `/learn/#body=${encodeURIComponent(reply.body_id)}`;
      a.textContent = this.t("openAsLearner");
      note.appendChild(a);
      let spoken = this.t("published", reply);
      if (this.answering.length) {
        // Closed against the version the library now holds, which the server reads itself.
        const closed = await post(`/api/guardian/questions/${encodeURIComponent(reply.body_id)}/answered`,
          { person_id: this.person, organisation: this.organisation, ids: this.answering.map((q) => q.id) });
        const line = document.createElement("p");
        line.textContent = this.t("closed", closed.closed, closed.version);
        note.appendChild(line);
        spoken += line.textContent;
        this.answering = [];
        store.set(`urithi.answering.${this.mapId}`, []);
        this.showAnswering();
      }
      this.say(spoken);
      const reloaded = await (await fetch(`/api/guardian/knowledge?person_id=${encodeURIComponent(this.person)}&organisation=${encodeURIComponent(this.organisation)}`)).json().catch(() => ({ maps: [] }));
      this.maps = reloaded.maps || this.maps;
    } catch (error) { $("publish-note").textContent = error.message; }
  }

  // ── voice ───────────────────────────────────────────────────────────────────
  async hold(start) {
    if (start) {
      if (this.listening) return;
      if (this.classroom?.open && !this.micOn) { $("class-status").textContent = this.t("micIsOff"); return; }
      this.listening = true;
      if (await this.mic.start()) {
        $("hold").classList.add("recording");
        $("hold").textContent = this.t("listening");
        this.prompter.listening();
      } else {
        this.listening = false;
        this.say(this.t("noMic"));
      }
      return;
    }
    if (!this.listening) return;
    this.listening = false;
    $("hold").classList.remove("recording");
    $("hold").textContent = this.t("hold");
    // Measured: with the live words unavailable, "Listening…" stayed on screen for the seconds
    // the recording took to be heard, and looked frozen. It says what is happening instead.
    this.prompter.show("you", this.t("writingDown"), { linger: 15000 });
    const said = await this.mic.stop();
    // In a class, the words decide where they go ("remember this", or an answer), so a
    // recording with no live words is heard first, then sent as words.
    if (!said.text && said.audio && this.classroom.open) {
      const heard = await post("/api/guardian/hear", { map_id: this.mapId, audio: said.audio }).catch(() => ({}));
      if (heard.said) said.text = heard.said;
    }
    if (said.text) {
      this.prompter.heard(said.text);
      await this.send(said.text);
    } else if (said.audio) {
      await this.send(null, said.audio);
    } else {
      this.prompter.hide();
    }
    const waiting = this.waitingQuestion;
    this.waitingQuestion = null;
    if (waiting && this.classroom.open) this.classroom.onQuestion(waiting);
  }

  // Urithi's voice, and its words lit on the teleprompter as it says them.
  voice(audio, words, text, after = null) {
    if (!audio) return;
    let handle = null;
    this.playback.enqueue(audio, "audio/wav", {
      start: (now) => { handle = this.prompter.timed(words || [], text, now); },
      end: () => { handle?.done(); after?.(); },
    });
  }

  // ── chrome ─────────────────────────────────────────────────────────────────
  applyLanguage() {
    document.documentElement.lang = this.lang;
    document.title = this.t("brand");
    $("lang").textContent = this.lang === "en" ? "FR" : "EN";
    $("lang").setAttribute("aria-label", this.lang === "en" ? "Lire en français" : "Read in English");
    for (const node of document.querySelectorAll("[data-i18n]")) node.textContent = this.t(node.dataset.i18n);
    for (const node of document.querySelectorAll("[data-i18n-placeholder]")) node.placeholder = this.t(node.dataset.i18nPlaceholder);
    for (const node of document.querySelectorAll("[data-i18n-label]")) node.setAttribute("aria-label", this.t(node.dataset.i18nLabel));
    $("tree").setAttribute("aria-label", this.t("treeLabel"));
    if (this.classroom) this.showSwitches();   // the switches say what they are, not their default
    if (this.mapId) this.refreshMap();
  }

  bind() {
    $("person").addEventListener("change", (e) => {
      this.choose(e.target.value);
      store.set("urithi.guardian", e.target.value);
      this.mapId = null;
      $("session").hidden = true;
      $("setup").hidden = false;
      this.loadHome();
    });
    $("lang").addEventListener("click", () => {
      this.lang = this.lang === "en" ? "fr" : "en";
      store.set("urithi.lang", this.lang);
      this.applyLanguage();
      if (!$("setup").hidden) {
        $("taught").value = this.lang;
        this.loadHome();
      }
    });
    $("start-form").addEventListener("submit", (e) => { e.preventDefault(); this.start($("task").value.trim()); });
    $("home").addEventListener("click", () => {
      this.mapId = null;
      this.probe = null;
      $("session").hidden = true;
      $("setup").hidden = false;
      this.loadHome();
    });
    const startClass = async (source) => {
      if (!this.mapId) return;
      this.captured = 0;
      $("class-board").innerHTML = "";
      $("class-status").textContent = this.t("classWaits");
      $("class-title").textContent = $("talk-title").textContent;
      try {
        this.prompter = this.classPrompter;
        this.classroom.pause(false);
        await this.classroom.start(source, { listen: this.micOn });
        if (source === "camera" && this.classroom.cameraWarned) {
          $("class-status").textContent = this.t("cameraFaceWarning");
        }
        this.micOn = this.micOn && Boolean(this.classroom.voice);   // refused by the browser: off
        this.showSwitches();
      } catch {
        this.prompter = this.pagePrompter;
        this.say(this.t("noScreen"));
      }
    };
    $("class-screen").addEventListener("click", () => startClass("screen"));
    $("class-camera").addEventListener("click", () => startClass("camera"));
    $("class-end").addEventListener("click", () => this.classroom.end());
    $("class-float").addEventListener("click", () => this.float().catch(() => { $("class-status").textContent = this.t("noFloat"); }));
    $("class-talk").addEventListener("click", () => (this.listening ? this.hold(false) : this.listenForAnswer({ byHand: true })));
    $("class-mic").addEventListener("click", async () => {
      this.micOn = await this.classroom.microphone(!this.micOn);
      if (!this.micOn && this.listening) await this.hold(false);
      store.set("urithi.class.mic", this.micOn);
      this.showSwitches();
    });
    $("class-handsfree").addEventListener("click", () => {
      this.handsFree = !this.handsFree;
      store.set("urithi.class.handsFree", this.handsFree);
      this.showSwitches();
    });
    $("class-silent")?.addEventListener("click", async () => {
      this.silentMode = !this.silentMode;
      store.set("urithi.class.silent", this.silentMode);
      await this.classroom.setSilent(this.silentMode);
      this.showSwitches();
    });
    $("class-pass")?.addEventListener("click", () => this.passQuestion());
    $("class-remember").addEventListener("click", () => this.rememberScreen());
    let pointStart = null;
    $("class-video")?.addEventListener("pointerdown", (e) => {
      const r = e.currentTarget.getBoundingClientRect();
      if (!r.width || !r.height) return;
      pointStart = { x: (e.clientX - r.left) / r.width, y: (e.clientY - r.top) / r.height };
    });
    $("class-video")?.addEventListener("pointerup", (e) => {
      if (!pointStart) return;
      const r = e.currentTarget.getBoundingClientRect();
      const end = { x: (e.clientX - r.left) / r.width, y: (e.clientY - r.top) / r.height };
      const dx = Math.abs(end.x - pointStart.x);
      const dy = Math.abs(end.y - pointStart.y);
      if (dx >= 0.02 && dy >= 0.02) {
        this.pointScreen({ x: Math.min(pointStart.x, end.x), y: Math.min(pointStart.y, end.y), w: dx, h: dy });
      } else {
        this.pointScreen({
          x: Math.max(0, Math.min(0.6, end.x - 0.2)),
          y: Math.max(0, Math.min(0.65, end.y - 0.175)),
          w: 0.4,
          h: 0.35,
        });
      }
      pointStart = null;
    });
    $("class-say").addEventListener("submit", (e) => {
      e.preventDefault();
      const said = $("class-said").value.trim();
      $("class-said").value = "";
      this.send(said);
    });
    $("classroom").addEventListener("cancel", (e) => { e.preventDefault(); this.classroom.end(); });
    $("class-pause").addEventListener("click", () => {
      this.classroom.pause(!this.classroom.paused);
      this.showSwitches();
    });
    $("deposit").addEventListener("change", (e) => { this.deposit(e.target.files[0]); e.target.value = ""; });
    $("say-form").addEventListener("submit", (e) => { e.preventDefault(); this.send($("said").value.trim()); });
    $("said").addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); this.send($("said").value.trim()); }
    });
    $("hold").addEventListener("pointerdown", () => this.hold(true));
    $("hold").addEventListener("pointerup", () => this.hold(false));
    $("hold").addEventListener("pointerleave", () => this.hold(false));
    $("sources").addEventListener("click", () => this.checkSources());
    $("debrief").addEventListener("click", () => this.debrief());
    $("confirm-yes").addEventListener("click", () => this.confirm(true));
    $("confirm-no").addEventListener("click", () => this.confirm(false));
    $("publish-go").addEventListener("click", () => this.publish());
    window.addEventListener("keydown", (e) => {
      const typing = ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName);
      if (e.key === " " && !typing && !e.repeat && this.mapId) { e.preventDefault(); this.hold(true); }
    });
    window.addEventListener("keyup", (e) => {
      if (e.key === " " && this.listening) { e.preventDefault(); this.hold(false); }
    });
  }
}

window.addEventListener("DOMContentLoaded", () => { window.teach = new Teach(); });
