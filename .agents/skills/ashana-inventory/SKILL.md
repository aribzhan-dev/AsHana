---
name: ashana-inventory
description: Design or change AsHana inventory, production and reservation behavior, including concurrent sales.
---

# ashana-inventory

Read AGENTS.md, docs/modules/inventory.md, docs/modules/production.md, docs/modules/orders.md
and docs/architecture/data-ownership.md from the project root.
Distinguish raw ingredients, finished batches, on-hand quantity and active reservations.
Production consumes ingredients once; fulfilment consumes finished stock and releases its reservation
in one transaction. Checkout reserves every line and slot atomically or changes nothing.
Exercise online-vs-counter and last-item races on PostgreSQL, duplicate requests, cancellation
and spoiled reserved batches. A screen count or mock repository does not prove correctness.
Preserve the movement audit trail; corrections compensate, not erase. Do not access real credentials.
