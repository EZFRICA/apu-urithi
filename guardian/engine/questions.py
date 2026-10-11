"""When the apprentice speaks, and what it asks.

Two questions decide whether a voice agent is an apprentice or an interruption: how does it
know the expert has paused, and how does it pick a question that reveals a reason rather
than one the screen already answers.

Neither is left to a model here.

**When** is arithmetic on activity. The expert is typing, reading or talking; a pause is a
measured gap in all three, long enough that a question lands between thoughts instead of
across one. A model asked "is this a good moment" would guess, and guess differently each
time.

**What** is a ledger of what the apprentice does not know yet. Every question kind has a
precondition over the gaps in the Work Map, so the apprentice can always say why it asked
that and not something else. The model is used for one narrow job: wording the chosen kind
against what is actually on screen. It never chooses the kind, so it cannot invent a
curiosity it does not have.
"""

from dataclasses import dataclass, replace
from enum import StrEnum
import re

from apu import config
from apu.inference import llm
from apu.inference.llm import call_main_model
from apu.logger import get_logger
from guardian.engine.workmap import Step, WorkMap

logger = get_logger(__name__)

# A pause worth speaking into. Below this, the expert is mid-thought and an interruption
# costs them the thread; far above it, the task has moved on and the question is stale.
PAUSE_SECONDS = 2.5
STALE_SECONDS = 25.0

# Never twice in a row without the expert having done something in between: an agent that
# fills every silence is the thing people switch off.
MIN_SECONDS_BETWEEN_QUESTIONS = 20.0

# Changes to one field closer together than this are one edit, not two. Measured on a real
# run: typing a supplier name reached vision as "typed Brenn", then the full name, and the
# apprentice asked what made them change it "the second time".
SAME_EDIT_SECONDS = 10.0


class QuestionKind(StrEnum):
    REASON = "reason"          # a decision was taken and no reason is recorded
    LIMIT = "limit"            # a reason exists, but nothing says when it stops applying
    ESCALATION = "escalation"  # nothing yet says who to ask when the rule does not cover it
    EXCEPTION = "exception"    # the same field changed twice: a rule with a carve-out
    TERM = "term"              # a term or acronym never explained for a learner
    SKIPPED_STEP = "skipped_step"  # a step between two states was skipped
    EXAMPLE = "example"        # a rule was stated without a concrete example
    RISK = "risk"              # a decision carries a risk if done wrong


@dataclass(frozen=True)
class Observation:
    """What the screen did, from the vision model, plus when."""

    at: float
    changed: str               # "cost center field changed from 4711 to 0400"
    field: str = ""            # the control that changed, when it can be named
    scene: str = ""            # what the vision sees on the screen around the change
    screen_fields: tuple[str, ...] = ()  # the fields and values read on the screen


@dataclass(frozen=True)
class Activity:
    """What the expert is doing right now, from the browser."""

    at: float
    typing: bool
    talking: bool
    scrolling: bool

    @property
    def is_busy(self) -> bool:
        return self.typing or self.talking or self.scrolling


class PauseDetector:
    """A gap in typing, talking and scrolling, measured rather than guessed."""

    def __init__(self, pause_seconds: float = PAUSE_SECONDS):
        self.pause_seconds = pause_seconds
        self.busy_until = 0.0

    def update(self, activity: Activity) -> None:
        if activity.is_busy:
            self.busy_until = activity.at

    def paused_for(self, now: float) -> float:
        return max(0.0, now - self.busy_until)

    def is_pause(self, now: float) -> bool:
        return self.paused_for(now) >= self.pause_seconds


def next_kind(work_map: WorkMap, observation: Observation,
              seen_fields: list[str], asked: tuple = ()) -> QuestionKind | None:
    """
    Which gap to close next, or None when the apprentice has nothing it needs.

    The order is the order a person would use: first why this was done at all, then where
    the rule ends, then who decides past that. A field that changed twice jumps the queue,
    because a decision taken and then taken differently is where the exceptions live.
    """
    if observation.field and seen_fields.count(observation.field) > 1:
        return QuestionKind.EXCEPTION

    # A decision on screen that no step explains yet. Without this, once the first answer
    # held a reason and a stop rule, every later decision went unasked: measured on a real
    # run, the cost center changed from 4711 to 0400 and the apprentice said nothing.
    if observation.changed and not any(s.observed == observation.changed for s in work_map.steps):
        return QuestionKind.REASON

    unexplained = [s for s in work_map.steps if not s.reason.strip()]
    if unexplained or not work_map.steps:
        return QuestionKind.REASON
    # Asked once, answered, and the gap still open: the guardian said there is none. Measured
    # in a real class: "where does it stop applying?" was answered "the size does not matter",
    # and was asked again, worse. A gap the guardian has answered is not asked twice.
    if not work_map.guardrails and QuestionKind.LIMIT not in asked:
        return QuestionKind.LIMIT
    if not any(g.severity == "stop" for g in work_map.guardrails) and QuestionKind.ESCALATION not in asked:
        return QuestionKind.ESCALATION
    return None


PROMPTS = {
    QuestionKind.REASON:
        "Ask why they made this particular choice. One short spoken question.",
    QuestionKind.LIMIT:
        "Ask where this rule stops applying: a threshold, an amount, a date, a category. "
        "One short spoken question.",
    QuestionKind.ESCALATION:
        "Ask what they would do if the rule did not cover the case, and who they would "
        "ask. One short spoken question.",
    QuestionKind.EXCEPTION:
        "They changed this twice. Ask what made them change it the second time. One short "
        "spoken question.",
    QuestionKind.TERM:
        "They used a term or acronym a learner would not know yet. Ask what it means in one "
        "short spoken question.",
    QuestionKind.SKIPPED_STEP:
        "A step between what was there and the result seems skipped. Ask what happened in "
        "between, in one short spoken question.",
    QuestionKind.EXAMPLE:
        "Ask for one concrete example of this rule so a learner can recognise it. One short "
        "spoken question.",
    QuestionKind.RISK:
        "Ask what goes wrong if a learner misses this step or gets it wrong. One short spoken "
        "question.",
}

SYSTEM = (
    "You are an apprentice watching an expert work. You ask one short question out loud, "
    "the way a new colleague would.\n"
    "Rules you never break:\n"
    "- Ask only about something the screen does NOT already answer. Never ask what a field "
    "now says, or what they just clicked: you can see that.\n"
    "- One sentence. Spoken, not written: no lists, no markup.\n"
    "- Never guess the answer inside the question.\n"
    "- Name the thing you saw change, so they know which step you mean. "
    "\"Why capex rather than opex there?\" beats \"why did you do that?\"\n"
    "- Use their words for things on screen.\n"
    # Measured in a live run: "Date and Announce in fields were filled" came back as "Why July
    # fourteenth for the date there?", a date the screen never showed.
    "- Name only values written in what you are given. When it names no value, name none: "
    "never a date, a number or a name of your own."
)


# Measured in a real class: the guardian introduced what they would show, and the question
# came back "At what member count does that creation rule stop applying?", a number nobody
# had mentioned, because their words were given to the model as a change on the screen.
SAID = (
    "\n- They were speaking, not working on screen: name what they said, and never bring in "
    "a number, an amount or a threshold they did not mention.\n"
    "- If what they said introduces the task rather than stating a rule, ask instead what "
    "they do first, and why."
)


def word_question(kind: QuestionKind, observation: Observation, task: str, language: str = "en",
                  *, said: bool = False) -> str:
    """
    The chosen kind, worded against what is on screen.

    The model's whole job. It is given the gap to close and what changed, and it writes one
    sentence; it is not given the choice of what to be curious about, because an apprentice
    that invents its own curiosity asks about whatever is most interesting rather than
    whatever it still needs in order to do the task.
    """
    french = language == "fr"
    fallbacks = FALLBACKS_FR if french else FALLBACKS
    try:
        question = call_main_model([
            {"role": "system", "content": SYSTEM + (SAID if said else "")
                + ("\n- Ask it in French, using tu." if french else "")},
            {"role": "user", "content":
                f"Task: {task}\n"
                + (f"What they just said: {observation.changed}\n" if said
                   else f"What just changed on screen: {observation.changed}\n")
                + PROMPTS[kind]},
            # Room to think. A reasoning model spends its budget before the first word of
            # the answer, and a cap sized for one spoken sentence returned "Why" and
            # "If the rule": truncation that reads as a model that cannot form a question.
        ], temperature=0.3, max_tokens=2000, model=config.QUESTION_MODEL)
    except Exception as error:
        # A question the apprentice cannot word is better asked plainly than not at all:
        # the fallback is the kind itself, which is still a real question about a real gap.
        logger.warning("Could not word a %s question: %s", kind.value, error)
        return fallbacks[kind]
    question = (question or "").strip().strip('"').strip()
    # A truncated answer is worse than no answer: it sounds like the apprentice lost its
    # thread. Anything that is not a whole question falls back to one that is.
    if len(question) < 12 or not question.endswith("?"):
        logger.info("Discarding a half-formed question: %r", question)
        return fallbacks[kind]
    return question


FALLBACKS = {
    QuestionKind.REASON: "Why did you do it that way?",
    QuestionKind.LIMIT: "Where does that rule stop applying?",
    QuestionKind.ESCALATION: "What if the rule does not cover it, who do you ask?",
    QuestionKind.EXCEPTION: "What made you change that the second time?",
    QuestionKind.TERM: "What does that term mean for someone new?",
    QuestionKind.SKIPPED_STEP: "What step comes right before that?",
    QuestionKind.EXAMPLE: "Could you give one example of when that applies?",
    QuestionKind.RISK: "What is the risk if someone skips that?",
}

FALLBACKS_FR = {
    QuestionKind.REASON: "Pourquoi l'as-tu fait de cette façon ?",
    QuestionKind.LIMIT: "Où est-ce que cette règle s'arrête de s'appliquer ?",
    QuestionKind.ESCALATION: "Et si la règle ne couvre pas le cas, à qui demandes-tu ?",
    QuestionKind.EXCEPTION: "Qu'est-ce qui t'a fait changer, la deuxième fois ?",
    QuestionKind.TERM: "Que veut dire ce terme pour quelqu'un de nouveau ?",
    QuestionKind.SKIPPED_STEP: "Quelle étape se passe juste avant cela ?",
    QuestionKind.EXAMPLE: "Peux-tu donner un exemple concret où cela s'applique ?",
    QuestionKind.RISK: "Quel est le risque si quelqu'un oublie cette étape ?",
}

WHY_FALLBACKS = {
    QuestionKind.REASON: "A learner sees the action on screen but not why this choice was made.",
    QuestionKind.LIMIT: "A learner needs to know the boundary where this rule stops applying.",
    QuestionKind.ESCALATION: "A learner needs to know who decides when a case falls outside the rule.",
    QuestionKind.EXCEPTION: "The same field was changed twice, which hides an exception a learner would miss.",
    QuestionKind.TERM: "An unexplained term or acronym would block a new learner.",
    QuestionKind.SKIPPED_STEP: "A step between the previous state and this result was not shown.",
    QuestionKind.EXAMPLE: "A concrete example helps a learner recognise when the rule applies.",
    QuestionKind.RISK: "A learner needs to know what goes wrong if this step is missed.",
}

WHY_FALLBACKS_FR = {
    QuestionKind.REASON: "Un apprenant voit l'action à l'écran mais pas la raison de ce choix.",
    QuestionKind.LIMIT: "Un apprenant doit savoir où cette règle cesse de s'appliquer.",
    QuestionKind.ESCALATION: "Un apprenant doit savoir à qui s'adresser hors de la règle.",
    QuestionKind.EXCEPTION: "Ce champ a changé deux fois, ce qui cache une exception.",
    QuestionKind.TERM: "Un terme ou sigle non expliqué bloquerait un nouvel apprenant.",
    QuestionKind.SKIPPED_STEP: "Une étape intermédiaire n'a pas été expliquée.",
    QuestionKind.EXAMPLE: "Un exemple concret aide l'apprenant à reconnaître le cas.",
    QuestionKind.RISK: "Un apprenant doit connaître le risque si cette étape est omise.",
}

# P2, the expert pupil: each gap is judged by its importance (1..5) and asked only when its
# importance reaches the guardian's threshold, which rises as the guardian passes questions.
DEFAULT_THRESHOLD = 3
DEFAULT_IMPORTANCE: dict[QuestionKind, int] = {
    QuestionKind.REASON: 5,
    QuestionKind.EXCEPTION: 5,
    QuestionKind.LIMIT: 4,
    QuestionKind.RISK: 4,
    QuestionKind.ESCALATION: 4,
    QuestionKind.SKIPPED_STEP: 3,
    QuestionKind.TERM: 3,
    QuestionKind.EXAMPLE: 2,
}
_ACRONYM = re.compile(r"\b[A-Z]{3,6}\b")
_NUMBER_TOKEN = re.compile(r"\d+(?:[.,]\d+)?")
_QUOTED_TOKEN = re.compile(r'"([^"]{2,80})"|«\s*([^»]{2,80})\s*»')


@dataclass(frozen=True)
class PupilJudgment:
    """What the expert pupil judged at a pause: kind (or None), importance (1..5), why, and question."""

    kind: QuestionKind | None
    importance: int
    why: str
    question: str


PUPIL_SYSTEM = (
    SYSTEM
    + "\n- You are the guardian's expert pupil in a classroom. At a pause after a change on screen, "
    "judge whether a learner watching would miss the reason, rule, boundary, or step behind what "
    "the guardian just showed or said, how important it is (1..5), why, and word the single question.\n"
    "- Return ONLY a valid JSON object with keys: "
    '{"kind": "reason|limit|term|skipped_step|example|risk|escalation|exception|none", '
    '"importance": 1..5, "why": "...", "question": "..."}.\n'
    "- The screen shows WHAT the guardian chose or marked Done, not WHY. When a decision, field choice, "
    "or item completion is shown on screen and no step or rule yet explains why those values were chosen "
    "or where the rule stops applying, a learner is missing the `reason` or `limit` (importance 3..5).\n"
    "- Never fabricate a `limit` or `escalation` question from a sentence that states no rule: when "
    "`Rules taught so far` is `none` and what the guardian said is not a conditional rule, never "
    "choose `limit` or `escalation`.\n"
    '- Return {"kind": "none", "importance": 0, "why": "", "question": ""} ONLY when the change '
    "is trivial or cosmetic (such as switching theme, resizing, resetting a form, or purely navigating "
    "without a decision) or when the steps and rules taught so far already explain it, or when the "
    "guardian's recent words already give the reason or the limit: what they said counts as answered "
    "even before they save it.\n"
    "- Never include any value, number, threshold, or option in `question` or `why` that does not "
    "appear in what was seen on screen or said by the guardian."
)


def default_why(kind: QuestionKind | None, language: str = "en") -> str:
    if kind is None:
        return ""
    return (WHY_FALLBACKS_FR if language == "fr" else WHY_FALLBACKS).get(kind, "")


def _question_model_ready() -> bool:
    return llm.is_configured("main")


def _question_grounded(question: str, context_text: str, language: str = "en") -> bool:
    """Refuse a question that invents a number, a quoted option, or the wrong language."""
    if not question.endswith("?") or len(question) < 12:
        return False
    norm_ctx = context_text.lower().replace(",", ".")
    for match in _NUMBER_TOKEN.finditer(question):
        num = match.group(0).replace(",", ".")
        if num not in norm_ctx:
            return False
    for match in _QUOTED_TOKEN.finditer(question):
        quoted = (match.group(1) or match.group(2) or "").strip().lower()
        if quoted and quoted not in context_text.lower():
            return False
    low = question.lower().strip()
    if language == "fr" and low.startswith(("why ", "what ", "where ", "how ", "when ", "could you ")):
        return False
    if language != "fr" and low.startswith(("pourquoi ", "qu'est-ce ", "où ", "quel ", "quelle ", "peux-tu ")):
        return False
    return True


def importance_of(kind: QuestionKind | None, work_map: WorkMap, observation: Observation) -> int:
    """How much a learner needs this gap closed (1..5)."""
    if kind is None:
        return 0
    base = DEFAULT_IMPORTANCE.get(kind, DEFAULT_THRESHOLD)
    if kind == QuestionKind.EXAMPLE and len(work_map.guardrails) >= 2 and not any(
        s.decision == "example" for s in work_map.steps
    ):
        return 3
    if kind == QuestionKind.REASON and not observation.changed.strip():
        return 2
    return base


def _with_said_step(work_map: WorkMap, observation: Observation) -> WorkMap:
    obs_text = observation.changed or "said"
    steps = [
        replace(s, reason=s.reason if s.reason.strip() else obs_text)
        for s in work_map.steps
    ]
    if not any(s.observed == observation.changed for s in steps):
        steps.append(
            Step(
                step_id=f"s-said-{len(steps) + 1}",
                number=len(steps) + 1,
                title=obs_text,
                screen_moment=observation.at,
                observed=observation.changed,
                decision=obs_text,
                reason=obs_text,
            )
        )
    return replace(work_map, steps=steps)


def _norm_question(text: str) -> str:
    return re.sub(r"[^a-z0-9àâçéèêëîïôûùüÿñæœ]+", " ", (text or "").lower()).strip()


def _is_repeated_question(question: str, asked_questions: tuple[str, ...] | list[str]) -> bool:
    norm_q = _norm_question(question)
    if not norm_q:
        return False
    q_words = {w for w in norm_q.split() if len(w) >= 4}
    for prev in asked_questions:
        norm_p = _norm_question(prev)
        if not norm_p:
            continue
        if norm_q == norm_p or norm_q in norm_p or norm_p in norm_q:
            return True
        p_words = {w for w in norm_p.split() if len(w) >= 4}
        if len(q_words) >= 3 and len(p_words) >= 3:
            overlap = len(q_words & p_words) / min(len(q_words), len(p_words))
            if overlap >= 0.8:
                return True
    return False


def _gap_already_answered_or_asked(
    kind: QuestionKind,
    work_map: WorkMap,
    observation: Observation,
    asked: tuple,
    *,
    said: bool = False,
) -> bool:
    if kind in asked and (said or kind != QuestionKind.REASON):
        return True
    obs_answered = bool(
        observation.changed
        and any(s.observed == observation.changed and s.reason.strip() for s in work_map.steps)
    )
    if not said:
        if obs_answered and kind == QuestionKind.REASON:
            return True
        if obs_answered and kind == QuestionKind.LIMIT and work_map.guardrails:
            return True
        if obs_answered and kind == QuestionKind.ESCALATION and any(
            g.severity == "stop" for g in work_map.guardrails
        ):
            return True
        return False
    if kind == QuestionKind.LIMIT and work_map.guardrails:
        return True
    if kind == QuestionKind.ESCALATION and any(g.severity == "stop" for g in work_map.guardrails):
        return True
    if kind == QuestionKind.REASON and any(s.reason.strip() for s in work_map.steps):
        return True
    return False


def find_learner_gap(
    work_map: WorkMap,
    observation: Observation,
    seen_fields: list[str],
    asked: tuple = (),
    *,
    said: bool = False,
) -> tuple[QuestionKind | None, int]:
    """
    What a learner would miss next, and its importance (1..5):
    the why, a limit, a term never explained, a step skipped, no example, a risk.
    """
    effective_map = _with_said_step(work_map, observation) if said else work_map
    kind = next_kind(effective_map, observation, seen_fields, asked)
    if kind is not None:
        return kind, importance_of(kind, effective_map, observation)
    if said:
        return None, 0

    text = f"{observation.changed} {' '.join(s.reason for s in work_map.steps[-2:])}"
    known_text = " ".join(s.reason for s in work_map.steps[:-1]).lower()
    acronyms = [m.group(0) for m in _ACRONYM.finditer(text) if m.group(0).lower() not in known_text]
    if acronyms and QuestionKind.TERM not in asked:
        return QuestionKind.TERM, importance_of(QuestionKind.TERM, work_map, observation)

    if len(work_map.steps) >= 2 and QuestionKind.SKIPPED_STEP not in asked:
        if any(w in observation.changed.lower() for w in ("finally", "done", "scheduled", "published")):
            return QuestionKind.SKIPPED_STEP, importance_of(QuestionKind.SKIPPED_STEP, work_map, observation)

    if work_map.guardrails and QuestionKind.RISK not in asked:
        if not any(g.severity == "stop" for g in work_map.guardrails):
            return QuestionKind.RISK, importance_of(QuestionKind.RISK, work_map, observation)

    if work_map.guardrails and QuestionKind.EXAMPLE not in asked:
        if not any(s.decision == "example" for s in work_map.steps):
            return QuestionKind.EXAMPLE, importance_of(QuestionKind.EXAMPLE, work_map, observation)

    return None, 0


def judge_learner_gap(
    work_map: WorkMap,
    observation: Observation,
    seen_fields: list[str],
    asked: tuple = (),
    *,
    recent_words: tuple[str, ...] | list[str] = (),
    asked_questions: tuple[str, ...] | list[str] = (),
    said: bool = False,
    word_obs: Observation | None = None,
) -> PupilJudgment:
    """
    One JSON call to QUESTION_MODEL at a pause after a change, returning
    {"kind", "importance" 1..5, "why", "question"}, with deterministic fallback if the model fails.
    """
    french = work_map.language == "fr"
    fallbacks = FALLBACKS_FR if french else FALLBACKS
    spoken_obs = word_obs or observation
    active_asked_questions = tuple(asked_questions) if asked else ()
    if _question_model_ready():
        steps_summary = "; ".join(
            f"{s.number}. {s.title} (observed: {s.observed}; reason: {s.reason})"
            for s in work_map.steps[-6:]
        ) or "none"
        rules_summary = "; ".join(
            f"when {g.when} -> {g.then} ({g.severity})" for g in work_map.guardrails[-6:]
        ) or "none"
        asked_names = ", ".join(k.value if hasattr(k, "value") else str(k) for k in asked) or "none"
        asked_q_summary = "; ".join(q for q in active_asked_questions[-6:] if str(q).strip()) or "none"
        repeated = bool(observation.field and seen_fields.count(observation.field) > 1)
        vision_description = observation.scene.strip() or observation.changed
        screen_fields_items = list(observation.screen_fields)
        for f in seen_fields:
            if f and not any(f.lower() in item.lower() for item in screen_fields_items):
                screen_fields_items.append(f)
        screen_fields_summary = "; ".join(screen_fields_items) or (observation.field or "none")
        words_items: list[str] = []
        for w in [*recent_words, *(s.reason for s in work_map.steps[-4:])]:
            text_w = str(w).strip()
            if text_w and text_w not in words_items:
                words_items.append(text_w)
        recent_words_summary = "; ".join(words_items[-4:]) or "none"
        context_text = " ".join([
            work_map.task,
            observation.changed,
            spoken_obs.changed,
            observation.field,
            vision_description,
            screen_fields_summary,
            recent_words_summary,
            steps_summary,
            rules_summary,
        ])
        user_prompt = (
            f"Task: {work_map.task}\n"
            f"Language: {work_map.language}\n"
            + (f"What they just said: {spoken_obs.changed}\n" if said else "")
            + f"What just changed on screen: {observation.changed}\n"
            + (f"Field changed: {observation.field} (changed more than once: {repeated})\n"
               if observation.field else "")
            + f"Vision description of the screen: {vision_description}\n"
            + f"Fields read on screen: {screen_fields_summary}\n"
            + f"Guardian's recent words: {recent_words_summary}\n"
            + f"Steps taught so far: {steps_summary}\n"
            + f"Rules taught so far: {rules_summary}\n"
            + f"Question kinds already asked in this session: {asked_names}\n"
            + f"Questions already asked in this session (never repeat any of these): {asked_q_summary}\n"
        )
        try:
            import json

            raw = call_main_model(
                [
                    {
                        "role": "system",
                        "content": PUPIL_SYSTEM
                        + (SAID if said else "")
                        + ("\n- Write `why` and `question` in French, using tu."
                           if french else "\n- Write `why` and `question` in English."),
                    },
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                max_tokens=2000,
                response_format={"type": "json_object"},
                model=config.QUESTION_MODEL,
            )
            cleaned = (raw or "").strip()
            if cleaned.startswith("```"):
                cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.DOTALL).strip()
            data = json.loads(cleaned)
            if isinstance(data, dict):
                kind_raw = str(data.get("kind") or "").strip().lower()
                if kind_raw == "none":
                    return PupilJudgment(
                        kind=None,
                        importance=0,
                        why=str(data.get("why") or "").strip(),
                        question="",
                    )
                if kind_raw in QuestionKind._value2member_map_:
                    kind = QuestionKind(kind_raw)
                    imp_raw = data.get("importance")
                    importance = max(1, min(5, int(imp_raw))) if imp_raw is not None else importance_of(
                        kind, work_map, observation
                    )
                    why = str(data.get("why") or "").strip() or default_why(kind, work_map.language)
                    question = str(data.get("question") or "").strip().strip('"').strip()
                    if not _question_grounded(question, context_text, work_map.language):
                        logger.info("Discarding ungrounded or half-formed pupil question: %r", question)
                        question = fallbacks[kind]
                    if _gap_already_answered_or_asked(
                        kind, work_map, observation, asked, said=said
                    ) or _is_repeated_question(question, active_asked_questions):
                        return PupilJudgment(kind=None, importance=0, why="", question="")
                    return PupilJudgment(kind=kind, importance=importance, why=why, question=question)
        except Exception as error:
            logger.warning("Could not judge learner gap with model, falling back to ledger: %s", error)

    kind, importance = find_learner_gap(work_map, observation, seen_fields, asked, said=said)
    if kind is None:
        return PupilJudgment(kind=None, importance=0, why="", question="")
    question = (
        word_question(kind, spoken_obs, work_map.task, work_map.language, said=True)
        if said
        else word_question(kind, observation, work_map.task, work_map.language)
    )
    return PupilJudgment(
        kind=kind,
        importance=importance,
        why=default_why(kind, work_map.language),
        question=question,
    )


def threshold_for(
    memory,
    *,
    organisation: str = "",
    guardian_id: str = "",
) -> tuple[int, dict[str, int]]:
    """The guardian's minimum importance threshold (default 3) and per-kind overrides."""
    level = DEFAULT_THRESHOLD
    by_kind: dict[str, int] = {}

    if organisation and guardian_id:
        from guardian.memory.mmu import get_guardian_mmu

        mmu_level, mmu_by_kind, _ = get_guardian_mmu().load_threshold(organisation, guardian_id)
        level = max(level, mmu_level)
        for k, v in mmu_by_kind.items():
            by_kind[k] = max(by_kind.get(k, DEFAULT_THRESHOLD), v)

    if memory is not None:
        block = memory.find("pupil-threshold")
        if block and isinstance(block.get("content"), dict):
            content = block["content"]
            level = max(level, int(content.get("threshold", DEFAULT_THRESHOLD)))
            for k, v in (content.get("by_kind") or {}).items():
                by_kind[str(k)] = max(by_kind.get(str(k), DEFAULT_THRESHOLD), int(v))

    return level, by_kind


def record_pass(
    memory,
    kind: str,
    importance: int = DEFAULT_THRESHOLD,
    *,
    organisation: str = "",
    guardian_id: str = "",
) -> int:
    """When the guardian passes a question, learn a higher threshold and keep it across knowledges."""
    level, by_kind = threshold_for(memory, organisation=organisation, guardian_id=guardian_id)
    block = memory.find("pupil-threshold") if memory is not None else None
    passed = int((block or {}).get("content", {}).get("passed", 0))
    if organisation and guardian_id:
        from guardian.memory.mmu import get_guardian_mmu

        _, _, mmu_passed = get_guardian_mmu().load_threshold(organisation, guardian_id)
        passed = max(passed, mmu_passed)
    passed += 1
    if kind:
        by_kind[kind] = min(6, max(by_kind.get(kind, level), importance + 1))
    if passed >= 2:
        level = min(6, max(level, DEFAULT_THRESHOLD + passed // 2))
    if memory is not None:
        memory.put(
            "retained",
            "pupil-threshold",
            {"threshold": level, "by_kind": by_kind, "passed": passed, "last_passed": kind},
        )
    if organisation and guardian_id:
        from guardian.memory.mmu import get_guardian_mmu

        get_guardian_mmu().save_threshold(
            organisation,
            guardian_id,
            threshold=level,
            by_kind=by_kind,
            passed=passed,
            last_passed=kind,
        )
    return by_kind.get(kind, level) if kind else level


def should_ask(
    kind: QuestionKind | None,
    importance: int,
    memory=None,
    *,
    organisation: str = "",
    guardian_id: str = "",
) -> bool:
    """Ask only when the gap is at least as important as the guardian's learned threshold."""
    if kind is None:
        return False
    level, by_kind = threshold_for(memory, organisation=organisation, guardian_id=guardian_id)
    required = max(level, by_kind.get(kind.value, level))
    return importance >= required


