"""Parsing the memory-extraction model's output.

Tolerant of prose, Markdown fences and truncated JSON objects so a model response wrapped in
code fences or cut early does not silently discard a turn's memory.
"""

import json
import re

_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.S)


def _candidates(raw: str) -> list[str]:
    """Progressively more forgiving readings of the payload, best first."""
    out = [raw]

    fenced = _FENCE.search(raw)
    if fenced:
        out.append(fenced.group(1))

    start = raw.find("{")
    if start != -1:
        depth, in_str, esc = 0, False, False
        for i in range(start, len(raw)):
            c = raw[i]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
                continue
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    out.append(raw[start:i + 1])
                    break
        else:
            repaired = raw[start:]
            if in_str:
                repaired += '"'
            repaired = repaired.rstrip().rstrip(",")
            repaired += "}" * max(depth, 0)
            out.append(repaired)

    return out


def parse_extraction(raw) -> tuple[dict[str, str], list[str]]:
    """Return (updates, problems). Never raises; a parse failure yields ({}, [reason])."""
    problems: list[str] = []

    if isinstance(raw, list):
        raw = " ".join(b.get("text", "") for b in raw if isinstance(b, dict))
    if not isinstance(raw, str):
        raw = str(raw)

    if not raw.strip():
        return {}, ["extractor returned an empty response"]

    parsed = None
    for candidate in _candidates(raw):
        try:
            value = json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(value, dict):
            parsed = value
            break

    if parsed is None:
        return {}, [f"no JSON object found in extractor output: {raw[:120]!r}"]

    updates: dict[str, str] = {}
    for key, value in parsed.items():
        if value is None or (isinstance(value, str) and not value.strip()):
            continue
        if not isinstance(value, str):
            problems.append(f"{key}: expected a string, got {type(value).__name__}")
            continue
        if len(value.strip()) <= 5:
            continue
        updates[key] = value

    return updates, problems
