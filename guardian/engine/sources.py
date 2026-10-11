"""Where a public rule is looked up, and by whom.

The apprentice needs to read authoritative pages: tax authorities, standards bodies,
government guidance. Those are exactly the sites that refuse a naive fetch, so the backend
matters and is kept behind one small interface.

**BrightData** when its token is set: its SERP API returns what a search engine really
shows rather than what a scraper is served, and its Web Unlocker fetches pages that block
datacentre traffic. That is the difference between reading a tax authority's own page and
reading somebody's blog post about it.

**Tavily** otherwise. It is enough to prove the logic and it is honest about what it is:
a search index, not the source.

Which one answered is recorded on every source, because a claim checked against a blog is
not a claim checked against the law, and a reader deserves to know which they are holding.
"""

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from apu import config
from apu.logger import get_logger

logger = get_logger(__name__)

BRIGHTDATA_TOKEN_ENV = config.BRIGHTDATA_TOKEN_ENV
BRIGHTDATA_SERP_ZONE_ENV = config.BRIGHTDATA_SERP_ZONE_ENV
BRIGHTDATA_UNLOCKER_ZONE_ENV = config.BRIGHTDATA_UNLOCKER_ZONE_ENV
TAVILY_TOKEN_ENV = config.TAVILY_TOKEN_ENV

REQUEST_TIMEOUT = 30


class SourceRefused(RuntimeError):
    """
    The search service answered, and refused. A setting on its side, not an empty result.

    Measured: the SERP zone stopped answering because the machine's address was not on the
    zone's allow-list, and every rule came back "the search returned no results". An empty
    search and a refused one are not the same thing, and only one of them a person can fix.
    """

    def __init__(self, message: str, status: int = 0):
        super().__init__(message)
        self.status = status


def _reason(detail: str) -> str:
    """The service's own words, without the machine's network address."""
    import re

    found = re.search(r'details="([^"]+)"', detail or "")
    text = (found.group(1) if found else str(detail or ""))[:300]
    return re.sub(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", "this machine's address", text)


class NoBackend(RuntimeError):
    """Nothing is configured to look anything up."""


@dataclass(frozen=True)
class Source:
    """One page, and where it came from."""

    url: str
    title: str
    text: str
    backend: str                 # "brightdata" or "tavily": a blog is not the law
    retrieved_at: str
    published: str = ""          # the page's own date, when the search engine reports one
    # Only the search engine's snippet: the page itself did not open. A snippet is cut, often
    # mid-sentence, so it may agree with a rule but is not enough to contradict one.
    snippet_only: bool = False

    @property
    def domain(self) -> str:
        from urllib.parse import urlparse
        return (urlparse(self.url).hostname or "").removeprefix("www.")


class SearchBackend(Protocol):
    name: str

    def search(self, query: str, limit: int = 4) -> list[Source]:
        ...


def _now() -> str:
    return datetime.now(UTC).date().isoformat()


class TavilyBackend:
    """A search index. Good enough to prove the logic, honest about not being the source."""

    name = "tavily"

    def search(self, query: str, limit: int = 4) -> list[Source]:
        import httpx

        token = os.environ.get(TAVILY_TOKEN_ENV)
        if not token:
            raise NoBackend(f"{TAVILY_TOKEN_ENV} is not set.")
        response = httpx.post(
            "https://api.tavily.com/search",
            json={"api_key": token, "query": query, "max_results": limit,
                  "search_depth": "advanced", "include_raw_content": True},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        found = []
        for item in response.json().get("results", [])[:limit]:
            text = (item.get("raw_content") or item.get("content") or "").strip()
            if not text:
                continue
            found.append(Source(url=item.get("url", ""), title=item.get("title", ""),
                                text=text[:6000], backend=self.name, retrieved_at=_now(),
                                snippet_only=not item.get("raw_content")))
        return found


class BrightDataBackend:
    """
    The search engine's own results, and pages that refuse a plain fetch.

    Two calls. The SERP API returns what a browser in the right country would be shown,
    which matters because a capitalisation threshold is national: asking from the wrong
    place returns the wrong country's rule, confidently. The Unlocker then fetches each
    result, because the pages worth citing here are the ones that block datacentre traffic.
    """

    name = "brightdata"

    def __init__(self, country: str = ""):
        self.token = os.environ.get(BRIGHTDATA_TOKEN_ENV)
        self.serp_zone = os.environ.get(BRIGHTDATA_SERP_ZONE_ENV, "serp_api")
        # None when no Unlocker zone is set up. Measured: the default name pointed at a zone
        # that did not exist, and every page came back a 400, leaving the judge a snippet.
        self.unlocker_zone = os.environ.get(BRIGHTDATA_UNLOCKER_ZONE_ENV) or None
        self.country = country

    @property
    def is_configured(self) -> bool:
        return bool(self.token)

    def _request(self, zone: str, url: str) -> str:
        """
        One request through a zone, as Bright Data's JSON envelope: the status the target
        answered with is in it, so a refusal is told apart from an empty page.
        """
        import json

        import httpx

        payload = {"zone": zone, "url": url, "format": "json"}
        if self.country:
            payload["country"] = self.country   # measured: an empty country is a 400
        reply = httpx.post(
            "https://api.brightdata.com/request",
            headers={"Authorization": f"Bearer {self.token}",
                     "Content-Type": "application/json"},
            json=payload, timeout=REQUEST_TIMEOUT * 2,
        )
        reply.raise_for_status()
        try:
            envelope = reply.json()
        except ValueError:
            return reply.text
        if not isinstance(envelope, dict) or "status_code" not in envelope:
            return reply.text
        status = envelope.get("status_code")
        if status != 200:
            headers = envelope.get("headers") or {}
            raise SourceRefused(f"Bright Data refused the request ({status}): "
                                f"{_reason(headers.get('proxy-status') or str(envelope.get('body', '')))}",
                                status=status if isinstance(status, int) else 0)
        body = envelope.get("body", "")
        return body if isinstance(body, str) else json.dumps(body)

    def search(self, query: str, limit: int = 4) -> list[Source]:
        from urllib.parse import quote_plus

        if not self.is_configured:
            raise NoBackend(f"{BRIGHTDATA_TOKEN_ENV} is not set.")

        target = f"https://www.google.com/search?q={quote_plus(query)}&brd_json=1"
        try:
            serp = self._request(self.serp_zone, target)
        except SourceRefused as refused:
            # Measured: four searches in seven came back 502 and the next one answered. A
            # failure on the far side is tried once more; a refusal (an allow-list) is not.
            if refused.status < 500:
                raise
            logger.info("Bright Data answered %d, asking once more", refused.status)
            serp = self._request(self.serp_zone, target)
        results = _organic(serp)[:limit]
        if not results:
            logger.warning("No organic results came back for %r", query[:60])
            return []

        found = []
        for item in results:
            url = item.get("link") or item.get("url") or ""
            if not url:
                continue
            page = ""
            if self.unlocker_zone:
                try:
                    page = self._request(self.unlocker_zone, url)
                except Exception as error:  # a refusal included: a plain fetch is tried next
                    logger.info("The Unlocker could not open %s: %s", url, error)
            # A page that will not open is a page not cited, not a run abandoned: the page
            # as anyone would fetch it, and failing that, the search engine's own snippet.
            page = page or _plain_fetch(url)
            snippet_only = not page
            page = page or item.get("description", "")
            found.append(Source(
                url=url, title=item.get("title", ""),
                text=_readable(page)[:6000],
                backend=self.name, retrieved_at=_now(), snippet_only=snippet_only,
                # The page's own date when the SERP carries one. A source published after
                # the expert learned the rule is the interesting case, so it is kept
                # rather than reduced to "corroborated".
                published=str(item.get("date") or item.get("published_date") or "")))
        return found


def _plain_fetch(url: str) -> str:
    """The page as a browser would fetch it, or "" when it will not come."""
    import httpx

    try:
        reply = httpx.get(url, timeout=15, follow_redirects=True,
                          headers={"User-Agent": "Mozilla/5.0 (compatible; Urithi source check)"})
    except Exception as error:
        logger.info("Could not fetch %s: %s", url, error)
        return ""
    kind = reply.headers.get("content-type", "")
    if reply.status_code != 200 or not ("html" in kind or "text" in kind):
        return ""
    return reply.text[:2_000_000]


def _organic(serp: str) -> list[dict]:
    """
    The organic results, whichever JSON the zone is set to return.

    Full JSON nests them under "organic", Light JSON has been seen to return the list
    itself, and a misconfigured zone returns HTML. A reader that only understands one of
    those turns a settings choice made months earlier into a feature that silently stops
    working.
    """
    import json

    try:
        parsed = json.loads(serp)
    except json.JSONDecodeError:
        logger.warning("The SERP zone returned something that is not JSON. "
                       "Set its data format to Full JSON.")
        return []
    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]
    for key in ("organic", "organic_results", "results"):
        found = parsed.get(key)
        if isinstance(found, list):
            return [item for item in found if isinstance(item, dict)]
    return []


def _readable(html: str) -> str:
    """Tags out, text left. Enough for a model to read a threshold out of a page."""
    import re

    without_script = re.sub(r"(?is)<(script|style|nav|footer|header)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", without_script)
    return re.sub(r"\s+", " ", text).strip()


class FallbackBackend:
    """
    The first search service that answers, in order. Which one did is recorded on every
    source, as before, so a citation from a search index never passes for one from the SERP.
    """

    def __init__(self, backends: list):
        self.backends = backends
        self.name = backends[0].name

    def search(self, query: str, limit: int = 4) -> list[Source]:
        refused = []
        for backend in self.backends:
            try:
                found = backend.search(query, limit=limit)
            except NoBackend:
                continue
            except Exception as error:
                logger.warning("%s could not search, trying the next: %s", backend.name, error)
                refused.append(f"{backend.name}: {error}")
                continue
            if found:
                self.name = backend.name
                return found
        if refused:
            raise SourceRefused("; ".join(refused))
        return []


def get_backend(country: str = "") -> SearchBackend:
    """
    BrightData first when it is configured, then Tavily, and an error when neither is.

    Deliberately not a silent fallback to nothing: a provenance check that quietly returns
    "no sources found" because no backend exists would mark every rule a house rule, which
    is the one answer that looks like a result. A service that refuses hands over to the
    next one, and if every one refuses, that is what the check says.
    """
    configured = []
    brightdata = BrightDataBackend(country=country)
    if brightdata.is_configured:
        configured.append(brightdata)
    if os.environ.get(TAVILY_TOKEN_ENV):
        configured.append(TavilyBackend())
    if not configured:
        raise NoBackend(
            f"Set {BRIGHTDATA_TOKEN_ENV} or {TAVILY_TOKEN_ENV} to check a rule against a source.")
    return configured[0] if len(configured) == 1 else FallbackBackend(configured)