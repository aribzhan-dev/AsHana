# Документация AsHana

Статус: FOUNDATION-01, IDENTITY-01, UI-01, INVENTORY-01, PRODUCTION-01, CATALOG-01, ORDERS-01, KITCHEN-01, POS-01, REPORTS-01,
WORKSPACE-01, OPERATIONS-01, PRODUCTS-02, DESIGN-02, OPERATIONS-02, LIVE-01 и FINANCE-01 реализованы; TELEGRAM-01 ждёт токен.
Оплата остаётся mock; технический PILOT-01 выполнен, пилот в столовой — нет. Аккаунты предназначены
только сотрудникам; публичной регистрации нет. Склад ведёт партии и движения; производство атомарно списывает сырьё и создаёт готовые партии.
Гостевые оформления резервируют партии/слоты; orders создаётся после успешной mock-оплаты. Комплектация и однократная тестовая выдача реализованы; реальные платежи не подключаются по решению владельца.
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
- [Финансы и зарплата](modules/finance.md)

## Разработка

- [Быстрый запуск на новом компьютере](engineering/quick-start.md)
- [Frontend](engineering/frontend-foundations.md)
- [Компоненты UI-01](engineering/ui-components.md)
- [Рабочий процесс и Definition of Done](engineering/development-workflow.md)
- [План проверок](engineering/testing.md)
- [E2E-сценарии](engineering/e2e-testing.md)
- [HTTP, ошибки и логи](engineering/http-errors-and-logging.md)
- [Локальная разработка и Docker](engineering/local-development.md)
- [Работа с меню](engineering/catalog-usage.md)
- [Финансы и зарплата](engineering/finance-usage.md)
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
- [QR-выдача и дизайн DESIGN-02](../tasks/DESIGN-02.md)
- [Возвраты, долги, отчёты OPERATIONS-02](../tasks/OPERATIONS-02.md)
- [Живые экраны LIVE-01](../tasks/LIVE-01.md)
- [Telegram TELEGRAM-01](../tasks/TELEGRAM-01.md)
- [Финансы, зарплата, фото, PILOT-01 — FINANCE-01](../tasks/FINANCE-01.md)
