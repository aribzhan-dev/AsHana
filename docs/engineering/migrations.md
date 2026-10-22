# Миграции и данные

В FOUNDATION-01 подключены SQLAlchemy + Alembic. Domain не зависит от ORM.
Каждое изменение схемы — отдельная ревизия, просмотр generated SQL и проверка ограничений.
Не менять уже применённые общие миграции; новая корректирующая ревизия вместо переписывания.
Проверить создание чистой тестовой БД и upgrade от предыдущей версии.

Начальные справочники отдельно от demo-данных. Demo seed идемпотентный, только для local/test;
не содержит настоящих людей, телефонов, паролей или реальных платёжных реквизитов.
Без универсального admin/admin. Учётные записи создаются через безопасную local bootstrap процедуру.
При destructive миграции описать последствия, резервную копию и запросить разрешение до выполнения.

Baseline `0001_foundation` фиксирует версию пустой бизнес-схемы и запрещает runtime-роли
менять таблицу Alembic. Мигратор запускается отдельно через Compose; соединение берётся
из переменных ASHANA_DB_*, без чтения `.env` внутри Python.
При добавлении ревизии обновить SCHEMA_REVISION в bootstrap/database.py:
readiness сравнивает БД с ожидаемой версией; unit-тест сверяет константу с Alembic head.
Metadata identity/inventory объединяется в migrations/env.py без дублирования identity_users.
Downgrade не запускался: проверка foundation выполняет лишь upgrade.

IDENTITY-01 добавляет `0002_identity`: users, roles, user_roles, sessions, audit, rate_limits.
Seed содержит только пять ролей, без пользователей и паролей. Runtime может добавлять аудит,
но не UPDATE/DELETE его; каталог ролей доступен только для чтения. Downgrade требует отдельного
согласованного плана сохранения данных и намеренно не выполняет удаления.

UI-01 добавляет `0003_staff_login`: уникальный нормализованный login, nullable phone
без уникальности. UPDATE заполняет новый login по UUID; аккаунты, hashes, контакты, роли
и сессии не удаляются и не пересоздаются. Перед обновлением сообщить сотрудникам новые
логины staff_ + UUID без дефисов. Downgrade требует отдельного плана сохранения доступа.

INVENTORY-01: 0004_inventory создаёт пять таблиц склада. CHECK, составной FK item/unit,
unique movement version и ограничения runtime защищают остаток и историю. Схема identity
не изменяется. Строки количества хранятся как NUMERIC(18,6), стоимость — BIGINT в тиынах.

PRODUCTION-01: 0005_production добавляет четыре immutable-таблицы рецептов/выпусков/расходов
и разрешает движения production_consume / production_output в существующем CHECK склада.
Применённая 0004 не переписывается. Metadata объединяет production с reference-only таблицами
inventory/identity без дубликатов. Новые таблицы не позволяют runtime UPDATE/DELETE.

CATALOG-01: 0006_catalog добавляет периоды, позиции и append-only аудит before/after.
Unique(period_id, item_id), CHECK цены/версии/интервала, FK на сотрудника и товар.
Runtime не удаляет периоды/позиции и не изменяет аудит. Существующие партии/рецепты/аккаунты
сохраняются; миграции 0001–0005 не переписываются. На этапе CATALOG-01 readiness ожидал 0006_catalog.

ORDERS-01: 0007_orders добавляет гостевые credentials (hash), слоты, checkout_drafts,
payment_attempts, orders, replay/audit, inventory_reservations/events и notification_outbox.
Orders/payment attempts/audit append-only для runtime; изменяемые сущности нельзя удалять.
Миграция не изменяет существующие данные. Readiness теперь ожидает 0007_orders.
Снимки состава хранятся в JSONB оформления, настоящий orders создаётся только после mock-success.

KITCHEN-01: 0008_kitchen добавляет nullable pickup_code в checkout_drafts (8 hex-символов),
заполняет случайным кодом существующие активные оплаченные заказы и расширяет CHECK журналов
действиями consume / mock_fulfil. Данные и ограничения immutable-аудита сохраняются.
Readiness ожидает 0008_kitchen. Downgrade без плана сохранения истории запрещён.

POS-01: 0009_pos добавляет pos_attempts (mock/KZT, исход, сумма, автор, JSONB-снимок) с FK/CHECK.
Runtime не может UPDATE/DELETE попытки. CHECK движений дополнен mock_pos_sale.
Существующие данные сохраняются; readiness ожидает 0009_pos. Downgrade требует плана сохранения истории.
