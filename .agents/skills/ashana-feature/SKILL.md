---
name: ashana-feature
description: Implement an AsHana business feature across clean architecture layers after reading its requirements.
---

# ashana-feature

Read AGENTS.md, tasks/current-sprint.md, docs/architecture/overview.md and the relevant docs/modules file.
Use these project-root paths; this skill lives at `.agents/skills/ashana-feature/`.
Map the requested behavior to R-IDs and observable acceptance criteria before editing.
Keep HTTP and ORM outside the domain; use an application transaction for cross-module invariants.
Do not broaden a documentation-only task into implementation. Russian UI/errors, English identifiers
and important comments. Check permissions, retries and failure transitions, not only the happy path.
Run relevant checks, review the result, update task status truthfully. Never publish or run Git mutations
without specific owner authorization. No external delegation is implied by this skill.
