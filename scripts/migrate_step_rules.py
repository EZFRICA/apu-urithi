"""Unlink the rules a step was given by mistake, in every map of this machine.

Until the review of 2026-10-14, a step saved with no rule of its own was given every rule the
knowledge held at that moment, in their order. This takes those rules off the step, in the map and
in its validated version alike, so a validated step stays validated. A rule is never deleted, only
unlinked.

Which ones: a rule an earlier step already holds existed before this step was saved; held here
without being said with this step (the same moment), it came with the mistake. A rule saved on its
own after the step is attached to the step before it by design, and stays; unsure, a rule stays.
Measured on the knowledge taught on 2026-10-10: step 2 was saved when only the pizza rule existed,
then two rules were saved alone and attached to it; only the pizza rule is taken off.

    uv run python scripts/migrate_step_rules.py            # says what it would change
    uv run python scripts/migrate_step_rules.py --apply    # a copy of the maps first, then the change
"""

import argparse
import shutil
import sys
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from apu.logger import get_logger  # noqa: E402
from guardian.engine.workmap import Guardrail, Step, WorkMapStore  # noqa: E402

logger = get_logger("migrate_step_rules")


def given_by_mistake(step: Step, guardrails: list[Guardrail], earlier: list[Step]) -> list[str]:
    """The ids of the rules this step was given by mistake: in the leading run of its rules that is the
    knowledge's rules in order, those an earlier step holds and that were not said with this step."""
    order = [g.guardrail_id for g in guardrails]
    said = {g.guardrail_id: g.said_at for g in guardrails}
    held_before = {gid for s in earlier for gid in s.guardrail_ids}
    ids = list(step.guardrail_ids)
    run = 0
    while run < len(ids) and run < len(order) and ids[run] == order[run]:
        run += 1
    return [gid for gid in ids[:run] if gid in held_before and said.get(gid) != step.said_at]


def mended(steps: list[Step], guardrails: list[Guardrail]) -> tuple[list[Step], list[tuple[Step, list[str]]]]:
    out, changed = [], []
    by_number = sorted(steps, key=lambda s: s.number)
    for step in steps:
        wrong = given_by_mistake(step, guardrails, [s for s in by_number if s.number < step.number])
        if wrong:
            changed.append((step, wrong))
            step = replace(step, guardrail_ids=tuple(g for g in step.guardrail_ids if g not in wrong))
        out.append(step)
    return out, changed


def migrate(store: WorkMapStore, apply: bool) -> int:
    count = 0
    for entry in store.list_maps():
        work_map = store.load(entry["map_id"])
        steps, changed = mended(work_map.steps, work_map.guardrails)
        kept_changed = []
        if work_map.validated:
            kept = work_map.validated
            kept_steps = [Step(**{**s, "guardrail_ids": tuple(s["guardrail_ids"])}) for s in kept["steps"]]
            kept_steps, kept_changed = mended(kept_steps, [Guardrail(**g) for g in kept["guardrails"]])
        if not changed and not kept_changed:
            continue
        count += 1
        when = {g.guardrail_id: g.when for g in work_map.guardrails}
        logger.info("%s | %s | %s", work_map.expert, work_map.task, work_map.map_id)
        for step, wrong in changed:
            logger.info("  step %s (%s): unlink %d rule(s): %s", step.number, step.title[:60], len(wrong),
                        "; ".join(when.get(g, g)[:50] for g in wrong))
        for step, wrong in kept_changed:
            logger.info("  validated step %s: unlink %d rule(s)", step.number, len(wrong))
        if apply:
            work_map.steps = steps
            if kept_changed:
                work_map.validated = {**work_map.validated, "steps": [asdict(s) for s in kept_steps]}
            store.save(work_map)
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write the change, after a copy of the maps")
    parser.add_argument("--path", default=None, help="the maps database (default: this machine's)")
    args = parser.parse_args()
    store = WorkMapStore(args.path) if args.path else WorkMapStore()
    if args.apply and Path(store.path).exists():
        backup = Path(store.path).with_name(f"workmap-before-step-rules-{datetime.now(UTC):%Y%m%dT%H%M%S}.sqlite3")
        shutil.copy2(store.path, backup)
        logger.info("copy of the maps kept: %s", backup)
    count = migrate(store, args.apply)
    logger.info("%d map(s) %s", count, "changed" if args.apply else "would change")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
