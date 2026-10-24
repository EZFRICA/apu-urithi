#!/usr/bin/env python3
"""
Check the Arize key: one small model call, traced the way the server traces, then what was sent.

    uv run python scripts/check_tracing.py

It needs ARIZE_API_KEY and ARIZE_SPACE_ID (and GEMINI_API_KEY for the call). It logs how many
spans were made, whether any of them holds the words sent or answered (none may: apu/observability.py
hides every text), and whether Arize took them or refused them. No key or id is ever logged; a
refusal is said by its kind, not by what the server wrote back.
"""

import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apu import config, meter, observability  # noqa: E402
from apu.logger import get_logger  # noqa: E402
from exchange.counters import SqliteCounters  # noqa: E402

logger = get_logger("check_tracing")
PROMPT = "Reply with the single word: ready. (urithi tracing check)"


class _Refusals(logging.Handler):
    """The exporter's own warnings: how a refused or unreachable endpoint is said."""

    def __init__(self):
        super().__init__(logging.WARNING)
        self.kinds: list[str] = []

    def emit(self, record):
        text = record.getMessage()
        for kind in ("UNAUTHENTICATED", "PERMISSION_DENIED", "UNAVAILABLE", "DEADLINE_EXCEEDED", "INVALID_ARGUMENT"):
            if kind in text:
                self.kinds.append(kind)
                return
        self.kinds.append(record.levelname)


def main() -> int:
    if not observability.configured():
        logger.error("Tracing is not set up: %s and %s are both needed.", config.ARIZE_API_KEY_ENV, config.ARIZE_SPACE_ID_ENV)
        return 1
    refusals = _Refusals()
    logging.getLogger("opentelemetry").addHandler(refusals)
    provider = observability.start(project=f"{config.TRACING_PROJECT}-check")
    if provider is None:
        logger.error("Tracing could not start; see the log above (no secret is in it).")
        return 1
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    kept = InMemorySpanExporter()               # a copy here, to read what was sent
    provider.add_span_processor(SimpleSpanProcessor(kept))

    from apu.inference.llm import call_extraction_model
    meter.set_counters(SqliteCounters())        # the call is metered like any other
    with meter.acting_as(meter.Principal("urithi", "tracing-check", "guardian")):
        answer = call_extraction_model([{"role": "user", "content": PROMPT}], max_tokens=200) or ""
    observability.stop()                         # flushed: what was waiting is sent now

    spans = kept.get_finished_spans()
    texts = [s.name for s in spans for v in (s.attributes or {}).values()
             if isinstance(v, str) and (PROMPT[:30] in v or (answer.strip() and answer.strip()[:20] in v))]
    logger.info("spans made: %d (%s)", len(spans), ", ".join(sorted({s.name for s in spans})) or "none")
    logger.info("spans holding the words sent or answered: %d", len(texts))
    if refusals.kinds:
        logger.error("Arize refused or could not be reached: %s", ", ".join(sorted(set(refusals.kinds))))
        return 1
    logger.info("sent to Arize, project %s-check: no refusal from the exporter", config.TRACING_PROJECT)
    return 0 if spans and not texts else 1


if __name__ == "__main__":
    sys.exit(main())
