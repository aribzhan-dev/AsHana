# Данные и транзакции

Identity реализован миграциями 0002/0003, inventory — 0004_inventory, production — 0005_production,
catalog — 0006_catalog, checkout/orders/reservations/notifications — 0007_orders.
KITCHEN-01 (0008_kitchen) добавляет код получения и consume/mock_fulfil в аудит.
POS-01 (0009_pos) добавляет неизменяемые demo-операции кассы. Реальные платежи остаются отдельным этапом.

| Владелец | Основные сущности |
|---|---|
| identity | identity_users, identity_sessions, identity_roles, identity_user_roles, identity_audit, identity_rate_limits |
| catalog | catalog_periods, catalog_entries, catalog_audit |
| inventory | inventory_items, inventory_batches, inventory_movements, inventory_audit, inventory_requests; inventory_reservations, inventory_reservation_events |
| production | production_recipes (версии), production_recipe_lines, production_batches, production_consumption |
| orders | order_guests, checkout_drafts (JSONB-снимок lines), orders, order_slots, order_events, order_requests |
| orders (минимальный mock-flow) | payment_attempts; отдельный payments gateway ещё не реализован |
| pos | pos_attempts; idempotency через inventory_requests, аудит через inventory_audit |
| notifications | notification_outbox |

Состав заказа хранит снимки названия, цены, валюты и размера порции: изменение каталога
не меняет старые заказы. Рецепт выпуска имеет фиксированную версию и фактический расход.
Внешние ключи, unique constraints и CHECK constraints защищают базовые инварианты.
Деньги BIGINT в тиынах; сырьё NUMERIC; идентификаторы UUID; время TIMESTAMPTZ.

Application use case открывает транзакцию; репозитории не commit-ят самостоятельно.
Checkout атомарно фиксирует оформление, резерв по всем позициям, слот, audit и replay.
Оплата отдельно атомарно создаёт orders, успешную попытку, confirmed, outbox и replay.
Ошибка любой записи откатывает соответствующую транзакцию.
Блокировки брать в стабильном порядке идентификаторов; повтор при deadlock ограничен
и использует тот же idempotency key. Нельзя держать транзакцию во время действий пользователя.

Свободный остаток = on_hand − active_reserved. Выдача одновременно уменьшает on_hand
и active_reserved; свободный остаток второй раз не уменьшается. Отмена снимает резерв;
списание физически отсутствующего/испорченного товара уменьшает on_hand с причиной.
Подтверждённые движения не удалять: исправления отдельными компенсирующими движениями.

Для гостевых заказов scope включает непрозрачный гостевой идентификатор, не телефон.
Идемпотентность scoped по авторизованному субъекту и операции; одинаковый ключ с другим payload — конфликт.
При повторе вернуть сохранённый результат. Авторизационные проверки действуют и при replay.

Catalog читает согласованную SQL-проекцию готовых остатков без изменения inventory.
Идемпотентность использует inventory_requests через инъецированный порт; аудит меню отдельный.
[Обоснование и границы](decisions/0011-catalog-publication.md).

REPORTS-01 не владеет изменяемыми таблицами. Явные read projections соединяют журналы
заказов/кассы/склада/выпуска; строки и полные итоги читаются одним SQL snapshot.
