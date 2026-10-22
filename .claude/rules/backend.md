---
paths:
  - "backend/**/*.py"
---

# backend

Читать docs/architecture/overview.md и документ модуля. Domain без FastAPI/ORM.
Application управляет UoW, infrastructure реализует порты. Routes преобразуют DTO и вызывают use case.
Повтор запроса безопасен; цены/остатки/права вычисляются сервером. Для склада и оплаты нужны
PostgreSQL integration tests с гонками. Ошибки пользователя русские, комментарии по делу английские.
