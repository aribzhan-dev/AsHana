# Документация AsHana

Статус: FOUNDATION-01, IDENTITY-01, UI-01, INVENTORY-01, PRODUCTION-01, CATALOG-01, ORDERS-01, KITCHEN-01, POS-01 и REPORTS-01 реализованы. Аккаунты предназначены
только сотрудникам; публичной регистрации нет. Склад ведёт партии и движения; производство атомарно списывает сырьё и создаёт готовые партии.
Гостевые оформления резервируют партии/слоты; orders создаётся после успешной mock-оплаты. Комплектация и однократная тестовая выдача реализованы; реальные платежи остаются следующим этапом.
Начать с [AGENTS.md](../AGENTS.md), результаты проверок — в [текущем этапе](../tasks/current-sprint.md).

## Продукт

- [Видение AsHana](product/vision.md)
- [Требования](product/requirements.md)
- [Пользовательские сценарии](product/user-flows.md)
- [Валидация и локализация](product/validation-and-localization.md)

## Архитектура

- [Архитектура](architecture/overview.md)
- [Модули и границы](architecture/module-system.md)
- [Данные и транзакции](architecture/data-ownership.md)
- [Аутентификация](architecture/authentication.md)
- [Авторизация](architecture/authorization.md)
- [Уведомления и фоновые операции](architecture/event-driven.md)
- [Несколько столовых](architecture/multi-tenancy.md)
- [Работа при потере связи](architecture/offline-sync.md)
- [Безопасность](architecture/security.md)
- [Структура проекта](architecture/repository-structure.md)
- [Архитектурные решения](architecture/decisions/README.md)

## Модули

- [Склад и готовые остатки](modules/inventory.md)
- [Рецепты и производство](modules/production.md)
- [Меню и периоды](modules/catalog.md)
- [Заказы, слоты и выдача](modules/orders.md)
- [Mock-оплата](modules/payments.md)
- [Отчёты](modules/reporting.md)

## Разработка

- [Frontend](engineering/frontend-foundations.md)
- [Компоненты UI-01](engineering/ui-components.md)
- [Рабочий процесс и Definition of Done](engineering/development-workflow.md)
- [План проверок](engineering/testing.md)
- [E2E-сценарии](engineering/e2e-testing.md)
- [HTTP, ошибки и логи](engineering/http-errors-and-logging.md)
- [Локальная разработка и Docker](engineering/local-development.md)
- [Работа с меню](engineering/catalog-usage.md)
- [Заказы и Telegram](engineering/orders-usage.md)
- [Работа со складом](engineering/inventory-usage.md)
- [Рецепты и производство](engineering/production-usage.md)
- [Миграции и данные](engineering/migrations.md)
- [Приватность и GitHub](engineering/privacy-and-git.md)
- [AI-разработка, навыки и доступ](engineering/ai-workflow.md)
- [Проверенные публичные источники](engineering/sources.md)

## План и вопросы

- [Текущий этап](../tasks/current-sprint.md)
- [Backlog](../tasks/backlog.md)
- [Открытые вопросы](open-questions.md)
- [Термины](glossary.md)

- [Отчёты REPORTS-01](engineering/reporting-usage.md)
- [Касса POS-01](engineering/pos-usage.md)
- [Комплектация и выдача](engineering/kitchen-usage.md)

- [Рабочий кабинет WORKSPACE-01](engineering/workspace-usage.md)
- [Накладные и ежедневные операции OPERATIONS-01](engineering/receiving-usage.md)
- [Карточки товаров и никнеймы PRODUCTS-02](engineering/product-profiles.md)
