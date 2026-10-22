# ADR-0006: локальная основа приложения

Статус: **Выбрано при реализации FOUNDATION-01**. Дата: 20.10.2026.
Это технический выбор в рамках запроса начать разработку, не утверждение владельцем
всех предложений по бизнес-модулям.

## Решение

Python 3.13, FastAPI, SQLAlchemy 2 + psycopg 3, Alembic; Node 22.22.2,
React 19, TypeScript 5.9, Vite 8; PostgreSQL 17, nginx 1.28.
Зависимости фиксируются `backend/uv.lock` и `frontend/pnpm-lock.yaml`.
Менеджеры: uv 0.13.3, pnpm 10.34.7. Точные версии библиотек — в lockfiles.
Базовые образы Python/PostgreSQL/nginx закреплены до ветки; их patch-обновления
могут изменить image. Перед пилотом нужны обновление, сканирование и pin по digest.

Один origin через nginx; Vite proxy для локальной разработки. Domain/application
будут добавляться с бизнес-модулями, без пустых абстракций в scaffold.
React Router и TanStack Query пока не нужны одному экрану.
Контракт OpenAPI экспортируется без подключения к БД, типы клиента генерируются из него.

В Compose отдельные db/migrate/api/web. Роль migrator владеет схемой;
runtime-роль имеет доступ к данным, но не DDL/созданию ролей/temporary tables.
Runtime может читать, но не изменять таблицу версии Alembic.
Bootstrap PostgreSQL выполняется только при создании нового volume.
Секреты передаются через окружение локального Compose, не в image/frontend.

Liveness проверяет процесс; readiness — соединение и точную ревизию схемы.
Миграции не запускаются на импорте или в каждом API worker.
Начальная миграция не создаёт бизнес-таблиц и учётных записей.

## Альтернативы и последствия

Миграции в каждом API worker создавали бы гонки старта; один выделенный мигратор
делает ошибку схемы видимой до запуска API. SQLite не воспроизводит PostgreSQL-поведение.
Vite dev server не выбран для Docker web: собранные файлы обслуживает nginx.

Синхронные короткие проверки БД выполняются в worker thread FastAPI с таймаутами.
Настройку пула и нагрузочные ограничения нужно пересмотреть при бизнес-сценариях.
Проверка соответствия SCHEMA_REVISION и Alembic head защищает от забытых обновлений версии.
Разделение ролей и baseline проверяются на локальном PostgreSQL.

Источники: [порядок запуска Compose](https://docs.docker.com/compose/how-tos/startup-order/),
[uv в Docker](https://docs.astral.sh/uv/guides/integration/docker/),
[FastAPI lifespan](https://fastapi.tiangolo.com/advanced/events/),
[Vite](https://vite.dev/guide/), [SQLAlchemy PostgreSQL](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html).
