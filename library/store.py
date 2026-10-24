"""The library's storage: Neo4j online, or memory for tests and a machine without it.

Both implement one contract, and the tests hold both to it:

  - publish() replaces a body's previous version as one unit of work, so a learner never
    reads half of an old version and half of a new one;
  - search() filters by access level and status INSIDE the vector search, before any
    ranking reaches the caller: a unit a learner may not see is not in the result, however
    close it is to the question, so it can never reach a model; within one knowledge, the words
    of a question asked in its language are ranked too (library/keywords.py), under the same filter;
  - what comes back with a unit (its prerequisites, the cases that decide it) is filtered
    by the same levels: a case reveals the units it decides;
  - withdraw() removes a body and everything hanging from it;
  - every method names the organisation, and nothing of another organisation is read,
    written or ranked: a body is the same name in two organisations, two bodies.
"""

import os
from contextlib import contextmanager
from dataclasses import asdict

from apu import config
from apu.embeddings import get_embedder
from apu.logger import get_logger
from library import config as library_config
from library import keywords
from library.model import (ACCESS_LEVELS, LINK_TYPES, KnowledgeError, LibraryUnavailable, Publication,
                           check_organisation)

logger = get_logger(__name__)

PUBLISHED = "published"
CANDIDATES = 20       # read by meaning and by words before the two rankings are fused and cut to k


def _check_allowed(allowed) -> list[str]:
    allowed = list(allowed)
    unknown = [a for a in allowed if a not in ACCESS_LEVELS]
    if unknown or not allowed:
        raise KnowledgeError(f"Access levels to search with must be some of {ACCESS_LEVELS}.")
    return allowed


class MemoryKnowledgeStore:
    """The contract in plain Python: exact cosine, filter first, then rank."""

    def __init__(self):
        self.bodies: dict[tuple[str, str], dict] = {}

    def publish(self, publication: Publication) -> dict:
        organisation = check_organisation(publication.body.organisation)
        vectors = get_embedder().embed([u.embedding_text() for u in publication.units])
        self.bodies[(organisation, publication.body.body_id)] = {
            "body": asdict(publication.body),
            "units": [{**u.as_dict(), "embedding": v} for u, v in zip(publication.units, vectors)],
            "links": [asdict(link) for link in publication.links],
            "cases": [asdict(c) for c in publication.cases],
            "sources": [asdict(s) for s in publication.sources],
            "evidence": [asdict(e) for e in publication.evidence],
        }
        return _summary(publication)

    def _of(self, organisation: str) -> list[dict]:
        organisation = check_organisation(organisation)
        return [b for (org, _), b in self.bodies.items() if org == organisation]

    def bodies_for(self, organisation: str, allowed) -> list[dict]:
        allowed = _check_allowed(allowed)
        return [{**b["body"], "units": sum(1 for u in b["units"] if u["access"] in allowed)}
                for b in self._of(organisation)]

    def search(self, organisation: str, query: str, allowed, k: int = 5, body_id: str | None = None,
               lang: str | None = None) -> list[dict]:
        allowed = _check_allowed(allowed)
        q = get_embedder().embed([query])[0]
        eligible = [(u, b) for b in self._of(organisation) for u in b["units"]
                    if u["status"] == PUBLISHED and u["access"] in allowed
                    and (body_id is None or u["body_id"] == body_id)]
        cosine = {u["unit_id"]: sum(x * y for x, y in zip(q, u["embedding"])) for u, _ in eligible}
        by_meaning = [u["unit_id"] for u, _ in sorted(eligible, key=lambda ub: -cosine[ub[0]["unit_id"]])]
        # Words only within one knowledge, among what is eligible, taught in the question's language.
        same = [(u, b) for u, b in eligible if body_id and keywords.same_language(lang, b["body"].get("language"))]
        scores = keywords.bm25(query, [f"{u['text']}\n{u['quote']}" for u, _ in same])
        by_words = [u["unit_id"] for (u, _), s in sorted(zip(same, scores), key=lambda us: -us[1]) if s > 0]
        found = {u["unit_id"]: (u, b) for u, b in eligible}
        ranked = [found[uid] for uid in keywords.fuse(by_meaning, by_words)]
        results = []
        for unit, body in ranked[:k]:
            score = cosine[unit["unit_id"]]
            visible = {u["unit_id"]: u for u in body["units"] if u["access"] in allowed}
            results.append({
                "unit": _public(unit), "score": round(score, 4), "guardian": body["body"]["guardian"],
                "prerequisites": [{"unit_id": v["unit_id"], "text": v["text"]}
                                  for link in body["links"] if link["type"] == "PREREQUISITE_OF"
                                  and link["target_id"] == unit["unit_id"]
                                  for v in [visible.get(link["source_id"])] if v],
                "cases": [_case(c) for c in body["cases"]
                          if unit["unit_id"] in c["decides"] and c["access"] in allowed],
                "sources": [_source(s) for s in body["sources"] if s["unit_id"] == unit["unit_id"]],
            })
        return results

    def body_units(self, organisation: str, body_id: str, allowed) -> dict | None:
        """A body as a learner may see it: its units, the links between them, its cases."""
        allowed = _check_allowed(allowed)
        found = self.bodies.get((check_organisation(organisation), body_id))
        if found is None:
            return None
        units = [_public(u) for u in found["units"]
                 if u["status"] == PUBLISHED and u["access"] in allowed]
        visible = {u["unit_id"] for u in units}
        return {"body": dict(found["body"]), "units": units,
                "links": _bridged(found["links"], visible),
                "cases": [_case_full(c) for c in found["cases"]
                          if c["access"] in allowed and set(c["decides"]) <= visible],
                "sources": [_source(src) | {"unit_id": src["unit_id"]} for src in found["sources"]
                            if src["unit_id"] in visible],
                "evidence": [_evidence(e) for e in found.get("evidence", [])
                             if e["unit_id"] in visible and e["access"] in allowed]}

    def version_of(self, organisation: str, body_id: str) -> int:
        return self.bodies.get((check_organisation(organisation), body_id), {}).get("body", {}).get("version", 0)

    def stamp_of(self, organisation: str, body_id: str) -> tuple | None:
        """What changes whenever the body does: its version and when it was published; None if absent."""
        body = self.bodies.get((check_organisation(organisation), body_id), {}).get("body")
        return (body.get("version", 0), body.get("published_at")) if body else None

    def withdraw(self, organisation: str, body_id: str) -> bool:
        return self.bodies.pop((check_organisation(organisation), body_id), None) is not None


def _ranked_by_words(query: str, lang: str, texts: list[dict]) -> list[str]:
    """Unit ids of one knowledge by the question's words (BM25, library/keywords.py), as the memory store ranks them.

    Not by a full-text index: measured on 2026-10-15, Neo4j's index scored the text and the quote apart and
    lost the gain measured (30 first in 38 either way, against 32 ranked here)."""
    same = [t for t in texts if keywords.same_language(lang, t["language"])]
    scores = keywords.bm25(query, [f"{t['text']}\n{t['quote']}" for t in same])
    return [t["id"] for t, s in sorted(zip(same, scores), key=lambda ts: -ts[1]) if s > 0]


class Neo4jKnowledgeStore:
    """[B] in Neo4j: a graph, with a vector index that filters as it searches."""

    # Named for what it filters on: the index before organisations filtered on access alone,
    # and is dropped when this one is made (ensure_schema).
    INDEX = "unit_embedding_org"
    _OLD_INDEX = "unit_embedding"

    def __init__(self, uri: str, user: str, password: str, database: str | None = None):
        from neo4j import GraphDatabase

        # Aura closes a connection that has been idle a while; measured, the next query on it
        # failed with "connection reset by peer". A connection idle longer than this is checked
        # before use, and every query below runs in a managed transaction, which is retried.
        self.driver = GraphDatabase.driver(uri, auth=(user, password), liveness_check_timeout=30,
                                           max_connection_lifetime=1800)
        self.database = database or None
        self._schema_ready = False

    @contextmanager
    def _session(self):
        """Every query goes through here, so a library out of reach is one error, said by its kind:
        the driver's own message names the address."""
        from neo4j.exceptions import AuthError, ServiceUnavailable, SessionExpired

        try:
            with self.driver.session(database=self.database) as session:
                yield session
        except (ServiceUnavailable, SessionExpired, AuthError) as error:
            logger.warning("The library cannot be reached (%s).", type(error).__name__)
            raise LibraryUnavailable() from None

    def _read(self, query: str, **params) -> list[dict]:
        with self._session() as s:
            return s.execute_read(lambda tx: tx.run(query, **params).data())

    def _write(self, query: str, **params) -> list[dict]:
        with self._session() as s:
            return s.execute_write(lambda tx: tx.run(query, **params).data())

    def ensure_schema(self) -> None:
        if self._schema_ready:
            return
        with self._session() as s:
            # Published before organisations existed: those records belong to the one
            # organisation there was, said in configuration rather than guessed per record.
            s.run("MATCH (n) WHERE (n:Body OR n:Unit OR n:Case OR n:Source OR n:Guardian) "
                  "AND n.organisation IS NULL SET n.organisation = $legacy",
                  legacy=config.LEGACY_ORGANISATION).consume()
            for statement in (
                "DROP CONSTRAINT body_id IF EXISTS",
                "DROP CONSTRAINT unit_id IF EXISTS",
                "DROP CONSTRAINT case_id IF EXISTS",
                f"DROP INDEX {self._OLD_INDEX} IF EXISTS",
                # The same name in two organisations is two bodies.
                "CREATE CONSTRAINT body_key IF NOT EXISTS FOR (b:Body) REQUIRE (b.organisation, b.body_id) IS UNIQUE",
                "CREATE CONSTRAINT unit_key IF NOT EXISTS FOR (u:Unit) REQUIRE (u.organisation, u.unit_id) IS UNIQUE",
                "CREATE CONSTRAINT case_key IF NOT EXISTS FOR (c:Case) REQUIRE (c.organisation, c.case_id) IS UNIQUE",
                # The properties a search filters on are stored beside each vector, which is
                # what lets the filter run inside the index rather than after it: the
                # organisation first, then the access level.
                f"CYPHER 25 CREATE VECTOR INDEX {self.INDEX} IF NOT EXISTS FOR (u:Unit) ON u.embedding "
                "WITH [u.organisation, u.access, u.status, u.body_id] OPTIONS {indexConfig: "
                f"{{`vector.dimensions`: {config.EMBEDDING_DIM}, `vector.similarity_function`: 'cosine'}}}}",
            ):
                s.run(statement).consume()
            s.run("CALL db.awaitIndexes(120)").consume()
        self._schema_ready = True

    def publish(self, publication: Publication) -> dict:
        organisation = check_organisation(publication.body.organisation)
        self.ensure_schema()
        vectors = get_embedder().embed([u.embedding_text() for u in publication.units])
        body = asdict(publication.body)
        units = [{**u.as_dict(), "embedding": v, "organisation": organisation}
                 for u, v in zip(publication.units, vectors)]
        cases = [{**asdict(c), "decides": list(c.decides), "organisation": organisation} for c in publication.cases]
        sources = [{**asdict(s), "organisation": organisation} for s in publication.sources]
        evidence = [{**asdict(e), "organisation": organisation} for e in publication.evidence]
        with self._session() as s:
            s.execute_write(self._replace, body, units, publication.links, cases, sources, evidence)
        return _summary(publication)

    @staticmethod
    def _replace(tx, body, units, links, cases, sources, evidence=()):
        org = body["organisation"]
        tx.run("MATCH (n) WHERE (n:Unit OR n:Case OR n:Source OR n:Evidence) AND n.organisation = $org "
               "AND n.body_id = $id DETACH DELETE n", org=org, id=body["body_id"])
        tx.run("MERGE (b:Body {organisation: $b.organisation, body_id: $b.body_id}) SET b += $b "
               "MERGE (g:Guardian {organisation: $b.organisation, name: $b.guardian}) MERGE (g)-[:GUARDS]->(b)", b=body)
        tx.run("MATCH (b:Body {organisation: $org, body_id: $id}) UNWIND $units AS u "
               "CREATE (n:Unit) SET n = u CREATE (n)-[:BELONGS_TO]->(b)", org=org, id=body["body_id"], units=units)
        for link_type in LINK_TYPES:   # a closed list: the type is never taken from input
            batch = [{"s": link.source_id, "t": link.target_id} for link in links if link.type == link_type]
            if batch:
                tx.run(f"UNWIND $batch AS l MATCH (a:Unit {{organisation: $org, unit_id: l.s}}), "
                       f"(c:Unit {{organisation: $org, unit_id: l.t}}) CREATE (a)-[:{link_type}]->(c)",
                       batch=batch, org=org)
        tx.run("UNWIND $cases AS c CREATE (n:Case) SET n = c "
               "WITH n, c UNWIND c.decides AS uid MATCH (u:Unit {organisation: $org, unit_id: uid}) "
               "CREATE (n)-[:DECIDES]->(u)", cases=cases, org=org)
        for relation in ("SUPPORTS", "DISAGREES"):
            batch = [src for src in sources if src["relation"] == relation]
            if batch:
                tx.run(f"UNWIND $batch AS s MATCH (u:Unit {{organisation: $org, unit_id: s.unit_id}}) "
                       f"CREATE (n:Source) SET n = s CREATE (n)-[:{relation} {{says: s.says}}]->(u)",
                       batch=batch, org=org)
        if evidence:
            tx.run("UNWIND $batch AS e MATCH (u:Unit {organisation: $org, unit_id: e.unit_id}) "
                   "CREATE (n:Evidence) SET n = e CREATE (n)-[:EVIDENCES]->(u)", batch=list(evidence), org=org)

    def bodies_for(self, organisation: str, allowed) -> list[dict]:
        organisation = check_organisation(organisation)
        allowed = _check_allowed(allowed)
        self.ensure_schema()
        rows = self._read("MATCH (b:Body {organisation: $org}) OPTIONAL MATCH (u:Unit)-[:BELONGS_TO]->(b) "
                          "WHERE u.access IN $allowed RETURN b{.*} AS body, count(u) AS units",
                          org=organisation, allowed=allowed)
        return [{**r["body"], "units": r["units"]} for r in rows]

    # What comes with each unit found, filtered by the same levels; shared by both ways of finding it.
    _WITH_UNIT = (
        "MATCH (u)-[:BELONGS_TO]->(b:Body) "
        "OPTIONAL MATCH (p:Unit)-[:PREREQUISITE_OF]->(u) WHERE p.access IN $allowed "
        "WITH u, score, b, collect(DISTINCT p{.unit_id, .text}) AS prerequisites "
        "OPTIONAL MATCH (c:Case)-[:DECIDES]->(u) WHERE c.access IN $allowed "
        "WITH u, score, b, prerequisites, collect(DISTINCT c{.*}) AS cases "
        # By type name in a WHERE, not in the pattern: a pattern naming a type the database
        # has never held draws a warning on every search until one exists.
        "OPTIONAL MATCH (s:Source)-[r]->(u) WHERE type(r) IN ['SUPPORTS', 'DISAGREES'] "
        "RETURN u{.*, embedding: null} AS unit, score, b.guardian AS guardian, prerequisites, "
        "cases, collect(DISTINCT s{.*}) AS sources ORDER BY score DESC")

    def search(self, organisation: str, query: str, allowed, k: int = 5, body_id: str | None = None,
               lang: str | None = None) -> list[dict]:
        organisation = check_organisation(organisation)
        allowed = _check_allowed(allowed)
        self.ensure_schema()
        q = get_embedder().embed([query])[0]
        body_filter = " AND u.body_id = $body_id" if body_id else ""
        eligible = "u.organisation = $org AND u.status = $published AND u.access IN $allowed" + body_filter
        params = {"q": q, "org": organisation, "published": PUBLISHED, "allowed": allowed, "body_id": body_id,
                  "n": max(k, CANDIDATES)}
        by_meaning = ("MATCH (u) SEARCH u IN (VECTOR INDEX " + self.INDEX + " FOR $q "
                      "WHERE " + eligible + " LIMIT $n) SCORE AS score " + self._WITH_UNIT)
        words_too = bool(lang and body_id)
        # Within one knowledge, its parts' words are read in the same query: measured on Aura on 2026-10-15, a
        # second query took the median search from 410 to 813 ms.
        cypher = ("CYPHER 25 " + by_meaning if not words_too else
                  "CYPHER 25 CALL () { " + by_meaning + " } WITH collect({unit: unit, score: score, guardian: guardian, "
                  "prerequisites: prerequisites, cases: cases, sources: sources}) AS rows "
                  "CALL () { MATCH (u:Unit)-[:BELONGS_TO]->(b:Body) WHERE " + eligible +
                  " RETURN collect({id: u.unit_id, text: u.text, quote: u.quote, language: b.language}) AS texts } "
                  "RETURN rows, texts")
        try:
            found = self._read(cypher, **params)
        except Exception:
            # Measured on Aura: a filtered vector search that no unit matches (an organisation
            # with nothing published, a body withdrawn) failed inside the database, "Index
            # 33554431 out of bounds for length 1", rather than finding nothing. Nothing to find
            # is said by a count; any other failure is raised as it came.
            left = self._read("MATCH (u:Unit) WHERE u.organisation = $org AND u.status = $published "
                              "AND u.access IN $allowed" + body_filter + " RETURN count(u) AS n",
                              org=organisation, published=PUBLISHED, allowed=allowed, body_id=body_id)
            if left and left[0]["n"] == 0:
                return []
            raise
        rows = (found[0]["rows"] if found else []) if words_too else found
        by_id = {r["unit"]["unit_id"]: r for r in rows}
        by_words = _ranked_by_words(query, lang, found[0]["texts"]) if words_too and found else []
        order = keywords.fuse([r["unit"]["unit_id"] for r in rows], by_words)[:k]
        missing = [uid for uid in order if uid not in by_id]
        if missing:
            # Found by its words alone: read with its meaning's score, under the same filter as any other.
            for r in self._read("UNWIND $ids AS id MATCH (u:Unit {organisation: $org, unit_id: id}) WHERE " + eligible +
                                " WITH u, vector.similarity.cosine(u.embedding, $q) AS score " + self._WITH_UNIT,
                                ids=missing, **params):
                by_id[r["unit"]["unit_id"]] = r
        return [{"unit": _public(r["unit"]), "score": round(r["score"], 4), "guardian": r["guardian"],
                 "prerequisites": r["prerequisites"], "cases": [_case(c) for c in r["cases"]],
                 "sources": [_source(src) for src in r["sources"]]} for uid in order for r in [by_id.get(uid)] if r]

    def body_units(self, organisation: str, body_id: str, allowed) -> dict | None:
        organisation = check_organisation(organisation)
        allowed = _check_allowed(allowed)
        self.ensure_schema()
        found = self._read("MATCH (b:Body {organisation: $org, body_id: $id}) RETURN b{.*} AS b",
                           org=organisation, id=body_id)
        if not found:
            return None
        units = self._read("MATCH (u:Unit {organisation: $org, body_id: $id}) WHERE u.status = $published "
                           "AND u.access IN $allowed RETURN u{.*, embedding: null} AS u",
                           org=organisation, id=body_id, published=PUBLISHED, allowed=allowed)
        visible = [r["u"]["unit_id"] for r in units]
        # Every link of the body, read here and never returned: _bridged keeps the order
        # across hidden parts and names only visible ones.
        every = self._read("MATCH (a:Unit {organisation: $org, body_id: $id})-[r]->(c:Unit {organisation: $org, body_id: $id}) "
                           "RETURN a.unit_id AS source_id, c.unit_id AS target_id, type(r) AS type",
                           org=organisation, id=body_id)
        links = _bridged(every, set(visible))
        cases = self._read("MATCH (c:Case {organisation: $org, body_id: $id}) WHERE c.access IN $allowed "
                           "AND all(uid IN c.decides WHERE uid IN $v) RETURN c{.*} AS c",
                           org=organisation, id=body_id, allowed=allowed, v=visible)
        sources = self._read("MATCH (src:Source {organisation: $org})-[]->(u:Unit {organisation: $org}) "
                             "WHERE u.unit_id IN $v RETURN src{.*} AS s", org=organisation, v=visible)
        evidence = self._read("MATCH (e:Evidence {organisation: $org, body_id: $id}) WHERE e.unit_id IN $v "
                              "AND e.access IN $allowed RETURN e{.*} AS e", org=organisation, id=body_id, v=visible,
                              allowed=allowed)
        return {"body": found[0]["b"], "units": [_public(r["u"]) for r in units], "links": links,
                "cases": [_case_full(r["c"]) for r in cases],
                "sources": [_source(r["s"]) | {"unit_id": r["s"]["unit_id"]} for r in sources],
                "evidence": [_evidence(r["e"]) for r in evidence]}

    def version_of(self, organisation: str, body_id: str) -> int:
        organisation = check_organisation(organisation)
        self.ensure_schema()
        rows = self._read("MATCH (b:Body {organisation: $org, body_id: $id}) RETURN b.version AS v",
                          org=organisation, id=body_id)
        return rows[0]["v"] if rows else 0

    def stamp_of(self, organisation: str, body_id: str) -> tuple | None:
        """One round trip, where reading the body takes six: what changes whenever the body does."""
        organisation = check_organisation(organisation)
        self.ensure_schema()
        rows = self._read("MATCH (b:Body {organisation: $org, body_id: $id}) RETURN b.version AS v, "
                          "b.published_at AS at", org=organisation, id=body_id)
        return (rows[0]["v"], rows[0]["at"]) if rows else None

    def withdraw(self, organisation: str, body_id: str) -> bool:
        organisation = check_organisation(organisation)
        self.ensure_schema()
        found = self._read("MATCH (b:Body {organisation: $org, body_id: $id}) RETURN count(b) AS n",
                           org=organisation, id=body_id)[0]["n"]
        self._write("MATCH (n) WHERE (n:Unit OR n:Case OR n:Source OR n:Evidence) AND n.organisation = $org "
                    "AND n.body_id = $id DETACH DELETE n", org=organisation, id=body_id)
        self._write("MATCH (b:Body {organisation: $org, body_id: $id}) DETACH DELETE b", org=organisation, id=body_id)
        self._write("MATCH (g:Guardian {organisation: $org}) WHERE NOT (g)-[:GUARDS]->() DELETE g", org=organisation)
        return bool(found)

    def close(self) -> None:
        self.driver.close()


def _bridged(links: list[dict], visible: set[str]) -> list[dict]:
    """
    The links a learner sees, with the order kept across what they may not see.

    Measured: a step taught last came second on a visitor's path, because the step before it
    was kept to the community; with that link gone, nothing said it came late. So when a
    hidden part sits between two visible ones, the second still comes after the first. Only
    parts the learner may see are ever named.
    """
    kept = [dict(link) for link in links if link["source_id"] in visible and link["target_id"] in visible]
    before: dict[str, list[str]] = {}
    for link in links:
        if link["type"] == "PREREQUISITE_OF":
            before.setdefault(link["target_id"], []).append(link["source_id"])
    pairs = {(link["source_id"], link["target_id"]) for link in kept if link["type"] == "PREREQUISITE_OF"}
    for target in sorted(visible):
        stack, walked = [s for s in before.get(target, []) if s not in visible], set()
        while stack:
            hidden = stack.pop()
            if hidden in walked:
                continue
            walked.add(hidden)
            for source in before.get(hidden, []):
                if source not in visible:
                    stack.append(source)
                elif (source, target) not in pairs and source != target:
                    pairs.add((source, target))
                    kept.append({"source_id": source, "target_id": target, "type": "PREREQUISITE_OF"})
    return kept


def _public(unit: dict) -> dict:
    return {k: v for k, v in unit.items() if k != "embedding"}


def _case(case: dict) -> dict:
    # .get: Neo4j stores no null property, so a case with no yes-or-no answer (a collision)
    # comes back without "applies" at all. Measured: the first live search failed on one.
    return {k: case.get(k) for k in ("case_id", "kind", "question", "said", "by", "applies")}


def _case_full(case: dict) -> dict:
    """A case with what it decides, for a learner's path and quiz."""
    return {**_case(case), "decides": list(case.get("decides") or []), "access": case.get("access")}


def _source(source: dict) -> dict:
    return {k: source.get(k, "") for k in ("url", "domain", "says", "relation", "jurisdiction")}


def _evidence(found: dict) -> dict:
    return {k: found.get(k, "") for k in ("unit_id", "name", "where", "excerpt")}


def _summary(publication: Publication) -> dict:
    return {"body_id": publication.body.body_id, "version": publication.body.version,
            "units": len(publication.units), "links": len(publication.links),
            "cases": len(publication.cases), "sources": len(publication.sources),
            "evidence": len(publication.evidence)}


_store = None


def get_store():
    """Neo4j when it is configured, memory otherwise, said once in the log."""
    global _store
    if _store is None:
        uri = os.environ.get(library_config.NEO4J_URI_ENV)
        if uri:
            _store = Neo4jKnowledgeStore(uri, os.environ.get(library_config.NEO4J_USERNAME_ENV, ""),
                                         os.environ.get(library_config.NEO4J_PASSWORD_ENV, ""),
                                         os.environ.get(library_config.NEO4J_DATABASE_ENV))
        else:
            logger.warning("NEO4J_URI is not set: the library is in memory and lasts as long as the process.")
            _store = MemoryKnowledgeStore()
    return _store


def set_store(store) -> None:
    global _store
    _store = store
    from library import reader

    reader._KEPT.clear()
