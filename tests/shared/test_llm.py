"""
The two model roles, through the provider's own SDK, and what each call was billed for.

Target: apu/inference/llm.py

Measured: the OpenAI-compatible endpoint reported 2 completion tokens for a call whose total
was 121; the thinking it billed was hidden. The SDK reports it, and the usage handed to the
meter counts it as output.
"""

from types import SimpleNamespace

import pytest

from apu.inference import llm


class FakeModels:
    def __init__(self, text="ok", usage=None):
        self.text, self.usage, self.calls = text, usage, []

    def generate_content(self, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        return SimpleNamespace(text=self.text, usage_metadata=self.usage)


@pytest.fixture
def fake():
    models = FakeModels(usage=SimpleNamespace(prompt_token_count=10, candidates_token_count=2,
                                              thoughts_token_count=84, total_token_count=96))
    llm.set_client(SimpleNamespace(models=models))
    yield models
    llm.set_client(None)


def test_the_chat_shape_becomes_a_system_instruction_and_turns(fake):
    llm.call_main_model([{"role": "system", "content": "Be brief."},
                         {"role": "user", "content": "a or an?"},
                         {"role": "assistant", "content": "an"},
                         {"role": "user", "content": "hour?"}], temperature=0.2, max_tokens=500)
    [call] = fake.calls
    assert call["config"].system_instruction == "Be brief."
    assert [c.role for c in call["contents"]] == ["user", "model", "user"]
    assert call["contents"][1].parts[0].text == "an"
    assert call["config"].temperature == 0.2 and call["config"].max_output_tokens == 500


def test_json_is_asked_for_in_the_sdks_own_terms(fake):
    llm.call_extraction_model([{"role": "user", "content": "x"}], response_format={"type": "json_object"})
    assert fake.calls[0]["config"].response_mime_type == "application/json"


def test_an_option_the_sdk_does_not_carry_is_refused_not_dropped(fake):
    with pytest.raises(TypeError, match="Unsupported options: top_k"):
        llm.call_main_model([{"role": "user", "content": "x"}], top_k=3)


def test_every_call_reports_what_was_billed_thinking_included(fake):
    heard = []
    llm.add_usage_listener(heard.append)
    try:
        assert llm.call_main_model([{"role": "user", "content": "x"}]) == "ok"
    finally:
        llm.remove_usage_listener(heard.append)
    [used] = heard
    assert (used.role, used.prompt_tokens, used.thinking_tokens, used.total_tokens) == ("main", 10, 84, 96)
    assert used.output_tokens == 86, "the answer and the thinking, never the 2 answer tokens alone"


def test_a_response_with_no_usage_counts_zero_rather_than_failing():
    used = llm.usage_of(SimpleNamespace(), "main", "gemini", "m")
    assert used.total_tokens == 0 and used.output_tokens == 0


def test_a_missing_answer_reads_as_empty_text():
    models = FakeModels(text=None)
    llm.set_client(SimpleNamespace(models=models))
    try:
        assert llm.call_main_model([{"role": "user", "content": "x"}]) == ""
    finally:
        llm.set_client(None)


def _cut_response(reason, output):
    usage = SimpleNamespace(prompt_token_count=10, candidates_token_count=20,
                            thoughts_token_count=output - 20, total_token_count=10 + output)
    return SimpleNamespace(text='```json\n{"case": "A report about', usage_metadata=usage,
                           candidates=[SimpleNamespace(finish_reason=reason)])


@pytest.mark.parametrize("reason", ["FinishReason.MAX_TOKENS", "FinishReason.STOP"])
def test_an_answer_cut_by_the_budget_is_refused_not_returned(reason):
    """Measured: thinking used 1,919 of 2,000 tokens and the JSON came back cut after 300
    characters; once the response said MAX_TOKENS, once STOP. Neither is an answer."""
    models = FakeModels()
    models.generate_content = lambda model, contents, config: _cut_response(reason, 1996)
    llm.set_client(SimpleNamespace(models=models))
    try:
        with pytest.raises(llm.Truncated):
            llm.call_main_model([{"role": "user", "content": "x"}], max_tokens=2000)
    finally:
        llm.set_client(None)


def test_an_answer_well_within_its_budget_is_returned():
    models = FakeModels()
    models.generate_content = lambda model, contents, config: _cut_response("FinishReason.STOP", 400)
    llm.set_client(SimpleNamespace(models=models))
    try:
        assert llm.call_main_model([{"role": "user", "content": "x"}], max_tokens=2000)
    finally:
        llm.set_client(None)


def test_how_much_the_model_thinks_is_asked_in_the_sdks_own_terms(fake):
    llm.call_main_model([{"role": "user", "content": "x"}], thinking="low")
    assert fake.calls[0]["config"].thinking_config.thinking_level.lower() == "low"
