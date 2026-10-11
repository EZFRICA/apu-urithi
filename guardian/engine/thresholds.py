"""Rules with a number in them are decided by arithmetic, not by a model.

Measured: asked four times whether a 2,400 euro invoice meets "equipment over five thousand
euros", the model said no twice and "unsure" twice. Unsure fails closed, so half the time a
new hire was stopped for a rule that plainly did not apply, which teaches them that the
apprentice cries wolf. That is the fastest way to make a guardrail ignored.

A comparison between two numbers has one answer. This finds the number in the rule and the
number in the case and compares them in code. The model is still asked everything else,
the judgment calls it is good at, and it is no longer asked to do arithmetic.

When either number cannot be found, this returns None and the model decides, as before. It
never guesses a number that was not there.
"""

import re
from dataclasses import dataclass

# "five thousand", "5,000", "5000", "5k", "€5.000" (a German thousands separator)
UNITS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90,
}
SCALES = {"hundred": 100, "thousand": 1_000, "million": 1_000_000}

# The same in French: a guardian teaches in the language they think in. "quatre-vingt" is
# four twenties, so it is read as one word; "soixante-dix" adds up on its own.
UNITS_FR = {
    "zéro": 0, "zero": 0, "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5,
    "six": 6, "sept": 7, "huit": 8, "neuf": 9, "dix": 10, "onze": 11, "douze": 12,
    "treize": 13, "quatorze": 14, "quinze": 15, "seize": 16, "vingt": 20, "vingts": 20,
    "trente": 30, "quarante": 40, "cinquante": 50, "soixante": 60, "quatre-vingt": 80,
    "quatre-vingts": 80,
}
SCALES_FR = {"cent": 100, "cents": 100, "mille": 1_000, "million": 1_000_000, "millions": 1_000_000}

ABOVE = ("over", "above", "more than", "greater than", "exceeds", "exceeding", "beyond",
         "higher than", "at least", "or more", "minimum of",
         "plus de", "au-dessus de", "au dessus de", "supérieur à", "supérieure à", "dépasse",
         "au moins", "ou plus", "à partir de")
BELOW = ("under", "below", "less than", "fewer than", "lower than", "at most", "or less",
         "up to", "maximum of", "within",
         "moins de", "en dessous de", "en-dessous de", "inférieur à", "inférieure à",
         "au plus", "ou moins", "jusqu'à", "maximum de")
# The value itself counts: "at least ten", "au moins dix".
INCLUSIVE = ("at least", "or more", "at most", "or less", "up to", "minimum of", "maximum of",
             "au moins", "ou plus", "au plus", "ou moins", "jusqu'à", "à partir de", "maximum de")

# Case fields that hold the amount a rule is about. Ordered: the first found wins.
AMOUNT_FIELDS = ("amount_eur", "net_amount", "amount", "net", "total", "value", "price",
                 "cost", "invoice_amount")


@dataclass(frozen=True)
class Threshold:
    value: float
    above: bool          # True: the rule applies above the value; False: below it
    inclusive: bool      # "at least", "or more": the value itself counts


def _words_to_number(words: str) -> float | None:
    """'five thousand' -> 5000. None when the words are not a number."""
    total, current, seen = 0, 0, False
    for word in re.findall(r"[a-zà-ÿ]+(?:-vingts?)?", words.lower()):
        if word in UNITS_FR:
            current += UNITS_FR[word]
            seen = True
        elif word in ("cent", "cents"):
            current = max(current, 1) * 100
            seen = True
        elif word in SCALES_FR:
            total += max(current, 1) * SCALES_FR[word]
            current = 0
            seen = True
        elif word == "et":
            continue
        elif word in UNITS:
            current += UNITS[word]
            seen = True
        elif word == "hundred":
            current = max(current, 1) * 100
            seen = True
        elif word in SCALES:
            total += max(current, 1) * SCALES[word]
            current = 0
            seen = True
        elif word in ("and", "a"):
            continue
        else:
            break
    return float(total + current) if seen else None


def _digits_to_number(text: str) -> float | None:
    """'5,000' / '5.000' / '5000' / '5k' / '€5 000' -> 5000."""
    match = re.search(r"(\d[\d.,\s]*\d|\d)\s*(k|thousand|m|million)?\b", text, re.IGNORECASE)
    if not match:
        return None
    raw, scale = match.group(1), (match.group(2) or "").lower()
    digits = re.sub(r"[\s]", "", raw).rstrip(".,")
    if "," in digits and "." in digits:
        # Both separators: whichever comes last is the decimal point. "1,250.50" in
        # English and "1.250,50" in German are the same amount, and a German invoice is
        # written the second way, so reading only one convention misreads real invoices.
        decimal = "," if digits.rfind(",") > digits.rfind(".") else "."
        thousands = "." if decimal == "," else ","
        digits = digits.replace(thousands, "").replace(decimal, ".")
    elif re.fullmatch(r"\d{1,3}([.,]\d{3})+", digits):
        # One separator followed by groups of exactly three digits is a thousands
        # separator, in either convention.
        digits = re.sub(r"[.,]", "", digits)
    else:
        digits = digits.replace(",", ".")
    try:
        value = float(digits)
    except ValueError:
        return None
    return value * {"k": 1_000, "thousand": 1_000, "m": 1_000_000, "million": 1_000_000}.get(scale, 1)


CURRENCY = r"(?:€|eur(?:os?)?\b|\$|usd\b|dollars?\b|£|gbp\b|cfa\b|xof\b)"
NUMBER = r"\d[\d.,\s]*\d|\d"


def money_in(text: str) -> float | None:
    """
    The amount of money a sentence states, not just its first number.

    Measured: reading "The threshold remains unchanged in 2026, at 800 euros net", the first
    number is the year, and the debrief built its test case around 2026 euros. A number is
    taken as money when a currency sits right beside it; failing that, the first number that
    is not plausibly a year.
    """
    lowered = text.lower()
    for pattern in (rf"({NUMBER})\s*(k\b)?\s*{CURRENCY}", rf"{CURRENCY}\s*({NUMBER})\s*(k\b)?"):
        match = re.search(pattern, lowered)
        if match:
            value = _digits_to_number(match.group(1))
            # "5k EUR": the k was matched to find the currency, and has to be kept too.
            return value * 1_000 if value is not None and match.group(2) else value
    for match in re.finditer(NUMBER, lowered):
        value = _digits_to_number(match.group(0))
        if value is not None and not (1900 <= value <= 2100 and float(value).is_integer()):
            return value
    return None


def threshold_in(condition: str) -> Threshold | None:
    """The number a rule turns on, and which side of it the rule applies. None if there is none."""
    text = condition.lower()
    above = next((w for w in ABOVE if w in text), None)
    below = next((w for w in BELOW if w in text), None)
    if not above and not below:
        return None

    value = _digits_to_number(text)
    if value is None:
        # The number written out, after the comparison word: "over five thousand euros".
        word = above or below
        value = _words_to_number(text.split(word, 1)[1])
    if value is None:
        # Or before it: "ten or more", "quatre-vingts inscrits ou plus". Never from an article:
        # "un sponsor" is not one of anything.
        words = re.findall(r"[a-zà-ÿ]+(?:-[a-zà-ÿ]+)*", text)
        vocabulary = (set(UNITS) | set(SCALES) | set(UNITS_FR) | set(SCALES_FR)) - {"un", "une", "a"}
        value = next((found for i, w in enumerate(words) if w in vocabulary
                      for found in [_words_to_number(" ".join(words[i:]))] if found is not None), None)
    if value is None:
        return None

    is_above = above is not None and (below is None or text.index(above) < text.index(below))
    inclusive = any(w in text for w in INCLUSIVE)
    return Threshold(value=value, above=is_above, inclusive=inclusive)


def amount_in(case: dict) -> float | None:
    """The amount in a case, from the first field that holds one."""
    for field in AMOUNT_FIELDS:
        value = case.get(field)
        if isinstance(value, bool) or value is None:
            continue
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            parsed = _digits_to_number(value)
            if parsed is not None:
                return parsed
    return None


def decide(condition: str, case: dict, inclusive: bool | None = None,
           value: float | None = None) -> bool | None:
    """
    Whether the rule applies, decided by arithmetic. None when it cannot be.

    None hands the decision back to the model. It is never a guess dressed as an answer.

    `inclusive` and `value` are what a person settled after the rule was written: whether
    the boundary itself counts, and which number the company now follows. A ruling on one
    case at the edge answers the question for every case, so it is applied here rather than
    only to the one invoice it was about.
    """
    threshold = threshold_in(condition)
    amount = amount_in(case)
    if threshold is None or amount is None:
        return None
    threshold = Threshold(value=threshold.value if value is None else value,
                          above=threshold.above,
                          inclusive=threshold.inclusive if inclusive is None else inclusive)
    if threshold.above:
        return amount >= threshold.value if threshold.inclusive else amount > threshold.value
    return amount <= threshold.value if threshold.inclusive else amount < threshold.value
