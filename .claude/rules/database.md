---
paths:
  - "backend/migrations/**/*"
---

# database

Читать docs/architecture/data-ownership.md и docs/engineering/migrations.md.
Не читать реальные .env и не выполнять destructive SQL без разрешения. Миграции отдельным шагом.
Деньги целые тиыны, сырьё Decimal/NUMERIC. CHECK/FK/unique ограничения и конкурентные тесты обязательны
для затронутых инвариантов. Не редактировать применённые общие ревизии.
