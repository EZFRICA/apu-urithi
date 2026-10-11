"""What the tests of both sides share: an offline embedder and one published body."""

import hashlib
import math
import re

from library.model import Body, Case, Link, Publication, Unit

DIM = 384

BODY = "ezekias--running-a-tech-community"
ORG = "urithi"


class WordEmbedder:
    """Deterministic and offline: a bag of hashed words, so shared words mean closeness."""

    model_name, dim = "test-words", DIM

    def embed(self, texts):
        vectors = []
        for text in texts:
            v = [0.0] * DIM
            for word in re.findall(r"[a-z0-9]+", text.lower()):
                v[int(hashlib.sha1(word.encode()).hexdigest(), 16) % DIM] += 1.0
            norm = math.sqrt(sum(x * x for x in v)) or 1.0
            vectors.append([x / norm for x in v])
        return vectors



def community() -> Publication:
    unit = lambda name, kind, text, quote, at, level="public": Unit(  # noqa: E731
        unit_id=f"{BODY}:{name}", body_id=BODY, kind=kind, text=text, quote=quote, at=at, access=level)
    units = [
        unit("step-1", "step", "Announce the meetup on the public channel",
             "I always announce a meetup two weeks ahead on the public channel.", 10.0),
        unit("step-2", "step", "Confirm the speakers",
             "Speakers confirm a week before, or the slot goes to the next one.", 20.0),
        unit("rule-cancel", "limit", "When fewer than ten people register, move the meetup.",
             "Under ten registrations, I move the meetup rather than run it half empty.", 30.0),
        unit("rule-report", "caution", "When a code of conduct report is made, two organisers handle it.",
             "A code of conduct report goes to two organisers only, never the whole team.", 40.0,
             "community"),
    ]
    links = [Link(f"{BODY}:step-1", f"{BODY}:step-2", "PREREQUISITE_OF"),
             Link(f"{BODY}:step-2", f"{BODY}:rule-cancel", "PREREQUISITE_OF"),
             Link(f"{BODY}:step-1", f"{BODY}:rule-report", "PREREQUISITE_OF")]
    cases = [Case(case_id=f"{BODY}:case-9", body_id=BODY, kind="boundary",
                  question="Exactly ten registrations: do you move it?", said="Ten is enough. We hold it.",
                  by="Ezekias", applies=False, decides=(f"{BODY}:rule-cancel",)),
             Case(case_id=f"{BODY}:case-report", body_id=BODY, kind="boundary",
                  question="A report about an organiser?", said="Yes, still two organisers.",
                  by="Ezekias", applies=True, decides=(f"{BODY}:rule-report",), access="community")]
    return Publication(Body(BODY, "Running a tech community", "Ezekias", 1, "now", organisation=ORG), units, links, cases)


def as_guardian(person_id: str = "sabine"):
    """What the guardian routes know of who is asking, for a route called as a function."""
    from types import SimpleNamespace

    from library import access

    return SimpleNamespace(state=SimpleNamespace(guardian=access.person(person_id)))


def guardian_client(app, person_id: str = "sabine"):
    """A test client that asks as this guardian on every request, beside the query it sends."""
    from fastapi.testclient import TestClient

    client = TestClient(app)

    def ask_as(request):
        request.url = request.url.copy_merge_params({"person_id": person_id})

    client.event_hooks = {"request": [ask_as], "response": []}
    return client
