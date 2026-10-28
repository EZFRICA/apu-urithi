"""
Traces of the model calls, sent to Arize: which model, which role, how long, how many tokens, and
what failed. Never what was said: no prompt, no answer, no instruction, no image leaves this way.

A learner's question, a guardian's words and a message of distress are all read by a model; a trace
that carried them would store them at a third party, and distress is stored nowhere. So every text
the OpenInference instrumentation can record is hidden (TraceConfig), and what remains is enough to
see that the key works and how the models behave.

Off unless ARIZE_API_KEY and ARIZE_SPACE_ID are both set; URITHI_TRACING=0 turns it off. A failure
here never stops the server: the traces are a help, not a dependency. No key or id is ever printed.

The owner may choose to see the texts (URITHI_TRACING_TEXTS=1, asked on 2026-10-24 to read what the
models were given and answered): then prompts and answers, a learner's distress included, are stored
at Arize. The server says so at its start, every time; without the switch, nothing changes.
"""

import os

from apu import config
from apu.logger import get_logger

logger = get_logger(__name__)

# Every text a trace could hold, hidden. A new kind of text the instrumentation learns to record is
# hidden too only once it is named here: tests/shared/test_observability.py lists them all.
HIDDEN = {
    "hide_inputs": True, "hide_outputs": True,
    "hide_input_messages": True, "hide_output_messages": True,
    "hide_input_text": True, "hide_output_text": True, "hide_input_images": True,
    "hide_prompts": True, "hide_choices": True,
    "hide_llm_invocation_parameters": True,      # they carry the system instruction
    "hide_llm_tools": True, "hide_embeddings_text": True, "hide_retrieval_documents": True,
}

_started: dict = {}


def texts_shown() -> bool:
    """Whether the owner turned the texts on (URITHI_TRACING_TEXTS=1). Anything else keeps them hidden."""
    return os.environ.get(config.TRACING_TEXTS_ENV, "0").strip() == "1"


def configured() -> bool:
    """Whether traces can be sent: both settings present, and tracing not turned off."""
    return os.environ.get(config.TRACING_SWITCH_ENV, "1") != "0" and bool(os.environ.get(config.ARIZE_API_KEY_ENV)) \
        and bool(os.environ.get(config.ARIZE_SPACE_ID_ENV))


def start(project: str | None = None):
    """Send the model calls' traces to Arize, texts hidden. Returns the tracer provider, or None."""
    if _started:
        return _started.get("provider")
    if not configured():
        missing = [n for n in (config.ARIZE_API_KEY_ENV, config.ARIZE_SPACE_ID_ENV) if not os.environ.get(n)]
        logger.info("Tracing off%s.", f": {', '.join(missing)} not set" if missing else " (URITHI_TRACING=0)")
        _started["provider"] = None
        return None
    try:
        from arize.otel import Endpoint, register
        from openinference.instrumentation import TraceConfig
        from openinference.instrumentation.google_genai import GoogleGenAIInstrumentor

        region = os.environ.get(config.TRACING_REGION_ENV, "us").strip().lower()
        if region not in ("us", "eu"):
            logger.warning("%s is %r: \"us\" or \"eu\" is expected; the US endpoint is used.", config.TRACING_REGION_ENV, region)
        endpoint = Endpoint.ARIZE_EUROPE if region == "eu" else Endpoint.ARIZE
        provider = register(space_id=os.environ[config.ARIZE_SPACE_ID_ENV], api_key=os.environ[config.ARIZE_API_KEY_ENV],
                            project_name=project or config.TRACING_PROJECT, endpoint=endpoint, verbose=False,
                            set_global_tracer_provider=False)
        shown = texts_shown()
        hidden = {name: False for name in HIDDEN} if shown else HIDDEN
        GoogleGenAIInstrumentor().instrument(tracer_provider=provider, config=TraceConfig(**hidden))
    except Exception as error:   # the server goes on without traces, and says so without a secret
        logger.warning("Tracing could not start (%s); the server goes on without it.", type(error).__name__)
        _started["provider"] = None
        return None
    _started["provider"] = provider
    if shown:
        logger.warning("Tracing on: model calls to Arize (%s), project %r, TEXTS SHOWN (%s=1): prompts and "
                       "answers, distress included, are stored at Arize.", "Europe" if region == "eu" else "US",
                       project or config.TRACING_PROJECT, config.TRACING_TEXTS_ENV)
    else:
        logger.info("Tracing on: model calls to Arize (%s), project %r, texts hidden.",
                    "Europe" if region == "eu" else "US", project or config.TRACING_PROJECT)
    return provider


def stop() -> None:
    """Send what is waiting, then stop: at the server's end, and in a check that must not lose a span."""
    provider = _started.pop("provider", None)
    if provider is not None:
        provider.force_flush()
        provider.shutdown()
