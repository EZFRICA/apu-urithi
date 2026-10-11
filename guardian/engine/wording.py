"""What the apprentice says, in the language the guardian teaches in.

The debrief's questions and the teach-back are built by code, not written by a model (see
probe.py): so are their words, here, one set per language. A guardian who teaches in French
is asked in French, tested in French, and hears their knowledge back in French; the rule
"quand moins de dix personnes sont inscrites, tu déplaces le meetup" stays in their words.

`then` is always what the guardian does, written so it reads after "you" or "tu": "treat it
as capex", "déplaces le meetup". The extractor is asked for it in that form (absorb.py).
"""


LANGUAGES = ("en", "fr")
LANGUAGE_NAMES = {"en": "English", "fr": "French"}

PHRASES = {
    "en": {
        "boundary": "Here is one for exactly {n}. You said that when {when}, you {then}. "
                    "Is exactly {n} {side}, or not?",
        "over": "over", "under": "under",
        "a_source": "A public source",
        "source_amount": "{domain} says: \"{says}\" You said {theirs}. Here is a case at {between}, "
                         "where the two disagree. Do you {then}, or not?",
        "source_quote": "{domain} says: \"{says}\" You said: \"{quote}\" Which one is followed here?",
        "collision": "Say both happen at once: {w1}, and {w2}. One rule says {t1}, the other says "
                     "{t2}. What do you do first?",
        "tb_intro": "Here is how I understand {task}.",
        "tb_step_said": "Step {n}: {said}.",
        "tb_step": "Step {n}: {title}, because {reason}.",
        "tb_rule": "When {when}, you {then}.",
        "tb_at": "at {amount}", "tb_case": "in that case",
        "tb_applies": "  And {where}, it {does} apply. You said: \"{said}\"",
        "does": "does", "does_not": "does not",
        "tb_collision": "  When {other} at the same time, you said: \"{said}\"",
        "tb_near": "  Asked \"{question}\", you said: \"{said}\"",
        "tb_end": "Is that how it works?",
        "rule_text": "When {when}, {then}.",
    },
    "fr": {
        "boundary": "Prenons un cas à exactement {n}. Tu as dit que quand {when}, tu {then}. "
                    "Exactement {n}, c'est {side}, ou pas ?",
        "over": "au-dessus", "under": "en dessous",
        "a_source": "Une source publique",
        "source_amount": "{domain} dit : « {says} » Tu as dit {theirs}. Voici un cas à {between}, "
                         "là où les deux ne sont pas d'accord. Est-ce que tu {then}, ou pas ?",
        "source_quote": "{domain} dit : « {says} » Tu as dit : « {quote} » Laquelle des deux "
                        "suit-on ici ?",
        "collision": "Imagine que les deux arrivent en même temps : {w1}, et {w2}. Une règle dit "
                     "que tu {t1}, l'autre que tu {t2}. Que fais-tu en premier ?",
        "tb_intro": "Voici comment je comprends « {task} ».",
        "tb_step_said": "Étape {n} : {said}.",
        "tb_step": "Étape {n} : {title}, parce que {reason}.",
        "tb_rule": "Quand {when}, tu {then}.",
        "tb_at": "à {amount}", "tb_case": "dans ce cas",
        "tb_applies": "  Et {where}, elle {does}. Tu as dit : « {said} »",
        "does": "s'applique", "does_not": "ne s'applique pas",
        "tb_collision": "  Si en même temps {other}, tu as dit : « {said} »",
        "tb_near": "  À « {question} », tu as dit : « {said} »",
        "tb_end": "Est-ce que ça marche comme ça ?",
        "rule_text": "Quand {when}, tu {then}.",
    },
}


def language_of(code: str | None) -> str:
    return code if code in LANGUAGES else "en"


def say(language: str | None, key: str, **values) -> str:
    return PHRASES[language_of(language)][key].format(**values)


def money(value: float, language: str | None = "en") -> str:
    """5,000 in English, 5 000 in French; 1,250.50 and 1 250,50."""
    text = f"{value:,.0f}" if value == int(value) else f"{value:,.2f}"
    if language_of(language) == "fr":
        text = text.replace(",", " ").replace(".", ",")
    return text
