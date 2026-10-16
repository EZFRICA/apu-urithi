"""
Words and meaning together: a keyword ranking (BM25) fused with the vector ranking (RRF).

Measured on 2026-10-15, 38 labelled questions on three knowledges (docs/measured-search.md): the
vector alone put the right part first 30 times, the fusion 32; asked in another language than the
knowledge's, keywords only matched short words by chance (French "on" for English "on") and the
fusion fell from 10 to 8 in 12. So keywords count only when the question is in the knowledge's
language; across languages the meaning alone links them, as before.

No list of words to leave out: in a knowledge about "a" and "an" those are the words that count,
and how often a word occurs across the parts (its IDF) already weighs the common ones down.
"""

import math
import re
from collections import Counter

RRF_K = 60            # the constant of reciprocal rank fusion as published; not tuned on our questions
_WORD = re.compile(r"[^\W_]+")


def words(text: str) -> list[str]:
    return _WORD.findall((text or "").lower())


def bm25(query: str, docs: list[str], k1: float = 1.2, b: float = 0.75) -> list[float]:
    """The BM25 score of each document for the query; 0 where no word is shared."""
    tokens = [words(d) for d in docs]
    if not tokens:
        return []
    n, avg = len(tokens), (sum(map(len, tokens)) / len(tokens)) or 1.0
    df = Counter(t for ts in tokens for t in set(ts))
    asked = set(words(query))
    scores = []
    for ts in tokens:
        tf, score = Counter(ts), 0.0
        for t in asked:
            if tf[t]:
                idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
                score += idf * tf[t] * (k1 + 1) / (tf[t] + k1 * (1 - b + b * len(ts) / avg))
        scores.append(score)
    return scores


def fuse(by_meaning: list[str], by_words: list[str]) -> list[str]:
    """Reciprocal rank fusion of two rankings of ids, best first; ties keep the meaning's order."""
    fused: dict[str, float] = {}
    for ranking in (by_meaning, by_words):
        for rank, key in enumerate(ranking):
            fused[key] = fused.get(key, 0.0) + 1.0 / (RRF_K + rank + 1)
    order = {key: i for i, key in enumerate(by_meaning)}
    return sorted(fused, key=lambda key: (-fused[key], order.get(key, len(order))))


def same_language(asked: str | None, taught: str | None) -> bool:
    """Keywords are compared only within one language; an unknown language is not assumed to match."""
    return bool(asked) and bool(taught) and asked.split("-")[0].lower() == taught.split("-")[0].lower()

