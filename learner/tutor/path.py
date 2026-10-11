"""The order a body of knowledge is learned in: nothing before what it rests on.

A topological sort over PREREQUISITE_OF, by code. Among units that are ready at the same
time, steps come before the limits and cautions that qualify them, then the order they were
said in. A cycle, which a guardian's map should never hold, does not hang the path: what is
left is appended in the order it was said, and the path says so.
"""

KIND_ORDER = {"step": 0, "limit": 1, "caution": 2}


def ordered(units: list[dict], links: list[dict]) -> tuple[list[dict], bool]:
    """(units in learning order, whether a cycle had to be broken)."""
    by_id = {u["unit_id"]: u for u in units}
    needs: dict[str, set[str]] = {uid: set() for uid in by_id}
    for link in links:
        if link["type"] == "PREREQUISITE_OF" and link["source_id"] in by_id and link["target_id"] in by_id:
            needs[link["target_id"]].add(link["source_id"])

    def rank(uid: str):
        unit = by_id[uid]
        return (KIND_ORDER.get(unit["kind"], 9), unit.get("at", 0.0), uid)

    done: list[str] = []
    placed: set[str] = set()
    while len(done) < len(by_id):
        ready = sorted((uid for uid in by_id if uid not in placed and needs[uid] <= placed), key=rank)
        if not ready:
            rest = sorted((uid for uid in by_id if uid not in placed), key=lambda u: by_id[u].get("at", 0.0))
            return [by_id[u] for u in done + rest], True
        done.append(ready[0])
        placed.add(ready[0])
    return [by_id[u] for u in done], False
