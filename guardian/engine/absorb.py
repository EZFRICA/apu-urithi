"""Turning what the expert said into something a tutor can check.

The expert answers out loud, in their own words: "Equipment over five thousand euros is
always capex, and if I do not recognise the supplier I stop and ask the controller." Two
different things are in that sentence. The first is a reason, and it is kept **verbatim**,
because a reason rewritten by a model is no longer the expert's and a new hire can hear the
difference. The second is a limit, and it has to become a condition and an action, or the
tutor can only recite it rather than catch a breach before a save.

So the model does exactly one job here: find the limits and split each into "when" and
"then". It never touches the reason. Whatever it extracts carries the sentence it came
from, so every rail the tutor enforces can be traced back to a person who said it.
"""

import re
import unicodedata
import uuid

from apu.inference.llm import call_extraction_model, call_main_model
from apu.logger import get_logger
from guardian.engine import jsonish
from guardian.engine.workmap import Guardrail, WorkMapError

logger = get_logger(__name__)

# Measured: defined as "the cases where they stop, escalate, or do something different",
# the extractor dropped "equipment over five thousand euros is always capex" in eight runs
# out of eight. A classification threshold is not a stop, so by that definition it was not
# a limit. It is the most valuable kind of rule there is, because it has a number that can
# be checked, tested at its boundary and looked up against the law. So every conditional
# rule is asked for, and each one separately.
EXTRACT_SYSTEM = (
    "You read one thing an expert said while explaining their work, and you list EVERY "
    "conditional rule in it, each as its own entry. A conditional rule is anything of the "
    "form 'when X, do Y': a threshold that decides a classification, a category that "
    "changes the treatment, a case where they stop, check or ask someone.\n"
    "Return JSON only: {\"guardrails\": [{\"when\": \"...\", \"then\": \"...\", "
    "\"severity\": \"stop\" or \"check\"}]}\n"
    "- One sentence can hold several rules. 'Over five thousand is capex, and an unknown "
    "supplier means I ask the controller' is two entries.\n"
    "- \"when\" is the condition, stated about the case and not about the speaker: "
    "\"the supplier is not recognised\", not \"I do not recognise the supplier\". A new "
    "hire will read it as a condition they check, and \"I\" would mean them. Keep any "
    "number exactly as said.\n"
    "- \"then\" is what to do, as an instruction that starts with a verb: \"treat it as "
    "capex\", \"stop and ask the controller\", never \"it is capex\". It is read back as "
    "\"you treat it as capex\" and \"do you treat it as capex?\".\n"
    "- \"stop\": never proceed without a person. \"check\": a rule to apply, or to proceed "
    "with care. A classification rule is \"check\".\n"
    "- A habit with no condition, something they do every time ('I announce every meetup "
    "two weeks ahead'), is a step, not a rule: leave it out.\n"
    "- A principle that names no case and no action ('the sound decides between a and an') "
    "is not a rule either. List only rules stated in this one thing they said, never rules "
    "you expect them to state next.\n"
    "- Rules already noted from what they said earlier are given to you: do not list one "
    "again, even in other words.\n"
    "- If they stated no rule at all, return an empty list. Do NOT invent one: a rule "
    "nobody stated will stop a new hire for a reason no one can explain.\n"
    "- Keep the whole instruction: what is forbidden or excepted ('never in #announcements', "
    "'only on Fridays', 'unless the controller agrees') belongs in \"then\" or \"when\"."
)


# A French guardian's rule is kept in French. "then" is read back after "tu" ("quand moins
# de dix personnes sont inscrites, tu déplaces le meetup"), so it is conjugated for it.
# Measured on a first French conversation: "j'annonce chaque meetup deux semaines avant" came
# back as a rule, "when j'annonce chaque meetup, then l'annonces deux semaines avant": a habit
# made into a condition, about the speaker. The same two rules as in English, said in French.
EXTRACT_FRENCH = (
    "\nThe expert spoke French. Write \"when\" and \"then\" in French, as they said them. "
    "\"then\" is conjugated for \"tu\", without the pronoun, so it reads after it: "
    "\"déplaces le meetup\", \"demandes au contrôleur\", never \"déplacer le meetup\". "
    "\"when\" is about the case, never about the speaker: \"le fournisseur n'est pas reconnu\", "
    "never \"je ne reconnais pas le fournisseur\". A habit with no condition (\"j'annonce chaque "
    "meetup deux semaines avant\") is not a rule: leave it out."
)


def find_guardrails(said: str, at: float, language: str = "en",
                    known: list[Guardrail] | tuple = ()) -> list[Guardrail]:
    """
    The limits inside one spoken answer. An empty list is a normal, common answer.

    Failure is empty, not an exception: a sentence the extractor could not parse must not
    lose the step it belongs to, and a missing rail is visible later as "no limit stated"
    rather than silently becoming a rail that was never said.
    """
    if not said.strip():
        return []
    try:
        raw = call_extraction_model([
            {"role": "system", "content": EXTRACT_SYSTEM + (EXTRACT_FRENCH if language == "fr" else "")},
            {"role": "user", "content": _with_known(said, known)},
        ], temperature=0.0, response_format={"type": "json_object"}, max_tokens=400)
        # Asked for an object, models return a bare list, or a fenced one, often enough
        # that refusing either would throw away rails the expert really stated.
        found = jsonish.as_list(jsonish.loads(raw), "guardrails")
    except Exception as error:
        logger.warning("Could not read limits out of %r: %s", said[:60], error)
        return []

    rails = []
    for item in found:
        when, then = _whole_rule(said, _clause(item.get("when", "")), _clause(item.get("then", "")))
        # Two readings that fall back on the same sentence of theirs are that sentence once, one rule said
        # once. Measured live on 2026-10-16: "Before watering, we push a finger into the soil, so we only
        # water the beds that are really dry" became two rules in 3 runs of 5, the whole sentence under two
        # invented conditions ("really dry", "not really dry"), and "save this" asked which.
        if any(r.then.lower() == then.lower() for r in rails):
            continue
        try:
            rails.append(Guardrail(
                guardrail_id=str(uuid.uuid4()),
                when=when,
                then=then,
                # The sentence the expert actually said, not the model's summary of it.
                quote=said.strip(),
                asked_at=at,
                severity="stop" if item.get("severity") != "check" else "check",
            ))
        except WorkMapError as error:
            logger.info("Skipping a half-formed limit: %s", error)
    return rails


# What a rule cannot lose and still be the guardian's: a prohibition, an exception, a limit word,
# a number, a channel or a name. Measured live: "we announce in #members only, never in
# #announcements" came back as "announce in #members only", the prohibition gone.
_KEEP_RE = re.compile(
    r"#[\w-]+|@\w+|\b\d+(?:[.,]\d+)?\b|\b(?:never|not|no|only|except|unless|without|"
    r"jamais|pas|sauf|seulement|uniquement|sans|aucune?)\b",
    re.IGNORECASE,
)
_CONDITION_RE = re.compile(
    r"^\s*(?:if|when|whenever|si|quand|lorsque|lorsqu')\s*(.+?),\s*(.+?)\s*[.!]?\s*$",
    re.IGNORECASE | re.DOTALL,
)
_SUBJECT_RE = re.compile(r"^(?:we|i|you|they|on|nous|je|tu|vous)\s+", re.IGNORECASE)


def _keep_words(text: str) -> set[str]:
    return {m.lower() for m in _KEEP_RE.findall(text or "")}


def _whole_rule(said: str, when: str, then: str) -> tuple[str, str]:
    """
    The rule as the model read it, unless it dropped what the guardian said must not be lost;
    then the guardian's own sentence, split at its condition, is the rule. The sentence it came
    from is the one that shares most words with what the model read.
    """
    sentences = [x.strip() for x in re.split(r"(?<=[.!?])\s+", said.strip()) if x.strip()] or [said.strip()]
    read = f"{when} {then}".lower()
    source = max(sentences, key=lambda x: sum(w in read for w in x.lower().split()))
    if not (_keep_words(source) - _keep_words(read)):
        return when, then
    found = _CONDITION_RE.match(source)
    if found:
        return _clause(found.group(1)), _clause(_SUBJECT_RE.sub("", found.group(2).strip()))
    return when, _clause(source)


def _with_known(said: str, known) -> str:
    """
    What they said, with the rules already noted. Measured on a first conversation about "a"
    and "an": "the sound decides between a and an" came back as two rules nobody had stated,
    and the next two sentences, which did state them, added them again: nine rules for seven.
    """
    if not known:
        return said
    noted = "\n".join(f"- when {g.when}, {g.then}" for g in known)
    return f"Rules already noted, not to list again:\n{noted}\n\nWhat they said now:\n{said}"


def _clause(text) -> str:
    """
    A clause that goes inside a sentence, so it starts lower case: "you treat it as capex",
    not "you Treat it as capex". An acronym ("VAT is due") keeps its capitals.
    """
    text = str(text or "").strip().rstrip(".")
    if text.startswith("I ") or text == "I":
        return text   # the pronoun: "when i do not recognise" is what lowering it produced
    if len(text) > 1 and text[0].isupper() and not text[1].isupper():
        text = text[0].lower() + text[1:]
    return text


def title_for(observed: str, decision: str, limit: int = 60) -> str:
    """
    A short name for a step. Cheap and local: a model call per step is not worth it.

    Cut at a word, never inside one: measured, "I stop and chec..." was the headline a
    learner read. A step taught in conversation is given a longer limit (routes.tell), since
    its first sentence is the step itself.
    """
    text = (decision or observed or "Step").strip()
    # The first sentence: cut where a full stop is followed by a capital, which is where
    # the next sentence starts. "Novak Precision s.r.o. not found" is one sentence, and
    # cutting at its first dot left "Novak Precision s" as a step title.
    sentences = [s.strip() for s in re.split(r"\.(?=\s+[A-Z]|$)", text) if s.strip()]
    # A lead-in is not the step. Measured: "One more thing. When a word starts with a u that
    # sounds like you, I write a" became a step called "One more thing". A short sentence
    # before a much longer one is a lead-in; two short ones ("cost center changed. Then the
    # account") are both the step, and the first names it.
    while (len(sentences) > 1 and len(sentences[0].split()) < 4
           and len(sentences[1].split()) >= 2 * len(sentences[0].split())):
        sentences.pop(0)
    first = sentences[0] if sentences else ""
    if len(first) <= limit + 3:
        return first or "Step"
    return first[:limit].rsplit(" ", 1)[0].rstrip(",;:") + "..."


_LIST_BULLET_RE = re.compile(r"(?:^|\n)\s*\d+\.\s+")
_NUMBER_RE = re.compile(r"\b\d+(?:[.,]\d+)?\b")
_WORD_RE = re.compile(r"[^\s,;:.?!()\[\]\"']+")


def numbers_in(text: str) -> set[str]:
    """Numbers stated in a text, normalised so '2,4' and '2.4' match while '24' does not."""
    cleaned = _LIST_BULLET_RE.sub(" ", text or "")
    return {m.replace(",", ".") for m in _NUMBER_RE.findall(cleaned)}


def _is_foreign_script_word(word: str, language: str = "en") -> bool:
    """True when a word contains letters outside the alphabet of the knowledge (Latin for en/fr)."""
    if language not in ("en", "fr"):
        return False
    for ch in word:
        if unicodedata.category(ch).startswith("L") and "LATIN" not in unicodedata.name(ch, ""):
            return True
    return False


def foreign_script_words(text: str, language: str = "en") -> list[str]:
    """Words in `text` written in another alphabet than the knowledge's (e.g. '벤트' in '2.벤트 bypass')."""
    out: list[str] = []
    for raw_token in _WORD_RE.findall(text or ""):
        if _is_foreign_script_word(raw_token, language) and raw_token not in out:
            out.append(raw_token)
    return out


def strip_unconfirmed_camera_script(
    camera_text: str, said: str, language: str = "en"
) -> tuple[str, list[str]]:
    """
    A word read by the camera in another alphabet than the knowledge's (measured live: '2. Vent
    bypass' read as '2.벤트 bypass') never enters a step without the guardian confirming it in
    their own words.
    """
    spoken_foreign = set(foreign_script_words(said, language))
    unconfirmed = [w for w in foreign_script_words(camera_text, language) if w not in spoken_foreign]
    if not unconfirmed:
        return camera_text, []
    cleaned = camera_text
    for word in unconfirmed:
        cleaned = cleaned.replace(word, " ")
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return cleaned, unconfirmed


def confirm_camera_rails(
    rails: list[Guardrail], said: str, camera_text: str = "", language: str = "en"
) -> tuple[list[Guardrail], list[str]]:
    """
    A value or foreign-script word read by the camera never enters a rule unless the guardian
    confirmed it in their own words. Measured live: '2.4 bar max' on a whiteboard was read as
    '24 bar max' by the camera, and '2. Vent bypass' was read as '2.벤트 bypass'.
    """
    spoken_numbers = numbers_in(said)
    spoken_foreign = set(foreign_script_words(said, language))
    confirmed: list[Guardrail] = []
    unconfirmed: list[str] = []
    for rail in rails:
        clause_text = f"{rail.when} {rail.then}"
        rail_numbers = numbers_in(clause_text)
        missing_numbers = sorted(rail_numbers - spoken_numbers)
        missing_foreign = [
            w for w in foreign_script_words(clause_text, language) if w not in spoken_foreign
        ]
        missing = missing_foreign + missing_numbers
        if missing:
            for token in missing:
                if token not in unconfirmed:
                    unconfirmed.append(token)
            continue
        confirmed.append(rail)
    for word in foreign_script_words(camera_text, language):
        if word not in spoken_foreign and word not in unconfirmed:
            unconfirmed.append(word)
    for num in sorted(numbers_in(camera_text) - spoken_numbers):
        if num not in unconfirmed:
            unconfirmed.append(num)
    return confirmed, unconfirmed


_DISFLUENCY_RE = re.compile(
    r"\[[^\]]*\]|\b(?:uh+|um+|mm+|hmm+|er+|ah+|euh+|hum+|ben|bah)\b",
    re.IGNORECASE,
)
_STUTTER_RE = re.compile(r"\b(\w+)(?:\s*,\s*|\s+)\1\b", re.IGNORECASE)
_OPENER_RE = re.compile(
    r"^(?:(?:hello|hi|hey|bonjour|salut|so|well|okay|ok|yeah|yes|alors|bon|like|you\s+know)[\s,.!:;-]+)+",
    re.IGNORECASE,
)
_DANGLING_END_RE = re.compile(
    r"\b(?:to|and|or|but|because|that|which|who|when|if|about|for|with|in|on|at|of|by|from|as|are|is|"
    r"de|[àa]|pour|avec|que|qui|quand|si|par|dans|sur|en)\s*$",
    re.IGNORECASE,
)

PROPOSAL_JUDGE_SYSTEM = (
    "You are Urithi, reviewing the notes taken while a guardian teaches a task.\n"
    "From the unsaved notes and extracted rules below, propose AT MOST what forms real "
    "knowledge to save:\n"
    "- At most ONE step (`step_note_id`: the `note_id` of the single note that states "
    "a concrete step and its reason, or names the specific operational fields/items to "
    'keep or check for the task, or "" if the notes only state general intentions to share, '
    "meta-commentary about what kind of information is needed in general, greetings, or "
    "hesitations).\n"
    '- At most ONE rule (`rule_id`: the `guardrail_id` of the rule to propose, or "" if no '
    "conditional rule was stated).\n"
    "- Never invent or paraphrase the guardian's words: pick the note by its `note_id` "
    "so the guardian's own words are kept verbatim.\n"
    "- A note that only states a conditional rule ('if/when X, do Y') is proposed as a rule, "
    "not as `step_note_id`.\n"
    'Return JSON only: {"step_note_id": "...", "rule_id": "..."}'
)


def _clean_note_text(said: str) -> str:
    cleaned = _DISFLUENCY_RE.sub(" ", said or "")
    cleaned = re.sub(r"\s*,\s*,+", ", ", cleaned)
    cleaned = re.sub(r"(?:^|(?<=[\s,.?!]))\s*,\s*", " ", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    cleaned = _STUTTER_RE.sub(r"\1", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" ,.:;!?-")
    cleaned = _OPENER_RE.sub("", cleaned).strip(" ,.:;!?-")
    return cleaned


def is_teaching_note(said: str, *, has_rules: bool = False) -> bool:
    """True when a spoken note is a complete sentence rather than a greeting, hesitation,
    unfinished fragment, or standalone conditional rule."""
    if has_rules:
        return False
    cleaned = _clean_note_text(said)
    if not cleaned:
        return False
    words = [w for w in re.findall(r"[A-Za-zÀ-ÿ0-9']+", cleaned) if len(w) >= 2]
    if len(words) < 4:
        return False
    if _DANGLING_END_RE.search(cleaned):
        return False
    return True


def _proposal_model_ready() -> bool:
    from apu.inference import llm

    return llm.is_configured("main")


def _build_step_proposal(note: dict, step_number: int) -> dict:
    reason = str(note.get("text") or "").strip()
    title = str(note.get("title") or "").strip() or title_for(reason, "", limit=140)
    observed = str(note.get("observed") or "").strip() or title
    decision = str(note.get("decision") or "").strip() or observed
    pid = str(note.get("note_id") or uuid.uuid4().hex[:10])
    rules_list = list(note.get("rules") or ())
    return {
        "proposal_id": pid,
        "kind": "step",
        "origin": str(note.get("kind") or "tell"),
        "number": step_number,
        "title": title,
        "reason": reason,
        "observed": observed,
        "decision": decision,
        "at": float(note.get("at", 0.0)),
        "said_at": str(note.get("said_at") or ""),
        "rules": rules_list,
        "guardrails": rules_list,
        "cites": list(note.get("cites") or ()),
    }


def _build_rule_proposal(rule: dict, all_rules: list[dict], language: str = "en") -> dict:
    from guardian.engine import wording

    gid = str(rule.get("guardrail_id") or uuid.uuid4().hex[:10])
    when = str(rule.get("when") or "").strip()
    then = str(rule.get("then") or "").strip()
    quote = str(rule.get("quote") or "").strip()
    severity = str(rule.get("severity") or "check")
    title = wording.say(language, "rule_text", when=when, then=then)
    return {
        "proposal_id": f"rule-{gid[:10]}",
        "kind": "rule",
        "origin": "rule",
        "guardrail_id": gid,
        "when": when,
        "then": then,
        "severity": severity,
        "quote": quote,
        "title": title,
        "reason": quote,
        "observed": str(rule.get("observed") or title),
        "decision": str(rule.get("decision") or title),
        "at": float(rule.get("at", 0.0)),
        "said_at": str(rule["step_said_at"] if "step_said_at" in rule else rule.get("said_at") or ""),
        "rules": [rule],
        "guardrails": [rule],
        "cites": list(rule.get("cites") or ()),
    }


def _fallback_proposals(
    work_map,
    candidate_notes: list[dict],
    unsaved_rules: list[dict],
) -> list[dict]:
    lang = getattr(work_map, "language", "en") or "en"
    step_num = len(getattr(work_map, "steps", ()) or ()) + 1
    out: list[dict] = []
    if candidate_notes:
        out.append(_build_step_proposal(candidate_notes[-1], step_num))
    if unsaved_rules:
        out.append(_build_rule_proposal(unsaved_rules[-1], unsaved_rules, language=lang))
    return out


_NO_CHOICE = {"none", "null", "nil", "n/a", "na", "no", "-", "aucun", "aucune", "rien"}


def judge_proposals(
    work_map,
    notes: list[dict] | tuple[dict, ...],
    noted_rules: list[dict] | tuple[dict, ...] = (),
    *,
    use_model: bool = True,
) -> list[dict]:
    """
    Decision 0016: re-read the guardian's notes and propose at most what forms knowledge:
    a step with its reason, or a rule (when / then), in the guardian's own words.
    Replaces previous proposals instead of piling them up; a note that adds nothing remains a note.
    Uses one call to QUESTION_MODEL with a deterministic fallback.
    """
    from apu import config

    lang = getattr(work_map, "language", "en") or "en"
    saved_reasons = {
        s.reason.strip() for s in (getattr(work_map, "steps", ()) or ()) if s.reason.strip()
    } | {
        g.quote.strip() for g in (getattr(work_map, "guardrails", ()) or ()) if g.quote.strip()
    }
    saved_rule_ids = {g.guardrail_id for g in (getattr(work_map, "guardrails", ()) or ())}
    saved_rule_clauses = {
        (g.when.strip().lower(), g.then.strip().lower())
        for g in (getattr(work_map, "guardrails", ()) or ())
    }

    # `memory.of_kind("recent", "note-")` is newest-first; restore chronological order.
    ordered_notes = [
        n
        for n in reversed(list(notes))
        if isinstance(n, dict)
        and str(n.get("text") or "").strip()
        and str(n.get("text") or "").strip() not in saved_reasons
    ]
    unsaved_rules: list[dict] = []
    seen_rule_clauses = set(saved_rule_clauses)
    raw_rules = [
        *(r for n in ordered_notes for r in (n.get("rules") or ()) if isinstance(r, dict)),
        *(r for r in reversed(list(noted_rules)) if isinstance(r, dict)),
    ]
    for r in raw_rules:
        gid = str(r.get("guardrail_id") or "")
        when = str(r.get("when") or "").strip()
        then = str(r.get("then") or "").strip()
        if not when or not then or gid in saved_rule_ids:
            continue
        key = (when.lower(), then.lower())
        if key in seen_rule_clauses:
            continue
        seen_rule_clauses.add(key)
        unsaved_rules.append(r)

    candidate_notes = [
        n
        for n in ordered_notes
        if is_teaching_note(str(n.get("text") or ""), has_rules=bool(n.get("rules")))
    ]
    if not candidate_notes and not unsaved_rules:
        return []

    if use_model and _proposal_model_ready():
        notes_lines = "\n".join(
            f"- note_id={n.get('note_id')}: {n.get('text')}" for n in ordered_notes[-8:]
        ) or "none"
        rules_lines = "\n".join(
            f"- guardrail_id={r.get('guardrail_id')}: when {r.get('when')} -> {r.get('then')} (quote: {r.get('quote')})"
            for r in unsaved_rules[-6:]
        ) or "none"
        try:
            raw = call_main_model(
                [
                    {"role": "system", "content": PROPOSAL_JUDGE_SYSTEM},
                    {
                        "role": "user",
                        "content": (
                            f"Task: {getattr(work_map, 'task', '')}\n"
                            f"Language: {lang}\n"
                            f"Unsaved notes:\n{notes_lines}\n"
                            f"Unsaved rules:\n{rules_lines}\n"
                        ),
                    },
                ],
                temperature=0.0,
                response_format={"type": "json_object"},
                max_tokens=400,
                model=config.QUESTION_MODEL,
            )
            parsed = jsonish.loads(raw)
            if isinstance(parsed, dict):
                chosen_id = str(parsed.get("step_note_id") or "").strip()
                # "none", "null" and the like say no step, as "" does. Found in the review of
                # 2026-10-14: read as an id, "none" proposed the latest note anyway.
                if chosen_id.lower() in _NO_CHOICE:
                    chosen_id = ""
                by_id = {str(n.get("note_id") or ""): n for n in candidate_notes}
                chosen_note = (
                    (by_id.get(chosen_id) or (candidate_notes[-1] if candidate_notes else None))
                    if chosen_id
                    else None
                )
                step_num = len(getattr(work_map, "steps", ()) or ()) + 1
                out: list[dict] = []
                if chosen_note is not None:
                    out.append(_build_step_proposal(chosen_note, step_num))
                if unsaved_rules:
                    rule_id = str(parsed.get("rule_id") or "").strip()
                    rules_by_id = {str(r.get("guardrail_id") or ""): r for r in unsaved_rules}
                    chosen_rule = rules_by_id.get(rule_id) or unsaved_rules[-1]
                    out.append(_build_rule_proposal(chosen_rule, unsaved_rules, language=lang))
                return out
        except Exception as error:
            logger.warning("Could not judge proposals with model, using fallback: %s", error)

    return _fallback_proposals(work_map, candidate_notes, unsaved_rules)


