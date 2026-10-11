# Agents for later steps

Not loaded: Claude Code reads agents from `.claude/agents/` only. Each moves there at the step
of `docs/plan.md` where it is needed, and gains then its `model`, preloaded `skills` and limits.

| Agent | Needed from |
|---|---|
| privacy-compliance | step 0b (organisations, stores) |
| scale-engineer | step 0b (stores behind interfaces, cost) |
| data-engineer | step 0b (stores, organisations on every record) |
| finops | step 0b (the meter and the cost ceiling) |
| frontend-engineer | step 1 (teleprompter, keys) |
| accessibility-reviewer | step 1 |
| llm-eval-engineer | when a model or a prompt changes |
| sre-platform | when the deployment is decided |
