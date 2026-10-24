"""The shared configuration: model ids, speech, pictures, embeddings, logs and the port.

What belongs to one package lives in its own config: library/config.py (Neo4j, the registry),
exchange/config.py, guardian/config.py and learner/config.py (each side's data). Modules read
these as `config.NAME` at call time rather than binding them with `from ... import NAME`, so a
test can redirect a path with monkeypatch and every call site sees the change.

Every variable this project reads is prefixed URITHI_, GUARDIAN_, LEARNER_ or EXCHANGE_ (or is
a provider's own name), so nothing exported for another project on the same machine can move
this one's data, models or port.
"""

import os

from dotenv import load_dotenv

load_dotenv()

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── Models ───────────────────────────────────────────────────────────────────
# Two text roles, configured apart because they are not the same job. Providers are listed
# in apu/inference/llm.py, each called through its own SDK.

# Judgment: words a question, decides whether a rule applies to a case, reads a verdict,
# compares a rule with its sources.
MAIN_PROVIDER = os.environ.get("URITHI_PROVIDER", "gemini")
MAIN_MODEL = os.environ.get("URITHI_MODEL", "gemini-3.8-flash")

# Turns what the expert said into rules, in JSON.
EXTRACTION_PROVIDER = os.environ.get("URITHI_EXTRACTION_PROVIDER", "gemini")
EXTRACTION_MODEL = os.environ.get("URITHI_EXTRACTION_MODEL", "gemini-3.5-flash-lite")

# Words the question a guardian waits on, in a class or a conversation (guardian/engine/
# questions.py). The main model by default. Measured on the owner's own words from a real
# class: 6 to 16 s a question with the main model; a faster model of the same provider asked
# the same questions in about 2 s, and the smallest one invented a number nobody had said.
QUESTION_MODEL = os.environ.get("URITHI_QUESTION_MODEL", MAIN_MODEL)
# Words a learner's answer from the guardian's parts (learner/tutor/answer.py), which a learner
# waits on. The main model by default. Measured on a real question to a real body: 8 to 17 s a
# worded answer with the main model, 0.6 s with the smallest, both checked against the parts the
# same way; an answer that fails the check is the guardian's own words, whichever model wrote it.
ANSWER_MODEL = os.environ.get("URITHI_ANSWER_MODEL", MAIN_MODEL)

# Looks at an image: an illustration before it is shown, a picture a guardian deposits
# (apu/modality/picture.py). Images do not go through the text router.
VISION_MODEL = os.environ.get("URITHI_VISION_MODEL", "gemini-3.8-flash")
# Compares two frames of a class, every time the shared screen changes, while the guardian
# waits for the question (guardian/engine/vision.py). Measured on the same real pair, three
# times each: 12.3 s a pair (24.4 s at worst) with the vision model above, 0.9 s with this one,
# which saw the change and named it more precisely, and saw nothing in a screen at rest.
CLASS_VISION_MODEL = os.environ.get("URITHI_CLASS_VISION_MODEL", "gemini-3.5-flash-lite")

# Draws an illustration from a unit's words, as a memory aid (apu/modality/picture.py). The
# vision model then checks the drawing holds no writing, which is refused.
PICTURE_MODEL = os.environ.get("URITHI_PICTURE_MODEL", "gemini-3.1-flash-image")

# ── Logs ─────────────────────────────────────────────────────────────────────
# The running server's log. Data is not here: each package keeps its own (see the docstring).
LOG_DIR = os.environ.get("URITHI_LOG_DIR", os.path.join(_REPO_ROOT, "logs"))

# ── Embeddings ───────────────────────────────────────────────────────────────
# One embedding model everywhere: the library online and a package offline share one vector
# space only if both are embedded by the same model. Local ONNX, multilingual (English and
# French), 384 dimensions, never downloaded at runtime.
EMBEDDING_MODEL = os.environ.get(
    "URITHI_EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
EMBEDDING_DIM = int(os.environ.get("URITHI_EMBEDDING_DIM", "384"))
EMBEDDING_CACHE_DIR = os.environ.get(
    "URITHI_EMBEDDING_CACHE_DIR", os.path.join(_REPO_ROOT, "models"))

# ── Server ───────────────────────────────────────────────────────────────────
# One port for the apprentice and the presentation, which share one server.
PORT = int(os.environ.get("URITHI_PORT", "8790"))
# Loopback by default: the server holds what an expert said about their work, and nothing
# here authenticates who asks for it. Set 0.0.0.0 deliberately, for a demo on a network.
HOST = os.environ.get("URITHI_HOST", "127.0.0.1")
# At start, the library's connection and the embedder are made ready in the background
# (server.py, warm_up). Measured: the first question after a start took 8.7 s, the next 1.7 s.
WARM_UP = os.environ.get("URITHI_WARM_UP", "1") != "0"

# ── Speech ───────────────────────────────────────────────────────────────────
# Which provider reads and writes speech. Measured (docs/measurements.md): ElevenLabs
# synthesises far faster than the Gemini batch models. Gemini stays available for both.
VOICE_TTS_PROVIDER = os.environ.get("URITHI_TTS_PROVIDER", "elevenlabs")
VOICE_TTS_MODEL = os.environ.get("URITHI_TTS_MODEL", "eleven_v4_turbo")
VOICE_STT_PROVIDER = os.environ.get("URITHI_STT_PROVIDER", "elevenlabs")
VOICE_STT_MODEL = os.environ.get("URITHI_STT_MODEL", "scribe_v2")

ELEVENLABS_API_KEY_ENV = "ELEVENLABS_API_KEY"
ELEVENLABS_URL = "https://api.elevenlabs.io/v1"
# A voice from the account. Library voices are refused on a free plan.
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "EXAVITQu4vr4xnSDxMaL")

GEMINI_API_KEY_ENV = "GEMINI_API_KEY"
GEMINI_TRANSCRIBE_MODEL = os.environ.get("GEMINI_TRANSCRIBE_MODEL", "gemini-3.8-flash")
GEMINI_TTS_MODEL = os.environ.get("GEMINI_TTS_MODEL", "gemini-3.8-flash-lite-tts")
GEMINI_TTS_VOICE = os.environ.get("GEMINI_TTS_VOICE", "Kore")

BRIGHTDATA_TOKEN_ENV = "BRIGHTDATA_API_TOKEN"
BRIGHTDATA_SERP_ZONE_ENV = "BRIGHTDATA_SERP_ZONE"
BRIGHTDATA_UNLOCKER_ZONE_ENV = "BRIGHTDATA_UNLOCKER_ZONE"
TAVILY_TOKEN_ENV = "TAVILY_API_KEY"

# Traces of the model calls, sent to Arize when both are set (apu/observability.py); never their texts.
ARIZE_API_KEY_ENV = "ARIZE_API_KEY"
ARIZE_SPACE_ID_ENV = "ARIZE_SPACE_ID"
TRACING_PROJECT = os.environ.get("URITHI_TRACING_PROJECT", "urithi")
TRACING_SWITCH_ENV = "URITHI_TRACING"      # "0" turns it off; read at each start, so the tests can
# Where the Arize space lives: "us" (the default) or "eu". A space made in Europe is unknown to the US
# endpoint, which answers "invalid Space ID" (measured on 2026-10-24).
TRACING_REGION_ENV = "URITHI_TRACING_REGION"
# "1" shows the prompts and answers in the traces (the owner's choice); anything else keeps them hidden.
TRACING_TEXTS_ENV = "URITHI_TRACING_TEXTS"

# An answer is an answer, not a lecture: a recording over this size is refused before it is
# uploaded, and a text is cut before it is read out.
VOICE_MAX_RECORDING_BYTES = int(
    os.environ.get("URITHI_VOICE_MAX_RECORDING_BYTES", str(8 * 1024 * 1024)))
VOICE_MAX_SPOKEN_CHARS = int(os.environ.get("URITHI_VOICE_MAX_SPOKEN_CHARS", "4000"))
# Speech runs at roughly 15 characters per second (measured: 341 characters read in 22 s of
# audio). Audio far shorter than that means the model stopped early, which a listener who
# cannot see the text has no way to notice, so it is checked and retried once.
VOICE_CHARS_PER_SECOND = float(os.environ.get("URITHI_VOICE_CHARS_PER_SECOND", "15"))
VOICE_MIN_AUDIO_RATIO = float(os.environ.get("URITHI_VOICE_MIN_AUDIO_RATIO", "0.6"))

# The organisation every record written before organisations existed belongs to: there was
# one. Each store reads it once, when it meets such a record; it is never a default for
# anything new (docs/decisions/0006).
LEGACY_ORGANISATION = os.environ.get("URITHI_LEGACY_ORGANISATION", "urithi")

# ── Metering (apu/meter.py) ──────────────────────────────────────────────────
# Quotas and ceilings, as data: set by the platform, narrowed by each organisation.
POLICY_PATH = os.environ.get("URITHI_POLICY_PATH", os.path.join(_REPO_ROOT, "registries", "policy.json"))


def _prices() -> dict[str, dict[str, float]]:
    """The price of each model role, per million tokens in and out: URITHI_PRICE_MAIN="0.30,2.50".
    No provider returns a price (docs/urithi-measured.md, docs/measured-a-and-an.md): the table is ours, by role, so it
    follows whichever model a role is set to."""
    found = {}
    for role in ("main", "extraction", "vision", "picture", "transcribe"):
        raw = os.environ.get(f"URITHI_PRICE_{role.upper()}", "").strip()
        if raw:
            given, taken = (float(x) for x in raw.split(","))
            found[role] = {"input": given, "output": taken}
    return found


MODEL_PRICES = _prices()

# A cheaper model for the main role, used only when a ceiling is near (the step-down), and
# only once measured for that role (.claude/skills/model-role-benchmark). Empty: no such step.
MAIN_MODEL_CHEAPER = os.environ.get("URITHI_MODEL_CHEAPER", "")

# ── MMU tunables (apu/mmu/, docs/decisions/0015) ─────────────────────────────
# Cap on non-fixed blocks in the L2 DLL. Creating or paging in one more at the cap pages the
# least recently accessed non-fixed block out to L3.
MAX_DYNAMIC_BLOCKS = int(os.environ.get("URITHI_MAX_DYNAMIC_BLOCKS", "5"))

# Minimum cosine similarity for a block to enter the working context, calibrated to the
# 384-dim multilingual MiniLM embedder (fundamental < knowledge/project < temporary).
CERTAINTY_THRESHOLDS: dict[str, float] = {
    "fundamental":    0.40,
    "knowledge":      0.45,
    "project":        0.45,
    "manual_chapter": 0.45,
    "temporary":      0.50,
}
MIN_RELEVANCE_CERTAINTY = 0.45

