"""The guardian's commands in a class, understood by intent with the fast question model.

P1 of docs/plan.md. Rather than matching only fixed keywords at the start of a sentence,
Urithi reads whether what the guardian just said is a command to the pupil ("remember this",
"this is an example", "a common mistake", "compare with before", "forget that") or ordinary
teaching and answering ("none"). Uses QUESTION_MODEL from .env so the guardian does not wait.
"""

from dataclasses import dataclass
import re

from apu import config
from apu.inference import llm
from apu.inference.llm import call_main_model
from apu.logger import get_logger
from guardian.engine import jsonish

logger = get_logger(__name__)

INTENTS = ("save", "remember", "example", "mistake", "compare", "forget", "ask_pupil", "none")


@dataclass(frozen=True)
class Command:
    intent: str          # one of INTENTS
    what: str = ""       # the part or detail the guardian named, in their words


SYSTEM = (
    "You classify one utterance spoken by a teacher (the guardian) in a live classroom session "
    "with their pupil Urithi.\n"
    "Decide whether the guardian is issuing a classroom command to Urithi, asking "
    "Urithi a question as their pupil (\"ask_pupil\"), or simply teaching / answering a question.\n"
    'Return JSON only: {"intent": "save"|"remember"|"example"|"mistake"|"compare"|"forget"|"ask_pupil"|"none", '
    '"what": "..."}\n'
    '- "save": explicitly asking Urithi to save a pending proposal or a noted step/rule into the '
    'knowledge tree ("save this", "save that step", "garde ça", "sauvegarde ça", "enregistre cette étape").\n'
    '- "remember": asking Urithi to note or remember what is on the screen right now as a source '
    '("remember this", "can you keep the venue and format", "retiens ça"). '
    'IMPORTANT: a sentence that describes the guardian\'s own habit or rule ("We keep this channel '
    'public for newcomers", "I keep that list in a spreadsheet", "On garde cette salle deux '
    'semaines à l\'avance") is teaching, so its intent is "none".\n'
    '- "example": flagging what is shown or said as a concrete example or illustration for learners '
    '("this is an example of a two-talk meetup", "here is a good example", "voici un exemple").\n'
    '- "mistake": flagging a common mistake, pitfall or trap that learners or newcomers fall into '
    '("a common mistake is announcing in general", "newcomers often get this wrong", '
    '"une erreur fréquente est de...").\n'
    '- "compare": asking to compare the screen now with how it looked before '
    '("compare with before", "look at what changed from the previous screen", '
    '"compare avec avant").\n'
    '- "forget": asking Urithi to drop, undo or forget a pending proposal, a note, or the last step '
    '("forget that", "scratch that last step", "oublie ça", "annule ce que je viens de dire").\n'
    '- "ask_pupil": asking Urithi a question, asking what Urithi saw on the screen or kept in '
    'its notes, asking what Urithi would save ("what would you save?"), asking what rule or '
    'question Urithi is talking about, or correcting a misheard word '
    '("did you see my screen?", "do you see the information on my deck?", "can you give me '
    'information about the organised desk?", "what rule are you talking about?", "give me the '
    'rule", "can you remind me the rule you talk about?", "I said rule, not room", '
    '"what would you save?", "as-tu vu mon écran ?", "de quelle règle parles-tu ?", "que garderais-tu ?").\n'
    '- "none": anything else (explaining a step, stating a rule, answering Urithi\'s question).\n'
    '- "what": the specific content, part of the screen, proposal, example, mistake, or question named by '
    'the guardian, in their own words (empty string when nothing specific was named).'
)

PUPIL_ANSWER_SYSTEM = (
    "You are Urithi, a pupil in a live teaching session with a guardian.\n"
    "The guardian just asked you a question or asked what you saw, noted, proposed, or meant.\n"
    "Answer in ONE short spoken sentence of at most 25 words (no lists, no markdown), the way a "
    "pupil would say it aloud, using ONLY the facts given to you below:\n"
    "- What you saw on the screen\n"
    "- Your last question\n"
    "- The steps and notes already noted or saved\n"
    "- The rules already noted or saved\n"
    "- The proposal waiting to be saved\n"
    "Strict rules you never break:\n"
    "- Answer the guardian's specific question directly using what you actually know.\n"
    "- Never invent a rule, a step, a role, a screen detail, or a number that is not written in the "
    "facts below.\n"
    "- If the guardian asks what rule or role you are talking about and 'Rules already noted or saved' "
    "is 'none', state simply that you have not cited or noted any rule yet, mention what you did "
    "note or see if relevant, and remind them of your last question.\n"
    "- If the guardian corrects a misheard word (for example 'I said rule, not room'), acknowledge "
    "the correction directly and state whether any rule is noted yet and what your question was.\n"
    "- Speech recognition may write 'my deck' or 'organized desk' when the guardian means their "
    "screen or the Organiser's Desk, and may write 'role', 'room', or 'whole to talk about' when "
    "the guardian means 'rule you talk about': if no rule is noted yet, say simply that no rule "
    "has been cited or noted yet, mention what you did see or note if relevant, and recall your "
    "last question.\n"
    "- Never repeat any sentence from 'Previous answers already given' word for word: tailor your "
    "answer to the exact question the guardian just asked.\n"
    "- If the guardian asks about the screen and nothing was seen on the screen yet, or asks "
    "for anything not present in the facts below, say \"I have not seen that yet.\" "
    '(or in French: "Je n\'ai pas encore vu cela.").\n'
    "- Never read a note back whole: name it in a few of its words.\n"
    "- Do not ask a new question back."
)


def _spoken_length(sentence: str, words: int = 25) -> str:
    """One spoken sentence of about `words` words, cut at a comma or semicolon when longer: the
    voice reads the whole answer before the guardian hears it, so length is waiting (measured live:
    answers of thirty words and more took past 3 s)."""
    cut = sentence.split()
    if len(cut) <= words:
        return sentence
    head = " ".join(cut[:words])
    stop = max(head.rfind(","), head.rfind(";"))
    return (head[:stop] if stop > len(head) // 2 else head).rstrip(" ,;:") + "."


def _short(text: str, words: int = 10) -> str:
    """A note named in a few of its words, never read back whole: a spoken answer stays short."""
    cut = _clean_speech(str(text or "")).split()
    return " ".join(cut[:words]) + ("..." if len(cut) > words else "")

_DISFLUENCY_RE = re.compile(
    r"\[[^\]]*\]|\b(?:uh+|um+|mm+|hmm+|er+|ah+|euh+|hum+|ben|bah)\b",
    re.IGNORECASE,
)
_STUTTER_RE = re.compile(r"\b(\w+)(?:\s*,\s*|\s+)\1\b", re.IGNORECASE)

_SAVE_RE = re.compile(
    r"^\s*(?:please\s+|ok(?:ay)?[\s,]+|yes[\s,]+|oui[\s,]+|bon[\s,]+|alors[\s,]+|euh[\s,]+)*"
    r"(?:"
    r"save(?:\s*[:,-]\s*(?P<what_colon>[^.?!]+)|\s+(?P<what_en>(?:this|that|it|the|a|an|step|rule|case|proposal|note|one|first|second|third|last|latest|#?\d)\b[^.?!]*)?)?"
    r"|(?:sauvegard(?:e|es|er|ez)|enregistr(?:e|es|er|ez))"
    r"(?:\s*[:,-]?\s*(?P<what_fr>[^.?!]*))?"
    r"|gard(?:e|es|ez)\s+(?P<what_garde>(?:ça|ca|ceci|cela|(?:la|cette)\s+r[èe]gle|(?:l'|cette\s+)[ée]tape|(?:la|cette)\s+proposition)[^.?!]*)"
    r")\s*[.?!]*\s*$",
    re.IGNORECASE,
)
_GENERIC_SAVE_WHAT_RE = re.compile(
    r"^(?:this|that|it|the\s+(?:proposal|note|one)|"
    r"this\s+(?:proposal|note|one)|that\s+(?:proposal|note|one)|"
    r"ça|ca|ceci|cela|la\s+proposition|cette\s+proposition)$",
    re.IGNORECASE,
)

_FORGET_RE = re.compile(
    r"^\s*(?:please\s+|ok(?:ay)?[\s,]+|bon[\s,]+|euh[\s,]+)*"
    r"(?:forget\s+(?:that|this|it|the\s+(?:last\s+|saved\s+)?(?:one|step|rule|proposal|note))|"
    r"scratch\s+that(?:\s+last\s+step)?|never\s+mind\s+that|"
    r"undo\s+that|oublie\s+(?:ça|ca|ceci|cela|la\s+derni[èe]re\s+[ée]tape|l'[ée]tape\s+sauvegard[ée]e|la\s+proposition)|"
    r"annule\s+(?:ça|ca|ce\s+que\s+je\s+viens\s+de\s+dire))\b",
    re.IGNORECASE,
)
_COMPARE_RE = re.compile(
    r"\b(?:compare\b[^.?!]{0,30}\b(?:before|earlier|previous|prior)|"
    r"difference\s+(?:with|from)\s+(?:before|earlier)|"
    r"compar(?:e|er|ez|ons)\b[^.?!]{0,30}\b(?:avant|pr[ée]c[ée]dent|tout\s+[àa]\s+l'heure))\b",
    re.IGNORECASE,
)
_EXAMPLE_RE = re.compile(
    r"\b(?:this\s+is\s+an?\s+(?:good\s+|concrete\s+)?example|here\s+is\s+an?\s+example|"
    r"as\s+an\s+example\s+here|c'est\s+un\s+(?:bon\s+)?exemple|voici\s+un\s+exemple)\b[:\s,-]*",
    re.IGNORECASE,
)
_MISTAKE_RE = re.compile(
    r"\b(?:a\s+common\s+(?:mistake|error|pitfall|trap)|common\s+(?:mistake|error)|"
    r"people\s+often\s+(?:make\s+the\s+mistake|get\s+this\s+wrong)|"
    r"(?:une\s+)?erreur\s+(?:fr[ée]quente|courante|classique)|pi[èe]ge\s+fr[ée]quent)\b[:\s,-]*",
    re.IGNORECASE,
)
_ASK_PUPIL_RE = re.compile(
    r"\b(?:did|do|can|could|have)\s+you\s+(?:see|seen|read|catch|caught|notice|get)\b|"
    r"\b(?:did|do|have)\s+you\s+(?:keep|kept|note|noted)\b|"
    r"\bwhat\s+(?:did|do|can|would|should)\s+you\s+(?:see|read|keep|have|notice|save|propose)\b|"
    r"\bwhat\s+(?:is\s+the\s+)?information\s+(?:do\s+)?you\s+(?:keep|kept|have|see|saw)\b|"
    r"\b(?:can|could)\s+you\s+(?:give|tell|show|read|remind|remember|state|repeat)\s+(?:me\b|the\s+(?:rule|role|room|question|step)\b)|"
    r"\b(?:give|tell|remind)\s+me\s+(?:the\s+(?:rule|role|room|question|step|information)|"
    r"information\s+about|what\s+(?:rule|you\s+(?:saw|see|asked|keep|kept|noted|mean)))\b|"
    r"\bwhat\s+(?:is\s+the\s+|rule\b|role\b|room\b|question\b)[^.?!]{0,45}"
    r"\byou(?:'re|\s+are)?\s+(?:talk(?:ing)?|ask(?:ing)?|speak(?:ing)?)\s+about\b|"
    r"\b(?:what|which)\s+(?:is\s+(?:the|your|that)\s+|was\s+(?:the|your|that)\s+)?(?:rule|role|room|question)s?\b|"
    r"\b(?:what|which)\s+(?:rule|role|room|question|step)s?\s+(?:are\s+you|do\s+you|did\s+you)\b|"
    r"\bneed\s+the\s+(?:rule|role|room|whole)\s+(?:you\s+|to\s+)?talk(?:ing)?\s+about\b|"
    r"\bi\s+said\s+[\w'-]+\s*,\s*not\s+[\w'-]+\b|"
    r"\b(?:as-tu|est-ce\s+que\s+tu\s+as|tu\s+as)\s+(?:vu|lu|not[ée]|gard[ée]|retenu)\b|"
    r"\b(?:vois-tu|est-ce\s+que\s+tu\s+vois|tu\s+vois)\b[^.?!]{0,30}\b(?:[ée]cran|information|page)\b|"
    r"\b(?:qu'est-ce\s+que|que)\s+(?:tu\s+(?:vois|as\s+vu|gardes|garderais|sauvegarderais|proposes|"
    r"as\s+not[ée]|demandes|as\s+demand[ée])|garderais-tu|proposes-tu)\b|"
    r"\b(?:de\s+)?quelle\s+(?:est\s+(?:la|ta|cette)\s+)?(?:r[èe]gle|question|salle|[ée]tape)\b|"
    r"\b(?:donne|dis|rappelle|redonne)-moi\s+(?:la\s+r[èe]gle|ta\s+question|les?\s+informations?|"
    r"ce\s+que\s+tu\s+as\s+vu)\b|"
    r"\bj'ai\s+dit\s+[\wÀ-ÿ'-]+\s*,\s*pas\s+[\wÀ-ÿ'-]+\b",
    re.IGNORECASE,
)
_HABIT_KEEP_RE = re.compile(
    r"^\s*(?:(?:ok(?:ay)?|so|yeah|yes|well|alors|bon|uh+|um+|euh+)[\s,]+)*"
    r"(?:we|i|they|people|organisers|organizers|members|on|nous|je|ils|elles)\s+"
    r"(?:always\s+|usually\s+|often\s+|toujours\s+)?"
    r"(?:keep|keeps|remember|note|save|garde|gardons|gardent|retient|retiennent|note|notons)\b",
    re.IGNORECASE,
)
_COMMAND_CUE_RE = re.compile(
    r"\b(?:remember|keep|save|note|capture|record|hold\s+on\s+to|propose|"
    r"retiens|retiennes|retenir|garde|gardes|garder|gardons|garderais|notes?|noter|sauvegard\w*|enregistr\w*|"
    r"examples?|case|instance|illustration|sample|exemples?|cas\b|"
    r"mistakes?|errors?|pitfalls?|traps?|wrong|careful|watch\s+out|"
    r"erreurs?|fautes?|pi[èe]ges?|tromp\w*|"
    r"compar\w*|changed|chang[ée]\w*|diff(?:erence|erent|[ée]rence)|before|earlier|previous|prior|avant|pr[ée]c[ée]dent\w*|"
    r"forget\w*|scratch|undo|drop|discard|delete|remove|never\s+mind|ignore|"
    r"oubli\w*|annul\w*|effac\w*|supprim\w*|laisse\s+tomber|"
    r"did\s+you|do\s+you|can\s+you|could\s+you|have\s+you|would\s+you|give\s+me|tell\s+me|remind\s+me|"
    r"what\s+rule|what\s+is\s+the\s+rule|talk(?:ing)?\s+about|said\s+\w+\s*,\s*not|"
    r"as-tu\s+vu|vois-tu|tu\s+vois|quelle\s+r[èe]gle|donne-moi|rappelle-moi|j'ai\s+dit)\b",
    re.IGNORECASE,
)


def _clean_speech(said: str) -> str:
    """Strip transcribed speech disfluencies ('uh', 'um', '[inhales]', 'on my, on my') for matching."""
    cleaned = _DISFLUENCY_RE.sub(" ", said or "")
    cleaned = re.sub(r"\s*,\s*,+", ", ", cleaned)
    cleaned = re.sub(r"(?:^|(?<=[\s,.?!]))\s*,\s*", " ", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    cleaned = _STUTTER_RE.sub(r"\1", cleaned)
    return re.sub(r"\s{2,}", " ", cleaned).strip()


def _extract_save_what(match: re.Match) -> str:
    raw = (
        match.groupdict().get("what_colon")
        or match.groupdict().get("what_en")
        or match.groupdict().get("what_fr")
        or match.groupdict().get("what_garde")
        or ""
    ).strip(" ,.:;-")
    if not raw or _GENERIC_SAVE_WHAT_RE.match(raw):
        return ""
    return raw


def has_save_cue(said: str) -> bool:
    """True when `said` is an explicit request by the guardian to save ('save this', 'garde ça')."""
    raw = (said or "").strip()
    if not raw:
        return False
    return bool(_SAVE_RE.match(raw) or _SAVE_RE.match(_clean_speech(raw)))


def has_ask_pupil_cue(said: str) -> bool:
    """True when `said` carries a direct question or request addressed to Urithi as the pupil.
    Any question (speech recognition writes its mark) goes to the classifier, which decides:
    measured live, "What was your last question?" matched no listed phrase and went unanswered."""
    raw = said or ""
    if "?" in raw or _ASK_PUPIL_RE.search(raw):
        return True
    return bool(_ASK_PUPIL_RE.search(_clean_speech(raw)))


def has_command_cue(said: str) -> bool:
    """True when `said` contains a word or verb that could be a classroom command or pupil question."""
    raw = said or ""
    if "?" in raw or _COMMAND_CUE_RE.search(raw) or _ASK_PUPIL_RE.search(raw) or _SAVE_RE.match(raw):
        return True
    cleaned = _clean_speech(raw)
    return bool(_COMMAND_CUE_RE.search(cleaned) or _ASK_PUPIL_RE.search(cleaned) or _SAVE_RE.match(cleaned))


def _fallback(said: str) -> Command:
    """Fast local fallback if the model cannot be reached or returns malformed output."""
    text = said.strip()
    if not text:
        return Command(intent="none")
    cleaned = _clean_speech(text)
    m_save = _SAVE_RE.match(text) or _SAVE_RE.match(cleaned)
    if m_save:
        return Command(intent="save", what=_extract_save_what(m_save))
    if _ASK_PUPIL_RE.search(text) or _ASK_PUPIL_RE.search(cleaned):
        return Command(intent="ask_pupil", what=text)
    if _FORGET_RE.search(text) or _FORGET_RE.search(cleaned):
        return Command(intent="forget", what=text)
    if _COMPARE_RE.search(text) or _COMPARE_RE.search(cleaned):
        return Command(intent="compare", what=text)
    m = _EXAMPLE_RE.search(text)
    if m:
        rest = text[m.end():].strip(" ,.:;-")
        return Command(intent="example", what=rest or text)
    m = _MISTAKE_RE.search(text)
    if m:
        rest = text[m.end():].strip(" ,.:;-")
        return Command(intent="mistake", what=rest or text)
    return Command(intent="none")


def _command_model_ready() -> bool:
    return llm.is_configured("main")


def classify_command(said: str, language: str = "en") -> Command:
    """
    Understand whether `said` is a guardian command ("save", "remember", "example", "mistake",
    "compare", "forget", "ask_pupil") or ordinary teaching ("none"), using QUESTION_MODEL
    only when the sentence carries a command cue.
    """
    text = (said or "").strip()
    if not text or not has_command_cue(text):
        return Command(intent="none")
    cleaned = _clean_speech(text)
    # Guard against first-person/plural habit statements ("We keep this channel public...")
    # ever being misread as a command to keep or save.
    if _HABIT_KEEP_RE.match(text) and not any(
        p.search(cleaned) for p in (_SAVE_RE, _FORGET_RE, _COMPARE_RE, _EXAMPLE_RE, _MISTAKE_RE, _ASK_PUPIL_RE)
    ):
        return Command(intent="none")
    if not _command_model_ready():
        return _fallback(text)

    try:
        raw = call_main_model(
            [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": f"Language: {language}\nGuardian said: {text}"},
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
            max_tokens=300,
            model=config.QUESTION_MODEL,
        )
        parsed = jsonish.loads(raw)
        if isinstance(parsed, list):
            parsed = parsed[0] if parsed else {}
        if not isinstance(parsed, dict):
            return _fallback(text)
        intent = str(parsed.get("intent", "none")).strip().lower()
        if intent not in INTENTS:
            return _fallback(text)
        what = str(parsed.get("what", "")).strip()
        m_save = _SAVE_RE.match(text) or _SAVE_RE.match(cleaned)
        if m_save and intent in ("none", "remember", "save"):
            return Command(intent="save", what=_extract_save_what(m_save) or ("" if _GENERIC_SAVE_WHAT_RE.match(what) else what))
        if intent in ("none", "remember") and (_ASK_PUPIL_RE.search(text) or _ASK_PUPIL_RE.search(cleaned)):
            return Command(intent="ask_pupil", what=what or text)
        return Command(intent=intent, what=what)
    except Exception as error:
        logger.warning("Could not classify command %r with model, using fallback: %s", text[:60], error)
        return _fallback(text)


def _not_seen_yet(language: str, detail: str = "") -> str:
    base = "Je n'ai pas encore vu cela" if language == "fr" else "I have not seen that yet"
    return f"{base} : {detail}" if (detail and language == "fr") else (f"{base}: {detail}" if detail else f"{base}.")


def is_save_preview_question(said: str) -> bool:
    cleaned = _clean_speech(said).lower()
    return bool(
        re.search(r"\bwhat\s+(?:would|do|should)\s+you\s+(?:save|propose)\b", cleaned)
        or re.search(r"\b(?:garderais-tu|tu\s+garderais|tu\s+sauvegarderais|proposes-tu|tu\s+proposes)\b", cleaned)
    )


def _contextual_rule_answer(
    lang: str,
    said: str,
    *,
    seen_parts: list[str],
    last_q: str,
    note_texts: list[str],
    rules_parts: list[str],
) -> str:
    french = lang == "fr"
    cleaned = _clean_speech(said).lower()
    m_corr = (
        re.search(r"\bj'ai\s+dit\s+([\wÀ-ÿ'-]+)\s*,\s*pas\s+([\wÀ-ÿ'-]+)\b", cleaned)
        if french
        else re.search(r"\bi\s+said\s+([\w'-]+)\s*,\s*not\s+([\w'-]+)\b", cleaned)
    )
    if rules_parts:
        latest_rule = rules_parts[-1]
        if m_corr:
            w1, w2 = m_corr.group(1), m_corr.group(2)
            return (
                f"Bien compris, tu parlais de {w1} et non de {w2} : la règle notée jusqu'ici est {latest_rule}."
                if french
                else f"Understood, you meant {w1} rather than {w2}: the rule noted so far is {latest_rule}."
            )
        if re.search(r"\b(?:give|tell|remind|donne|dis|rappelle)\b", cleaned):
            return (
                f"Voici la règle que j'ai notée : {latest_rule}."
                if french
                else f"Here is the rule I have noted: {latest_rule}."
            )
        return (
            f"La règle notée jusqu'ici est : {latest_rule}."
            if french
            else f"The rule noted so far is: {latest_rule}."
        )

    latest_note = _short(note_texts[0]) if note_texts else ""
    screen_summary = _short(seen_parts[-1].split(" | ")[0].splitlines()[0], 16).rstrip(".") if seen_parts else ""
    short_q = _short(last_q, 10).rstrip("?") + "?" if last_q else ""
    q_tail_en = f'; I asked: "{short_q}"' + "." if last_q else "."
    q_tail_fr = f" ; j'ai demandé : « {short_q} »." if last_q else "."

    if m_corr:
        w1, w2 = m_corr.group(1), m_corr.group(2)
        if french:
            return f"Bien compris, tu as dit {w1} et non {w2} : je n'ai cité aucune règle jusqu'ici{q_tail_fr}"
        return f"Understood, you said {w1} rather than {w2}: I have not cited any rule yet{q_tail_en}"

    if re.search(r"\b(?:rooms?|salles?)\b", cleaned):
        if french:
            if screen_summary:
                return f"Sur l'écran j'ai vu {screen_summary}, mais je n'ai cité aucune règle sur une salle{q_tail_fr}"
            return f"Je n'ai parlé d'aucune salle ni d'aucune règle jusqu'ici{q_tail_fr}"
        if screen_summary:
            return f"On your screen I saw {screen_summary}, I have not cited any rule about a room{q_tail_en}"
        return f"I have not mentioned a room or a rule yet{q_tail_en}"

    if re.search(r"\b(?:roles?|r[ôo]les?)\b", cleaned):
        if french:
            if latest_note:
                return f"Je n'ai cité aucun rôle ni règle : j'ai seulement noté « {latest_note} »{q_tail_fr}"
            return f"Je n'ai cité aucun rôle d'organisateur ni aucune règle jusqu'ici{q_tail_fr}"
        if latest_note:
            return f'I did not mention an organiser role or rule: I only noted "{latest_note}"{q_tail_en}'
        return f"I have not mentioned an organiser role or rule so far{q_tail_en}"

    if re.search(r"\b(?:need|whole|for\s+organi[sz]ers?|pour\s+l'organisateur)\b", cleaned):
        if french:
            if latest_note:
                return f"Pour l'organisateur, je n'ai encore noté aucune règle{q_tail_fr}"
            return f"Pour l'organisateur, aucune règle n'a encore été formulée dans mes notes{q_tail_fr}"
        if latest_note:
            return f"For the organiser, I have no rule noted yet{q_tail_en}"
        if screen_summary:
            return f"For the organiser, I saw {screen_summary} on screen and have no rule noted yet{q_tail_en}"
        return f"For the organiser, no rule has been stated in my notes yet{q_tail_en}"

    if re.search(r"\b(?:give|tell|remind|donne|dis|rappelle)\b", cleaned):
        if french:
            if screen_summary:
                return f"Je n'ai aucune règle à te donner car aucune n'a été citée ; à l'écran j'ai vu {screen_summary}{q_tail_fr}"
            return f"Je n'ai aucune règle à te donner car aucune règle n'a encore été citée{q_tail_fr}"
        if screen_summary:
            return f"I have no rule to give because I have not cited one yet; on screen I saw {screen_summary}{q_tail_en}"
        return f"I have no rule to give because no rule has been cited yet{q_tail_en}"

    if french:
        detail = (
            f"aucune règle n'est encore notée, et ma dernière question était « {last_q} »."
            if last_q
            else "aucune règle n'est encore notée."
        )
    else:
        detail = (
            f'no rule has been noted so far, and my last question was "{last_q}".'
            if last_q
            else "no rule has been noted so far."
        )
    return _not_seen_yet(lang, detail)


def _norm_answer(text: str) -> str:
    return re.sub(r"[^a-zà-ÿ0-9]+", " ", (text or "").lower()).strip()


def _is_near_duplicate_answer(
    candidate: str,
    cleaned_said: str,
    previous_qa: list[tuple[str, str]] | tuple[tuple[str, str], ...],
) -> bool:
    cand_norm = _norm_answer(candidate)
    cand_tokens = [w for w in cand_norm.split() if len(w) >= 3]
    if not cand_norm:
        return False
    for pq, pa in previous_qa or ():
        if _clean_speech(pq).lower() == cleaned_said:
            continue
        prev_norm = _norm_answer(pa)
        if not prev_norm:
            continue
        if cand_norm == prev_norm:
            return True
        prev_set = {w for w in prev_norm.split() if len(w) >= 3}
        if cand_tokens and prev_set:
            overlap = sum(1 for w in cand_tokens if w in prev_set) / len(cand_tokens)
            if overlap >= 0.85:
                return True
    return False


def _ensure_distinct_answer(
    ans: str,
    said: str,
    lang: str,
    previous_qa: list[tuple[str, str]] | tuple[tuple[str, str], ...],
) -> str:
    cleaned_said = _clean_speech(said).lower()
    used = {
        pa.strip().lower()
        for pq, pa in (previous_qa or ())
        if _clean_speech(pq).lower() != cleaned_said and str(pa or "").strip()
    } | {
        ans.strip().lower()
        for _ in (1,)
        if _is_near_duplicate_answer(ans, cleaned_said, previous_qa)
    }
    if ans.strip().lower() not in used:
        return ans
    topic = _short(said, 6).strip(" ?.!,;:")
    if lang == "fr":
        return f"Sur « {topic} » : {ans[0].lower() + ans[1:] if len(ans) > 1 else ans}"
    return f'About "{topic}": {ans[0].lower() + ans[1:] if len(ans) > 1 else ans}'


def answer_pupil_question(
    work_map,
    said: str,
    *,
    observations: list | tuple = (),
    kept_screens: list | tuple = (),
    last_question: str = "",
    notes: list | tuple = (),
    noted_rules: list | tuple = (),
    proposals: list | tuple = (),
    previous_qa: list[tuple[str, str]] | tuple[tuple[str, str], ...] = (),
) -> str:
    """
    Answer a guardian's question addressed to Urithi in 1 or 2 sentences, strictly from what
    Urithi has: what it saw on screen, its last question, its notes/proposals, and what is saved.
    Never invents anything, and says 'I have not seen that yet' when it does not know.
    """
    lang = getattr(work_map, "language", "en") or "en"
    french = lang == "fr"
    seen_parts: list[str] = []
    for obs in observations[-4:]:
        parts = [
            str(getattr(obs, "changed", "") or "").strip(),
            str(getattr(obs, "scene", "") or "").strip(),
            ", ".join(str(f).strip() for f in (getattr(obs, "screen_fields", ()) or ()) if str(f).strip()),
        ]
        line = " | ".join(p for p in parts if p)
        if line and line not in seen_parts:
            seen_parts.append(line)
    for desc in kept_screens[-2:]:
        text_d = str(desc or "").strip()
        if text_d and text_d not in seen_parts:
            seen_parts.append(text_d[:500])

    last_q = (last_question or "").strip()
    steps = list(getattr(work_map, "steps", ()) or ())
    rules = list(getattr(work_map, "guardrails", ()) or ())
    steps_parts = [f"Step {s.number} ({s.title}): {s.reason}" for s in steps[-6:]]
    note_texts: list[str] = []
    for n in notes[:6]:
        text_n = str(n.get("text") if isinstance(n, dict) else n).strip()
        if text_n:
            note_texts.append(text_n)
            if all(text_n not in sp for sp in steps_parts):
                steps_parts.append(f"Noted: {text_n}")
    proposal_parts: list[str] = []
    for p in proposals[:3]:
        if not isinstance(p, dict):
            continue
        if p.get("kind") == "rule" and p.get("when") and p.get("then"):
            quote_p = str(p.get("quote") or p.get("reason") or "").strip()
            line_p = (
                f"Règle (quand {p['when']}, {p['then']}) : {quote_p}"
                if french
                else f"Rule (when {p['when']}, {p['then']}): {quote_p}"
            )
            if line_p not in proposal_parts:
                proposal_parts.append(line_p)
        elif p.get("reason"):
            line_p = f"{p.get('title', 'Proposal')}: {p['reason']}"
            if line_p not in proposal_parts:
                proposal_parts.append(line_p)
            if all(p["reason"] not in sp for sp in steps_parts):
                steps_parts.append(f"Proposed ({p.get('title', 'Step')}): {p['reason']}")

    rules_parts = [f"when {g.when}, {g.then}" for g in rules[-6:]]
    for nr in noted_rules[-6:]:
        if isinstance(nr, dict) and nr.get("when") and nr.get("then"):
            line_r = f"when {nr['when']}, {nr['then']}"
        else:
            line_r = str(nr).strip()
        if line_r and line_r not in rules_parts:
            rules_parts.append(line_r)

    cleaned = _clean_speech(said).lower()
    asks_save = is_save_preview_question(said)
    asks_rule = bool(
        re.search(r"\b(?:rules?|roles?|rooms?|whole|r[èe]gles?)\b", cleaned)
        or re.search(r"\bsaid\s+rule\b|\bdit\s+r[èe]gle\b", cleaned)
    )
    asks_screen = bool(re.search(r"\b(?:screen|deck|desk|[ée]cran)\b", cleaned)) and not asks_rule
    asks_question = bool(re.search(r"\b(?:question|ask(?:ed)?|demand[ée])\b", cleaned))

    if asks_save:
        # Named, not read whole: the rule as "when ..., ...", a step by its title (measured live:
        # the reply read each proposal and its quote back, past a minute of speech).
        named = []
        for p in proposals[:3]:
            if not isinstance(p, dict):
                continue
            if p.get("kind") == "rule" and p.get("when") and p.get("then"):
                named.append(_short(f"{'la règle : quand' if french else 'the rule: when'} {p['when']}, {p['then']}", 16))
            elif p.get("title"):
                named.append(_short(f"{'l’étape' if french else 'the step'} {p['title']}", 12))
        if named:
            joined = " ; ".join(named)
            return (
                f"Je proposerais de sauvegarder : {joined}."
                if french
                else f"I would save: {joined}."
            )
        return _not_seen_yet(lang)

    if not seen_parts and not last_q and not steps_parts and not rules_parts and not proposal_parts:
        if asks_rule:
            return _ensure_distinct_answer(
                _contextual_rule_answer(
                    lang,
                    said,
                    seen_parts=seen_parts,
                    last_q=last_q,
                    note_texts=note_texts,
                    rules_parts=rules_parts,
                ),
                said,
                lang,
                previous_qa,
            )
        return _not_seen_yet(lang)
    if asks_screen and not seen_parts:
        return _not_seen_yet(lang)

    fallback_ans = ""
    if asks_rule:
        fallback_ans = _contextual_rule_answer(
            lang,
            said,
            seen_parts=seen_parts,
            last_q=last_q,
            note_texts=note_texts,
            rules_parts=rules_parts,
        )

    if _command_model_ready():
        prev_lines = "\n".join(
            f'- Q: "{pq}" -> A: "{pa}"' for pq, pa in list(previous_qa or ())[-6:]
        ) or "none"
        user_prompt = (
            f"Language: {lang}\n"
            f"What you saw on the screen: {' ; '.join(seen_parts) or 'none'}\n"
            f"Your last question: {last_q or 'none'}\n"
            f"Steps and notes: {' ; '.join(steps_parts) or 'none'}\n"
            f"Rules already noted or saved: {' ; '.join(rules_parts) or 'none'}\n"
            f"Proposal waiting to be saved: {' ; '.join(proposal_parts) or 'none'}\n"
            f"Previous answers already given (do not repeat any of these verbatim):\n{prev_lines}\n"
            f"Guardian asked: {said}\n"
        )
        try:
            reply = call_main_model(
                [
                    {
                        "role": "system",
                        "content": PUPIL_ANSWER_SYSTEM
                        + ("\n- Answer in French, using tu." if french else "\n- Answer in English."),
                    },
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.0,
                max_tokens=80,
                model=config.QUESTION_MODEL,
            )
            text = (reply or "").strip().strip('"').strip()
            if text:
                sentences = [s.strip() for s in re.split(r"(?<=[.?!])\s+", text) if s.strip()]
                candidate = _spoken_length(sentences[0]) if sentences else ""
                valid_no_rule = True
                if asks_rule and not rules_parts:
                    has_no_rule_ack = bool(
                        re.search(
                            r"\b(?:no\s+(?:rules?|organi[sz]er\s+roles?)|"
                            r"not\s+(?:[\w\s]{0,20}\b)?(?:rules?|roles?|cited|noted|mentioned|seen|stated|talked\s+about)|"
                            r"haven't\s+(?:[\w\s]{0,20}\b)?(?:rules?|roles?|cited|noted|mentioned|seen|stated)|"
                            r"aucune\s+r[èe]gle|pas\s+(?:[\wÀ-ÿ\s]{0,20}\b)?(?:r[èe]gles?|cit[ée]|not[ée]|mentionn[ée]|vu))\b",
                            candidate,
                            re.IGNORECASE,
                        )
                    ) and not candidate.lower().startswith("i have not seen that yet.")
                    # A short answer that says no rule was noted is kept. Recalling the question is
                    # asked for in the prompt; refusing an answer without it sent replies to the long
                    # fallbacks and past 3 s (measured live).
                    valid_no_rule = has_no_rule_ack
                if (
                    candidate
                    and valid_no_rule
                    and not _is_near_duplicate_answer(candidate, cleaned, previous_qa)
                ):
                    return _ensure_distinct_answer(candidate, said, lang, previous_qa)
        except Exception as error:
            logger.warning("Could not word pupil answer with model, using fallback: %s", error)

    if fallback_ans:
        return _ensure_distinct_answer(fallback_ans, said, lang, previous_qa)
    if asks_question and last_q:
        return _ensure_distinct_answer(
            f"Ma dernière question était : {last_q}" if french else f"My last question was: {last_q}",
            said,
            lang,
            previous_qa,
        )
    if seen_parts:
        summary = _short(seen_parts[-1].split(" | ")[0].splitlines()[0], 20).rstrip(".")
        ans = f"À l'écran, j'ai vu : {summary}." if french else f"On your screen I saw {summary}."
        return _ensure_distinct_answer(ans, said, lang, previous_qa)
    if rules_parts:
        return _ensure_distinct_answer(
            f"La règle notée jusqu'ici est : {rules_parts[-1]}."
            if french
            else f"The rule noted so far is: {rules_parts[-1]}.",
            said,
            lang,
            previous_qa,
        )
    if steps_parts:
        return _ensure_distinct_answer(
            f"La dernière chose que j'ai notée : {_short(steps_parts[-1], 12)}."
            if french
            else f"The last thing I noted: {_short(steps_parts[-1], 12)}.",
            said,
            lang,
            previous_qa,
        )
    if last_q:
        return _ensure_distinct_answer(
            f"Ma dernière question était : {last_q}" if french else f"My last question was: {last_q}",
            said,
            lang,
            previous_qa,
        )
    return _not_seen_yet(lang)



def crop_region(raw: bytes, region: dict | None) -> bytes:
    """Crop a frame to the normalized rectangle {x, y, w, h} (0..1) pointed at by the guardian."""
    if not region or not isinstance(region, dict):
        return raw
    try:
        import io
        from PIL import Image

        x = max(0.0, min(0.95, float(region.get("x", 0.0))))
        y = max(0.0, min(0.95, float(region.get("y", 0.0))))
        w = max(0.05, min(1.0 - x, float(region.get("w", 1.0))))
        h = max(0.05, min(1.0 - y, float(region.get("h", 1.0))))
        with Image.open(io.BytesIO(raw)) as img:
            img = img.convert("RGB")
            width, height = img.size
            box = (
                int(round(x * width)),
                int(round(y * height)),
                max(int(round(x * width)) + 1, int(round((x + w) * width))),
                max(int(round(y * height)) + 1, int(round((y + h) * height))),
            )
            cropped = img.crop(box)
            out = io.BytesIO()
            cropped.save(out, format="JPEG", quality=85)
            return out.getvalue()
    except Exception as error:
        logger.warning("Could not crop pointed region: %s", error)
        return raw


def compare_frames(before: bytes | None, now: bytes, *, focus: str = "") -> str:
    """Compare the current screen against the earlier one using CLASS_VISION_MODEL."""
    from guardian.engine import vision

    return vision.compare_frames(before, now, focus=focus)

