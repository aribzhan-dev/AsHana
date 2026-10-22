---
name: ashana-ui
description: Build or review AsHana Russian-language responsive forms, themes and customer or staff screens.
---

# ashana-ui

Read AGENTS.md, docs/engineering/frontend-foundations.md and
 docs/product/validation-and-localization.md from the project root.
Use React/TypeScript. Verify Russian visible and accessible labels, loading/empty/error states,
light/dark themes and mobile/tablet/desktop behavior. Every password field needs a non-submit
visibility toggle with a changing Russian accessible label; preserve paste and password managers.
Kazakhstan phone validation uses normalized length and country metadata, not only the +7 prefix.
Names support Kazakh Unicode letters and reject digits; numeric fields reject invalid values
without breaking IME, paste or editing. Server validates again. Never trust UI stock or permissions.
