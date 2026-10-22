---
paths:
  - "**/*"
---

# security

Соблюдать AGENTS.md и docs/engineering/privacy-and-git.md.
Не выполнять Git-мутации/GitHub-операции и внешние публикации без отдельного разрешения.
Не печатать секреты, дампы, cookies, реальные .env. Ignore-файл не является гарантией защиты.
Backend проверяет ownership и роли; mock недоступен как реальный платёжный канал.
