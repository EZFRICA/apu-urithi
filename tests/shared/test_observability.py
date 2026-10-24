"""
Traces of the model calls (apu/observability.py): sent to Arize only when it is set up, and never
with a text in them. A learner's question, a guardian's words and a message of distress are all read
by a model; distress is stored nowhere, so no prompt and no answer may leave in a trace.
"""

import inspect
import logging

import pytest

from apu import config, observability

KEY, SPACE = "test-arize-key-not-real", "test-space-not-real"


@pytest.fixture
def fresh(monkeypatch):
    monkeypatch.setattr(observability, "_started", {})
    calls = {}

    def register(**kwargs):
        calls["register"] = kwargs

        class Provider:
            def force_flush(self):
                calls["flushed"] = True

            def shutdown(self):
                calls["shut"] = True
        return Provider()

    class Instrumentor:
        def instrument(self, **kwargs):
            calls["instrument"] = kwargs

    import arize.otel
    import openinference.instrumentation.google_genai as genai_instrumentation
    monkeypatch.setattr(arize.otel, "register", register)
    monkeypatch.setattr(genai_instrumentation, "GoogleGenAIInstrumentor", Instrumentor)
    return calls


@pytest.mark.parametrize("key,space,switch", [(None, SPACE, "1"), (KEY, None, "1"), (KEY, SPACE, "0")])
def test_nothing_is_sent_unless_both_settings_are_there_and_tracing_is_on(fresh, monkeypatch, key, space, switch):
    for name, value in ((config.ARIZE_API_KEY_ENV, key), (config.ARIZE_SPACE_ID_ENV, space), (config.TRACING_SWITCH_ENV, switch)):
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    assert not observability.configured(), "not set up: nothing is even tried"
    assert observability.start() is None and "register" not in fresh


def test_every_text_a_trace_could_hold_is_hidden(fresh, monkeypatch, caplog):
    monkeypatch.setenv(config.ARIZE_API_KEY_ENV, KEY)
    monkeypatch.setenv(config.ARIZE_SPACE_ID_ENV, SPACE)
    monkeypatch.setenv(config.TRACING_SWITCH_ENV, "1")
    monkeypatch.delenv(config.TRACING_TEXTS_ENV, raising=False)
    with caplog.at_level(logging.INFO):
        assert observability.start(project="urithi-test") is not None
    sent = fresh["register"]
    assert sent["api_key"] == KEY and sent["space_id"] == SPACE and sent["project_name"] == "urithi-test"
    assert sent["verbose"] is False, "register would print its settings"
    traced = fresh["instrument"]["config"]
    from openinference.instrumentation import TraceConfig
    fields = [f for f in inspect.signature(TraceConfig).parameters if f.startswith("hide_")]
    for field in fields:
        if "vectors" in field:
            continue                               # numbers, not words
        assert getattr(traced, field) is True, f"{field} would let a text leave in a trace"
    assert KEY not in caplog.text and SPACE not in caplog.text, "no key or id in the log"
    observability.stop()
    assert fresh.get("flushed") and fresh.get("shut"), "what is waiting is sent before the end"


def test_a_tracing_failure_never_stops_the_server_and_names_no_secret(fresh, monkeypatch, caplog):
    import arize.otel

    def refused(**kwargs):
        raise RuntimeError(f"bad credentials {kwargs['api_key']}")
    monkeypatch.setattr(arize.otel, "register", refused)
    monkeypatch.setenv(config.ARIZE_API_KEY_ENV, KEY)
    monkeypatch.setenv(config.ARIZE_SPACE_ID_ENV, SPACE)
    monkeypatch.setenv(config.TRACING_SWITCH_ENV, "1")
    with caplog.at_level(logging.WARNING):
        assert observability.start() is None
    assert "Tracing could not start" in caplog.text and KEY not in caplog.text


def test_the_tests_never_send_a_trace():
    """Whatever .env holds, the suite runs with tracing off (tests/conftest.py)."""
    import os
    assert os.environ.get(config.TRACING_SWITCH_ENV) == "0"


@pytest.mark.parametrize("region,expected", [(None, "ARIZE"), ("eu", "ARIZE_EUROPE"), ("EU", "ARIZE_EUROPE"), ("mars", "ARIZE")])
def test_the_traces_go_to_the_region_the_space_lives_in(fresh, monkeypatch, region, expected):
    """Measured on 2026-10-24: a space made in Europe was refused by the US endpoint, "invalid Space ID",
    and taken by the European one."""
    monkeypatch.setenv(config.ARIZE_API_KEY_ENV, KEY)
    monkeypatch.setenv(config.ARIZE_SPACE_ID_ENV, SPACE)
    monkeypatch.setenv(config.TRACING_SWITCH_ENV, "1")
    if region is None:
        monkeypatch.delenv(config.TRACING_REGION_ENV, raising=False)
    else:
        monkeypatch.setenv(config.TRACING_REGION_ENV, region)
    observability.start()
    from arize.otel import Endpoint
    assert fresh["register"]["endpoint"] is getattr(Endpoint, expected)


@pytest.mark.parametrize("value,shown", [("1", True), ("0", False), ("yes", False), ("true", False)])
def test_the_texts_are_shown_only_when_the_owner_sets_the_switch_to_one(fresh, monkeypatch, caplog, value, shown):
    """Asked by the owner on 2026-10-24 to read the prompts and answers in Arize; said loudly at start."""
    monkeypatch.setenv(config.ARIZE_API_KEY_ENV, KEY)
    monkeypatch.setenv(config.ARIZE_SPACE_ID_ENV, SPACE)
    monkeypatch.setenv(config.TRACING_SWITCH_ENV, "1")
    monkeypatch.setenv(config.TRACING_TEXTS_ENV, value)
    with caplog.at_level(logging.INFO):
        observability.start()
    traced = fresh["instrument"]["config"]
    for field in observability.HIDDEN:
        assert getattr(traced, field) is (not shown), f"{field} with {config.TRACING_TEXTS_ENV}={value!r}"
    assert ("TEXTS SHOWN" in caplog.text) is shown, "the server says when texts leave, and only then"
