"""Which model answers which role, through the provider's own SDK.

Two roles call a language model with text, and they are not the same job:

  main         judgment: words a question, decides whether a rule applies to a case,
               reads the expert's verdict, compares a rule with what the sources say
  extraction   turns what the expert said into rules, in JSON

Each is configured on its own in apu/config.py. Gemini is called through its own SDK
(google-genai), not its OpenAI-compatible endpoint. Measured: that endpoint returns no price
(nor does the SDK) and hides the thinking tokens it bills, reporting 2 completion tokens for a
call whose total was 121. The SDK reports them (`thoughts_token_count`), and every call here
hands its usage to whoever listens (the meter, apu/), so cost is counted from what was billed.

Every call is metered (apu/meter.py): a budget granted before, the billed cost recorded after;
`always=True` is counted but never refused, for the guard that must read every message.

Callers keep the chat shape they had: a list of {"role", "content"} messages, with
`temperature`, `max_tokens`, `response_format={"type": "json_object"}` and `thinking` ("low" or
"high", how much the model may think before it answers). Clients are built
on first use: the server starts without a key, and a missing key fails the first call that
needs it, naming the variable to set.
"""

import os
from collections.abc import Callable
from dataclasses import dataclass

from apu import config
from apu.meter import cost, meter

# provider -> the environment variable holding its key
PROVIDERS = {"gemini": config.GEMINI_API_KEY_ENV}

_clients: dict[str, object] = {}
_listeners: list[Callable[["Usage"], None]] = []


class ProviderKeyMissing(RuntimeError):
    """A role was called and its provider has no key."""


@dataclass(frozen=True)
class Usage:
    """What one call was billed for, in tokens. Prices are ours: no provider returns one."""

    role: str
    provider: str
    model: str
    prompt_tokens: int
    output_tokens: int     # the answer and the thinking: everything billed as output
    thinking_tokens: int
    total_tokens: int


def is_configured(role: str = "main") -> bool:
    """Whether the provider for `role` ('main' or 'extraction') has a client or key configured."""
    provider = config.EXTRACTION_PROVIDER if role == "extraction" else config.MAIN_PROVIDER
    if provider in _clients:
        return True
    key_variable = PROVIDERS.get(provider, "")
    return bool(key_variable and os.environ.get(key_variable))


def get_client(provider: str):
    """The client for one provider, built on first use."""
    if provider not in _clients:
        if provider not in PROVIDERS:
            raise ValueError(f"Unknown provider {provider!r}; one of: {', '.join(PROVIDERS)}")
        key_variable = PROVIDERS[provider]
        api_key = os.environ.get(key_variable)
        if not api_key:
            raise ProviderKeyMissing(
                f"{key_variable} is not set, and it is needed for the {provider} models. "
                "Add it to your .env file."
            )
        from google import (
            genai,  # imported here: the server starts without it being used
        )

        _clients[provider] = genai.Client(api_key=api_key)
    return _clients[provider]


def set_client(client, provider: str | None = None) -> None:
    """Swap a client, for tests. None clears them all."""
    if client is None:
        _clients.clear()
        return
    for name in ([provider] if provider else PROVIDERS):
        _clients[name] = client


def add_usage_listener(listener: Callable[[Usage], None]) -> None:
    """Called with the usage of every call, after it returns. The meter subscribes here."""
    _listeners.append(listener)


def remove_usage_listener(listener: Callable[[Usage], None]) -> None:
    if listener in _listeners:
        _listeners.remove(listener)


def _request(messages: list[dict], kwargs: dict):
    """The chat shape the callers use, as the SDK's: system instruction, contents, config."""
    from google.genai import types

    system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
    contents = [types.Content(role="model" if m["role"] == "assistant" else "user",
                              parts=[types.Part.from_text(text=m["content"])])
                for m in messages if m["role"] != "system"]
    settings = {}
    if "temperature" in kwargs:
        settings["temperature"] = kwargs.pop("temperature")
    if "max_tokens" in kwargs:
        settings["max_output_tokens"] = kwargs.pop("max_tokens")
    if "thinking" in kwargs:
        settings["thinking_config"] = types.ThinkingConfig(thinking_level=kwargs.pop("thinking"))
    if (kwargs.pop("response_format", None) or {}).get("type") == "json_object":
        settings["response_mime_type"] = "application/json"
    if kwargs:
        raise TypeError(f"Unsupported options: {', '.join(sorted(kwargs))}")
    return contents, types.GenerateContentConfig(system_instruction=system or None, **settings)


def usage_of(response, role: str, provider: str, model: str) -> Usage:
    """Tokens billed, from the response. Output is total minus prompt: thinking included."""
    meta = getattr(response, "usage_metadata", None)
    prompt = getattr(meta, "prompt_token_count", None) or 0
    thinking = getattr(meta, "thoughts_token_count", None) or 0
    total = getattr(meta, "total_token_count", None) or 0
    answer = getattr(meta, "candidates_token_count", None) or 0
    total = total or prompt + answer + thinking
    return Usage(role=role, provider=provider, model=model, prompt_tokens=prompt,
                 output_tokens=max(total - prompt, 0), thinking_tokens=thinking,
                 total_tokens=total)


def _complete(role: str, provider: str, model: str, messages: list[dict], **kwargs) -> str:
    model = kwargs.pop("model", model)
    always = kwargs.pop("always", False)
    contents, settings = _request(messages, dict(kwargs))
    # No call without a budget (apu/meter.py): estimated before from the words sent and the
    # most it may write, recorded after from what the provider billed.
    sent = sum(len(m["content"]) for m in messages) // 4
    budget = meter().grant("model_cost", cost(role, sent, settings.max_output_tokens or 2000), never_refuse=always)
    response = get_client(provider).models.generate_content(model=model, contents=contents,
                                                            config=settings)
    used = usage_of(response, role, provider, model)
    meter().record(budget, cost(role, used.prompt_tokens, used.output_tokens))
    for listener in list(_listeners):
        listener(used)
    if _cut(response, used, settings.max_output_tokens):
        raise Truncated(f"The answer was cut at {used.output_tokens} tokens of {settings.max_output_tokens}, "
                        f"{used.thinking_tokens} of them thinking.")
    return response.text or ""


class Truncated(RuntimeError):
    """The budget ran out before the answer did: what came back is not the whole answer."""


def _cut(response, used: Usage, budget: int | None) -> bool:
    """
    Measured: the thinking used 1,919 of 2,000 output tokens, and the JSON came back cut after
    300 characters, three times in three. Once the response said MAX_TOKENS; once it said STOP
    with the budget spent all the same. So both are read: a cut answer is never handed on as
    an answer, it fails, and the caller does what it does when a model fails.
    """
    reason = str(getattr((getattr(response, "candidates", None) or [None])[0], "finish_reason", "") or "")
    if reason.endswith("MAX_TOKENS"):
        return True
    return bool(budget) and used.output_tokens >= budget - 10


def call_main_model(messages: list[dict], *, model: str | None = None, **kwargs) -> str:
    """A judgment call: a question, a verdict, a comparison. `model` names a faster one of the
    same provider for a call a person waits on (config.QUESTION_MODEL)."""
    return _complete("main", config.MAIN_PROVIDER, model or config.MAIN_MODEL, messages, **kwargs)


def call_extraction_model(messages: list[dict], **kwargs) -> str:
    """What the expert said, as rules."""
    return _complete("extraction", config.EXTRACTION_PROVIDER, config.EXTRACTION_MODEL,
                     messages, **kwargs)
