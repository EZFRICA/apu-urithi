"""Is the rule the expert taught still the rule?

Sabine has run accounts payable for 24 years and retires in 18 months. Most of what she
knows is judgment, and judgment is what this whole system exists to capture. But some of
what she "knows" is not hers at all: it is a public rule she learned once and has not
revisited since, and public rules move.

"Equipment over five thousand euros is always capex" is not an opinion. It is a
capitalisation threshold, it comes from somewhere, and it has a date. A Work Map that
teaches it without checking hands a new hire an error with 24 years of authority behind it,
which is worse than handing them nothing.

So every rule gets looked up, and lands in one of four states:

- **corroborated**: a public source says the same thing. The citation travels with the rule.
- **conflicted**: a public source says something different. This is the valuable one, and it
  is a flag for a person, never a correction. The apprentice does not overrule a 24-year
  expert on the strength of a search result.
- **house rule**: nothing public says anything. Perfectly legitimate, and worth knowing:
  telling a new hire which rules are law and which are "how we do it here" is exactly the
  distinction that lives only in people's heads.
- **unchecked**: the lookup did not happen or could not be read. Never dressed up as one of
  the other three, because "verified" is the one answer that must never be guessed.
"""

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from apu.inference.llm import call_main_model
from apu.logger import get_logger
from guardian.engine import jsonish, thresholds
from guardian.engine.sources import NoBackend, Source, SourceRefused, get_backend
from guardian.engine.workmap import Guardrail

logger = get_logger(__name__)


# Per search. The SERP returns up to ten; past six the sources are blogs quoting the ones
# above them, and each one read is a model call.
SOURCES_PER_QUERY = 6


class Verdict(StrEnum):
    CORROBORATED = "corroborated"
    CONFLICTED = "conflicted"
    HOUSE_RULE = "house_rule"
    UNCHECKED = "unchecked"


@dataclass(frozen=True)
class Citation:
    url: str
    title: str
    domain: str
    says: str                # what the source states, in the source's terms
    agrees: bool
    jurisdiction: str = ""   # where this page's rule applies, or "any"
    published: str = ""
    backend: str = ""
    retrieved_at: str = ""
    snippet_only: bool = False   # read from a search snippet, the page itself did not open


@dataclass
class Provenance:
    verdict: Verdict
    checked_at: str
    query: str = ""
    citations: list[Citation] = field(default_factory=list)
    note: str = ""           # why it is unchecked, or what the conflict is

    @property
    def is_flag(self) -> bool:
        return self.verdict is Verdict.CONFLICTED

    def as_dict(self) -> dict:
        return {"verdict": str(self.verdict), "checked_at": self.checked_at,
                "query": self.query, "note": self.note,
                "citations": [asdict(c) for c in self.citations]}


QUERY_SYSTEM = (
    "You turn one rule someone teaches into web searches that would find a published "
    "reference for it, if there is one.\n"
    "Return JSON only: {\"query\": \"...\", \"local_query\": \"...\", \"public\": true|false}\n"
    "- \"local_query\": the same search in the jurisdiction's own language and its own legal "
    "terms, the words its tax authority would use. Empty when that language is English or "
    "when no jurisdiction is given.\n"
    "- \"public\": false if this is plainly an internal habit with no external authority "
    "(who to copy on an email, which folder to file in). true if a law, a standard, a tax "
    "rule, a reference grammar or dictionary, a style guide or another published guideline "
    "could govern it.\n"
    "- \"query\": the words someone would type to find that authority. Include the "
    "jurisdiction and the year if the rule implies one. Empty string when public is false."
)

JUDGE_SYSTEM = (
    "You compare one rule an expert stated with one page, and report only what the page "
    "says.\n"
    "Return JSON only: {\"relevant\": true|false, \"jurisdiction\": \"...\", "
    "\"agrees\": true|false, \"says\": \"...\"}\n"
    "- \"relevant\": does this page actually address the rule's subject? Most pages do not.\n"
    "- \"jurisdiction\": the two-letter country code the page's rule applies to, or "
    "\"any\" when it is not country specific. A university's internal policy applies to "
    "that university, so give its country.\n"
    "- \"agrees\": does the page state the same threshold, condition or requirement? It "
    "agrees when it gives the same answer for the cases the rule covers, even in other words "
    "or by a more general principle; it disagrees only when following it would give a "
    "different answer.\n"
    "- \"says\": what the page states, in one clause, with its number if it has one. "
    "Quote the page, do not summarise what you believe to be true.\n"
    "A page about a neighbouring question (how a word is spelled, when it takes a capital) "
    "does not address the subject.\n"
    "If the page does not address the subject, relevant is false and the rest is ignored. "
    "Never fill a gap from your own knowledge: a page that is silent is silent."
)


COUNTRY_NAMES = {"de": "Germany", "fr": "France", "ci": "Côte d'Ivoire", "us": "United States",
                 "gb": "United Kingdom", "es": "Spain", "it": "Italy", "nl": "Netherlands",
                 "be": "Belgium", "ch": "Switzerland", "at": "Austria", "sn": "Senegal"}


def _query_for(rail: Guardrail, context: str, country: str = "") -> tuple[list[str], bool]:
    # The country goes in the request, because the server only knows the task's name.
    # Measured: without it, the query became "capitalization threshold equipment capex
    # accounting standard", no jurisdiction at all, and the search returned nothing.
    where = COUNTRY_NAMES.get(country.lower(), country.upper()) if country else ""
    try:
        parsed = jsonish.loads(call_main_model([
            {"role": "system", "content": QUERY_SYSTEM},
            {"role": "user", "content":
                f"Work: {context}\n"
                + (f"Jurisdiction: {where}. Search for that country's rule.\n" if where else "")
                + f"The rule: when {rail.when}, {rail.then}\n"
                f"They said it like this: {rail.quote}"},
        ], temperature=0.0, max_tokens=2000))
    except Exception as error:
        logger.warning("Could not form a search for %r: %s", rail.when[:50], error)
        return [], True
    if not isinstance(parsed, dict):
        return [], True
    # Two searches, in English and in the country's language. Measured: a German tax
    # threshold is written up on German sites in German, and an English query reached one
    # usable source in five runs out of five; the rest were cut before the number.
    queries = [str(parsed.get(k, "")).strip() for k in ("query", "local_query")]
    return [q for i, q in enumerate(queries) if q and q not in queries[:i]], \
        bool(parsed.get("public", True))


# Not sources: anyone posts there, and nobody answers for it. Measured: "use an before a
# vowel sound (b, c, d, f...)", a garbled post on a social network, was the one page that
# disagreed with four grammar references, and it alone made a textbook rule "conflicted".
NOT_AN_AUTHORITY = ("facebook.com", "youtube.com", "youtu.be", "tiktok.com", "instagram.com",
                    "x.com", "twitter.com", "reddit.com", "quora.com", "pinterest.com",
                    "linkedin.com", "threads.net")


def _an_authority(domain: str) -> bool:
    domain = (domain or "").lower()
    return not any(domain == d or domain.endswith("." + d) for d in NOT_AN_AUTHORITY)


def _applies_here(citation_jurisdiction: str, country: str) -> bool:
    """
    Whether a page speaks for the place the work happens.

    Measured, and it is why this function exists: asked about a German capitalisation
    threshold, the first run came back with an American university's internal accounting
    manual and raised a conflict on it. A rule flagged against the wrong country's law is
    worse than no flag, because somebody acts on it.
    """
    if not country:
        return True   # knowledge with no jurisdiction: grammar is not a country's law
    found = (citation_jurisdiction or "").strip().lower()
    return found in ("", "any", "international", country.lower())


def _judge(rail: Guardrail, source: Source) -> Citation | None:
    try:
        parsed = jsonish.loads(call_main_model([
            {"role": "system", "content": JUDGE_SYSTEM},
            {"role": "user", "content":
                f"The rule: when {rail.when}, {rail.then}\n\n"
                f"The page ({source.domain}):\n{source.text[:5000]}"},
        ], temperature=0.0, max_tokens=2000))
    except Exception as error:
        logger.info("Could not read %s against the rule: %s", source.domain, error)
        return None
    if not isinstance(parsed, dict) or not parsed.get("relevant"):
        return None
    return Citation(
        url=source.url, title=source.title, domain=source.domain,
        says=str(parsed.get("says", "")).strip(),
        agrees=bool(parsed.get("agrees")),
        jurisdiction=str(parsed.get("jurisdiction", "")).strip(),
        published=source.published, backend=source.backend,
        retrieved_at=source.retrieved_at, snippet_only=source.snippet_only,
    )


def check(rail: Guardrail, context: str = "", country: str = "") -> Provenance:
    """
    Look the rule up, and say honestly which of the four states it is in.

    Nothing here changes the rule. A conflict is written down and shown to a person; the
    expert's sentence stays exactly as they said it.
    """
    now = datetime.now(UTC).isoformat()

    queries, public = _query_for(rail, context, country)
    # A number in a rule nearly always comes from somewhere: a tax threshold, a limit in a
    # policy, a standard. Measured: the same capitalisation threshold was judged "no external
    # authority" in one run and found contradicted by German law in the next. The costs are
    # not symmetric: checking costs one search, skipping a public rule teaches a wrong number
    # for as long as the map is used. So a rule with an amount in it is always checked.
    if not public and thresholds.threshold_in(rail.when) is not None:
        public = True
        queries = queries or [f"{rail.when} {COUNTRY_NAMES.get(country, '')} threshold".strip()]
    query = " | ".join(queries)
    if not public:
        return Provenance(verdict=Verdict.HOUSE_RULE, checked_at=now,
                          note="No external authority would govern this.")
    if not queries:
        return Provenance(verdict=Verdict.UNCHECKED, checked_at=now,
                          note="No search could be formed for this rule.")

    try:
        backend = get_backend(country=country)
        sources, seen = [], set()
        for one in queries:
            for found in backend.search(one, limit=SOURCES_PER_QUERY):
                if found.url not in seen:
                    seen.add(found.url)
                    sources.append(found)
    except (NoBackend, SourceRefused) as error:
        return Provenance(verdict=Verdict.UNCHECKED, checked_at=now, query=query,
                          note=str(error))
    except Exception as error:
        logger.warning("The lookup failed for %r: %s", query[:60], error)
        return Provenance(verdict=Verdict.UNCHECKED, checked_at=now, query=query,
                          note=f"The lookup failed: {error}")

    if not sources:
        # Nothing came back. That is a failed lookup, not a finding: it says nothing about
        # whether a public rule exists. It used to be reported as "house rule", which states
        # that no authority governs this, on the strength of an empty response.
        return Provenance(verdict=Verdict.UNCHECKED, checked_at=now, query=query,
                          note="The search returned no results, which is not evidence that "
                               "no public rule exists.")

    judged = [c for c in (_judge(rail, s) for s in sources if _an_authority(s.domain)) if c]
    citations = [c for c in judged if _applies_here(c.jurisdiction, country)]
    elsewhere = [c for c in judged if c not in citations]
    if elsewhere:
        logger.info("Set aside %d source(s) that speak for another country: %s",
                    len(elsewhere), ", ".join(f"{c.domain} ({c.jurisdiction})"
                                              for c in elsewhere))

    if not citations:
        note = "Nothing public was found that addresses this rule."
        if elsewhere:
            note += (f" {len(elsewhere)} page(s) addressed it for another country "
                     f"({', '.join(sorted({c.jurisdiction for c in elsewhere}))}) "
                     f"and were set aside.")
        return Provenance(verdict=Verdict.HOUSE_RULE, checked_at=now, query=query,
                          note=note)

    # Measured: "you should use an if the word that follows sounds like it begins with a ...",
    # a snippet cut mid-sentence, was read as Merriam-Webster disagreeing with a textbook rule.
    disagreeing = [c for c in citations if not c.agrees and not c.snippet_only]
    citations = [c for c in citations if c.agrees or not c.snippet_only]
    if not citations:
        return Provenance(verdict=Verdict.HOUSE_RULE, checked_at=now, query=query,
                          note="Only search snippets addressed this rule, too short to rely on.")
    if disagreeing:
        return Provenance(
            verdict=Verdict.CONFLICTED, checked_at=now, query=query, citations=citations,
            note=(f"{disagreeing[0].domain} states: {disagreeing[0].says} "
                  f"The expert said: {rail.quote}"))

    return Provenance(verdict=Verdict.CORROBORATED, checked_at=now, query=query,
                      citations=citations)


def from_dict(data: dict | None) -> Provenance | None:
    """A stored provenance, read back. Unknown or missing is None, not a false verdict."""
    if not data:
        return None
    try:
        return Provenance(
            verdict=Verdict(data.get("verdict", "unchecked")),
            checked_at=data.get("checked_at", ""),
            query=data.get("query", ""),
            note=data.get("note", ""),
            citations=[Citation(**c) for c in data.get("citations", [])],
        )
    except (ValueError, TypeError) as error:
        logger.info("Could not read a stored provenance: %s", error)
        return None


__all__ = ["Citation", "Provenance", "Verdict", "check", "from_dict"]
