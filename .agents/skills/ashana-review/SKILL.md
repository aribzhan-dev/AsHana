---
name: ashana-review
description: Review completed AsHana changes for business invariants, privacy and verifiable acceptance evidence.
---

# ashana-review

Read AGENTS.md and the documents relevant to the changed files. Review actual behavior and diff,
not just a checklist. Prioritize overselling, duplicate fulfilment/payment, role/ownership failures,
raw-material double deduction, mock-money mixing and leaked secrets.
For UI changes check Russian labels, both themes, responsiveness and all password toggles.
Use docs/engineering/testing.md to choose meaningful verification; distinguish executed checks
from proposed tests. Do not read real .env files while searching for configuration problems.
Report concrete findings with a reproduction and location. If no application exists, report only
what documentation checks establish. Do not publish, commit or start subagents automatically.
