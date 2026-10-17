#!/usr/bin/env python3
"""
Teach Sabine a knowledge on this machine, through Urithi's own routes, so the stage has a map.

    uv run python scripts/demo_map.py                      # teach, check sources, debrief, validate
    uv run python scripts/demo_map.py --quick              # the same without the public-source check
    uv run python scripts/demo_map.py --guardian ezekias   # taught by another guardian (Sabine by default)

The stage (/presentation/) presents the maps of the guardian chosen on it; with none it says so. This
teaches one the way the teach page does since decision 0016: each sentence is told, then saved
by the guardian's word; the debrief's cases are answered and saved; the teach-back is read and
confirmed. The routes are the server's own, run in this process on this machine's stores; the
models are real; nothing is spoken, since nobody is listening. The knowledge goes with the
practice screen tests/screens/invoice-desk.html.

It needs GEMINI_API_KEY; the public-source check needs BRIGHTDATA_API_TOKEN or TAVILY_API_KEY.
To remove the knowledge: delete it on the teach page, or
DELETE /api/guardian/map/<map id>?person_id=<guardian>&organisation=urithi.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402

from apu import config  # noqa: E402
from guardian.api import routes  # noqa: E402

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
PATHS = ("start", "tell", "save", "provenance", "debrief", "rule", "map/{map_id}/teach-back", "confirm")


def main(argv: list[str]) -> int:
    if not os.environ.get(config.GEMINI_API_KEY_ENV):
        print(f"{config.GEMINI_API_KEY_ENV} is not set. Add it to .env first.")
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
        print(f"Work Map {map_id}: {TASK}, taught by {GUARDIAN['person_id']}\n")

        for said in SAID:
            proposal = call("POST", "tell", {"map_id": map_id, "said": said}).get("proposal") or {}
            body = {"map_id": map_id, **({"proposal_id": proposal["proposal_id"]} if proposal.get("proposal_id") else {})}
            print(f"   {call('POST', 'save', body).get('noted', '')}")

        if "--quick" not in argv:
            checked = call("POST", "provenance", {"map_id": map_id, "country": "de"})
            print(f"\nsources: {checked.get('backend')}")
            for rail in checked.get("checked", []):
                print(f"   {rail.get('verdict', ''):<13} {rail.get('when', '')}")

        print("\ndebrief")
        probe = call("POST", "debrief", {"map_id": map_id}).get("probe")
        while probe:
            said = RULINGS.get(probe.get("kind"), "Yes, the rule holds as I said it.")
            print(f"   [{probe.get('kind')}] {probe.get('question', '')[:110]}\n      she says: {said}")
            ruled = call("POST", "rule", {"map_id": map_id, "probe_id": probe["probe_id"], "said": said})
            case = ruled.get("proposal") or {}
            if case.get("proposal_id"):
                call("POST", "save", {"map_id": map_id, "proposal_id": case["proposal_id"]})
            probe = ruled.get("probe")

        teach_back = call("GET", f"map/{map_id}/teach-back")
        print(f"\n{teach_back.get('text') or teach_back.get('teach_back', '')}\n")
        done = call("POST", "confirm", {"map_id": map_id, "confirmed": True})
        print(f"confirmed: {done.get('confirmed')}. Open http://localhost:8790/presentation/?guardian={GUARDIAN['person_id']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
