#!/usr/bin/env python3
"""
Teach and publish a knowledge on this machine, through Urithi's own routes, so the stage has one to learn.

    uv run python scripts/demo_map.py                      # teach, check sources, debrief, validate
    uv run python scripts/demo_map.py --quick              # the same without the public-source check
    uv run python scripts/demo_map.py --guardian ezekias   # taught by another guardian (Sabine by default)

The stage (/presentation/) learns what was published, as /learn/ does; with nothing it says so.
This teaches one the way the teach page does since decision 0016: each sentence is told, then saved
by the guardian's word; the debrief's cases are answered and saved; the teach-back is read and
confirmed; then it is published, the rule on an unknown supplier for members only, so a visitor
and a member learn two different paths. The routes are the server's own, run in this process on this machine's stores; the
models are real; nothing is spoken, since nobody is listening. The knowledge goes with the
practice screen tests/screens/invoice-desk.html.

It needs GEMINI_API_KEY; the public-source check needs BRIGHTDATA_API_TOKEN or TAVILY_API_KEY.
To remove the knowledge (withdrawn from the library too): delete it on the teach page, or
DELETE /api/guardian/map/<map id>?person_id=<guardian>&organisation=urithi.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402

from apu import config  # noqa: E402
from apu.logger import get_logger  # noqa: E402
from guardian.api import routes  # noqa: E402

logger = get_logger("demo_map")
GUARDIAN = {"person_id": "sabine", "organisation": "urithi"}
TASK = "Code a supplier invoice"

# What she says, one sentence at a time; each is saved by her word once Urithi proposes it.
SAID = [
    "Before coding an invoice, I look the supplier up in the vendor master, where every supplier we "
    "have paid is kept with the bank account we pay them on.",
    "When a single item of equipment costs more than five thousand euros, we book it as capex.",
    "When I do not recognise the supplier, I stop and ask the controller before booking anything.",
]

# Her answer to each kind of case the debrief puts to her: a yes or a no a learner can be asked.
RULINGS = {
    "source": "Yes, we follow the law where it sets a lower limit.",
    "boundary": "Yes. Exactly five thousand euros counts as capex.",
    "collision": "Yes. The supplier first: nothing is coded until the controller has cleared it.",
    "near_miss": "No. The rule is for one item of equipment on its own, not for parts bought together.",
}

# The routes this script calls (tests/shared/test_scripts.py holds them to the server's).
PATHS = ("start", "tell", "save", "provenance", "debrief", "rule", "map/{map_id}/teach-back", "confirm", "preview",
         "publish")


def main(argv: list[str]) -> int:
    if not os.environ.get(config.GEMINI_API_KEY_ENV):
        logger.error("%s is not set. Add it to .env first.", config.GEMINI_API_KEY_ENV)
        return 1
    if "--guardian" in argv:
        GUARDIAN["person_id"] = argv[argv.index("--guardian") + 1]
    routes._voiced = lambda text: {"audio": None, "words": []}   # silent: nobody is listening
    import server

    with TestClient(server.app) as client:                       # its start-up wires the meter
        def call(method: str, path: str, body: dict | None = None) -> dict:
            reply = client.request(method, f"/api/guardian/{path}", params=GUARDIAN, json=body)
            reply.raise_for_status()
            return reply.json()

        map_id = call("POST", "start", {"task": TASK, "language": "en"})["map_id"]
        logger.info("Work Map %s: %s, taught by %s", map_id, TASK, GUARDIAN["person_id"])

        for said in SAID:
            proposal = call("POST", "tell", {"map_id": map_id, "said": said}).get("proposal") or {}
            body = {"map_id": map_id, **({"proposal_id": proposal["proposal_id"]} if proposal.get("proposal_id") else {})}
            logger.info("   %s", call("POST", "save", body).get("noted", ""))

        if "--quick" not in argv:
            checked = call("POST", "provenance", {"map_id": map_id, "country": "de"})
            logger.info("sources: %s", checked.get("backend"))
            for rail in checked.get("checked", []):
                logger.info("   %-13s %s", rail.get("verdict", ""), rail.get("when", ""))

        logger.info("debrief")
        probe = call("POST", "debrief", {"map_id": map_id}).get("probe")
        while probe:
            said = RULINGS.get(probe.get("kind"), "Yes, the rule holds as I said it.")
            logger.info("   [%s] %s", probe.get("kind"), probe.get("question", "")[:110])
            logger.info("      she says: %s", said)
            ruled = call("POST", "rule", {"map_id": map_id, "probe_id": probe["probe_id"], "said": said})
            case = ruled.get("proposal") or {}
            if case.get("proposal_id"):
                call("POST", "save", {"map_id": map_id, "proposal_id": case["proposal_id"]})
            probe = ruled.get("probe")

        teach_back = call("GET", f"map/{map_id}/teach-back")
        logger.info("teach-back: %s", teach_back.get("text") or teach_back.get("teach_back", ""))
        done = call("POST", "confirm", {"map_id": map_id, "confirmed": True})
        logger.info("confirmed: %s", done.get("confirmed"))

        who = {"map_id": map_id, "person_id": GUARDIAN["person_id"]}
        units = call("POST", "preview", who).get("units", [])
        members = {u["unit_id"]: "community" for u in units if "recognis" in u.get("text", "").lower()}
        published = call("POST", "publish", {**who, "access": members})
        logger.info("published: %s, %s parts, %d for members only", published.get("body_id"), published.get("units"),
                    len(members))
        logger.info("Open http://localhost:8790/presentation/?knowledge=%s", published.get("body_id"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
