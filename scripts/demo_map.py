#!/usr/bin/env python3
"""
Teach Sabine's Work Map on this machine, through the apprentice's own routes.

    uv run python scripts/demo_map.py

A fresh clone has no Work Map, so the stage has nothing to present. This builds one the
way the page does: the same route functions, in the same order, with real models. Her
answers are a script, the ones in the README, and so is what the screen showed: the vision
step is the one thing replaced, by the sentence it would have reported, because a script
has no screen to share. Everything else is live:

  - her sentences are turned into rules by the extraction model;
  - each rule is checked against public sources (Bright Data, or Tavily);
  - the debrief's cases are built by code, and her verdicts read by the model;
  - the teach-back is built from the map, and she confirms it.

It needs GEMINI_API_KEY, and BRIGHTDATA_API_TOKEN or TAVILY_API_KEY for the sources. It
stays silent: no speech is synthesised, since nobody is listening.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apu import config  # noqa: E402
from guardian.engine import routes  # noqa: E402
from guardian.engine.questions import Observation  # noqa: E402

TASK = "Code a supplier invoice"
EXPERT = "Sabine"

# (seconds into the session, what the screen showed, what she said when asked why)
SESSION = [
    (74.0, "Novak Precision not found in the vendor master",
     "That is the vendor master. Every supplier we have ever paid is in there, with the "
     "bank account we pay them on."),
    (192.0, "cost center changed from 4711 to 0400",
     "Equipment over five thousand euros is always capex. And if I do not recognise the "
     "supplier, I stop and ask the controller before booking anything."),
]

# Her answer to each kind of case the debrief puts to her.
RULINGS = {
    "source": "If the law says eight hundred, then yes, that is capex, we follow the law.",
    "boundary": "Exactly five thousand counts. Five thousand is capex.",
    "collision": "The supplier first, always. Nothing gets coded until the controller has "
                 "cleared the supplier.",
    "near_miss": "No. Spare parts for a machine we already own are maintenance, not capex.",
}


def main() -> int:
    if not os.environ.get(config.GEMINI_API_KEY_ENV):
        print(f"{config.GEMINI_API_KEY_ENV} is not set. Add it to .env first.")
        return 1
    routes._spoken = lambda text: None   # silent: nobody is listening to a script

    map_id = routes.start(routes.StartBody(task=TASK, expert=EXPERT))["map_id"]
    print(f"Work Map {map_id}: {TASK}, taught by {EXPERT}\n")

    for at, changed, said in SESSION:
        routes._session(map_id)["pending"] = {
            "kind": "reason", "observation": Observation(at=at, changed=changed), "asked_at": at}
        reply = routes.answer(routes.AnswerBody(map_id=map_id, said=said))
        print(f"step {reply['step']['number']}  {reply['step']['title']}")
        for rail in reply["guardrails"]:
            print(f"   rule  when {rail['when']} -> {rail['then']}  [{rail['severity']}]")

    checked = routes.check_provenance(routes.ProvenanceBody(map_id=map_id, country="de"))
    print(f"\nsources: {checked.get('backend')}")
    for rail in checked.get("checked", []):
        print(f"   {rail['verdict']:<13} {rail['when']}")

    reply = routes.start_debrief(routes.MapBody(map_id=map_id))
    print("\ndebrief")
    while reply.get("probe"):
        found = reply["probe"]
        said = RULINGS.get(found["kind"], "Yes.")
        print(f"   [{found['kind']}] {found['question']}\n      she says: {said}")
        reply = routes.rule(routes.RuleBody(map_id=map_id, probe_id=found["probe_id"], said=said))
        if "ruling" in reply:
            print(f"      read as: applies={reply['ruling']['applies']}")
    if reply.get("error"):
        print(f"   stopped: {reply['error']}")
        return 1

    print(f"\n{reply.get('teach_back', '')}\n")
    done = routes.confirm(routes.ConfirmBody(map_id=map_id, confirmed=True))
    print(f"confirmed: {done['confirmed']}. Open http://localhost:8790/presentation/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
