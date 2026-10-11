"""Reading JSON back from a model that was asked for JSON.

Asking for an object and getting a markdown fence around it, or a bare list, or a sentence
of preamble, is ordinary. Measured here on the first live run: a trailing fence made the
tutor fail closed on a rule that did not apply, so a new hire was stopped for a reason that
was not real. Failing closed is right; failing closed because of a backtick is not.

This finds the JSON in whatever came back, and raises when there genuinely is none, so a
caller can tell "the model said something I could not read" from "the model said no".
"""

import json
import re

FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


def loads(raw: str):
    """The first JSON value in `raw`. Raises ValueError when there is none."""
    if not raw or not raw.strip():
        raise ValueError("The model returned nothing.")

    text = FENCE.sub("", raw.strip())
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # A sentence before or after the object, which no amount of prompting removes entirely.
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        end = text.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                continue
    raise ValueError(f"No JSON in {raw[:120]!r}")


def as_list(parsed, key: str) -> list:
    """`parsed[key]` when it is an object, `parsed` when the model returned a bare list."""
    found = parsed.get(key, []) if isinstance(parsed, dict) else parsed
    if not isinstance(found, list):
        raise ValueError(f"Expected a list for {key!r}, got {type(found).__name__}")
    return found
