# Urithi

Read `.claude/skills/house-rules/SKILL.md` before anything else: commands through `uv`, no
commit without the owner's word, secrets never printed, English in the repository and French
with the owner, no dash in prose, no Markdown over 100 lines.

- The design: `docs/architecture.md` (and `docs/architecture-*.md`). The order of building: `docs/plan.md` (and `docs/plan-done.md`, `docs/plan-steps-3-to-8.md`). Why: `docs/decisions/`.
- What was done, action by action: `docs/journal/` (one file per day; add an entry after each action).
- What was measured: `docs/measurements.md`, `docs/urithi-measured.md`, `docs/measured-steps.md`,
  `docs/measured-class.md`, and their per-feature `docs/measured-*.md` files.
- Skills in `.claude/skills/` (boundaries, guarantees, real-condition test, stores, metering,
  organisations, security, accessibility, languages, Neo4j, load, release, incidents, decisions).
- Agents in `.claude/agents/` (architecture, security, tests, real conditions, documents); those
  for later steps (privacy, scale, data, model evaluation, accessibility, frontend, platform,
  cost) wait in `.claude/agents-later/`.
- Evaluations: `.claude/skills/<skill>/evals/evals.json`, three cases each for the critical
  skills (house rules, boundaries, guarantees). Give a case's query to a fresh session with the
  skill loaded and check every expected behaviour; add a case whenever a real task shows a gap.
- One deliberate defect alone: `uv run python scripts/mutate.py --only "<label words>"`.
